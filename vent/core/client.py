# -*- coding: utf-8 -*-
"""Flet 桌面客户端：优先用本地已解压的副本，绝不去网上拉。

flet_desktop 自己会走 `~/.flet/client`（必要时联网下载），而下载在很多机器上
会因为 TLS 证书 / 代理 / 安全软件直接失败（`CERTIFICATE_VERIFY_FAILED`），
用户看到的就是"双击没窗口"。这里提前把现成的客户端目录塞进 `FLET_VIEW_PATH`，
flet 就完全跳过缓存检查和下载。
"""
from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

from ..paths import app_dir, data_dir

ARTIFACT = "flet-windows.zip"


def _has_client(d: Path) -> bool:
    try:
        return (d / "flet" / "flet.exe").is_file()
    except Exception:
        return False


def _candidate_dirs():
    """已经解压好的客户端目录，按优先级。"""
    yield data_dir() / "flet-client"
    for base in (data_dir() / "home", Path.home()):
        try:
            root = base / ".flet" / "client"
            for d in sorted(root.glob("flet-desktop-*"), reverse=True):
                yield d
        except Exception:
            continue


def _artifact_paths():
    """随程序发布的客户端压缩包。"""
    out = []
    meipass = getattr(sys, "_MEIPASS", "") or ""
    if meipass:
        out.append(Path(meipass) / "flet_desktop" / "app" / ARTIFACT)
        out.append(Path(meipass) / ARTIFACT)
    try:
        import flet_desktop

        out.append(Path(flet_desktop.__file__).parent / "app" / ARTIFACT)
    except Exception:
        pass
    out.append(app_dir() / ARTIFACT)
    out.append(app_dir() / "vendor" / ARTIFACT)   # 项目里自带的副本（源码运行 / 自建包）
    try:
        out.append(Path(sys.executable).parent / "vendor" / ARTIFACT)  # exe 旁边
    except Exception:
        pass
    return [p for p in out if p.is_file()]


def _extract(zip_path: Path, dest: Path) -> bool:
    try:
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest)
        return _has_client(dest)
    except Exception:
        return False


def prepare_flet_client() -> str:
    """让 flet 用一个现成的客户端目录，返回该目录（失败返回空串）。"""
    env = os.environ.get("FLET_VIEW_PATH", "")
    if env and (Path(env) / "flet.exe").is_file():
        return env
    for d in _candidate_dirs():
        if _has_client(d):
            os.environ["FLET_VIEW_PATH"] = str(d / "flet")
            return str(d / "flet")
    for z in _artifact_paths():
        dest = data_dir() / "flet-client"
        if _extract(z, dest):
            os.environ["FLET_VIEW_PATH"] = str(dest / "flet")
            return str(dest / "flet")
    return ""
