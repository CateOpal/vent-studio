# -*- coding: utf-8 -*-
"""Wallpaper Engine 库扫描 / 资源识别 / 缩略图生成。

负责：
  * 自动定位 Wallpaper Engine 安装目录、创意工坊 (431960) 与本地 projects 目录
  * 解析 project.json 元数据（UTF-8 / GBK 兜底）
  * 列出某个壁纸的图片 / 视频 / 音频等资源（含 scene.pkg 内打包资源）
  * 生成缩略图缓存（预览图、视频首帧）
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import cache_dir

CACHE_DIR = cache_dir()
THUMB_DIR = CACHE_DIR / "thumbs"

WORKSHOP_APPID = "431960"

try:  # 解析器由 weparser.py 提供；缺失时优雅降级
    from . import pkg as weparser

    PKG_OK = True
except Exception:  # pragma: no cover
    weparser = None
    PKG_OK = False


IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".jfif"}
VID_EXT = {".mp4", ".webm", ".avi", ".mov", ".mkv", ".m4v", ".wmv", ".flv"}
AUD_EXT = {".mp3", ".ogg", ".wav", ".flac", ".m4a", ".aac", ".opus"}
TEX_EXT = {".tex"}
CFG_EXT = {".json"}
SHADER_EXT = {".vert", ".frag", ".hlsl", ".glsl", ".shader", ".h", ".inc"}

KIND_LABEL = {
    "texture": "贴图",
    "image": "图像",
    "video": "视频",
    "audio": "音频",
    "config": "配置",
    "shader": "着色器",
    "other": "其他",
}

TYPE_LABEL = {
    "scene": "场景",
    "video": "视频",
    "web": "网页",
    "application": "程序",
    "preset": "预设",
    "unknown": "未知",
}


def kind_of(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext in IMG_EXT:
        return "image"
    if ext in VID_EXT:
        return "video"
    if ext in AUD_EXT:
        return "audio"
    if ext in TEX_EXT:
        return "texture"
    if ext in CFG_EXT:
        return "config"
    if ext in SHADER_EXT:
        return "shader"
    return "other"


def human_size(n: float) -> str:
    if n < 0:
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


# --------------------------------------------------------------------------- 定位

def _reg(key: str, name: str, hive=None):
    """读注册表字符串值；hive 默认 HKCU，可传 HKLM。"""
    try:
        import winreg

        root = hive if hive is not None else winreg.HKEY_CURRENT_USER
        with winreg.OpenKey(root, key) as k:
            return winreg.QueryValueEx(k, name)[0]
    except Exception:
        return None


def _reg_any(name: str):
    """同一个值在 HKCU / HKLM 两处都试一遍（Steam 装给所有用户时只在 HKLM）。"""
    try:
        import winreg

        hives = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    except Exception:
        hives = (None, None)
    for key in (r"Software\Valve\Steam", r"Software\WOW6432Node\Valve\Steam"):
        for hive in hives:
            val = _reg(key, name, hive)
            if val:
                return str(val)
    return None


def _fixed_drives() -> list[str]:
    """所有本地固定磁盘的根目录（网络盘、光驱跳过，避免扫描卡住）。"""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        mask = kernel32.GetLogicalDrives()
        out = []
        for i in range(26):
            if not mask & (1 << i):
                continue
            root = f"{chr(65 + i)}:\\"
            if kernel32.GetDriveTypeW(root) == 3:  # DRIVE_FIXED
                out.append(root)
        return out or ["C:\\"]
    except Exception:
        return ["C:\\"]


def _library_paths(vdf: Path) -> list[Path]:
    """从 libraryfolders.vdf 里抠出所有库路径（新老两种写法都能认）。"""
    out: list[Path] = []
    try:
        text = vdf.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return out
    for m in re.finditer(r'"path"\s+"([^"]+)"', text):
        raw = m.group(1).replace("\\\\", "\\").strip()
        if raw:
            out.append(Path(raw))
    return out


def steam_roots() -> list[Path]:
    """推断所有 Steam 库根目录：注册表 → 各盘常见位置 → libraryfolders.vdf → config.vdf。"""
    roots: list[Path] = []

    def add(p):
        try:
            if p and Path(p).is_dir():
                q = Path(p)
                if q not in roots:
                    roots.append(q)
        except Exception:
            pass

    # 手动指定：VENT_STEAM_LIBRARY=D:\SteamLibrary;E:\Games\Steam（分号分隔）
    for chunk in (os.environ.get("VENT_STEAM_LIBRARY") or "").split(";"):
        if chunk.strip():
            add(Path(chunk.strip()))

    steam = _reg_any("SteamPath") or _reg_any("InstallPath")
    add(Path(steam) if steam else None)
    add(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam")
    add(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam")

    # 每个盘上常见的安装 / 库目录（Steam 装在 D 盘、E 盘都很常见）
    for drive in _fixed_drives():
        for rel in ("Steam", "SteamLibrary", "Games\\Steam", "Games\\SteamLibrary",
                    "Program Files (x86)\\Steam", "Program Files\\Steam",
                    "Steam\\SteamLibrary", "游戏\\Steam", "Steam Games"):
            add(Path(drive) / rel)

    # libraryfolders.vdf 会指向别的盘，来回读两三轮直到不再冒出新路径
    seen: set[str] = set()
    for _ in range(3):
        fresh = False
        for r in list(roots):
            vdf = r / "steamapps" / "libraryfolders.vdf"
            if not vdf.is_file():
                continue
            key = str(vdf).lower()
            if key in seen:
                continue
            seen.add(key)
            for p in _library_paths(vdf):
                if p not in roots:
                    before = len(roots)
                    add(p)
                    fresh = fresh or len(roots) > before
        if not fresh:
            break

    # 老版本 Steam 把库路径写在 config.vdf 的 BaseInstallFolder_N 里
    for r in list(roots):
        cfg = r / "config" / "config.vdf"
        if not cfg.is_file():
            continue
        try:
            text = cfg.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in re.finditer(r'"BaseInstallFolder_\d+"\s+"([^"]+)"', text):
            add(Path(m.group(1).replace("\\\\", "\\").strip()))
    return roots


def _workshop_from(p: Path) -> Path | None:
    """把用户选的目录解释成 431960 创意工坊目录（也接受它的上级）。"""
    try:
        if p.name == WORKSHOP_APPID and p.is_dir():
            return p
        for cand in (p / "steamapps" / "workshop" / "content" / WORKSHOP_APPID,
                     p / WORKSHOP_APPID,
                     p / "workshop" / "content" / WORKSHOP_APPID):
            if cand.is_dir():
                return cand
    except Exception:
        pass
    return None


def find_engine(extra_roots: list[Path] | None = None) -> dict:
    """返回 {'install': Path|None, 'workshop': [..], 'projects': [..], 'steam': [..]}

    extra_roots 是用户手动指定的目录（Steam 库根目录、创意工坊 431960 或它上一级）。
    """
    install = None
    workshop: list[Path] = []
    projects: list[Path] = []
    steam_dirs = steam_roots()
    for r in extra_roots or []:
        try:
            if r.is_dir() and r not in steam_dirs:
                steam_dirs.insert(0, r)
        except Exception:
            pass
    for root in steam_dirs:
        common = root / "steamapps" / "common"
        we = common / "wallpaper_engine"
        if install is None and we.is_dir():
            install = we
        ws = root / "steamapps" / "workshop" / "content" / WORKSHOP_APPID
        if ws.is_dir() and ws not in workshop:
            workshop.append(ws)
    for r in extra_roots or []:
        w = _workshop_from(r)
        if w is not None and w not in workshop:
            workshop.append(w)
    if install is not None:
        pj = install / "projects"
        if pj.is_dir():
            projects.append(pj)
    # 兜底：默认安装位置
    if install is None:
        d = Path(r"C:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine")
        if d.is_dir():
            install = d
            if (d / "projects").is_dir():
                projects.append(d / "projects")
    return {"install": install, "workshop": workshop, "projects": projects, "steam": steam_dirs}


# --------------------------------------------------------------------------- 数据模型

@dataclass
class Wallpaper:
    wid: str
    root: Path
    title: str = "未知壁纸"
    type: str = "unknown"
    preview: Path | None = None
    project_file: str = ""
    tags: list[str] = field(default_factory=list)
    description: str = ""
    workshop_id: str | None = None
    dependency: str | None = None
    source: str = "workshop"
    _size: int | None = None
    _files: list[Path] | None = None

    @property
    def key(self) -> str:
        return str(self.root).lower()

    def files(self, refresh: bool = False) -> list[Path]:
        if self._files is None or refresh:
            out: list[Path] = []
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames[:] = [d for d in dirnames if d.lower() not in ("shaders",)]
                for fn in filenames:
                    out.append(Path(dirpath) / fn)
            self._files = out
        return self._files

    def size(self) -> int:
        if self._size is None:
            total = 0
            try:
                for f in self.files():
                    try:
                        total += f.stat().st_size
                    except OSError:
                        pass
            except OSError:
                pass
            self._size = total
        return self._size

    def pkgs(self) -> list[Path]:
        return [f for f in self.files() if f.suffix.lower() == ".pkg"]

    def videos(self) -> list[Path]:
        return [f for f in self.files() if f.suffix.lower() in VID_EXT]

    def images(self) -> list[Path]:
        return [f for f in self.files() if f.suffix.lower() in IMG_EXT and f.name.lower() != "preview.gif"]


@dataclass
class Resource:
    name: str            # 展示用路径
    size: int
    kind: str
    origin: str          # 'file' | 'pkg'
    path: str | None = None
    pkg: str | None = None
    entry: object | None = None

    @property
    def ext(self) -> str:
        return Path(self.name).suffix.lower()


def _read_json(path: Path) -> dict:
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except Exception:
            continue
    return {}


def _preview_from(data: dict, root: Path) -> Path | None:
    pv = data.get("preview")
    if isinstance(pv, str) and pv:
        p = root / pv.replace("\\", "/")
        if p.is_file():
            return p
    for name in ("preview.jpg", "preview.png", "preview.gif", "preview.webp"):
        p = root / name
        if p.is_file():
            return p
    return None


def load_library(roots: list[Path], projects: list[Path], *, on_item=None) -> list[Wallpaper]:
    """扫描创意工坊与本地 projects 目录。"""
    out: list[Wallpaper] = []
    seen: set[str] = set()

    def add(folder: Path, source: str):
        pj = folder / "project.json"
        if not pj.is_file():
            return
        data = _read_json(pj)
        wp = Wallpaper(
            wid=folder.name,
            root=folder,
            title=str(data.get("title") or folder.name),
            type=str(data.get("type") or "unknown").strip().lower(),
            preview=_preview_from(data, folder),
            project_file=str(data.get("file") or ""),
            tags=[str(t) for t in (data.get("tags") or [])],
            description=str(data.get("description") or ""),
            workshop_id=str(data.get("workshopid") or (folder.name if source == "workshop" else "")) or None,
            dependency=str(data.get("dependency") or "") or None,
            source=source,
        )
        if wp.type in ("Scene", "Video", "Web", "Application", ""):
            wp.type = wp.type.lower() or "unknown"
        if wp.type == "unknown" and data.get("preset") is not None:
            wp.type = "preset"
        if wp.type not in TYPE_LABEL:
            wp.type = "unknown"
        if wp.key in seen:
            return
        seen.add(wp.key)
        out.append(wp)
        if on_item:
            on_item(wp)

    for root in roots:
        if not root.is_dir():
            continue
        try:
            for folder in sorted(root.iterdir(), key=lambda p: p.name):
                if folder.is_dir():
                    add(folder, "workshop")
        except OSError:
            continue
    for root in projects:
        if not root.is_dir():
            continue
        try:
            for folder in sorted(root.iterdir(), key=lambda p: p.name):
                if folder.is_dir():
                    add(folder, "projects")
        except OSError:
            continue
    return out


# --------------------------------------------------------------------------- 缩略图

def _thumb_path(src: Path, w: int) -> Path:
    try:
        st = src.stat()
        sig = f"{src}|{st.st_mtime_ns}|{st.st_size}|{w}"
    except OSError:
        sig = f"{src}|{w}"
    h = hashlib.sha1(sig.encode("utf-8", "ignore")).hexdigest()[:20]
    return THUMB_DIR / f"{h}.png"


def _video_frame(src: Path, dest: Path) -> bool:
    exe = shutil.which("ffmpeg")
    if not exe:
        return False
    try:
        subprocess.run(
            [exe, "-y", "-ss", "00:00:00.800", "-i", str(src), "-frames:v", "1", "-vf", "scale=640:-1", str(dest)],
            capture_output=True,
            timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return dest.is_file() and dest.stat().st_size > 0
    except Exception:
        return False


def make_thumb(src: Path, w: int = 560) -> Path | None:
    """为图片/视频生成 png 缩略图（带磁盘缓存）。"""
    if src is None:
        return None
    src = Path(src)
    if not src.is_file():
        return None
    dest = _thumb_path(src, w)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    if src.suffix.lower() in VID_EXT:
        if _video_frame(src, tmp):
            try:
                from PIL import Image

                im = Image.open(tmp)
                im.thumbnail((w, w * 2))
                im.convert("RGB").save(dest)
                return dest
            except Exception:
                pass
        return None
    try:
        from PIL import Image

        with Image.open(src) as im:
            try:
                im.draft("RGB", (w, w))
            except Exception:
                pass
            if getattr(im, "is_animated", False):
                im.seek(0)
            frame = im.convert("RGB")
            frame.thumbnail((w, w))
            frame.save(dest, "PNG")
        return dest
    except Exception:
        return None


def thumb_for_wallpaper(wp: Wallpaper, w: int = 560) -> Path | None:
    if wp.preview is not None:
        t = make_thumb(wp.preview, w)
        if t is not None:
            return t
    for v in wp.videos()[:2]:
        t = make_thumb(v, w)
        if t is not None:
            return t
    for i in wp.images()[:2]:
        t = make_thumb(i, w)
        if t is not None:
            return t
    return None


# --------------------------------------------------------------------------- 资源枚举

def resources(wp: Wallpaper, include_pkg: bool = True) -> list[Resource]:
    """列出壁纸的全部资源；scene.pkg 内部条目单独标记。"""
    res: list[Resource] = []
    for f in wp.files():
        ext = f.suffix.lower()
        if ext == ".pkg":
            continue
        rel = f.relative_to(wp.root).as_posix()
        try:
            size = f.stat().st_size
        except OSError:
            size = 0
        res.append(Resource(rel, size, kind_of(rel), "file", path=str(f)))

    if include_pkg and PKG_OK:
        for pkg_path in wp.pkgs():
            try:
                pkg = weparser.open_pkg(str(pkg_path))
            except Exception:
                continue
            base = pkg_path.name
            for e in pkg.entries:
                res.append(
                    Resource(
                        f"{base}/{e.path}",
                        int(e.length),
                        kind_of(e.path),
                        "pkg",
                        pkg=str(pkg_path),
                        entry=e,
                    )
                )
    order = {"texture": 0, "image": 1, "video": 2, "audio": 3, "config": 4, "shader": 5}
    res.sort(key=lambda r: (order.get(r.kind, 6), -r.size))
    return res


def count_kinds(res: list[Resource]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in res:
        out[r.kind] = out.get(r.kind, 0) + 1
    return out
