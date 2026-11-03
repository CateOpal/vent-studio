# -*- coding: utf-8 -*-
"""窗口外壳：标题栏、状态栏、背景、对话框、日志面板、沉浸模式。"""
from __future__ import annotations

from ..compat import *  # noqa: F401,F403


class ShellMixin:
    def build(self):
        page = self.page
        self.refresh_palette()
        page.padding = 0
        page.spacing = 0
        # 全局字体：直接用系统里的微软雅黑（Windows 字体族名可被 Flutter 解析）
        try:
            page.theme = ft.Theme(font_family="Microsoft YaHei")
        except Exception:
            pass
        try:
            w = page.window
            w.frameless = True
            w.title_bar_hidden = True
            fw, fh = fit_window_size(WINDOW_W, WINDOW_H)
            w.width = fw
            w.height = fh
            w.resizable = False
            w.maximizable = False
            w.title = APP_NAME
            # 任务栏 / 窗口图标：用代码画的那枚 V，不依赖系统缓存
            icon = asset_path("icon.ico")
            if icon:
                w.icon = icon
        except Exception:
            pass

        self.build_bg()

        self.title_holder.content = self.titlebar()
        self.main_stack = ft.Stack([self.body, self.overlay, self.dialog_host], expand=True,
                                   fit=ft.StackFit.EXPAND)
        # 欣赏背景时用这个占位块顶住中间区域，底栏位置才不会被顶到上面去
        self.immersive_spacer = ft.Container(expand=True, visible=False)
        self.status_holder = ft.Container(content=self.statusbar())
        shell = ft.Column(
            [self.title_holder, self.main_stack, self.immersive_spacer, self.status_holder],
            spacing=0,
            expand=True,
        )
        self.shell = shell
        # 四周不做圆角：窗口内容铺满整个矩形
        root = ft.Container(
            expand=True,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Stack(
                [self.bg_layer, shell, self.toast_host],
                expand=True,
                fit=ft.StackFit.EXPAND,
            ),
        )
        page.add(root)

    def tool_button(self, icon, tip: str, on_click) -> ft.Control:
        return ft.IconButton(
            icon=icon,
            icon_size=17,
            icon_color=T.DIM,
            tooltip=tip,
            on_click=on_click,
            width=36,
            height=36,
            style=ft.ButtonStyle(
                padding=ft.Padding.all(0),
                shape=ft.RoundedRectangleBorder(radius=10),
                bgcolor=T.CARD_BG,
                side=ft.BorderSide(1, T.CARD_BORDER),
                overlay_color=a(0.11),
            ),
        )

    def close_button(self) -> ft.Control:
        holder = ft.Container(
            width=36,
            height=36,
            border_radius=ft.BorderRadius.all(10),
            alignment=ft.Alignment.CENTER,
            bgcolor=T.CARD_BG,
            border=ft.Border.all(1, T.CARD_BORDER),
            tooltip="关闭",
            on_click=lambda e: self.page.run_task(self.close),
            content=ft.Icon(ft.Icons.CLOSE_ROUNDED, size=17, color=T.DIM),
        )

        def hover(e):
            hot = str(e.data).lower() == "true"
            holder.bgcolor = a(0.92, "#E5484D") if hot else T.CARD_BG
            holder.content.color = "#FFFFFF" if hot else T.DIM
            holder.update()

        holder.on_hover = hover
        return holder

    def brand(self) -> ft.Control:
        return ft.Row(
            tight=True,
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=28,
                    height=28,
                    border_radius=ft.BorderRadius.all(8),
                    gradient=ft.LinearGradient(
                        begin=ft.Alignment.TOP_LEFT,
                        end=ft.Alignment.BOTTOM_RIGHT,
                        colors=[self.cfg.get("accent", T.ACCENT), "#5EEAD4"],
                    ),
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text("V", size=16, weight=ft.FontWeight.W_900, color="#08101C"),
                ),
                ft.Text(APP_NAME, size=15, weight=ft.FontWeight.W_700, color=T.INK),
            ],
        )

    async def rescan(self):
        if getattr(self, "_scanning", False):
            return
        self._scanning = True
        self.close_overlay()
        try:
            self.wps = []
            self.body.content = ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    [ft.ProgressRing(width=32, height=32, stroke_width=3, color=T.ACCENT),
                     txt("正在重新扫描壁纸库…", S_BODY, T.DIM)],
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                ),
            )
            self.page.update()
            await self.reload_library()
            self.log(f"重新扫描完成：{len(self.wps)} 个壁纸", "info")
            self.toast(f"已重新扫描：{len(self.wps)} 个壁纸")
        finally:
            self._scanning = False

    def rescan_pill(self) -> ft.Control:
        ic = ft.Icon(ft.Icons.REFRESH_ROUNDED, size=15, color=T.DIM)
        label = txt("重新扫描", 13, T.TEXT, ft.FontWeight.W_500)
        box = ft.Container(
            height=36,
            padding=ft.Padding.only(left=14, right=15, top=0, bottom=0),
            border_radius=ft.BorderRadius.all(18),
            bgcolor=T.CARD_BG,
            border=ft.Border.all(1, T.CARD_BORDER),
            tooltip="重新扫描壁纸库",
            on_click=lambda e: self.page.run_task(self.rescan),
            content=ft.Row([ic, label], spacing=6, tight=True,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

        def hover(e):
            hot = str(e.data).lower() == "true"
            box.bgcolor = T.CARD_HOT if hot else T.CARD_BG
            box.border = ft.Border.all(1, T.CARD_BORDER)
            ic.color = T.TEXT if hot else T.DIM
            label.color = T.TEXT
            box.update()

        box.on_hover = hover
        return box

    def titlebar(self) -> ft.Control:
        # 隐藏模式下顶栏留在原位，但里面的东西全收起来（只留拖拽区，还能拖窗口）
        if getattr(self, "immersive", False):
            self._brand_ctl = ft.Container(height=56)
            self._drag_area = ft.WindowDragArea(
                expand=True, maximizable=False, content=self._brand_ctl)
            return ft.Container(
                height=56,
                padding=ft.Padding.only(left=18, right=10),
                content=ft.Row([self._drag_area], spacing=0,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
            )
        self._brand_ctl = ft.Container(
            height=56,
            alignment=ft.Alignment.CENTER_LEFT,
            content=self.brand(),
        )
        self._drag_area = ft.WindowDragArea(
            expand=True,
            maximizable=False,
            content=self._brand_ctl,
        )
        self._rescan_ctl = self.rescan_pill()
        self._gear_ctl = self.tool_button(ft.Icons.TUNE_ROUNDED, "外观与背景",
                                          lambda e: self.open_settings())
        self._close_ctl = self.close_button()
        return ft.Container(
            height=56,
            padding=ft.Padding.only(left=18, right=10),
            # 顶栏透明：不加单独底色，直接透出背景（纯色或图片/视频）
            content=ft.Row(
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    self._drag_area,
                    ft.Container(width=8),
                    self._rescan_ctl,
                    ft.Container(width=8),
                    self._gear_ctl,
                    ft.Container(width=10),
                    self._close_ctl,
                ],
            ),
        )

    async def close(self):
        try:
            await self.page.window.close()
        except Exception:
            pass

    def bar_pill(self, content: ft.Control, expand: bool = False,
                 accent: str | None = None) -> ft.Container:
        """底栏 / 顶栏用的胶囊：和卡片同一套玻璃底色，保证任何背景上都看得清。"""
        return ft.Container(
            expand=expand,
            height=30,
            padding=ft.Padding.only(left=13, right=13),
            border_radius=ft.BorderRadius.all(15),
            bgcolor=a(0.30, accent) if accent else T.CARD_BG,
            border=ft.Border.all(1, T.CARD_BORDER),
            alignment=ft.Alignment.CENTER_LEFT,
            content=content,
        )

    def statusbar(self) -> ft.Container:
        minimal = bool(getattr(self, "immersive", False))
        self.eye_icon = ft.Icon(
            ft.Icons.VISIBILITY_OFF_ROUNDED if minimal else ft.Icons.VISIBILITY_ROUNDED,
            size=15, color=T.DIM)
        eye_pill = ft.Container(
            width=34,
            height=30,
            border_radius=ft.BorderRadius.all(15),
            bgcolor=T.CARD_BG,
            border=ft.Border.all(1, T.CARD_BORDER),
            alignment=ft.Alignment.CENTER,
            on_click=self.toggle_immersive,
            on_hover=self._pill_hover,
            tooltip="恢复壁纸库" if minimal else "隐藏中间内容，欣赏背景",
            content=self.eye_icon,
        )
        self.eye_pill = eye_pill
        if minimal:
            # 隐藏模式：底栏只留这颗眼睛，其它胶囊全部不创建
            return ft.Container(
                height=46,
                padding=ft.Padding.only(left=16, right=16),
                content=ft.Row(
                    [ft.Container(expand=True), eye_pill],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        self.status_text.color = T.DIM
        self.count_text.color = T.FAINT
        self.engine_text.color = T.FAINT
        dot = ft.Container(width=7, height=7, border_radius=ft.BorderRadius.all(4),
                           bgcolor=T.OK)
        # 胶囊内宽 = 250 - 左右内边距 26 - 图标 14 - 间距 6
        self.engine_text.width = 204
        engine_row = ft.Row(
            [ft.Icon(ft.Icons.FOLDER_SPECIAL_ROUNDED, size=14, color=T.FAINT),
             self.engine_text],
            spacing=6,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        # 整块可点，点开是运行日志；有错误时圆点由绿变红
        self.status_dot = dot
        status_row = ft.Row([dot, self.status_text], spacing=8, tight=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER)
        status_pill = ft.Container(
            height=30,
            padding=ft.Padding.only(left=13, right=13),
            border_radius=ft.BorderRadius.all(15),
            bgcolor=T.CARD_BG,
            border=ft.Border.all(1, T.CARD_BORDER),
            alignment=ft.Alignment.CENTER_LEFT,
            on_click=self.open_log,
            on_hover=self._pill_hover,
            tooltip="点击查看运行日志 / 错误详情",
            content=status_row,
        )
        self.status_pill = status_pill
        # 保存位置：可点击的胶囊，点一下弹窗改
        self.save_text = txt(self.export_label(), S_SMALL,
                             T.DIM if self.export_dir() else T.FAINT,
                             max_lines=1, ellipsis=True, tooltip=self.export_dir() or "未设置默认保存位置")
        save_row = ft.Row(
            [ft.Icon(ft.Icons.SAVE_ALT_ROUNDED, size=14, color=T.FAINT), self.save_text],
            spacing=6,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        save_pill = ft.Container(
            height=30,
            padding=ft.Padding.only(left=13, right=13),
            border_radius=ft.BorderRadius.all(15),
            bgcolor=T.CARD_BG,
            border=ft.Border.all(1, T.CARD_BORDER),
            alignment=ft.Alignment.CENTER,
            on_click=lambda e: self.show_export_dialog(),
            on_hover=self._pill_hover,
            content=save_row,
        )
        # 引擎目录：宽度最多 250，超出省略号；点一下打开资源管理器
        engine_pill = ft.Container(
            width=250 if self.engine_dir else 186,
            height=30,
            padding=ft.Padding.only(left=13, right=13),
            border_radius=ft.BorderRadius.all(15),
            bgcolor=T.CARD_BG,
            border=ft.Border.all(1, T.CARD_BORDER),
            alignment=ft.Alignment.CENTER_LEFT,
            on_click=lambda e: self.open_engine_dir(),
            on_hover=self._pill_hover,
            tooltip=(self.engine_dir or "未找到 Wallpaper Engine") + chr(10) + "点击打开引擎目录",
            content=engine_row,
        )
        self.engine_pill = engine_pill

        self._status_pill = status_pill
        self._save_pill = save_pill
        self._count_pill = self.bar_pill(self.count_text)
        self._sync_status_pill()

        return ft.Container(
            height=46,
            padding=ft.Padding.only(left=16, right=16, top=0, bottom=0),
            # 底栏本身透明：左两块 / 中间留空 / 右边四块，胶囊只包文字
            content=ft.Row(
                [
                    status_pill,
                    engine_pill,
                    ft.Container(expand=True),
                    self._save_pill,
                    self._count_pill,
                    eye_pill,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def open_engine_dir(self):
        d = getattr(self, "engine_dir", "") or ""
        if d and Path(d).is_dir():
            if open_in_explorer(d):
                self.toast(f"已打开 {Path(d).name}", ft.Icons.FOLDER_OPEN_ROUNDED, T.OK)
            else:
                self.copy_path(d)
        else:
            self.toast("没有找到 Wallpaper Engine 目录", ft.Icons.ERROR_OUTLINE_ROUNDED, T.WARN)

    def copy_path(self, path: str):
        """打不开资源管理器时的兜底：把路径丢进剪贴板并提示。"""
        try:
            self.page.run_task(self.page.set_clipboard, path)
        except Exception:
            pass
        self.log(f"打不开资源管理器，路径已复制：{path}", "warn", EXPLORE_ERROR)
        self.toast("无法调起资源管理器，路径已复制：" + chr(10) + path,
                   ft.Icons.CONTENT_COPY_ROUNDED, T.WARN, log_it=False)

    def _set_immersive(self, on: bool) -> None:
        """整条顶栏 / 底栏按模式重建：隐藏模式下压根不创建那些胶囊，
        比逐个改 visible 可靠（Flet 里 Row 子控件只改属性时容易不重绘）。"""
        self.immersive = on
        try:
            self.title_holder.content = self.titlebar()
        except Exception:
            pass
        try:
            self.status_holder.content = self.statusbar()
        except Exception:
            pass
        try:
            self.main_stack.visible = not on
            self.immersive_spacer.visible = on
        except Exception:
            pass
        try:
            self.page.update()
        except Exception:
            pass

    def exit_immersive(self):
        """有弹窗/子页面要出现时，先把「只看背景」模式关掉。"""
        if not getattr(self, "immersive", False):
            return
        self._set_immersive(False)

    def toggle_immersive(self, e=None):
        self._set_immersive(not getattr(self, "immersive", False))

    @staticmethod
    def _pill_hover(e):
        hot = str(e.data).lower() == "true"
        try:
            e.control.bgcolor = T.CARD_HOT if hot else T.CARD_BG
            e.control.update()
        except Exception:
            pass

    def log_path(self) -> Path:
        return log_file()

    def log(self, message: str, level: str = "info", detail: str = "") -> None:
        """统一出口：错误 / 警告 / 重要事件都记下来，底栏状态胶囊点开就能看。

        level="debug" 的进度类消息（载入壁纸、缩略图、定位引擎）直接丢弃：
        日志窗和 vent.log 只留有意义的东西。
        """
        if level == "debug":
            return
        try:
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            self.logs.append({"t": now[11:], "level": level,
                              "msg": str(message)[:4000],
                              "detail": (detail or "")[:12000]})
            if len(self.logs) > 400:
                del self.logs[:-400]
            if level == "error":
                self.error_count += 1
            with open(self.log_path(), "a", encoding="utf-8") as fh:
                fh.write(f"[{now}] {level.upper():5s} {message}" + chr(10))
                if detail:
                    fh.write(str(detail).rstrip() + chr(10))
        except Exception:
            pass
        self._refresh_status_badge()

    @staticmethod
    def _text_width(value: str, size: float) -> int:
        """粗略估算文字宽度（中文按 1em、西文按 0.56em），只用来定胶囊宽度。"""
        w = 0.0
        for ch in str(value or ""):
            w += size * (1.03 if ord(ch) > 0x2E80 else 0.58)
        return int(round(w))

    def _sync_status_pill(self) -> None:
        """状态胶囊最宽 200，超出就是省略号（宽度按当前文字算，短就短）。"""
        pill = getattr(self, "status_pill", None)
        text = getattr(self, "status_text", None)
        if pill is None or text is None:
            return
        avail = 250 - 26 - 7 - 8                # 左右内边距 + 圆点 + 间距
        # 估宽只是给胶囊定宽用的，多留 6px 余量，别把「就绪」这种短词也截掉
        tw = max(18, min(avail, self._text_width(text.value, S_SMALL) + 6))
        text.width = int(tw)
        pill.width = int(min(250, 26 + 7 + 8 + tw))
        try:
            text.update()
            pill.update()
        except Exception:
            pass

    def _refresh_status_badge(self) -> None:
        """有错误时把状态灯的绿点换成红点。"""
        dot = getattr(self, "status_dot", None)
        if dot is not None:
            try:
                want = T.DANGER if self.error_count > 0 else T.OK
                if dot.bgcolor != want:
                    dot.bgcolor = want
                    dot.update()
            except Exception:
                pass
        self._sync_status_pill()

    def _install_error_hooks(self) -> None:
        """主线程 / 后台线程里没被接住的异常，也写进日志而不是只打控制台。"""
        def on_uncaught(exc_type, exc, tb):
            self.log(f"未捕获异常：{exc}", "error",
                     "".join(traceback.format_exception(exc_type, exc, tb)))

        def on_thread(args):
            self.log(f"后台线程异常：{args.exc_value}", "error",
                     "".join(traceback.format_exception(
                         args.exc_type, args.exc_value, args.exc_traceback)))

        try:
            sys.excepthook = on_uncaught
            threading.excepthook = on_thread
        except Exception:
            pass

    def open_log(self, e=None):
        self.show_dialog(self.log_dialog())

    def log_row(self, entry: dict) -> ft.Control:
        """一条日志 = 一行可展开的条目，点开看完整错误（traceback）。"""
        level = entry["level"]
        color = {"error": T.DANGER, "warn": T.WARN,
                 "info": T.DIM, "debug": T.FAINT}.get(level, T.DIM)
        has_detail = bool(entry["detail"])
        body = ft.Text(entry["msg"], size=S_SMALL, color=T.TEXT, max_lines=2,
                       overflow=ft.TextOverflow.ELLIPSIS, no_wrap=False,
                       expand=True, selectable=True)
        detail_box = ft.Container(
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            border_radius=ft.BorderRadius.all(8),
            bgcolor=a(0.10, "#000000"),
            border=ft.Border.all(1, T.CARD_BORDER),
            content=ft.Text(entry["detail"].strip(), size=10.5, color=T.FAINT,
                            no_wrap=False, selectable=True),
        )
        detail = ft.Container(visible=False,
                              padding=ft.Padding.only(left=74, top=6),
                              content=detail_box)
        chevron = ft.Icon(ft.Icons.EXPAND_MORE_ROUNDED, size=16,
                          color=a(0.45) if has_detail else ft.Colors.TRANSPARENT)
        # 顺序：色点 → 时间 → 内容 → 展开箭头。
        # 色点和时间都放进「首行同高」的盒子里居中，正文永远贴顶，多行时左边两列不会跟着漂
        line_h = S_SMALL + 7
        dot = ft.Container(
            width=line_h, height=line_h, alignment=ft.Alignment.CENTER,
            content=ft.Container(width=6, height=6,
                                 border_radius=ft.BorderRadius.all(3), bgcolor=color),
        )
        time_col = ft.Container(
            width=52, height=line_h, alignment=ft.Alignment.CENTER_LEFT,
            content=txt(entry["t"], 11, T.FAINT),
        )
        chevron_box = ft.Container(height=line_h, alignment=ft.Alignment.CENTER,
                                   content=chevron)
        row = ft.Row(
            [dot, time_col, body, chevron_box],
            spacing=8, vertical_alignment=ft.CrossAxisAlignment.START, tight=True,
        )

        def toggle(e):
            if not has_detail:
                return
            detail.visible = not detail.visible
            body.max_lines = None if detail.visible else 2
            chevron.icon = (ft.Icons.EXPAND_LESS_ROUNDED if detail.visible
                            else ft.Icons.EXPAND_MORE_ROUNDED)
            self.page.update()

        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=10, vertical=7),
            border_radius=ft.BorderRadius.all(9),
            bgcolor=a(0.12, T.DANGER) if level == "error" else None,
            on_click=toggle if has_detail else None,
            tooltip="点击展开详情" if has_detail else None,
            content=ft.Column([row, detail], spacing=2, tight=True),
        )

    def log_dialog(self) -> ft.Control:
        # debug 级（载入壁纸 / 缩略图 / 定位引擎）在 log() 里就被丢掉了，这里只剩有意义的记录
        shown = [e for e in self.logs if e["level"] != "debug"]
        rows = [self.log_row(e) for e in reversed(shown[-200:])]
        if not rows:
            rows = [ft.Container(
                padding=ft.Padding.symmetric(vertical=26),
                alignment=ft.Alignment.CENTER,
                content=txt("还没有错误或重要事件", S_SMALL, T.FAINT))]
        errors = sum(1 for e in self.logs if e["level"] == "error")
        warns = sum(1 for e in self.logs if e["level"] == "warn")

        def clear_all(e):
            self.clear_logs()
            self.show_dialog(self.log_dialog())
            self.toast("日志已清空", ft.Icons.DELETE_OUTLINE_ROUNDED, T.OK)

        def open_file(e):
            p = self.log_path()
            if not p.is_file():
                self.toast("还没有日志文件", ft.Icons.INFO_ROUNDED, T.WARN)
                return
            if not open_in_explorer(str(p)):
                self.copy_path(str(p))

        head = [txt("运行日志", S_TITLE, T.TEXT, ft.FontWeight.W_700)]
        if errors:
            head.append(th.pill(f"{errors} 个错误", T.DANGER))
        elif warns:
            head.append(th.pill(f"{warns} 个警告", T.WARN))
        head += [
            ft.Container(expand=True),
            th.icon_button(ft.Icons.CLOSE_ROUNDED, lambda e: self.close_dialog(),
                           tooltip="关闭", size=18, box=34),
        ]
        card = ft.Container(
            width=700,
            height=min(556, WINDOW_H - 130),
            padding=ft.Padding.only(left=18, right=18, top=15, bottom=14),
            border_radius=ft.BorderRadius.all(18),
            bgcolor=T.PANEL,
            border=ft.Border.all(1, T.PANEL_BORDER),
            shadow=ft.BoxShadow(blur_radius=40, spread_radius=-4,
                                color=a(0.6, "#000000"), offset=ft.Offset(0, 16)),
            content=ft.Column(
                [
                    ft.Row(head, spacing=9,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    txt("错误和重要事件都记在这里，点一行可以展开详情；完整记录也写在 vent.log 里",
                        S_SMALL, T.FAINT),
                    ft.Container(height=6),
                    ft.Container(
                        expand=True,
                        border_radius=ft.BorderRadius.all(12),
                        bgcolor=a(0.10, "#000000"),
                        border=ft.Border.all(1, T.CARD_BORDER),
                        padding=ft.Padding.symmetric(horizontal=6, vertical=6),
                        content=ft.ListView(controls=rows, spacing=2, expand=True,
                                            auto_scroll=False, padding=0),
                    ),
                    ft.Container(height=6),
                    ft.Row(
                        [
                            th.text_button("打开日志文件", open_file,
                                           icon=ft.Icons.DESCRIPTION_ROUNDED, height=34),
                            ft.Container(expand=True),
                            th.text_button("清空", clear_all,
                                           icon=ft.Icons.DELETE_OUTLINE_ROUNDED, height=34),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=3,
                tight=True,
            ),
        )
        # 不加蒙版；透明层只负责挡住下层点击，点外面不关
        return ft.Container(
            expand=True,
            bgcolor=ft.Colors.TRANSPARENT,
            on_click=lambda e: None,
            alignment=ft.Alignment.CENTER,
            content=card,
        )

    def set_status(self, text: str, count: str | None = None, level: str = "debug"):
        # 状态变化进日志（debug 级，默认不显示）；纯数字变化的进度只记第一条
        shape = re.sub(r"\d+", "#", text)
        if shape != self._last_status_shape:
            self._last_status_shape = shape
            self.log(text, level)
        self._last_status = text
        self.status_text.value = text
        if count is not None:
            self.count_text.value = count
        try:
            self.status_text.update()
            self.count_text.update()
        except Exception:
            pass
        self._sync_status_pill()

    def show_dialog(self, control: ft.Control):
        self.exit_immersive()
        self.dialog_host.controls = [control]
        self.page.update()

    def close_dialog(self):
        if self.dialog_host.controls:
            self.dialog_host.controls = []
            try:
                self.page.update()
            except Exception:
                pass

    def _set_native_title(self, name: str) -> None:
        """把原生窗口标题改成 name：Flet 只认启动时的默认标题（"Flet"），
        任务栏悬停会露出来，所以启动后自己 SetWindowTextW 一次。"""
        try:
            import ctypes
            from ctypes import wintypes

            k32 = ctypes.windll.kernel32
            u32 = ctypes.windll.user32

            class PE32(ctypes.Structure):
                _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                            ("th32ProcessID", wintypes.DWORD),
                            ("th32DefaultHeapID", ctypes.c_void_p),
                            ("th32ModuleID", wintypes.DWORD),
                            ("cntThreads", wintypes.DWORD),
                            ("th32ParentProcessID", wintypes.DWORD),
                            ("pcPriClassBase", ctypes.c_long),
                            ("dwFlags", wintypes.DWORD),
                            ("szExeFile", ctypes.c_wchar * 260)]

            me = k32.GetCurrentProcessId()
            snap = k32.CreateToolhelp32Snapshot(0x2, 0)
            pe = PE32()
            pe.dwSize = ctypes.sizeof(PE32)
            kids = set()
            if k32.Process32FirstW(snap, ctypes.byref(pe)):
                while True:
                    if pe.th32ParentProcessID == me and "flet" in (pe.szExeFile or "").lower():
                        kids.add(pe.th32ProcessID)
                    if not k32.Process32NextW(snap, ctypes.byref(pe)):
                        break
            k32.CloseHandle(snap)
            if not kids:
                return
            done = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def cb(hwnd, lp):
                pid = wintypes.DWORD()
                u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in kids and u32.IsWindowVisible(hwnd):
                    u32.SetWindowTextW(hwnd, name)
                    done.append(hwnd)
                    return False
                return True

            u32.EnumWindows(cb, 0)
        except Exception:
            pass

    def titlebar_refresh(self):
        # 重新构建标题栏以应用新的强调色
        try:
            self.title_holder.content = self.titlebar()
            self.page.update()
        except Exception:
            pass

    def rebuild_ui(self):
        """配色变化后重建标题栏 / 网格 / 状态栏。"""
        try:
            self.title_holder.content = self.titlebar()
            if getattr(self, "status_holder", None) is not None:
                self.status_holder.content = self.statusbar()
            self.fill_grid()
            self.page.update()
        except Exception:
            pass

    @staticmethod
    def _short_path(p: str, keep: int = 30) -> str:
        p = str(p or "")
        return p if len(p) <= keep + 10 else "…" + p[-keep:]

    def sample_bg(self) -> list[list[float]]:
        """把背景按 3×3 网格采样成亮度表（0~1），用来实时算控件需要的底色浓度。"""
        cfg = self.cfg
        mode = cfg.get("bg_mode")
        if mode == "solid":
            v = 0.84 if is_light_color(cfg.get("bg_color", "")) else 0.09
            return [[v, v, v] for _ in range(3)]
        if mode == "video":
            # 视频没法预判，按「中间偏亮」估算，宁可比实际更保守
            return [[0.54, 0.54, 0.54] for _ in range(3)]
        path = cfg.get("bg_image") or ""
        if not path or not Path(path).is_file():
            return [[0.5, 0.5, 0.5] for _ in range(3)]
        try:
            from PIL import Image

            with Image.open(self._bg_image_src(path)) as im:
                gray = im.convert("L")
                w, h = gray.size
                # COVER 时窗口只看到中间那块，先按 1:1.36 居中裁一遍更接近实际
                target = WINDOW_W / max(1, WINDOW_H)
                if w / h > target:
                    cw = int(h * target)
                    gray = gray.crop(((w - cw) // 2, 0, (w + cw) // 2, h))
                else:
                    ch = int(w / target)
                    gray = gray.crop((0, (h - ch) // 2, w, (h + ch) // 2))
                small = gray.resize((12, 12))
                raw = small.tobytes()
        except Exception:
            return [[0.5, 0.5, 0.5] for _ in range(3)]
        grid = []
        for y in range(3):
            row = []
            for x in range(3):
                vals = [raw[(y * 4 + dy) * 12 + (x * 4 + dx)]
                        for dy in range(4) for dx in range(4)]
                row.append(sum(vals) / (len(vals) * 255.0))
            grid.append(row)
        return grid

    def ui_is_light(self) -> bool:
        """整套配色：背景最亮处都够亮 → 用深色文字 + 白色玻璃，否则白字 + 深色玻璃。"""
        cfg = self.cfg
        if cfg.get("bg_mode") == "solid":
            return is_light_color(cfg.get("bg_color", ""))
        grid = getattr(self, "_luma_grid", None)
        if not grid:
            return False
        return max(max(r) for r in grid) > 0.55

    @staticmethod
    def _dark_plate_alpha(luma: float) -> float:
        """白字压在亮度 luma 上，需要多浓的深色底才能到 4.5:1。"""
        # 白字 #EAF1FF 相对亮度≈0.82，要 4.5:1 就得 L' <= (0.87/4.5) - 0.05 ≈ 0.143
        need = 1.0 - 0.143 / max(luma, 0.02)
        return round(min(0.93, max(0.55, need)), 3)

    def refresh_palette(self) -> bool:
        """采样背景 → 切配色 → 按实际亮度调整玻璃浓度。返回是否浅色。"""
        self._luma_grid = self.sample_bg()
        light = self.ui_is_light()
        apply_palette(light)
        if not light:
            need = self._dark_plate_alpha(max(max(r) for r in self._luma_grid))
            T.CARD_BG = a(need, "#070A12")
            T.CARD_HOT = a(min(0.97, need + 0.16), "#0A101C")
            T.PANEL = a(min(0.98, need + 0.22), "#080D15")
            T.CHROME = a(need, "#04070C")
            T.OVERLAY = a(min(0.98, need + 0.20), "#05080E")
        try:
            self.page.bgcolor = "#EEF2F8" if light else T.BG
        except Exception:
            pass
        return light

    def build_bg(self):
        cfg = self.cfg
        mode = cfg.get("bg_mode", "solid")
        layers: list[ft.Control] = []
        accent = cfg.get("accent", T.ACCENT)

        base = ft.Container(
            expand=True,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                colors=[cfg.get("bg_color", "#080B12"),
                        _darken(cfg.get("bg_color", "#080B12"),
                                0.12 if self.ui_is_light() else 0.45)],
            ),
            ignore_interactions=True,
        )
        layers.append(base)

        op = float(cfg.get("bg_opacity", 0.72) or 0.0)
        op = min(1.0, max(0.0, op))
        self.bg_opacity = op

        if mode == "image" and cfg.get("bg_image") and Path(cfg["bg_image"]).is_file():
            layers.append(
                ft.Container(
                    expand=True,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    content=ft.Image(src=self._bg_image_src(cfg["bg_image"]), expand=True,
                                     fit=ft.BoxFit.COVER,
                                     filter_quality=ft.FilterQuality.LOW, gapless_playback=True),
                )
            )
        elif mode == "video" and cfg.get("bg_video") and Path(cfg["bg_video"]).is_file():
            # 与 login.py 的视频背景写法保持一致：file:// URI + fill_color + COVER
            try:
                player = Video(
                    playlist=[VideoMedia(resource=file_uri(cfg["bg_video"]))],
                    autoplay=True,
                    muted=True,
                    volume=0,
                    controls=None,
                    playlist_mode=PlaylistMode.LOOP,
                    fill_color="#04060F",
                    fit=ft.BoxFit.COVER,
                    filter_quality=ft.FilterQuality.MEDIUM,
                    expand=True,
                    on_error=self._on_bg_video_error,
                )
                self.bg_video = player
                layers.append(
                    ft.Container(
                        expand=True,
                        bgcolor="#04060F",
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                        content=player,
                    )
                )
            except Exception:
                layers.append(ft.Container(expand=True, bgcolor=cfg.get("bg_color", "#080B12")))

        if mode == "solid":
            layers.append(
                ft.Container(
                    expand=True,
                    gradient=ft.RadialGradient(
                        center=ft.Alignment(-0.7, -0.8),
                        radius=1.1,
                        colors=[a(0.13 if self.ui_is_light() else 0.22, accent), a(0.0, accent)],
                    ),
                    ignore_interactions=True,
                )
            )

        # 透明度：用底色叠加实现，避免给平台纹理加 opacity 图层（会让视频消失）
        self.veil_layer = None
        self.scrim_layer = None
        self.edge_layer = None
        if mode in ("image", "video"):
            bgc = cfg.get("bg_color", "#080B12")
            if is_light_color(bgc):
                bgc = "#04070C"   # 媒体背景用深色薄纱，避免把画面洗白
            veil = ft.Container(
                expand=True,
                bgcolor=a(round(max(0.0, 1.0 - op), 3), bgc),
                ignore_interactions=True,
            )
            self.veil_layer = veil
            layers.append(veil)

            # 背景越清晰，压暗层越轻（0.55 → 图像基本原色；1 附近仍够白字可读）
            k = 0.55 + 0.30 * (1.0 - op)
            self.scrim_light = self.ui_is_light()
            scrim_col = "#FFFFFF" if self.scrim_light else "#02040A"
            if mode == "video":
                # 视频背景保持原始亮度：整幅横向压暗层会明显变灰，这里不加。
                # 视频又没法预判亮度，所以只在顶/底两条窄带做渐隐，保证白字可读。
                self.scrim_layer = None
            else:
                l_alpha, r_alpha = ((0.34, 0.12) if self.scrim_light else (0.66, 0.36))
                scrim = ft.Container(
                    expand=True,
                    gradient=ft.LinearGradient(
                        begin=ft.Alignment.CENTER_LEFT,
                        end=ft.Alignment.CENTER_RIGHT,
                        colors=[a(min(0.92, l_alpha * k), scrim_col),
                                a(min(0.92, r_alpha * k), scrim_col)],
                    ),
                    ignore_interactions=True,
                )
                self.scrim_layer = scrim
                layers.append(scrim)

            # 顶栏 / 底栏没有独立底色，但文字直接压在背景上：
            # 用一层上下淡出的薄纱保证白字可读（渐变，不是色块）
            if self.scrim_light:
                top_alpha, bot_alpha = 0.30, 0.20
            elif mode == "video":
                # 只保住顶/底两条窄带的白字可读，画面中间一点不动
                top_alpha, bot_alpha = 0.50, 0.34
            else:
                top_alpha, bot_alpha = 0.62, 0.46
            edge = ft.Container(
                expand=True,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.TOP_CENTER,
                    end=ft.Alignment.BOTTOM_CENTER,
                    colors=[a(round(top_alpha * k, 3), scrim_col),
                            a(0.0, scrim_col),
                            a(0.0, scrim_col),
                            a(round(bot_alpha * k, 3), scrim_col)],
                    stops=[0.0, 0.12, 0.90, 1.0] if mode == "video"
                    else [0.0, 0.16, 0.86, 1.0],
                ),
                ignore_interactions=True,
            )
            self.edge_layer = edge
            layers.append(edge)
        elif mode == "solid":
            layers.append(
                ft.Container(
                    expand=True,
                    gradient=ft.LinearGradient(
                        begin=ft.Alignment.TOP_CENTER,
                        end=ft.Alignment.BOTTOM_CENTER,
                        colors=[a(0.0), a(0.05 if self.ui_is_light() else 0.18, "#000000")],
                    ),
                    ignore_interactions=True,
                )
            )

        self.bg_layer.controls = layers
        try:
            self.page.update()
        except Exception:
            pass
        if mode == "video":
            self.page.run_task(self._kick_bg_video)

    def _bg_image_src(self, path: str) -> str:
        """背景图只做等比缩放缓存（不模糊）：玻璃质感只属于控件，背景保持原样清晰。"""
        try:
            src = Path(path)
            if not src.is_file():
                return path
            st = src.stat()
            key = hashlib.sha1(f"{src}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()[:16]
            dest = ws.THUMB_DIR / f"bgd_{key}.jpg"
            if not dest.is_file():
                ws.THUMB_DIR.mkdir(parents=True, exist_ok=True)
                from PIL import Image

                im = Image.open(src).convert("RGB")
                im.thumbnail((1920, 1920), Image.LANCZOS)
                im.save(dest, "JPEG", quality=90)
            return str(dest)
        except Exception:
            return path

    async def _kick_bg_video(self):
        await asyncio.sleep(0.6)
        vid = getattr(self, "bg_video", None)
        if vid is None:
            return
        try:
            await vid.play()
        except Exception:
            pass

    def _on_bg_video_error(self, e):
        """背景视频放不出来时回退到图片 / 纯色，避免只剩黑屏。"""
        self.bg_video_error = str(getattr(e, "data", "") or "")
        cfg = self.cfg
        if cfg.get("bg_image") and Path(cfg["bg_image"]).is_file():
            cfg["bg_mode"] = "image"
        else:
            cfg["bg_mode"] = "solid"
        save_cfg(cfg)
        try:
            self.build_bg()
        except Exception:
            pass
        try:
            self.toast("背景视频无法播放，已回退背景", ft.Icons.ERROR_OUTLINE_ROUNDED, T.WARN)
        except Exception:
            pass

    def toast(self, message: str, icon=ft.Icons.CHECK_CIRCLE_ROUNDED, color: str = T.OK,
              log_it: bool = True):
        box = ft.Container(
            content=ft.Row([ft.Icon(icon, size=17, color=color), txt(message, S_SMALL, T.TEXT)],
                           tight=True, spacing=9),
            padding=ft.Padding.symmetric(horizontal=18, vertical=12),
            border_radius=ft.BorderRadius.all(14),
            bgcolor=T.PANEL,
            border=ft.Border.all(1, T.PANEL_BORDER),
            shadow=ft.BoxShadow(blur_radius=26, color=a(0.55, "#000000"), offset=ft.Offset(0, 8)),
            opacity=0.0,
            offset=ft.Offset(0, 12),
            animate_opacity=ft.Animation(170, ft.AnimationCurve.EASE_OUT),
            animate_offset=ft.Animation(210, ft.AnimationCurve.EASE_OUT),
        )
        wrap = ft.Container(
            left=0, right=0, bottom=52,
            alignment=ft.Alignment.CENTER,
            content=box,
        )
        # 警告 / 错误也进运行日志（原来的提示照旧弹）
        if not log_it:
            pass
        elif color == T.DANGER:
            self.log(message, "error")
        elif color == T.WARN:
            self.log(message, "warn")
        self.toast_host.controls.append(wrap)
        self.page.update()

        async def run():
            await asyncio.sleep(0.02)
            box.opacity = 1.0
            box.offset = ft.Offset(0, 0)
            self.page.update()
            await asyncio.sleep(2.2)
            box.opacity = 0.0
            box.offset = ft.Offset(0, 10)
            self.page.update()
            await asyncio.sleep(0.3)
            if wrap in self.toast_host.controls:
                self.toast_host.controls.remove(wrap)
            self.page.update()

        self.page.run_task(run)

    def open_overlay(self, control: ft.Control):
        self.exit_immersive()
        self.overlay.controls = [control]
        self.overlay.visible = True
        self.page.update()

    def close_overlay(self):
        self.detail_video = None
        self.overlay.controls = []
        self.overlay.visible = False
        self.page.update()

    async def boot(self):
        await asyncio.sleep(0.3)
        if paths.client_home():
            self.log("用户目录不可写，Flet 客户端的解压缓存已改到数据目录", "warn",
                     paths.client_home())
        try:
            await self.page.window.center()
        except Exception:
            pass
        self.body.content = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [ft.ProgressRing(width=34, height=34, stroke_width=3, color=T.ACCENT),
                 txt("正在扫描壁纸库…", S_BODY, T.DIM)],
                spacing=14,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )
        self.page.update()
        self._set_native_title(APP_NAME)
        rid = process_integrity_rid()
        if 0 < rid < 0x2000:
            self.low_privilege = True
            self.log("当前进程是低权限（Low IL）运行：Windows 会挡住截屏接口和 shell 启动，"
                     "录制会得到黑屏、资源管理器也打不开。想正常录制请自己双击启动 Vent Studio。",
                     "warn", "integrity RID=0x%x" % rid)
        info = ffmpeg_info()
        if info:
            note = "" if info.get("x264") else "（不含 libx264，转码可能失败）"
            self.log(f"FFmpeg {info['version']} · {info['source']}{note}", "info", info["path"])
        elif _FFMPEG_REJECTS:
            source, path, why = _FFMPEG_REJECTS[0]
            self.log(f"系统里的 ffmpeg 不可用，已忽略：{path}", "warn", f"{source} · {why}")
        await self.reload_library()
        self.auto_pick_bg()
        self._clean_mux_cache()

    def clear_logs(self) -> None:
        """清空日志：错误计数归零（状态灯变绿），状态文字也回到「就绪」。"""
        self.logs.clear()
        self.error_count = 0
        self._refresh_status_badge()
        try:
            self.log_path().unlink(missing_ok=True)
        except Exception:
            pass
        if self.wps:
            self.set_status("就绪", f"{len(self.wps)} 个壁纸")
        else:
            self.set_status("就绪")