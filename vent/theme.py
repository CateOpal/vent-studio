# -*- coding: utf-8 -*-
"""液态玻璃 (Liquid Glass) 设计系统 —— 颜色令牌与控件工厂。

所有界面元素都由这些工厂函数生成，保证整体风格统一：
半透明渐变填充 + 1px 高光描边 + 顶部镜面反光 + 柔和外阴影。
"""

from __future__ import annotations

import flet as ft

W = "#FFFFFF"


class T:
    """颜色 / 尺寸令牌（深浅两套，apply_palette() 切换）。"""

    BG = "#080B12"
    TEXT = "#EAF1FF"
    DIM = "#A8B5CF"
    FAINT = "#77839E"
    LINE = "#FFFFFF"
    ACCENT = "#8FB6FF"
    ACCENT2 = "#C29BFF"
    OK = "#66E3B2"
    WARN = "#FFC46B"
    DANGER = "#FF6F7D"
    R = 22

    LIGHT = False
    INK = "#FFFFFF"      # 叠加/描边色：深色主题用白，浅色主题用墨
    # 表面色：卡片 / 顶栏 / 面板 / 对话框
    CARD_BG = "#070A12"
    CARD_HOT = "#0A101C"
    CARD_BORDER = "#FFFFFF"
    CHROME = "#04070C"
    PANEL = "#080D15"
    PANEL_BORDER = "#FFFFFF"
    HILITE = "#FFFFFF"
    OVERLAY = "#05080E"
    SCRIM = "#04070C"
    SWATCH_LIGHT = "#FFFFFF"


def _surface(alpha: float, color: str) -> str:
    return ft.Colors.with_opacity(alpha, color)


def apply_palette(light: bool) -> None:
    """切换深色 / 浅色两套配色，保证任何背景上文字都有足够对比度。"""
    T.LIGHT = bool(light)
    T.INK = "#0B1220" if light else "#FFFFFF"
    if light:
        T.TEXT = "#0C1524"
        T.DIM = "#3D4A61"
        T.FAINT = "#66738A"
        T.CARD_BG = _surface(0.86, "#FFFFFF")
        T.CARD_HOT = _surface(0.97, "#FFFFFF")
        T.CARD_BORDER = _surface(0.10, "#0B1220")
        T.CHROME = _surface(0.78, "#FFFFFF")
        T.PANEL = _surface(0.98, "#FFFFFF")
        T.PANEL_BORDER = _surface(0.10, "#0B1220")
        T.HILITE = _surface(0.07, "#0B1220")
        T.OVERLAY = _surface(0.97, "#F4F7FC")
        T.SCRIM = "#E8EEF7"
        T.SWATCH_LIGHT = "#FFFFFF"
    else:
        T.TEXT = "#EAF1FF"
        T.DIM = "#A8B5CF"
        T.FAINT = "#8E9AB4"
        T.CARD_BG = _surface(0.64, "#070A12")
        T.CARD_HOT = _surface(0.80, "#0A101C")
        T.CARD_BORDER = _surface(0.13, "#FFFFFF")
        T.CHROME = _surface(0.52, "#04070C")
        T.PANEL = _surface(0.97, "#080D15")
        T.PANEL_BORDER = _surface(0.14, "#FFFFFF")
        T.HILITE = _surface(0.10, "#FFFFFF")
        T.OVERLAY = _surface(0.94, "#05080E")
        T.SCRIM = "#04070C"
        T.SWATCH_LIGHT = "#FFFFFF"


def _mix_black(color: str, ratio: float) -> str:
    try:
        c = (color or "#FFFFFF").lstrip("#")
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        k = 1.0 - max(0.0, min(1.0, ratio))
        return "#%02X%02X%02X" % (round(r * k), round(g * k), round(b * k))
    except Exception:
        return color


def for_text(color: str) -> str:
    """强调色当文字用时，浅色主题下压暗，保证对比度。"""
    return _mix_black(color, 0.55) if T.LIGHT else color


def is_light_color(color: str) -> bool:
    """判断颜色是不是浅色（决定用深字还是浅字）。"""
    try:
        c = (color or "").strip().lstrip("#")
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except Exception:
        return False
    # 感知亮度
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return lum > 0.62


def a(alpha: float, color: str | None = None) -> str:
    """带透明度的颜色；不指定颜色时用当前主题的「叠加色」（深色=白，浅色=墨）。"""
    return ft.Colors.with_opacity(alpha, color or T.INK)


