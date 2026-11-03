# -*- coding: utf-8 -*-
"""界面常量：窗口尺寸、卡片尺寸、字号、类型图标。"""
from __future__ import annotations

import flet as ft

REC_TITLE = "Vent_Capture"
REC_W, REC_H = 1920, 1080
REC_DEFAULT_SECONDS = 15.0
REC_MAX_SECONDS = 120.0
WINDOW_W = 1100
WINDOW_H = 750
CARD_W = 240
IMG_H = 240          # 正方形：图片按 1:1 完整显示
CARD_H = 306
GRID_GAP = 12
BODY_PAD = 24
S_HERO = 30.0
S_TITLE = 19.0
S_BODY = 15.0
S_SMALL = 13.5
S_TINY = 12.0
TYPE_ICON = {
    "scene": ft.Icons.LANDSCAPE_ROUNDED,
    "video": ft.Icons.MOVIE_ROUNDED,
    "web": ft.Icons.PUBLIC_ROUNDED,
    "application": ft.Icons.APPS_ROUNDED,
    "preset": ft.Icons.TUNE_ROUNDED,
    "unknown": ft.Icons.HELP_OUTLINE_ROUNDED,
}
