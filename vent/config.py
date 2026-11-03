# -*- coding: utf-8 -*-
"""配置读写（data\config.json）。"""
from __future__ import annotations

import json


from .paths import config_file, default_config_file

CFG_PATH = config_file()

DEFAULT_CFG = {
    "bg_mode": "solid",       # solid | image | video（首次启动就是纯色）
    "bg_color": "#080B12",
    "bg_image": "",
    "bg_video": "",
    "bg_opacity": 0.72,       # 背景不透明度：0 = 完全透明（只见底色），1 = 背景最清晰
    "accent": "#8FB6FF",
    "export_dir": "",
    "play_when_done": True,   # 录制 / 转换完成后立刻用系统播放器打开产物
    "steam_library": "",      # 手动指定的 Steam 库目录（自动找不到时才用得上）
}


def load_cfg() -> dict:
    """读配置；第一次启动时用随程序发布的 config.json 初始化一份到数据目录。"""
    cfg = dict(DEFAULT_CFG)
    try:
        if CFG_PATH.is_file():
            data = json.loads(CFG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if k in DEFAULT_CFG})
            return cfg
    except Exception:
        pass
    try:  # 没有就地拷一份模板 → 之后用户改设置就有地方存
        tpl = default_config_file()
        if tpl.is_file() and tpl != CFG_PATH:
            data = json.loads(tpl.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if k in DEFAULT_CFG})
        save_cfg(cfg)
    except Exception:
        pass
    return cfg


def save_cfg(cfg: dict) -> None:
    try:
        payload = {k: v for k, v in cfg.items() if k in DEFAULT_CFG}
        CFG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
