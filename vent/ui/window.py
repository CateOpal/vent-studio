# -*- coding: utf-8 -*-
"""窗口尺寸自适应。"""
from __future__ import annotations


def fit_window_size(w: int, h: int) -> tuple[int, int]:
    """按屏幕可用区域收缩窗口，避免在高 DPI 小屏上超出可视范围。"""
    try:
        import ctypes

        u = ctypes.windll.user32
        try:
            u.SetProcessDPIAware()
        except Exception:
            pass
        sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
        try:
            scale = u.GetDpiForSystem() / 96.0
        except Exception:
            scale = 1.0
        avail_w = int(sw / scale) - 24
        avail_h = int(sh / scale) - 64
        return min(w, avail_w), min(h, avail_h)
    except Exception:
        return w, h
