# -*- coding: utf-8 -*-
"""详情页：预览、播放、转码、设为背景。"""
from __future__ import annotations

from ..compat import *  # noqa: F401,F403


class DetailMixin:
    def open_detail(self, wp: ws.Wallpaper):
        self.sel = wp
        self.detail_wp = wp
        self.detail_video = None
        self.detail_media_path = None
        self._video_fallback_shown = False
        # 注意：这里不能加 alignment —— 有 Align 时子控件拿不到紧约束，
        # expand 的视频会缩成 0 尺寸（表现为详情页一片灰/黑）
        self.detail_holder = ft.Container(
            expand=True,
            content=ft.Container(
                alignment=ft.Alignment.CENTER,
                content=ft.ProgressRing(width=34, height=34, stroke_width=3, color=T.ACCENT),
            ),
        )
        self.detail_footer = ft.Row(spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self.open_overlay(self.detail_view(wp))
        self.page.run_task(self._load_detail_media, wp)

    def detail_view(self, wp: ws.Wallpaper) -> ft.Control:
        head = ft.Row(
            [
                ft.Column(
                    [txt(wp.title or "未命名", S_TITLE, T.TEXT, ft.FontWeight.W_600, max_lines=1),
                     txt(f"{pretty_type(wp.type)} · {ws.human_size(wp.size())} · {wp.wid}",
                         S_SMALL, T.FAINT, max_lines=1)],
                    spacing=2, tight=True, expand=True,
                ),
                self.folder_button(wp),
                th.icon_button(ft.Icons.CLOSE_ROUNDED, lambda e: self.close_overlay(),
                               tooltip="关闭", size=19, box=36),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.detail_toolbar = ft.Row(spacing=8, tight=True)
        self.bg_btn = th.text_button("设为软件背景", lambda e: self.use_wallpaper_as_bg(wp),
                                     icon=ft.Icons.WALLPAPER_ROUNDED, height=38)
        self.unpack_btn = th.text_button("解包", lambda e: self.open_unpack_menu(wp),
                                         icon=ft.Icons.DOWNLOAD_ROUNDED, accent=True, height=38)
        footer = ft.Row(
            [self.detail_toolbar, ft.Container(expand=True), self.bg_btn, self.unpack_btn],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # 玻璃面板：比整页小一圈，四周留出背景，玻璃质感更明显
        panel_w = min(920, WINDOW_W - 90)
        panel_h = min(596, WINDOW_H - 118)
        # 媒体区可用尺寸（面板内宽 / 高度减去标题行、间距、底栏按钮），用来按画面比例定框
        self._media_avail = (panel_w - 32, panel_h - 13 - 48 - 10 - 10 - 38 - 14 - 8)
        sheen = a(0.055, "#FFFFFF") if not T.LIGHT else a(0.62, "#FFFFFF")
        panel = ft.Container(
            width=panel_w,
            height=panel_h,
            padding=ft.Padding.only(left=16, right=16, top=13, bottom=14),
            border_radius=ft.BorderRadius.all(22),
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                colors=[T.PANEL, sheen],
            ),
            border=ft.Border.all(1, T.PANEL_BORDER),
            shadow=ft.BoxShadow(blur_radius=54, spread_radius=-8, color=a(0.55, "#000000"),
                                offset=ft.Offset(0, 22)),
            content=ft.Column(
                [
                    head,
                    ft.Container(height=10),
                    ft.Container(
                        expand=True,
                        bgcolor=a(0.18, "#000000"),
                        border_radius=ft.BorderRadius.all(14),
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                        border=ft.Border.all(1, T.CARD_BORDER),
                        alignment=ft.Alignment.CENTER,
                        content=self.detail_holder,
                    ),
                    ft.Container(height=10),
                    footer,
                ],
                spacing=0,
                expand=True,
            ),
        )
        # 不压蒙版：背景壁纸原样透出来，只靠面板自己的描边和投影分层
        return ft.Container(
            expand=True,
            bgcolor=ft.Colors.TRANSPARENT,
            alignment=ft.Alignment.CENTER,
            on_click=lambda e: None,
            content=panel,
        )

    def folder_button(self, wp: ws.Wallpaper) -> ft.Control:
        """「打开目录」：点一下用资源管理器定位到壁纸文件夹。"""
        def go(e):
            self.open_wallpaper_folder(wp)

        ic = ft.Icon(ft.Icons.FOLDER_OPEN_ROUNDED, size=16, color=T.DIM)
        label = txt("打开目录", S_SMALL, T.DIM, ft.FontWeight.W_500)
        box = ft.Container(
            height=32,
            padding=ft.Padding.only(left=11, right=12),
            border_radius=ft.BorderRadius.all(16),
            bgcolor=a(0.08) if not T.LIGHT else a(0.55, "#FFFFFF"),
            border=ft.Border.all(1, T.CARD_BORDER),
            on_click=go,
            tooltip=str(wp.root),
            content=ft.Row([ic, label], spacing=6, tight=True,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

        def hover(e):
            hot = str(e.data).lower() == "true"
            box.bgcolor = a(0.16) if not T.LIGHT else a(0.85, "#FFFFFF")
            ic.color = T.TEXT
            label.color = T.TEXT
            try:
                box.update()
            except Exception:
                pass

        box.on_hover = hover
        return box

    def open_wallpaper_folder(self, wp: ws.Wallpaper):
        root = Path(str(wp.root))
        if not root.is_dir():
            self.toast("壁纸目录不存在", ft.Icons.ERROR_OUTLINE_ROUNDED, T.DANGER)
            return
        if open_in_explorer(root):
            self.toast(f"已打开 {root.name}", ft.Icons.FOLDER_OPEN_ROUNDED, T.OK)
        else:
            self.copy_path(str(root))

    def use_wallpaper_as_bg(self, wp: ws.Wallpaper):
        """把这张壁纸设成软件背景（视频→直接当视频背景；其余先问要不要解包）。"""
        try:
            vids = [v for v in wp.videos()
                    if ws.weparser is not None and ws.weparser.is_playable_video(v)]
        except Exception:
            vids = []
        if vids:
            self._apply_wallpaper_bg("video", str(vids[0]), wp)
            return
        # 非视频壁纸：画面藏在 pkg / 贴图里，必须先解包，弹窗问一句
        self.confirm_unpack_for_bg(wp)

    def confirm_unpack_for_bg(self, wp: ws.Wallpaper):
        """「要解包才能当背景」的确认弹窗：确认 → 走正常解包流程，解完自动设背景。"""
        title = str(getattr(wp, "title", "") or "未命名")
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
                        [ft.Icon(ft.Icons.INVENTORY_2_ROUNDED, size=19, color=T.WARN),
                         txt("需要先解包", S_TITLE, T.TEXT, ft.FontWeight.W_700, max_lines=1,
                             expand=True)],
                        spacing=9, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    txt(f"「{title[:24]}」不是视频壁纸，画面在壁纸包里，"
                        "要先解包才能当软件背景。解包完成后会自动把它设为背景。",
                        S_BODY, T.DIM),
                    ft.Row(
                        [
                            ft.Container(expand=True),
                            th.text_button("取消", lambda e: self.close_dialog(), height=38),
                            th.text_button("解包并设为背景",
                                           lambda e: self._bg_unpack_go(wp),
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

    def _bg_unpack_go(self, wp: ws.Wallpaper):
        self.close_dialog()
        self.page.run_task(self._unpack_then_bg, wp)

    async def _unpack_then_bg(self, wp: ws.Wallpaper):
        """解包 → 用产出的画面当背景；解不出画面就退回壁纸预览图。"""
        self._last_unpack = []
        if self.resolve_unpack_dest() is None:
            # 没设过保存位置时别为了设背景弹目录选择框，直接用默认位置
            self._unpack_dest = self.default_export_dir()
        await self.unpack(wp, "media", autoplay=False)
        written = list(getattr(self, "_last_unpack", []) or [])
        img = next((p for p in written
                    if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp")), None)
        if img is not None and Path(img).is_file():
            self._apply_wallpaper_bg("image", str(img), wp)
            return
        # 场景壁纸解出来的是贴图；实在没有就退回预览图
        prev = str(getattr(wp, "preview", "") or "")
        if prev and Path(prev).is_file():
            self._apply_wallpaper_bg("image", prev, wp)
            return
        # 最后兜底：直接抽一张预览画面（不进解包目录）
        await self._scene_bg_task(wp)

    async def _scene_bg_task(self, wp: ws.Wallpaper):
        self.toast("正在提取画面…", ft.Icons.HOURGLASS_ROUNDED, T.DIM)
        got = None
        try:
            got = await asyncio.to_thread(self.preview_payload, wp)
        except Exception:
            got = None
        if not got:
            self.toast("这个壁纸没有可用作背景的画面",
                       ft.Icons.IMAGE_NOT_SUPPORTED_ROUNDED, T.WARN)
            return
        ext, data = got
        try:
            out_dir = ws.CACHE_DIR / "bg"
            out_dir.mkdir(parents=True, exist_ok=True)
            suffix = "jpg" if ext in ("jpg", "jpeg") else "png"
            fp = out_dir / f"wp_{getattr(wp, 'wid', 'bg')}.{suffix}"
            fp.write_bytes(data)
        except Exception as exc:
            self.toast(f"写入背景图失败：{str(exc)[:40]}",
                       ft.Icons.ERROR_OUTLINE_ROUNDED, T.DANGER)
            return
        self._apply_wallpaper_bg("image", str(fp), wp)

    def _apply_wallpaper_bg(self, mode: str, path: str, wp=None):
        title = str(getattr(wp, "title", "") or Path(path).stem or "壁纸")
        self.close_overlay()
        self.cfg["bg_mode"] = mode
        if mode == "video":
            self.cfg["bg_video"] = path
        else:
            self.cfg["bg_image"] = path
        save_cfg(self.cfg)
        self.refresh_palette()
        self.build_bg()
        self.rebuild_ui()
        label = "视频背景" if mode == "video" else "图片背景"
        self.log(f"已设为{label}：{title}", "info")
        self.toast(f"已把「{title[:16]}」设为{label}", ft.Icons.WALLPAPER_ROUNDED, T.OK)

    def _media_box(self, aspect: float) -> tuple[int, int]:
        """按画面比例算出媒体区的框大小，框贴着画面 → 不会出现上下左右的黑边。"""
        aw, ah = getattr(self, "_media_avail", (888, 455))
        try:
            aspect = float(aspect)
        except Exception:
            aspect = 0.0
        if aspect <= 0.05:
            aspect = aw / ah
        w, h = float(aw), float(aw) / aspect
        if h > ah:
            h = float(ah)
            w = h * aspect
        return max(80, int(round(w))), max(45, int(round(h)))

    def _video_aspect(self, path) -> float:
        try:
            w, h = ws.weparser.mp4_dimensions(path)
            if w > 0 and h > 0:
                return w / h
        except Exception:
            pass
        return 16 / 9

    async def _load_detail_media(self, wp: ws.Wallpaper):
        vids = wp.videos()
        playable = [v for v in vids if ws.weparser is not None
                    and ws.weparser.is_playable_video(v)]
        if playable:
            vid_path = playable[0]
            has_audio = True
            try:
                has_audio = ws.weparser.mp4_probe(vid_path)["has_audio"]
            except Exception:
                has_audio = True
            video = Video(
                playlist=[VideoMedia(resource=file_uri(vid_path))],
                expand=True,
                fit=ft.BoxFit.CONTAIN,
                autoplay=True,
                muted=not has_audio,
                volume=100 if has_audio else 0,
                # 关键：controls 必须是 None；传 False/True 时 flet_video 只画一张灰底静帧
                controls=None,
                fill_color="#04060F",
                filter_quality=ft.FilterQuality.MEDIUM,
                playlist_mode=PlaylistMode.LOOP,
            )
            video.on_error = self._on_detail_video_error
            self.detail_video = video
            self.detail_media_path = vid_path
            mw, mh = self._media_box(self._video_aspect(vid_path))
            self.detail_holder.content = ft.Container(
                width=mw,
                height=mh,
                bgcolor="#04060F",
                border_radius=ft.BorderRadius.all(10),
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                content=video,
            )
            # 声音按钮一直显示：有音轨可点，没音轨就置灰
            self.detail_toolbar.controls = [self.mute_button(video, enabled=has_audio)]
            self.page.update()
            self.page.run_task(self._kick_detail_video, video)
            return

        # 不支持的视频格式（webm / 其它封装）：给提示 + 海报图，声音按钮禁用
        if vids:
            poster = None
            if wp.preview is not None and Path(wp.preview).is_file():
                poster = ft.Image(src=str(wp.preview), fit=ft.BoxFit.CONTAIN, expand=True,
                                  opacity=0.55)
            self.detail_holder.content = ft.Stack(
                [
                    ft.Container(expand=True, content=poster) if poster else ft.Container(),
                    ft.Container(
                        expand=True,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Column(
                            [ft.Icon(ft.Icons.VIDEO_FILE_OUTLINED, size=44, color=a(0.45)),
                             txt(f"该壁纸的视频是 {vids[0].suffix.upper()} 格式，播放器无法直接预览",
                                 S_BODY, T.TEXT, ft.FontWeight.W_500),
                             txt("可以点右下角「解包」导出为视频文件", S_SMALL, T.FAINT)],
                            spacing=8,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            tight=True,
                        ),
                    ),
                ],
                expand=True,
            )
            self.detail_toolbar.controls = []
            self.page.update()
            return

        # 场景壁纸：解出最大贴图作为静态预览
        got = None
        try:
            got = await asyncio.to_thread(self.preview_payload, wp)
        except Exception:
            got = None
        if got is not None:
            ext, data = got
            if ext in ("png", "jpg", "jpeg"):
                try:
                    from PIL import Image as _Img

                    with _Img.open(io.BytesIO(data)) as _im:
                        mw, mh = self._media_box(_im.width / max(1, _im.height))
                except Exception:
                    mw, mh = self._media_box(16 / 9)
                self.detail_holder.content = ft.Container(
                    width=mw,
                    height=mh,
                    border_radius=ft.BorderRadius.all(10),
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                    content=ft.Image(src=data, fit=ft.BoxFit.CONTAIN, expand=True),
                )
            else:
                self.detail_holder.content = ft.Container(
                    alignment=ft.Alignment.CENTER,
                    content=ft.Column(
                        [ft.Icon(ft.Icons.IMAGE_ROUNDED, size=40, color=a(0.4)),
                         txt("静态预览不可用，可直接解包", S_SMALL, T.FAINT)],
                        spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
                )
        else:
            self.detail_holder.content = ft.Container(
                alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    [ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED_ROUNDED, size=40, color=a(0.4)),
                     txt("这个壁纸没有可预览的画面", S_SMALL, T.FAINT)],
                    spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
            )
        self.page.update()

    async def _kick_detail_video(self, video: Video):
        """media_kit 偶尔首帧后停住，这里补一次 play()；始终放不起来就给出提示。"""
        tries = 0
        for delay in (0.9, 2.2, 3.2):
            await asyncio.sleep(delay)
            if getattr(self, "detail_video", None) is not video:
                return
            try:
                if await video.is_playing():
                    tries = 0
                    continue
            except Exception:
                pass
            try:
                await video.play()
                tries += 1
            except Exception:
                tries += 1
            if tries >= 2:
                self._show_video_fallback("这个 MP4 的解码器不受支持")
                return

    def _video_codec(self, path) -> str:
        try:
            info = ws.weparser.mp4_probe(path) if ws.weparser else {}
            return (info or {}).get("codec_label") or (info or {}).get("codec") or ""
        except Exception:
            return ""

    def _on_detail_video_error(self, e):
        """视频解码失败：换成海报 + 文字说明，并把声音按钮置灰。"""
        msg = str(getattr(e, "data", "") or "")
        reason = self._video_codec(getattr(self, "detail_media_path", None)) or msg[:40]
        self.log(f"视频解码失败：{reason or msg[:120]}", "error")
        self._show_video_fallback(f"这个视频无法解码（{reason}）" if reason else "这个视频无法解码")

    def _show_video_fallback(self, reason: str):
        if getattr(self, "_video_fallback_shown", False):
            return
        self._video_fallback_shown = True
        wp = getattr(self, "detail_wp", None)
        poster = None
        if wp is not None and wp.preview is not None and Path(wp.preview).is_file():
            poster = ft.Image(src=str(wp.preview), fit=ft.BoxFit.CONTAIN, expand=True, opacity=0.5)
        # 容器格式没问题、只是编码不受支持时，提供「转成 H.264」的补救
        can_transcode = False
        path = getattr(self, "detail_media_path", None)
        try:
            info = ws.weparser.mp4_probe(path) if (path and ws.weparser) else {}
            can_transcode = bool(info.get("ok")) and (info.get("codec") or "") not in ("", "avc1", "avc3")
        except Exception:
            can_transcode = False
        extra: list[ft.Control] = []
        if can_transcode:
            extra.append(th.text_button(
                "转成 H.264 后播放",
                lambda e: self.page.run_task(self.transcode_and_play),
                icon=ft.Icons.AUTO_FIX_HIGH_ROUNDED, accent=True, height=36))
        self.detail_holder.content = ft.Stack(
            [
                ft.Container(expand=True, content=poster) if poster else ft.Container(),
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Column(
                        [ft.Icon(ft.Icons.VIDEO_FILE_OUTLINED, size=44, color=a(0.45)),
                         txt(reason, S_BODY, T.TEXT, ft.FontWeight.W_500),
                         txt("也可以点右下角「解包」直接导出原始视频文件", S_SMALL, T.FAINT),
                         *extra],
                        spacing=10,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        tight=True,
                    ),
                ),
            ],
            expand=True,
        )
        try:
            self.detail_toolbar.controls = [self.mute_button(self.detail_video, enabled=False)]
            self.page.update()
        except Exception:
            pass

    def _transcode_cache_path(self, src) -> Path:
        p = Path(src)
        try:
            st = p.stat()
            key = hashlib.sha1(f"{p}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()[:20]
        except Exception:
            key = hashlib.sha1(str(p).encode()).hexdigest()[:20]
        return ws.CACHE_DIR / "trans" / f"{key}.mp4"

    def _transcode_worker(self, src, ff: str, state: dict) -> str:
        out = self._transcode_cache_path(src)
        out.parent.mkdir(parents=True, exist_ok=True)
        total = self._media_duration(ff, src)
        state["phase"] = "转码中（→ H.264）…"
        cmd = [ff, "-y", "-loglevel", "error", "-i", str(src),
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
               "-movflags", "+faststart", str(out)]
        ok = self._run_ffmpeg_progress(cmd, total, state, "转码中")
        if not ok or not out.is_file() or out.stat().st_size < 4096:
            out.unlink(missing_ok=True)
            raise RuntimeError("ffmpeg 转码失败")
        return str(out)

    async def transcode_and_play(self):
        src = getattr(self, "detail_media_path", None)
        if not src:
            return
        cached = self._transcode_cache_path(src)
        if cached.is_file() and cached.stat().st_size > 4096:
            self._play_transcoded(cached)
            return
        ff = await self.ensure_ffmpeg()
        if not ff:
            self.toast("ffmpeg 不可用，无法转码", ft.Icons.ERROR_OUTLINE_ROUNDED, T.WARN)
            return
        res = await self.run_with_progress("转码为 H.264", "正在转码，稍等一下…",
                                           lambda st: self._transcode_worker(src, ff, st),
                                           done_text="转码完成")
        if res["error"] or not res["result"]:
            self.toast(f"转码失败：{(res['error'] or '未知错误')[:50]}",
                       ft.Icons.ERROR_OUTLINE_ROUNDED, T.DANGER)
            return
        self._play_transcoded(Path(res["result"]))

    def _play_transcoded(self, path: Path):
        try:
            self._video_fallback_shown = False
            video = Video(
                playlist=[VideoMedia(resource=file_uri(path))],
                expand=True,
                fit=ft.BoxFit.CONTAIN,
                autoplay=True,
                muted=False,
                volume=100,
                controls=None,
                fill_color="#04060F",
                playlist_mode=PlaylistMode.LOOP,
            )
            video.on_error = self._on_detail_video_error
            self.detail_video = video
            self.detail_media_path = path
            self.detail_holder.content = ft.Container(expand=True, content=video)
            self.detail_toolbar.controls = [self.mute_button(video, enabled=True)]
            self.page.update()
            self.page.run_task(self._kick_detail_video, video)
            self.toast("已转为 H.264 播放（缓存可复用）", ft.Icons.CHECK_CIRCLE_ROUNDED, T.OK)
        except Exception as exc:  # noqa: BLE001
            self.toast(f"播放失败：{exc}"[:60], ft.Icons.ERROR_OUTLINE_ROUNDED, T.DANGER)

    def mute_button(self, video: Video, enabled: bool = True) -> ft.Control:
        """声音按钮：enabled=False 时置灰不可点；点击切换图标与文字。"""
        state = {"muted": False}

        ic = ft.Icon(ft.Icons.VOLUME_UP_ROUNDED if enabled else ft.Icons.VOLUME_OFF_ROUNDED,
                     size=19, color=T.DIM if enabled else a(0.30))
        label = txt("声音" if enabled else "无音轨", S_SMALL,
                    T.DIM if enabled else a(0.38))

        def paint():
            ic.icon = ft.Icons.VOLUME_OFF_ROUNDED if state["muted"] else ft.Icons.VOLUME_UP_ROUNDED
            ic.color = a(0.30) if not enabled else (T.FAINT if state["muted"] else T.DIM)
            label.value = ("无音轨" if not enabled else ("已静音" if state["muted"] else "声音"))
            label.color = a(0.38) if not enabled else (T.FAINT if state["muted"] else T.DIM)

        def toggle(e):
            if not enabled:
                return
            state["muted"] = not state["muted"]
            try:
                video.muted = state["muted"]
                video.volume = 0 if state["muted"] else 100
                video.update()
            except Exception:
                pass
            paint()
            try:
                btn.update()
            except Exception:
                pass

        # 玻璃胶囊：半透明底 + 顶部高光 + 细边 + 轻微投影，和顶栏胶囊同一套质感
        sheen_a, sheen_b = (0.14, 0.02) if not T.LIGHT else (0.85, 0.35)
        btn = ft.Container(
            height=34,
            padding=ft.Padding.only(left=13, right=15),
            border_radius=ft.BorderRadius.all(17),
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                colors=[a(sheen_a, "#FFFFFF"), a(sheen_b, "#FFFFFF")],
            ),
            border=ft.Border.all(1, a(0.22, "#FFFFFF") if not T.LIGHT else a(0.75, "#FFFFFF")),
            shadow=ft.BoxShadow(blur_radius=14, spread_radius=-2,
                                color=a(0.22, "#000000"), offset=ft.Offset(0, 4)),
            on_click=toggle,
            tooltip="切换声音" if enabled else "这个视频没有音轨",
            alignment=ft.Alignment.CENTER,
            content=ft.Row([ic, label], spacing=7, tight=True,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

        def on_hover(e):
            if not enabled:
                return
            hot = str(e.data).lower() == "true"
            btn.border = ft.Border.all(1, a(0.40 if hot else 0.22, "#FFFFFF"))
            try:
                btn.update()
            except Exception:
                pass

        btn.on_hover = on_hover
        return btn

    def play_media(self, path: Path) -> None:
        """转换 / 录制完成后按设置直接播放（系统默认播放器，外部打开）。"""
        if not Path(path).is_file():
            return
        if open_with_system(path):
            self.log(f"已用系统播放器打开：{Path(path).name}", "info")
        else:
            self.copy_path(str(path))

    @staticmethod
    def _media_duration(ff: str, path) -> float:
        """用 ffmpeg -i 的 stderr 拿时长（秒）。"""
        try:
            r = subprocess.run([ff, "-hide_banner", "-i", str(path)],
                               capture_output=True, text=True, timeout=90,
                               encoding="utf-8", errors="replace")
            txt_err = (r.stderr or "") + (r.stdout or "")
            for line in txt_err.splitlines():
                line = line.strip()
                if line.startswith("Duration:"):
                    stamp = line.split("Duration:")[1].split(",")[0].strip()
                    h, m, s = stamp.split(":")
                    return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:
            pass
        return 0.0

    def _run_ffmpeg_progress(self, cmd: list[str], total: float, state: dict | None,
                             phase: str = "合成中", lo: float = 0.06, hi: float = 0.86) -> bool:
        """跑 ffmpeg 并用 -progress 输出刷新进度；成功返回 True。"""
        full = [cmd[0], "-progress", "pipe:1", "-nostats", *cmd[1:]]
        try:
            proc = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    text=True, bufsize=1,
                                    encoding="utf-8", errors="replace")
        except Exception:
            return False
        try:
            for line in proc.stdout or []:
                line = line.strip()
                if state is not None and line.startswith("out_time_ms="):
                    try:
                        us = int(line.split("=", 1)[1])
                    except Exception:
                        continue
                    done = us / 1_000_000.0
                    if total > 0:
                        frac = max(0.0, min(1.0, done / total))
                        state["value"] = lo + (hi - lo) * frac
                        state["phase"] = f"{phase}  {done:.0f}s / {total:.0f}s"
                elif state is not None and line.startswith("progress=end"):
                    state["value"] = 0.99
        finally:
            proc.wait()
        return proc.returncode == 0

    def preview_payload(self, wp: ws.Wallpaper):
        """场景壁纸：从包里解出最大的一张贴图（阻塞调用，带磁盘缓存）。"""
        try:
            st = (wp.root / (wp.pkgs()[0].name if wp.pkgs() else "")).stat()
            key = hashlib.sha1(f"{wp.root}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()[:16]
        except Exception:
            key = None
        dest = ws.THUMB_DIR / f"prev_{key}.jpg" if key else None
        if dest is not None and dest.is_file() and dest.stat().st_size > 0:
            return "jpg", dest.read_bytes()
        got = self._tex_payload(wp, 1400)
        if got is not None and got[0] == "png" and dest is not None:
            try:
                from PIL import Image

                ws.THUMB_DIR.mkdir(parents=True, exist_ok=True)
                im = Image.open(io.BytesIO(got[1])).convert("RGB")
                im.save(dest, "JPEG", quality=90)
                return "jpg", dest.read_bytes()
            except Exception:
                return got
        return got

    def _tex_payload(self, wp: ws.Wallpaper, max_size: int | None):
        if ws.weparser is None:
            return None
        best = None
        for pkg_path in wp.pkgs():
            try:
                pkg = self._pkg(str(pkg_path))
            except Exception:
                continue
            for e in pkg.entries:
                if str(e.path).lower().endswith(".tex"):
                    if best is None or int(e.length) > int(best[0].length):
                        best = (e, str(pkg_path))
        if best is None:
            return None
        entry, pkg_path = best
        try:
            data = self._pkg(pkg_path).read_entry(entry)
            return ws.weparser.tex_media(data, max_size)
        except Exception:
            return None

    def audio_candidates(self, wp: ws.Wallpaper) -> list:
        try:
            res = ws.resources(wp)
        except Exception:
            return []
        return [r for r in res if r.kind == "audio" and r.size > 0]

    def read_resource(self, r) -> bytes | None:
        try:
            if r.pkg:
                return self._pkg(r.pkg).read_entry(r.entry)
            if r.path and Path(r.path).is_file():
                return Path(r.path).read_bytes()
        except Exception:
            return None
        return None

    def _pkg(self, pkg_path: str):
        if pkg_path not in self._pkg_cache:
            self._pkg_cache[pkg_path] = ws.weparser.open_pkg(pkg_path)
        return self._pkg_cache[pkg_path]
