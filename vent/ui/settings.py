# -*- coding: utf-8 -*-
"""设置面板：外观、组件、导出目录。"""
from __future__ import annotations

from ..compat import *  # noqa: F401,F403


class SettingsMixin:
    def open_settings(self):
        self.open_overlay(self.settings_view())

    def settings_view(self) -> ft.Control:
        cfg = self.cfg
        mode = cfg.get("bg_mode", "solid")

        modes = ft.Row(
            [self.mode_tile("solid", "纯色", ft.Icons.FORMAT_PAINT_ROUNDED),
             self.mode_tile("image", "图片", ft.Icons.IMAGE_ROUNDED),
             self.mode_tile("video", "视频", ft.Icons.MOVIE_ROUNDED)],
            spacing=10,
        )

        extra: list[ft.Control] = []
        if mode == "solid":
            extra.append(ft.Column(
                [
                    ft.Row([txt("深色模板", S_TINY, T.FAINT),
                            ft.Container(expand=True),
                            txt("浅色模板会自动切换深色文字", S_TINY, T.FAINT)],
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([self.bg_swatch(c) for c in
                            ("#080B12", "#101826", "#1B2431", "#2A2036", "#0F2430", "#241018")],
                           spacing=10, wrap=True, run_spacing=10),
                    ft.Row([self.bg_swatch(c) for c in
                            ("#EFF3F9", "#E4EBF5", "#F6F1E9", "#E9F3EE", "#F2ECF7", "#E7F0F7")],
                           spacing=10, wrap=True, run_spacing=10),
                ],
                spacing=8,
                tight=True,
            ))
        elif mode == "image":
            extra.append(self.file_row(
                "背景图片", cfg.get("bg_image") or "未选择",
                lambda e: self.page.run_task(self.pick_image)))
        else:
            extra.append(self.file_row(
                "背景视频", cfg.get("bg_video") or "未选择",
                lambda e: self.page.run_task(self.pick_video)))

        accents = ft.Row(
            [self.accent_swatch(c) for c in
             ("#8FB6FF", "#C29BFF", "#7BE0C0", "#FFB86B", "#FF8FA3", "#9EE7FF")]
            + [ft.Container(expand=True)],
            spacing=10)

        save_row = self.export_row()
        play_row = self.toggle_row(
            "转换完成立即播放",
            "录制 / 转换结束后用系统默认播放器直接打开产物",
            bool(cfg.get("play_when_done", True)),
            self.set_play_when_done)

        body = ft.Column(
            [
                ft.Row([txt("外观与背景", 20, T.TEXT, ft.FontWeight.W_700), ft.Container(expand=True),
                        th.icon_button(ft.Icons.CLOSE_ROUNDED, lambda e: self.close_overlay(),
                                       tooltip="关闭", size=19, box=36)],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.section("背景模式"), self.card_box(modes), *extra,
                *([self.section("背景浓度"),
                   self.opacity_control()] if mode != "solid" else []),
                self.section("强调色"), self.card_box(accents),
                self.section("导出"), play_row,
                self.section("组件"), self.engine_row(), self.ffmpeg_row(),
                self.section("文件"), save_row,
                ft.Container(
                    padding=ft.Padding.only(top=6, bottom=2),
                    alignment=ft.Alignment.CENTER,
                    content=txt(f"{APP_NAME} · v{APP_VERSION}", S_TINY, T.FAINT),
                ),
            ],
            spacing=12,
            tight=True,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        sheet = ft.Container(
            width=404,
            padding=ft.Padding.only(left=20, right=20, top=16, bottom=16),
            bgcolor=T.PANEL,
            border=ft.Border.only(left=ft.BorderSide(1, T.PANEL_BORDER)),
            content=body,
        )
        # 右侧抽屉：背景仍然可见，调参数能立刻看到效果
        return ft.Row(
            [
                ft.Container(expand=True, on_click=lambda e: self.close_overlay()),
                sheet,
            ],
            spacing=0,
            expand=True,
        )

    def opacity_control(self) -> ft.Control:
        value = float(self.cfg.get("bg_opacity", 0.72) or 0.0)
        value = min(1.0, max(0.0, value))
        label = txt(f"{value:.2f}", S_SMALL, T.DIM, ft.FontWeight.W_600)

        def on_change(e):
            label.value = f"{float(e.control.value):.2f}"
            try:
                label.update()
            except Exception:
                pass

        def on_end(e):
            self.set_bg_opacity(float(e.control.value))

        return self.card_box(ft.Column(
            [
                ft.Row([txt("0 = 背景完全透明，1 = 背景最清晰", S_TINY, T.FAINT),
                        ft.Container(expand=True), label],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Slider(
                    min=0.0, max=1.0, divisions=20, value=value,
                    active_color=T.ACCENT, inactive_color=a(0.12),
                    on_change=on_change, on_change_end=on_end,
                    padding=ft.Padding.symmetric(horizontal=4),
                ),
            ],
            spacing=2,
            tight=True,
        ))

    def set_bg_opacity(self, value: float):
        """value = 背景不透明度：1 表示背景最清晰、0 表示只剩底色。"""
        value = min(1.0, max(0.0, value))
        self.cfg["bg_opacity"] = round(value, 3)
        save_cfg(self.cfg)
        veil = getattr(self, "veil_layer", None)
        if veil is None:
            self.build_bg()
            return
        # 视频模式没有横向压暗层（scrim_layer=None），此时只更新薄纱和顶/底渐隐
        scrim = getattr(self, "scrim_layer", None)
        bgc = self.cfg.get("bg_color", "#080B12")
        if is_light_color(bgc):
            bgc = "#04070C"
        veil.bgcolor = a(round(1.0 - value, 3), bgc)
        k = 0.55 + 0.30 * (1.0 - value)
        light_ui = getattr(self, "scrim_light", False)
        scrim_col = "#FFFFFF" if light_ui else "#02040A"
        if scrim is not None:
            l_alpha, r_alpha = ((0.34, 0.12) if light_ui else (0.66, 0.36))
            scrim.gradient = ft.LinearGradient(
                begin=ft.Alignment.CENTER_LEFT,
                end=ft.Alignment.CENTER_RIGHT,
                colors=[a(min(0.92, l_alpha * k), scrim_col),
                        a(min(0.92, r_alpha * k), scrim_col)],
            )
        edge = getattr(self, "edge_layer", None)
        if edge is not None:
            if light_ui:
                top_alpha, bot_alpha = 0.30, 0.20
            elif self.cfg.get("bg_mode") == "video":
                top_alpha, bot_alpha = 0.50, 0.34
            else:
                top_alpha, bot_alpha = 0.62, 0.46
            edge.gradient = ft.LinearGradient(
                begin=ft.Alignment.TOP_CENTER,
                end=ft.Alignment.BOTTOM_CENTER,
                colors=[a(round(top_alpha * k, 3), scrim_col), a(0.0, scrim_col),
                        a(0.0, scrim_col), a(round(bot_alpha * k, 3), scrim_col)],
                stops=[0.0, 0.12, 0.90, 1.0] if self.cfg.get("bg_mode") == "video"
                else [0.0, 0.16, 0.86, 1.0],
            )
        try:
            veil.update()
            if scrim is not None:
                scrim.update()
            if edge is not None:
                edge.update()
        except Exception:
            pass

    def section(self, label: str) -> ft.Control:
        return txt(label.upper(), S_TINY, T.FAINT, ft.FontWeight.W_700)

    def card_box(self, content: ft.Control) -> ft.Container:
        """设置页统一容器：左右 12 内边距 + 同样的圆角/描边，所有行对齐到同一条线。

        注意别叫 card()：那是壁纸卡片构建器，重名会把它覆盖掉。
        """
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=ft.BorderRadius.all(11),
            bgcolor=T.CARD_BG,
            border=ft.Border.all(1, T.CARD_BORDER),
            content=content,
        )

    def mode_tile(self, key: str, label: str, icon) -> ft.Container:
        active = self.cfg.get("bg_mode") == key
        return ft.Container(
            content=ft.Column(
                [ft.Icon(icon, size=22, color=T.TEXT if active else T.DIM),
                 txt(label, S_BODY, T.TEXT if active else T.DIM, ft.FontWeight.W_600)],
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
            height=84,
            expand=True,
            alignment=ft.Alignment.CENTER,
            border_radius=ft.BorderRadius.all(14),
            bgcolor=a(0.20, T.ACCENT) if active else T.CARD_BG,
            border=ft.Border.all(1, a(0.45, T.ACCENT) if active else T.CARD_BORDER),
            on_click=lambda e: self.set_bg_mode(key),
            animate=ft.Animation(130, ft.AnimationCurve.EASE_OUT),
        )

    def file_row(self, label: str, value: str, on_click) -> ft.Control:
        name = Path(value).name if value else "未选择"
        return self.card_box(ft.Row(
            [
                ft.Column(
                    [
                        txt(label, S_TINY, T.FAINT),
                        txt(name, S_SMALL, T.DIM, expand=True, ellipsis=True,
                            selectable=False),
                    ],
                    spacing=3,
                    tight=True,
                    expand=True,
                ),
                th.text_button("更改", on_click, icon=ft.Icons.FOLDER_ROUNDED, height=34),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ))

    def toggle_row(self, title: str, desc: str, value: bool, on_change) -> ft.Control:
        """设置里的一行开关：左边标题 + 说明，右边 Switch。"""
        sw = ft.Switch(value=bool(value), active_color=T.ACCENT,
                       inactive_thumb_color=T.DIM, on_change=on_change)
        return self.card_box(ft.Row(
            [ft.Column([txt(title, S_SMALL, T.TEXT),
                        txt(desc, S_TINY, T.FAINT, max_lines=2)],
                       spacing=2, tight=True, expand=True),
             sw],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ))

    def set_play_when_done(self, e):
        self.cfg["play_when_done"] = bool(e.control.value)
        save_cfg(self.cfg)
        self.log("导出后自动播放：" + ("开" if self.cfg["play_when_done"] else "关"), "info")

    def export_row(self) -> ft.Control:
        """设置面板里的「默认保存位置」行，路径文字可被 sync_export_ui() 就地刷新。"""
        d = self.export_dir()
        self.export_text = txt(d or "未设置（解包时再选）", S_SMALL,
                               T.DIM if d else T.WARN, expand=True, ellipsis=True,
                               max_lines=1, selectable=False)
        return self.card_box(ft.Row(
            [
                ft.Column(
                    [txt("默认保存位置", S_TINY, T.FAINT), self.export_text],
                    spacing=3,
                    tight=True,
                    expand=True,
                ),
                th.text_button("更改", lambda e: self.page.run_task(self.pick_export_dir),
                               icon=ft.Icons.FOLDER_ROUNDED, height=34),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ))

    def bg_swatch(self, color: str) -> ft.Container:
        active = (self.cfg.get("bg_color") or "").lower() == color.lower()
        return ft.Container(
            width=38, height=38,
            border_radius=ft.BorderRadius.all(11),
            bgcolor=color,
            border=ft.Border.all(2, T.TEXT if active else a(0.15)),
            on_click=lambda e: self.set_bg_color(color),
        )

    def accent_swatch(self, color: str) -> ft.Container:
        active = (self.cfg.get("accent") or "").lower() == color.lower()
        return ft.Container(
            width=34, height=34,
            border_radius=ft.BorderRadius.all(999),
            bgcolor=color,
            border=ft.Border.all(2.5, T.TEXT if active else a(0.15)),
            on_click=lambda e: self.set_accent(color),
        )

    def set_accent(self, color: str):
        self.cfg["accent"] = color
        save_cfg(self.cfg)
        self.titlebar_refresh()
        self.build_bg()
        self.open_settings()

    def set_bg_color(self, color: str):
        self.cfg["bg_color"] = color
        self.cfg["bg_mode"] = "solid"
        save_cfg(self.cfg)
        self.refresh_palette()
        # 先换底色，再重建控件（配色令牌已切换）
        self.build_bg()
        self.rebuild_ui()
        self.open_settings()

    def set_bg_mode(self, mode: str):
        if mode == "image" and not (self.cfg.get("bg_image") and Path(self.cfg["bg_image"]).is_file()):
            self.toast("先选择一张背景图片", ft.Icons.IMAGE_ROUNDED, T.WARN)
            self.page.run_task(self.pick_image)
            return
        if mode == "video" and not (self.cfg.get("bg_video") and Path(self.cfg["bg_video"]).is_file()):
            self.toast("先选择一个背景视频", ft.Icons.MOVIE_ROUNDED, T.WARN)
            self.page.run_task(self.pick_video)
            return
        self.cfg["bg_mode"] = mode
        save_cfg(self.cfg)
        self.refresh_palette()
        self.build_bg()
        self.rebuild_ui()
        self.open_settings()
        label = {"solid": "纯色", "image": "图片", "video": "视频"}[mode]
        self.toast(f"背景已切换为{label}", ft.Icons.WALLPAPER_ROUNDED, T.OK)

    async def pick_image(self):
        try:
            files = await self.picker.pick_files(dialog_title="选择背景图片", allow_multiple=False,
                                                 file_type=ft.FilePickerFileType.IMAGE)
        except Exception:
            files = None
        if files:
            self.cfg["bg_image"] = files[0].path
            self.cfg["bg_mode"] = "image"
            save_cfg(self.cfg)
            self.refresh_palette()
            self.build_bg()
            self.rebuild_ui()
            self.open_settings()

    async def pick_video(self):
        try:
            files = await self.picker.pick_files(dialog_title="选择背景视频", allow_multiple=False,
                                                 file_type=ft.FilePickerFileType.VIDEO)
        except Exception:
            files = None
        if files:
            self.cfg["bg_video"] = files[0].path
            self.cfg["bg_mode"] = "video"
            save_cfg(self.cfg)
            self.refresh_palette()
            self.build_bg()
            self.rebuild_ui()
            self.open_settings()

    async def pick_export_dir(self):
        d = await self.ask_dir()
        if d:
            self.sync_export_ui()
            self.toast(f"默认保存位置已设为 {Path(d).name}", ft.Icons.FOLDER_ROUNDED, T.OK)

    async def pick_engine_dir(self):
        """手动指定 Steam 库 / Wallpaper Engine 目录，然后重新扫描壁纸库。"""
        try:
            d = await self.picker.get_directory_path(
                dialog_title="选择 Steam 库目录，或 Wallpaper Engine 的安装目录",
                initial_directory=str(self.engine_dir or Path.home()))
        except Exception:
            d = None
        if not d:
            return
        self.cfg["steam_library"] = d
        save_cfg(self.cfg)
        self.log("手动指定壁纸库目录", "info", str(d))
        self.toast("已记住这个目录，正在重新扫描", ft.Icons.REFRESH_ROUNDED, T.OK)
        await self.reload_library()

    def engine_row(self) -> ft.Control:
        """设置里的一行：壁纸库在哪、找到多少，右边可以手动换目录。"""
        install = str(self.engine_dir or "")
        manual = str(self.cfg.get("steam_library") or "")
        if self.wps:
            title, color = f"已找到 {len(self.wps)} 个壁纸", T.DIM
        elif install:
            title, color = "已找到引擎，但库里没有壁纸", T.WARN
        else:
            title, color = "未找到 Wallpaper Engine", T.WARN
        if manual:
            detail = "手动指定：" + manual
        elif install:
            detail = install
        else:
            detail = "自动查找（注册表 / 各盘 Steam 库）＋ 可手动指定"
        return self.card_box(ft.Row(
            [
                ft.Column([txt("壁纸库", S_TINY, T.FAINT), txt(title, S_SMALL, color),
                           txt(detail, S_TINY, T.FAINT, max_lines=2, ellipsis=True)],
                          spacing=2, tight=True, expand=True),
                th.text_button("更改", lambda e: self.page.run_task(self.pick_engine_dir),
                               icon=ft.Icons.FOLDER_OPEN_ROUNDED, height=34),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ))

    def ffmpeg_state_text(self) -> tuple[str, str, str]:
        """(状态标题, 次要说明, 颜色) —— 设置行和日志共用。"""
        info = ffmpeg_info()
        if info:
            extra = "" if info.get("x264") else " · 不含 libx264（转码会失败）"
            return (f"可用 · {info['version']}（{info['source']}）{extra}",
                    info["path"], T.DIM if info.get("x264") else T.WARN)
        if _FFMPEG_REJECTS:
            source, path, why = _FFMPEG_REJECTS[0]
            return ("未安装（检测到系统里有，但不可用）",
                    f"已忽略 {path}（{why}）", T.WARN)
        return ("未安装（合成音视频时需要）",
                "点右边下载，或自己把 ffmpeg.exe 放进 data\\bin\\", T.WARN)

    def ffmpeg_row(self) -> ft.Control:
        """设置里的一行：显示 FFmpeg 是否可用（含版本和来源），右边一个下载按钮。"""
        title, detail, color = self.ffmpeg_state_text()
        self._ffmpeg_label = txt(title, S_SMALL, color)
        self._ffmpeg_path = txt(detail, S_TINY, T.FAINT, max_lines=2, ellipsis=True)
        return self.card_box(ft.Row(
            [
                ft.Column([txt("FFmpeg", S_TINY, T.FAINT), self._ffmpeg_label,
                           self._ffmpeg_path],
                          spacing=2, tight=True, expand=True),
                th.text_button("下载" if not find_ffmpeg() else "重新下载",
                               lambda e: self.page.run_task(self.install_ffmpeg),
                               icon=ft.Icons.DOWNLOAD_ROUNDED, height=34),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ))

    def refresh_ffmpeg_row(self) -> None:
        title, detail, color = self.ffmpeg_state_text()
        try:
            self._ffmpeg_label.value = title
            self._ffmpeg_label.color = color
            self._ffmpeg_path.value = detail
            self._ffmpeg_label.update()
            self._ffmpeg_path.update()
        except Exception:
            pass

    def set_engine_dir(self, path: str):
        self.engine_dir = path
        # 不再手工截断：交给 Text 的 ellipsis，胶囊宽度固定，多余的字自动变省略号
        self.engine_text.value = (f"引擎目录  {path}" if path
                                  else "引擎目录  未找到 Wallpaper Engine")
        try:
            self.engine_text.update()
        except Exception:
            pass
        pill = getattr(self, "engine_pill", None)
        if pill is not None:
            try:
                pill.width = 250 if path else 186
                pill.tooltip = (path or "未找到 Wallpaper Engine") + chr(10) + "点击打开引擎目录"
                self.engine_text.width = (250 if path else 186) - 46
                self.engine_text.update()
                pill.update()
            except Exception:
                pass

    async def ask_ffmpeg_download(self) -> bool:
        """问一句要不要下载 ffmpeg（静态构建，约 90 MB）。"""
        done = asyncio.Event()
        choice = {"ok": False}

        def pick(ok: bool):
            choice["ok"] = ok
            done.set()
            self.close_dialog()

        card = ft.Container(
            width=430,
            padding=ft.Padding.only(left=22, right=22, top=20, bottom=18),
            border_radius=ft.BorderRadius.all(18),
            bgcolor=T.PANEL,
            border=ft.Border.all(1, T.PANEL_BORDER),
            shadow=ft.BoxShadow(blur_radius=40, spread_radius=-4, color=a(0.6, "#000000"),
                                offset=ft.Offset(0, 16)),
            content=ft.Column(
                [
                    ft.Row(
                        [ft.Icon(ft.Icons.MOVIE_FILTER_ROUNDED, size=19, color=T.ACCENT),
                         txt("需要 FFmpeg", S_TITLE, T.TEXT, ft.FontWeight.W_700, max_lines=1,
                             expand=True)],
                        spacing=9, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    txt("合并画面与音频要用到 FFmpeg。程序不预置（约 30 MB），"
                        "现在下载一份放到数据目录，只下一次。国内镜像会自动测速，慢了就换官方源。",
                        S_BODY, T.DIM),
                    ft.Row(
                        [
                            ft.Container(expand=True),
                            th.text_button("暂不下载", lambda e: pick(False), height=38),
                            th.text_button("立即下载", lambda e: pick(True),
                                           icon=ft.Icons.DOWNLOAD_ROUNDED,
                                           accent=True, height=38),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=14,
                tight=True,
            ),
        )
        host = ft.Stack(
            [
                ft.Container(expand=True, bgcolor=ft.Colors.TRANSPARENT,
                             on_click=lambda e: None),
                ft.Container(expand=True, alignment=ft.Alignment.CENTER, content=card),
            ],
            expand=True,
        )
        self.show_dialog(host)
        await done.wait()
        return bool(choice["ok"])

    async def install_ffmpeg(self) -> str | None:
        """下载并安装 ffmpeg（带进度），成功后返回 exe 路径。"""
        def worker(state):
            src = {"label": ""}

            def on_source(label: str):
                src["label"] = f"{label} · "

            def note(text: str):
                state["phase"] = text

            def prog(done: int, total: int):
                state["value"] = (done / total * 0.92) if total else 0.35
                got = done / 1048576
                state["phase"] = (f"{src['label']}已下载 {got:.1f} / {total/1048576:.0f} MB"
                                  if total else f"{src['label']}已下载 {got:.1f} MB")
            path = ffsetup.download(prog, note, on_source)
            state["value"] = 1.0
            state["phase"] = "正在解压…"
            return str(path)

        state = await self.run_with_progress(
            "安装 FFmpeg", "正在连接下载源…", worker, "FFmpeg 已就绪")
        if state["error"] or not state["result"]:
            self.log("FFmpeg 下载失败：" + (state["error"] or "未知原因"), "error")
            self.toast("下载失败，可在「设置 → 组件」重试",
                       ft.Icons.ERROR_OUTLINE_ROUNDED, T.DANGER)
            return None
        reset_ffmpeg_cache()
        info = ffmpeg_info()
        exe = info["path"] if info else None
        detail = (f"{info['version']} · {info['source']} · {exe}") if info else (exe or "")
        self.log("FFmpeg 已就绪", "ok", detail)
        self.refresh_ffmpeg_row()
        self.toast("FFmpeg 安装完成", ft.Icons.CHECK_CIRCLE_ROUNDED, T.OK)
        return exe

    async def ensure_ffmpeg(self) -> str | None:
        """ffmpeg 是可选的：没有就问一句要不要现场下载，拒绝则画面/音频分开导出。"""
        ff = find_ffmpeg()
        if ff:
            return ff
        if not await self.ask_ffmpeg_download():
            self.warn_no_ffmpeg()
            return None
        return await self.install_ffmpeg()

    def warn_no_ffmpeg(self) -> None:
        if getattr(self, "_ffmpeg_warned", False):
            return
        self._ffmpeg_warned = True
        self.log("没有 ffmpeg：这次只导出画面", "warn",
                 "可以在「设置 → 组件」里下载，或自己把 ffmpeg.exe 放进 data\\bin\\")
        self.toast("没找到 ffmpeg，画面和音频会分开导出",
                   ft.Icons.INFO_OUTLINE_ROUNDED, T.WARN)

    def default_export_dir(self) -> str:
        d = self.cfg.get("export_dir") or ""
        if d and Path(d).is_dir():
            return d
        return str(Path.home() / "Desktop")

    async def ask_dir(self, persist: bool = True) -> Path | None:
        try:
            d = await self.picker.get_directory_path(
                dialog_title="选择保存位置", initial_directory=self.default_export_dir()
            )
        except Exception:
            d = None
        if not d:
            return None
        if persist:
            self.cfg["export_dir"] = d
            save_cfg(self.cfg)
        return Path(d)

    @staticmethod
    def _unique_dir(path: Path) -> Path:
        if not path.exists():
            return path
        for i in range(1, 999):
            cand = path.parent / f"{path.name} ({i})"
            if not cand.exists():
                return cand
        return path

    @staticmethod
    def _unique(path: Path) -> Path:
        if not path.exists():
            return path
        stem, suffix, parent = path.stem, path.suffix, path.parent
        for i in range(1, 999):
            cand = parent / f"{stem} ({i}){suffix}"
            if not cand.exists():
                return cand
        return parent / f"{stem} ({int(time.time())}){suffix}"

    @staticmethod
    def _safe_name(name: str) -> str:
        for ch in '\\/:*?"<>|':
            name = name.replace(ch, "_")
        return (name or "wallpaper").strip()[:80]

    def resolve_unpack_dest(self) -> Path | None:
        """解包保存位置：本次在弹窗里选的 > 已设置的默认保存位置 > None（需要现场选）。"""
        for cand in (getattr(self, "_unpack_dest", ""), str(self.export_dir() or "")):
            if not cand:
                continue
            try:
                p = Path(cand)
            except Exception:
                continue
            if p.is_dir():
                return p
        return None

    def export_dir(self) -> str:
        """当前可用的默认保存位置；空串表示还没设置。"""
        d = self.cfg.get("export_dir") or ""
        return d if d and Path(d).is_dir() else ""

    def export_label(self) -> str:
        d = self.export_dir()
        return ("保存位置  " + self._short_path(d)) if d else "保存位置  未设置"

    def sync_export_ui(self):
        """默认保存位置变了以后，把所有展示它的控件一起刷新。"""
        d = self.export_dir()
        if self.save_text is not None:
            try:
                self.save_text.value = self.export_label()
                self.save_text.color = T.DIM if d else T.FAINT
                self.save_text.tooltip = d or "未设置默认保存位置"
                self.save_text.update()
            except Exception:
                pass
        if self.export_text is not None:
            try:
                self.export_text.value = d or "未设置（解包时再选）"
                self.export_text.color = T.DIM if d else T.WARN
                self.export_text.update()
            except Exception:
                pass

    def show_export_dialog(self):
        self.show_dialog(self.export_dialog())

    async def _choose_export_from_dialog(self):
        """对话框里点「选择文件夹」：选完立刻同步所有显示位置，然后关掉对话框。"""
        d = await self.ask_dir()
        if not d:
            return
        self.sync_export_ui()
        self.close_dialog()
        self.toast(f"默认保存位置已设为 {d.name}", ft.Icons.FOLDER_ROUNDED, T.OK)

    def export_dialog(self) -> ft.Control:
        d = self.export_dir()
        path = txt(d or "还没有设置默认保存位置", S_BODY, T.TEXT if d else T.FAINT,
                   max_lines=3, selectable=True, expand=True)
        note = txt("设置后，解包会直接存到这里，不再弹出选择窗口。", S_SMALL, T.FAINT,
                   max_lines=2)
        card = ft.Container(
            width=500,
            padding=ft.Padding.only(left=20, right=20, top=18, bottom=16),
            border_radius=ft.BorderRadius.all(18),
            bgcolor=T.PANEL,
            border=ft.Border.all(1, T.PANEL_BORDER),
            shadow=ft.BoxShadow(blur_radius=40, spread_radius=-4, color=a(0.6, "#000000"),
                                offset=ft.Offset(0, 16)),
            content=ft.Column(
                [
                    ft.Row([txt("默认保存位置", S_TITLE, T.TEXT, ft.FontWeight.W_700),
                            ft.Container(expand=True),
                            th.icon_button(ft.Icons.CLOSE_ROUNDED, lambda e: self.close_dialog(),
                                           tooltip="关闭", size=18, box=34)],
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(
                        height=46,
                        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                        border_radius=ft.BorderRadius.all(12),
                        bgcolor=a(0.30, T.CARD_BG) if T.LIGHT else T.CARD_BG,
                        border=ft.Border.all(1, T.CARD_BORDER),
                        alignment=ft.Alignment.CENTER_LEFT,
                        content=path,
                    ),
                    note,
                    ft.Row(
                        [
                            ft.Container(expand=True),
                            th.text_button("取消", lambda e: self.close_dialog(), height=36),
                            th.text_button("选择文件夹",
                                           lambda e: self.page.run_task(self._choose_export_from_dialog),
                                           icon=ft.Icons.FOLDER_ROUNDED, accent=True, height=38),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=10,
                tight=True,
            ),
        )
        # 不加蒙版，背景壁纸保持可见；透明层只负责挡住下层点击
        return ft.Container(
            expand=True,
            bgcolor=ft.Colors.TRANSPARENT,
            on_click=lambda e: None,
            alignment=ft.Alignment.CENTER,
            content=card,
        )
