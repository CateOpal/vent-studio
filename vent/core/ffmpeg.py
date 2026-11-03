# -*- coding: utf-8 -*-
"""查找 / 校验系统里的 ffmpeg。

顺序：VENT_FFMPEG / FFMPEG_BINARY → data\bin\ffmpeg.exe → 程序旁 _vendor →
imageio-ffmpeg → PATH → WinGet / Scoop / Chocolatey / MSYS2 / C:\ffmpeg。
"""
from __future__ import annotations

import functools
import os
import re
import subprocess
from pathlib import Path

from .. import paths
from ..paths import app_dir

FFMPEG_MIN_VERSION = (4, 0)


_FFMPEG_REJECTS: list[tuple[str, str, str]] = []


def _ffmpeg_candidates():
    """按优先级给出 (来源说明, 可执行文件路径)。只负责列，不负责验证。"""
    for key in ("VENT_FFMPEG", "ORE_FFMPEG", "FFMPEG_BINARY"):
        val = os.environ.get(key)
        if val:
            yield ("环境变量 " + key, Path(val))
    yield ("已下载", paths.data_dir() / "bin" / "ffmpeg.exe")
    yield ("程序目录", app_dir() / "_vendor" / "ffmpeg" / "ffmpeg.exe")
    yield ("程序目录", app_dir() / "ffmpeg.exe")
    try:  # imageio-ffmpeg 自带的静态构建
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe:
            yield ("imageio-ffmpeg", Path(exe))
    except Exception:
        pass
    # PATH 里的每一个同名文件（相当于 where ffmpeg 的全部结果）
    for folder in (os.environ.get("PATH") or "").split(os.pathsep):
        if folder.strip():
            yield ("系统 PATH", Path(folder) / "ffmpeg.exe")
    # 包管理器 / 手动解压的常见位置
    local = Path(os.environ.get("LOCALAPPDATA", "") or ".")
    user = Path(os.environ.get("USERPROFILE", "") or ".")
    known = [
        local / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe",
        user / "scoop" / "shims" / "ffmpeg.exe",
        Path("C:/ProgramData/chocolatey/bin/ffmpeg.exe"),
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/Program Files (x86)/ffmpeg/bin/ffmpeg.exe"),
        local / "Programs" / "ffmpeg" / "bin" / "ffmpeg.exe",
        Path("C:/msys64/usr/bin/ffmpeg.exe"),
        Path("C:/ProgramData/msys64/usr/bin/ffmpeg.exe"),
    ]
    for c in known:
        yield ("常见安装位置", c)
    # winget 装的是带版本号的包目录
    try:
        for d in (local / "Microsoft" / "WinGet" / "Packages").glob("Gyan.FFmpeg*"):
            for exe in d.rglob("ffmpeg.exe"):
                yield ("WinGet 包", exe)
    except Exception:
        pass


@functools.lru_cache(maxsize=64)
def probe_ffmpeg(exe: str) -> tuple[str, bool] | None:
    """跑一次 ffmpeg -version：能用就返回 (版本号, 是否带 libx264)，否则 None。"""
    try:
        r = subprocess.run([exe, "-hide_banner", "-version"], capture_output=True,
                           text=True, timeout=10, encoding="utf-8", errors="replace",
                           creationflags=0x08000000)  # CREATE_NO_WINDOW
    except Exception:
        return None
    out = (r.stdout or "") + (r.stderr or "")
    m = re.search(r"ffmpeg version (\d+)\.(\d+)", out)
    if r.returncode != 0 or not m:
        return None
    ver = (int(m.group(1)), int(m.group(2)))
    if ver < FFMPEG_MIN_VERSION:
        return None
    has_x264 = "libx264" in out  # 静态构建的 banner 一般会列出来
    if not has_x264:
        try:
            r2 = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True,
                                text=True, timeout=10, encoding="utf-8", errors="replace",
                                creationflags=0x08000000)
            has_x264 = "libx264" in ((r2.stdout or "") + (r2.stderr or ""))
        except Exception:
            has_x264 = False
    return (f"{ver[0]}.{ver[1]}", has_x264)


@functools.lru_cache(maxsize=1)
def ffmpeg_info() -> dict | None:
    """找一份能用的 ffmpeg，返回 {path, source, version, x264}；没有就 None。"""
    _FFMPEG_REJECTS.clear()
    seen: set[str] = set()
    for source, cand in _ffmpeg_candidates():
        try:
            path = str(cand)
            if not path or path in seen:
                continue
            seen.add(path)
            if not Path(path).is_file():
                continue
            if Path(path).stat().st_size < 1 << 20:  # 几十 KB 的多半是占位/转发脚本
                _FFMPEG_REJECTS.append((source, path, "文件过小，不像真实构建"))
                continue
        except Exception:
            continue
        got = probe_ffmpeg(path)
        if got is None:
            _FFMPEG_REJECTS.append((source, path, f"版本低于 {FFMPEG_MIN_VERSION[0]}.0 或无法运行"))
            continue
        version, has_x264 = got
        return {"path": path, "source": source, "version": version, "x264": has_x264}
    return None


def find_ffmpeg() -> str | None:
    """要一份能用的 ffmpeg 路径（系统自带的优先复用）。"""
    info = ffmpeg_info()
    return info["path"] if info else None


def reset_ffmpeg_cache() -> None:
    """下载完 / 手动放了新文件之后调用，重新探测。"""
    try:
        ffmpeg_info.cache_clear()
        probe_ffmpeg.cache_clear()
    except Exception:
        pass
