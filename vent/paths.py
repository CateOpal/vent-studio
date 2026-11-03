# -*- coding: utf-8 -*-
"""运行时目录（配置 / 日志 / 缓存）。

顺序：环境变量 VENT_DATA_DIR → 程序所在目录下的 data → %APPDATA%\Vent Studio → 临时目录。
第一个能真正写入的胜出，所以绿色运行、装到 Program Files、只读盘都不会崩。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

APP_NAME = "Vent Studio"
APP_VERSION = "1.1.0"

_data_dir: Path | None = None
_client_home: str = ""


def app_dir() -> Path:
    """源码目录，或打包后 exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _usable(d: Path) -> bool:
    """能不能在这个目录里建文件、建子目录（Flet 客户端要建带随机后缀的子目录）。"""
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".write-check"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        sub = d / f".vent-probe-{os.getpid()}"
        sub.mkdir()
        sub.rmdir()
        return True
    except Exception:
        return False


def data_dir() -> Path:
    global _data_dir
    if _data_dir is not None:
        return _data_dir
    cands: list[Path] = []
    env = os.environ.get("VENT_DATA_DIR") or os.environ.get("ORE_DATA_DIR")
    if env:
        cands.append(Path(env))
    cands.append(app_dir() / "data")
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if base:
        cands.append(Path(base) / APP_NAME)
    cands.append(Path(tempfile.gettempdir()) / APP_NAME)
    for c in cands:
        if _usable(c):
            _data_dir = c
            return c
    _data_dir = Path(tempfile.gettempdir()) / APP_NAME   # 兜底，大概率还是能用
    return _data_dir


def client_home() -> str:
    """Flet 客户端缓存被改到别处时返回那个目录，否则返回空串。"""
    return _client_home


def _redirect_client_home() -> str:
    """把 Flet 客户端的解压位置改到数据目录，返回新 home（失败返回空串）。"""
    global _client_home
    alt = data_dir() / "home"
    if not _usable(alt / ".flet" / "client"):
        return ""
    os.environ["USERPROFILE"] = str(alt)
    os.environ["HOME"] = str(alt)
    _client_home = str(alt)
    return str(alt)


def prepare_client_home() -> str:
    """Flet 桌面客户端要解压到 ~/.flet/client。

    有些机器上用户目录不可写（安全软件把 ~/.flet 拦了、漫游目录只读等），
    mkdir 会直接 PermissionError，程序连窗口都开不出来。
    这里先探一下，写不进去就把 HOME / USERPROFILE 指到数据目录，让客户端解压在那儿。
    """
    home = Path.home()
    if _usable(home / ".flet" / "client"):
        return str(home)
    return _redirect_client_home() or str(home)


def force_client_home() -> str:
    """兜底：不管探测结果，强制把客户端解压位置换到数据目录。"""
    return _redirect_client_home()


def cache_dir() -> Path:
    d = data_dir() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file() -> Path:
    return data_dir() / "config.json"


def default_config_file() -> Path:
    """随程序发布的默认配置（打包后在 _MEIPASS 里，源码运行就是项目根目录）。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "") or ""
        if meipass:
            p = Path(meipass) / "config.json"
            if p.is_file():
                return p
    return app_dir() / "config.json"


def log_file() -> Path:
    return data_dir() / "vent.log"

def asset_path(name: str) -> str:
    """随程序一起发布的素材（assets/xxx）的绝对路径；找不到返回空串。

    源码运行时在仓库根目录，打包后在 PyInstaller 的解包目录（--add-data 放的）。
    """
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        roots.append(Path(meipass))
    roots.append(Path(__file__).resolve().parent.parent)
    for root in roots:
        p = root / "assets" / name
        if p.is_file():
            return str(p)
    return ""
