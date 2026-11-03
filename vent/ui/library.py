# -*- coding: utf-8 -*-
"""壁纸库：搜索、筛选、网格、卡片、空状态、缩略图。"""
from __future__ import annotations

from ..compat import *  # noqa: F401,F403


class LibraryMixin:
    def head(self) -> ft.Control:
        self.search = th.field("搜索壁纸名称…", prefix_icon=ft.Icons.SEARCH_ROUNDED,
                               on_change=self.on_search, expand=True, height=42, text_size=S_BODY)
        chips = [
            self.chip("全部", "all"),
            self.chip("场景", "scene"),
            self.chip("视频", "video"),
            self.chip("网页", "web"),
        ]
        self.chip_row = ft.Row(chips, spacing=8, tight=True)
        return ft.Column(
            [
                ft.Row(
                    [txt("壁纸库", S_HERO, T.TEXT, ft.FontWeight.W_700),
                     ft.Container(expand=True),
                     self.search],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=16,
                ),
                ft.Row([self.chip_row, ft.Container(expand=True)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ],
            spacing=14,
            tight=True,
        )

    def chip(self, label: str, key: str) -> ft.Container:
        active = self.type_filter == key
        return ft.Container(
            content=txt(label, S_SMALL, T.TEXT if active else T.DIM,
                        ft.FontWeight.W_600 if active else ft.FontWeight.W_400),
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            border_radius=ft.BorderRadius.all(999),
            bgcolor=a(0.22, T.ACCENT) if active else T.CARD_BG,
            border=ft.Border.all(1, a(0.42, T.ACCENT) if active else T.CARD_BORDER),
            on_click=lambda e: self.set_filter(key),
            animate=ft.Animation(120, ft.AnimationCurve.EASE_OUT),
        )

    def set_filter(self, key: str):
        self.type_filter = key
        self.body.content = self.library_view()
        self.page.update()

    def on_search(self, e):
        self.q = (e.control.value or "").strip().lower()
        # 防抖：连续输入时只重建一次网格
        token = getattr(self, "_search_token", 0) + 1
        self._search_token = token

        async def later():
            await asyncio.sleep(0.25)
            if token == self._search_token:
                self.refresh_grid()

        self.page.run_task(later)

    def visible_wallpapers(self) -> list[ws.Wallpaper]:
        items = self.wps
        if self.type_filter != "all":
            items = [w for w in items if w.type == self.type_filter]
        if self.q:
            items = [w for w in items if self.q in w.title.lower() or self.q in w.wid]
        if self.sort == "size":
            items = sorted(items, key=lambda w: w.size(), reverse=True)
        else:
            items = sorted(items, key=lambda w: w.title.lower())
        return items

    def library_view(self) -> ft.Container:
        self.grid_host = ft.Column(spacing=0, expand=True, scroll=ft.ScrollMode.AUTO,
                                   horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        self.fill_grid()
        return ft.Container(
            expand=True,
            padding=ft.Padding.only(left=BODY_PAD, right=BODY_PAD, top=16, bottom=6),
            content=ft.Column(
                [self.head(), ft.Container(height=6), self.grid_host],
                spacing=0,
                expand=True,
            ),
        )

    def refresh_grid(self):
        self.fill_grid()
        self.page.update()

    def fill_grid(self):
        self.card_holders = {}
        items = self.visible_wallpapers()
        if not items:
            self.grid_host.controls = [self.empty_state()]
        else:
            # 单行自动换行：横向 spacing + 纵向 run_spacing 一致，整体居中
            self.grid_host.controls = [
                ft.Container(
                    alignment=ft.Alignment.TOP_CENTER,
                    content=ft.Row(
                        [self.card(w) for w in items],
                        spacing=GRID_GAP, run_spacing=GRID_GAP,
                        wrap=True, tight=True,
                    ),
                )
            ]
        self.count_text.value = f"{len(items)} / {len(self.wps)} 个壁纸"

    def empty_state(self) -> ft.Control:
        if not self.wps:
            # 库是空的：多半是 Wallpaper Engine / Steam 装在别的盘，或者根本不是默认目录
            return ft.Container(
                padding=ft.Padding.symmetric(vertical=80),
                alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    [ft.Icon(ft.Icons.LAYERS_CLEAR_ROUNDED, size=44, color=a(0.35)),
                     txt("没有找到壁纸库", S_TITLE, T.DIM, ft.FontWeight.W_600),
                     txt("Steam 装在 D 盘、E 盘也能自动找到；还不行就手动指定一次目录",
                         S_SMALL, T.FAINT, text_align=ft.TextAlign.CENTER, max_lines=2),
                     ft.Container(height=6),
                     th.text_button("选择 Wallpaper Engine 目录",
                                    lambda e: self.page.run_task(self.pick_engine_dir),
                                    icon=ft.Icons.FOLDER_OPEN_ROUNDED, accent=True, height=38)],
                    spacing=10,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        return ft.Container(
            padding=ft.Padding.symmetric(vertical=90),
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [ft.Icon(ft.Icons.AUTO_AWESOME_ROUNDED, size=44, color=a(0.35)),
                 txt("没有找到壁纸", S_TITLE, T.DIM, ft.FontWeight.W_600),
                 txt("换个关键词，或点标题栏的刷新按钮重新扫描", S_SMALL, T.FAINT)],
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def card(self, wp: ws.Wallpaper) -> ft.Control:
        thumb = self.thumbs.get(wp.key)
        holder = ft.Container(
            width=CARD_W,
            height=IMG_H,
            bgcolor=a(0.05, "#FFFFFF"),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Image(src=str(thumb), fit=ft.BoxFit.FILL,
                             width=CARD_W, height=IMG_H, gapless_playback=True)
            if thumb is not None else None,
        )
        self.card_holders[wp.key] = holder

        kind_color = {"scene": T.ACCENT, "video": T.ACCENT2, "web": T.OK}.get(wp.type, T.DIM)
        box = ft.Container(
            width=CARD_W,
            height=CARD_H,
            border_radius=ft.BorderRadius.all(14),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            bgcolor=T.CARD_BG,
            border=ft.Border.all(1, T.CARD_BORDER),
            on_click=lambda e: self.open_detail(wp),
            content=ft.Column(
                [
                    holder,
                    ft.Container(
                        padding=ft.Padding.only(left=11, right=11, top=8, bottom=8),
                        content=ft.Column(
                            [
                                txt(wp.title or "未命名", 14, T.TEXT, ft.FontWeight.W_600),
                                ft.Row(
                                    [
                                        th.pill(pretty_type(wp.type), kind_color),
                                        th.pill(ws.human_size(wp.size()), T.DIM, 0.10),
                                    ],
                                    spacing=6,
                                    tight=True,
                                ),
                            ],
                            spacing=6,
                            tight=True,
                        ),
                    ),
                ],
                spacing=0,
            ),
        )

        def hover(e):
            hot = str(e.data).lower() == "true"
            box.border = ft.Border.all(1, a(0.45, T.ACCENT) if hot else T.CARD_BORDER)
            box.bgcolor = T.CARD_HOT if hot else T.CARD_BG
            box.shadow = (ft.BoxShadow(blur_radius=18, spread_radius=0,
                                       color=a(0.35, "#000000"), offset=ft.Offset(0, 6))
                          if hot else None)
            box.update()

        box.on_hover = hover
        return box

    def auto_pick_bg(self):
        """不自动挑壁纸：只有「上次选了图片 / 视频但文件没了」时才退回纯色。"""
        cfg = self.cfg
        mode = cfg.get("bg_mode", "solid")
        if mode not in ("image", "video"):
            return
        key = "bg_video" if mode == "video" else "bg_image"
        path = cfg.get(key) or ""
        try:
            if path and Path(path).is_file():
                return
        except Exception:
            pass
        cfg["bg_mode"] = "solid"
        cfg["bg_image"] = ""
        cfg["bg_video"] = ""
        save_cfg(cfg)
        self.build_bg()

    async def reload_library(self):
        self.set_status("正在定位 Wallpaper Engine…")
        extra = []
        manual = str(self.cfg.get("steam_library") or "")
        if manual:
            extra.append(Path(manual))
        try:
            roots = await asyncio.to_thread(ws.find_engine, extra)
        except Exception:
            roots = {}
        self.roots = roots
        install = str(roots.get("install") or "")
        self.set_engine_dir(install)
        self.set_status("正在扫描壁纸库…")
        try:
            wps = await asyncio.to_thread(ws.load_library,
                                          roots.get("workshop") or [], roots.get("projects") or [])
        except Exception:
            wps = []
        self.wps = wps
        self.thumbs = {}
        self.card_holders = {}
        self._pkg_cache = {}
        self.body.content = self.library_view()
        self.page.update()
        self.set_status(f"已载入 {len(wps)} 个壁纸", f"{len(wps)} 个壁纸")
        self.log(f"壁纸库 {len(wps)} 个", "info",
                 "；".join(str(p) for p in (roots.get("workshop") or [])) or "没有创意工坊目录")
        self.page.run_task(self.load_thumbs)

    async def load_thumbs(self):
        if self._thumb_running:
            return
        self._thumb_running = True
        try:
            todo = [w for w in self.wps if w.key not in self.thumbs]
            total = len(todo)
            for i, wp in enumerate(todo):
                thumb = await asyncio.to_thread(ws.thumb_for_wallpaper, wp, 520)
                self.thumbs[wp.key] = thumb
                holder = getattr(self, "card_holders", {}).get(wp.key)
                if holder is not None and thumb is not None:
                    holder.content = ft.Image(src=str(thumb), fit=ft.BoxFit.FILL, expand=True,
                                              gapless_playback=True)
                    try:
                        holder.update()
                    except Exception:
                        pass
                if i % 10 == 9:
                    self.set_status(f"正在载入缩略图 {i + 1}/{total}",
                                    f"{len(self.wps)} 个壁纸")
            self.set_status("就绪", f"{len(self.wps)} 个壁纸")
        finally:
            self._thumb_running = False