def glass(
    content=None,
    *,
    radius: float = T.R,
    alpha: float = 0.085,
    border_alpha: float = 0.22,
    padding=None,
    expand: bool = False,
    width=None,
    height=None,
    shadow: bool = True,
    sheen: bool = True,
    blur: float = 0,
    clip: bool = True,
    visible: bool = True,
) -> ft.Container:
    """一块液态玻璃面板。"""
    radius_obj = ft.BorderRadius.all(radius)
    deco = ft.BoxDecoration(
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=[a(min(1.0, alpha + 0.055)), a(min(1.0, alpha * 0.55))],
        ),
        border=ft.Border.all(1, a(border_alpha)),
        border_radius=radius_obj,
    )
    fg = None
    if sheen:
        fg = ft.BoxDecoration(
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_CENTER,
                stops=[0.0, 0.28, 0.45],
                colors=[a(0.10), a(0.02), a(0.0)],
            ),
            border_radius=radius_obj,
        )
    return ft.Container(
        content=content,
        width=width,
        height=height,
        expand=expand,
        padding=padding,
        visible=visible,
        border_radius=radius_obj,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS if clip else ft.ClipBehavior.NONE,
        gradient=deco.gradient,
        border=deco.border,
        foreground_decoration=fg,
        blur=ft.Blur(blur, blur, ft.BlurTileMode.CLAMP) if blur else None,
        shadow=ft.BoxShadow(
            blur_radius=36,
            spread_radius=-6,
            color=a(0.42, "#04070D"),
            offset=ft.Offset(0, 16),
        )
        if shadow
        else None,
    )


def txt(
    value: str = "",
    size: float = 13,
    color: str = T.TEXT,
    weight: ft.FontWeight = ft.FontWeight.W_400,
    *,
    max_lines: int | None = 1,
    ellipsis: bool = True,
    expand: bool = False,
    selectable: bool = False,
    italic: bool = False,
    spacing: float = 0,
    tooltip: str | None = None,
) -> ft.Text:
    return ft.Text(
        value,
        size=size,
        color=color,
        weight=weight,
        max_lines=max_lines,
        overflow=ft.TextOverflow.ELLIPSIS if ellipsis else ft.TextOverflow.VISIBLE,
        no_wrap=ellipsis,
        expand=expand,
        selectable=selectable,
        italic=italic,
        tooltip=tooltip,
    )


def pill(label: str, color: str = T.ACCENT, alpha: float = 0.16, icon=None) -> ft.Container:
    """小型标签胶囊。"""
    color = for_text(color)
    row: list[ft.Control] = []
    if icon is not None:
        row.append(ft.Icon(icon, size=11, color=color))
    row.append(txt(label, 11.5, color, ft.FontWeight.W_600))
    return ft.Container(
        content=ft.Row(row, spacing=4, tight=True),
        padding=ft.Padding.symmetric(horizontal=9, vertical=3),
        border_radius=ft.BorderRadius.all(20),
        bgcolor=a(alpha, color),
        border=ft.Border.all(1, a(0.20, color)),
    )


def hline(alpha: float = 0.10) -> ft.Container:
    return ft.Container(height=1, bgcolor=a(alpha), width=None, expand=True)


def icon_button(
    icon,
    on_click,
    *,
    tooltip: str | None = None,
    size: float = 18,
    color: str = T.DIM,
    box: float = 34,
    radius: float = 10,
) -> ft.Container:
    """自绘的图标按钮（悬停发光），不使用系统按钮样式。"""
    ic = ft.Icon(icon, size=size, color=color)

    def on_hover(e):
        hot = str(e.data).lower() == "true"
        con.bgcolor = a(0.14) if hot else a(0.0)
        con.border = ft.Border.all(1, a(0.28) if hot else a(0.10))
        ic.color = T.TEXT if hot else color
        con.update()

    con = ft.Container(
        content=ft.Row([ic], alignment=ft.MainAxisAlignment.CENTER, tight=True),
        width=box,
        height=box,
        border_radius=ft.BorderRadius.all(radius),
        border=ft.Border.all(1, a(0.10)),
        bgcolor=a(0.0),
        on_click=on_click,
        on_hover=on_hover,
        tooltip=tooltip,
        animate=ft.Animation(120, ft.AnimationCurve.EASE_OUT),
    )
    return con


def text_button(
    label: str,
    on_click,
    *,
    icon=None,
    accent: bool = False,
    width=None,
    height: float = 34,
    disabled: bool = False,
) -> ft.Container:
    """自绘的主/次按钮。"""
    color = T.TEXT if accent else T.DIM
    base_bg = 0.22 if accent else 0.05
    items: list[ft.Control] = []
    if icon is not None:
        items.append(ft.Icon(icon, size=15, color=color))
    items.append(txt(label, 12.5, color, ft.FontWeight.W_600))
    ic_like = items[0] if icon is not None else None

    def on_hover(e):
        hot = str(e.data).lower() == "true"
        con.bgcolor = a(base_bg + (0.12 if hot else 0.0), T.ACCENT if accent else T.INK)
        con.border = ft.Border.all(1, a(0.42 if hot else 0.22, T.ACCENT if accent else T.INK))
        con.update()

    con = ft.Container(
        content=ft.Row(items, spacing=7, tight=True, alignment=ft.MainAxisAlignment.CENTER),
        width=width,
        height=height,
        padding=ft.Padding.symmetric(horizontal=13, vertical=0),
        border_radius=ft.BorderRadius.all(11),
        bgcolor=a(base_bg, T.ACCENT if accent else T.INK),
        border=ft.Border.all(1, a(0.30 if accent else 0.16, T.ACCENT if accent else T.INK)),
        on_click=None if disabled else on_click,
        on_hover=None if disabled else on_hover,
        opacity=0.45 if disabled else 1.0,
        animate=ft.Animation(130, ft.AnimationCurve.EASE_OUT),
    )
    return con


def field(
    hint: str,
    *,
    prefix_icon=None,
    on_change=None,
    on_submit=None,
    width=None,
    expand: bool = False,
    height: float = 38,
    text_size: float = 12.5,
) -> ft.TextField:
    return ft.TextField(
        hint_text=hint,
        hint_style=ft.TextStyle(color=T.DIM, size=text_size),
        prefix_icon=prefix_icon,
        prefix_icon_size_constraints=ft.BoxConstraints(min_width=18, max_width=18, min_height=18, max_height=18) if prefix_icon else None,
        text_size=text_size,
        width=width,
        expand=expand,
        height=height,
        content_padding=ft.Padding.symmetric(horizontal=13, vertical=0),
        # 玻璃底：和卡片/胶囊同一套令牌（按背景亮度自动加深），不再是 6% 透明
        border={
            ft.ControlState.DEFAULT: ft.OutlineInputBorder(
                side=ft.BorderSide(1, T.CARD_BORDER),
                border_radius=ft.BorderRadius.all(11)),
            ft.ControlState.FOCUSED: ft.OutlineInputBorder(
                side=ft.BorderSide(1.4, T.ACCENT),
                border_radius=ft.BorderRadius.all(11)),
        },
        bgcolor=T.CARD_BG,
        color=T.TEXT,
        cursor_color=T.ACCENT,
        on_change=on_change,
        on_submit=on_submit,
    )


def toast(page: ft.Page, message: str, *, icon=ft.Icons.CHECK_CIRCLE, color: str = T.OK, host: ft.Stack | None = None):
    """在窗口底部弹出一条玻璃提示。"""
    box = ft.Container(
        content=ft.Row(
            [ft.Icon(icon, size=15, color=color), txt(message, 12.5, T.TEXT)],
            tight=True,
            spacing=8,
        ),
        padding=ft.Padding.symmetric(horizontal=16, vertical=10),
        border_radius=ft.BorderRadius.all(13),
        bgcolor=a(0.16, "#0B0F18"),
        border=ft.Border.all(1, a(0.20)),
        shadow=ft.BoxShadow(blur_radius=24, color=a(0.5, "#000000"), offset=ft.Offset(0, 8)),
        left=None,
        top=None,
        offset=ft.Offset(0, 14),
        opacity=0.0,
        animate_opacity=ft.Animation(180, ft.AnimationCurve.EASE_OUT),
        animate_offset=ft.Animation(220, ft.AnimationCurve.EASE_OUT),
    )
    host = host if host is not None else page.overlay
    host.append(box)
    page.update()

    async def run():
        import asyncio

        await asyncio.sleep(0.02)
        box.opacity = 1.0
        box.offset = ft.Offset(0, 0)
        page.update()
        await asyncio.sleep(2.1)
        box.opacity = 0.0
        box.offset = ft.Offset(0, 10)
        page.update()
        await asyncio.sleep(0.3)
        host.remove(box)
        page.update()

    page.run_task(run)


def _darken(color: str, amount: float) -> str:
    """把颜色按比例压暗，用于背景渐变。"""
    c = (color or "#000000").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except Exception:
        return color
    k = max(0.0, 1.0 - amount)
    return "#%02x%02x%02x" % (int(r * k), int(g * k), int(b * k))
