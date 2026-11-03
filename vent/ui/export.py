# -*- coding: utf-8 -*-
"""导出与解包：收集素材、合成、进度对话框。"""
from __future__ import annotations

from ..compat import *  # noqa: F401,F403


class ExportMixin:
    def collect_export(self, wp: ws.Wallpaper, mode: str,
                       state: dict | None = None) -> list[tuple[str, object]]:
        """返回 [(文件名, Path | bytes)]。mode: media = 只导画面；av = 画面 + 音频。"""
        base = self._safe_name(wp.title or "wallpaper")
        parser = ws.weparser
        items: list[tuple[str, object]] = []
        auds = self.audio_candidates(wp)

        # 录制模式：非视频壁纸（场景 / 网页）先让 Wallpaper Engine 渲染成窗口再录，
        # 录出来的 mp4 有真实动效；壁纸自带音频就一起合进去。
        if mode == "rec":
            rec = self._record_worker(wp, state if state is not None else {})
            if auds:
                data = self.read_resource(auds[0])
                if data:
                    try:
                        rec_dur = float(getattr(self, "_last_record_dur", 0) or 0)
                        rec_end = float(getattr(self, "_last_record_end", -1) or -1)
                        if rec_end > 0:
                            limit = min(rec_dur, rec_end) if rec_dur > 0 else rec_end
                        else:
                            limit = rec_dur or None
                    except Exception:
                        limit = None
                    merged = self._mux(rec, data, auds[0].ext, base, state, limit=limit)
                    if merged is not None:
                        rec.unlink(missing_ok=True)
                        # 兜底：成品绝不允许比录制时长更长
                        if limit:
                            try:
                                got = float(ws.weparser.mp4_duration(merged) or 0)
                                if got > limit + 0.05:
                                    self._trim_clip(merged, limit)
                            except Exception:
                                pass
                        return [(f"{base}.mp4", merged)]
            return [(f"{base}.mp4", rec)]

        playable = [v for v in wp.videos() if parser is not None and parser.is_playable_video(v)]
        if playable:
            v = playable[0]
            if mode == "media":
                return [(f"{base}.mp4", v)]
            info = parser.mp4_probe(v)
            if info.get("has_audio"):
                return [(f"{base}.mp4", v)]
            if auds:
                aud = auds[0]
                data = self.read_resource(aud)
                if data:
                    merged = self._mux(v, data, aud.ext, base, state)
                    if merged is not None:
                        return [(f"{base}.mp4", merged)]
                    items.append((f"{base}_画面.mp4", v))
                    items.append((f"{base}_音频{aud.ext}", data))
                    return items
            return [(f"{base}.mp4", v)]

        # 图片 / 场景壁纸：解出最大贴图
        got = None
        try:
            got = self._tex_payload(wp, None)
        except Exception:
            got = None
        if got is not None:
            items.append((f"{base}.{got[0]}", got[1]))
        elif wp.preview is not None and Path(wp.preview).is_file():
            p = Path(wp.preview)
            items.append((f"{base}{p.suffix}", p))
        else:
            imgs = sorted(wp.images(), key=lambda p: p.stat().st_size, reverse=True)
            if imgs:
                items.append((f"{base}{imgs[0].suffix}", imgs[0]))
        if mode == "av" and auds:
            aud = auds[0]
            data = self.read_resource(aud)
            if data:
                if got is not None and items and isinstance(items[0][1], bytes):
                    made = self._synth_still(items[0][1], data, aud.ext, base, state)
                    if made is not None:
                        return [(f"{base}.mp4", made)]
                items.append((f"{base}_音频{aud.ext}", data))
        return items

    def _synth_still(self, image: bytes, audio: bytes, ext: str, base: str,
                     state: dict | None = None) -> Path | None:
        """静图 + 音频 → mp4（需要 ffmpeg）。"""
        ff = find_ffmpeg()
        if not ff:
            return None
        tmp = ws.CACHE_DIR / "mux"
        tmp.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time() * 1000)
        img_path = tmp / f"i_{stamp}.png"
        aud_path = tmp / f"s_{stamp}{ext}"
        out = tmp / f"v_{stamp}.mp4"
        try:
            img_path.write_bytes(image)
            aud_path.write_bytes(audio)
            if state is not None:
                state["phase"] = "合成静图 + 音频…"
                state["value"] = 0.12
            total = self._media_duration(ff, aud_path)
            # 4K 静图合成很慢，宽度先压到 1920，速度和体积都更合理
            cmd = [ff, "-y", "-loglevel", "error", "-loop", "1", "-i", str(img_path),
                   "-i", str(aud_path), "-vf", "scale='min(1920,iw)':-2",
                   "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
                   "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                   "-shortest", str(out)]
            ok = self._run_ffmpeg_progress(cmd, total, state, "合成中")
            if ok and out.is_file() and out.stat().st_size > 1024:
                return out
        except Exception:
            return None
        finally:
            img_path.unlink(missing_ok=True)
            aud_path.unlink(missing_ok=True)
        return None

    def _mux(self, video: Path, audio: bytes, ext: str, base: str,
             state: dict | None = None, limit: float | None = None) -> Path | None:
        """用 ffmpeg 把音频合进视频；没有 ffmpeg 或失败时返回 None。"""
        ff = find_ffmpeg()
        if not ff:
            return None
        tmp = ws.CACHE_DIR / "mux"
        tmp.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time() * 1000)
        aud_path = tmp / f"a_{stamp}{ext}"
        out = tmp / f"m_{stamp}.mp4"
        try:
            aud_path.write_bytes(audio)
            if state is not None:
                state["phase"] = "合成音轨…"
                state["value"] = 0.12
            total = self._media_duration(ff, video)
            # limit = 画面长度：音频比画面长时按画面截断，避免出现「画面定格、声音还在放」。
            # 另外再夹一层「真实帧尾」：容器时长可能被写长，只信 demux 出来的最后一帧。
            end = self._video_real_end(video)
            if end > 0:
                limit = min(limit, end) if limit else end
            tail = ["-shortest"] if not limit else ["-t", f"{limit:.3f}"]
            for extra in (["-c", "copy"], ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]):
                cmd = [ff, "-y", "-loglevel", "error", "-i", str(video), "-i", str(aud_path),
                       *extra, *tail, str(out)]
                ok = self._run_ffmpeg_progress(cmd, total, state, "合成中")
                if ok and out.is_file() and out.stat().st_size > 1024:
                    return out
                out.unlink(missing_ok=True)
        except Exception:
            return None
        finally:
            aud_path.unlink(missing_ok=True)
        return None

    def _export_worker(self, wp: ws.Wallpaper, mode: str, dest: Path, state: dict) -> dict:
        """在线程里跑：解出资源 → 必要时合成 → 分块写盘并回报进度。"""
        state["phase"] = "正在解出壁纸资源…"
        state["value"] = 0.04
        items = self.collect_export(wp, mode, state)
        if not items:
            return {"written": []}
        target_dir = dest
        if len(items) > 1:
            target_dir = self._unique_dir(dest / f"{self._safe_name(wp.title)}_解包")
            target_dir.mkdir(parents=True, exist_ok=True)
        sizes = []
        for name, data in items:
            if isinstance(data, Path):
                try:
                    sizes.append(data.stat().st_size)
                except Exception:
                    sizes.append(0)
            else:
                sizes.append(len(data))
        total = max(1, sum(sizes))
        done = 0
        written: list[Path] = []
        for (name, data), size in zip(items, sizes):
            target = self._unique(target_dir / name)
            target.parent.mkdir(parents=True, exist_ok=True)
            state["phase"] = f"写入 {target.name}"
            if isinstance(data, Path):
                with open(data, "rb") as src, open(target, "wb") as out:
                    while True:
                        chunk = src.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
                        done += len(chunk)
                        state["value"] = 0.88 + 0.12 * (done / total)
            else:
                view = memoryview(data)
                with open(target, "wb") as out:
                    for i in range(0, len(view), 1 << 20):
                        piece = view[i:i + (1 << 20)]
                        out.write(piece)
                        done += len(piece)
                        state["value"] = 0.88 + 0.12 * (done / total)
            written.append(target)
        # 合成用的临时文件用完就删（转码缓存 .cache/trans 要留着复用）
        for name, data in items:
            try:
                if isinstance(data, Path) and data.parent == ws.CACHE_DIR / "mux":
                    data.unlink(missing_ok=True)
            except Exception:
                pass
        state["value"] = 1.0
        state["phase"] = "写入完成"
        return {"written": written}

    async def unpack(self, wp: ws.Wallpaper, mode: str = "media", autoplay: bool | None = None):
        self.close_dialog()
        dest = self.resolve_unpack_dest()
        if dest is None:
            dest = await self.ask_dir(persist=False)
            if dest is None:
                return
            self._unpack_dest = str(dest)
        # 需要合成又没装 ffmpeg：先弹进度窗自动安装
        if self.needs_ffmpeg(wp, mode) and find_ffmpeg() is None:
            if await self.ensure_ffmpeg() is None:
                self.toast("没有 ffmpeg，改为分别导出画面与音频",
                           ft.Icons.INFO_ROUNDED, T.WARN)
        if mode == "rec" and find_ffmpeg() is None:
            # 录制必须要有 ffmpeg：capturekit 用它编码，gdigrab 回退也用它
            self.set_status("录制需要 FFmpeg…")
            if await self.ensure_ffmpeg() is None:
                self.set_status("录制需要 FFmpeg")
                self.toast("录制需要 FFmpeg：请到「设置 → 组件」下载一份再试",
                           ft.Icons.ERROR_OUTLINE_ROUNDED, T.DANGER)
                return
        if mode == "rec":
            self.set_status(f"正在录制 {wp.title[:20]}…")
            self.toast("录制期间壁纸窗口会顶在最前面（防止画面中途冻住），录完自动收起",
                       ft.Icons.VISIBILITY_ROUNDED, T.WARN, log_it=False)
            sub_text = "正在打开壁纸渲染窗口…（请不要最小化它）"
        else:
            self.set_status(f"正在解包 {wp.title[:20]}…")
            sub_text = "正在读取壁纸资源…"
        res = await self.run_with_progress(
            "解包壁纸", sub_text,
            lambda st: self._export_worker(wp, mode, Path(dest), st),
            done_text="写入完成")
        if res["error"]:
            self.set_status("解包失败")
            self.toast(f"解包失败：{res['error'][:60]}",
                       ft.Icons.ERROR_OUTLINE_ROUNDED, T.DANGER)
            return
        written = (res["result"] or {}).get("written") or []
        self._last_unpack = list(written)
        if not written:
            self.set_status("解包失败")
            self.toast("这个壁纸没有可解包的画面", ft.Icons.INFO_ROUNDED, T.WARN)
            return
        total = sum(p.stat().st_size for p in written)
        summary = written[0].name if len(written) == 1 else f"{len(written)} 个文件"
        self.log(f"解包完成：{summary} · {ws.human_size(total)} → {dest}", "info")
        self.set_status(f"已解包 {summary} · {ws.human_size(total)}")
        self.toast(f"已保存到 {dest} · {ws.human_size(total)}",
                   ft.Icons.DOWNLOAD_DONE_ROUNDED, T.OK)
        self._unpack_dest = str(dest)
        # 录制 / 转换完成 → 按设置立刻用系统播放器打开产物
        # （设背景这条链路传 autoplay=False：产物已经在当背景了，别再弹播放器）
        if autoplay is not False and self.cfg.get("play_when_done", True):
            playable = next((p for p in written
                             if p.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv")), None)
            if playable is not None:
                self.play_media(playable)

    def open_unpack_menu(self, wp: ws.Wallpaper):
        self.show_dialog(self.unpack_dialog(wp))

    def option_card(self, icon, title: str, desc: str, on_click, enabled: bool = True,
                    tag: str = "", rec: bool = False) -> ft.Control:
        """一个导出方式卡片；rec=True 时标「推荐」并换成强调色描边。"""
        color = T.TEXT if enabled else T.FAINT
        row = [
            ft.Container(
                width=38, height=38, border_radius=ft.BorderRadius.all(11),
                bgcolor=a(0.12, T.ACCENT if enabled else "#FFFFFF"),
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(icon, size=20, color=T.ACCENT if enabled else T.FAINT),
            ),
            ft.Column(
                [ft.Row([txt(title, S_BODY, color, ft.FontWeight.W_600),
                         *([th.pill("推荐", T.OK)] if rec else []),
                         *([th.pill(tag, T.ACCENT)] if tag else [])],
                        spacing=8, tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER),
                 txt(desc, S_SMALL, T.FAINT, max_lines=2)],
                spacing=3, tight=True, expand=True,
            ),
            ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, size=18, color=a(0.35)),
        ]
        base_bg = a(0.06, T.OK) if rec else T.CARD_BG
        base_border = (ft.Border.all(1.4, a(0.55, T.OK)) if rec
                       else ft.Border.all(1, T.CARD_BORDER))
        box = ft.Container(
            padding=ft.Padding.symmetric(horizontal=14, vertical=12),
            border_radius=ft.BorderRadius.all(14),
            bgcolor=base_bg,
            border=base_border,
            on_click=on_click,
            content=ft.Row(row, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

        def hover(e):
            hot = str(e.data).lower() == "true"
            box.bgcolor = a(0.14, T.OK) if (hot and rec) else (a(0.10) if hot else base_bg)
            box.border = (ft.Border.all(1.4, a(0.75, T.OK)) if (hot and rec)
                          else (ft.Border.all(1, a(0.30 if hot else 0.12)) if not rec
                                else base_border))
            box.update()

        box.on_hover = hover
        return box

    def unpack_dialog(self, wp: ws.Wallpaper) -> ft.Control:
        ff = find_ffmpeg()
        has_video = bool([v for v in wp.videos()])
        auds = self.audio_candidates(wp)
        av_tag = "ffmpeg 已就绪" if ff else "自动安装 ffmpeg"

        playable = [v for v in wp.videos()
                    if ws.weparser is not None and ws.weparser.is_playable_video(v)]
        rec_ok = self.can_record(wp)

        # 推荐哪种导出方式：能直接播的视频 → 画面(+音频)；场景 / 网页 → 录制才有动效
        has_audio = False
        if playable:
            try:
                has_audio = bool(ws.weparser and ws.weparser.mp4_probe(playable[0]).get("has_audio"))
            except Exception:
                has_audio = False
        if playable:
            best = "av" if (has_audio or auds) else "media"
        else:
            best = "rec" if rec_ok else "media"

        opts = [
            self.option_card(
                ft.Icons.IMAGE_ROUNDED, "只解包画面",
                "视频壁纸导出 MP4，场景壁纸导出最大贴图 PNG（原尺寸）",
                lambda e: self.page.run_task(self.unpack, wp, "media"),
                rec=(best == "media"),
            ),
            self.option_card(
                ft.Icons.GRAPHIC_EQ_ROUNDED, "解包画面 + 提取音频",
                ("视频自带音轨时直接导出完整 MP4；没有音轨则提取壁纸音频，"
                 + ("合成一个视频" if ff else "首次会自动下载 ffmpeg 再合成"))
                if auds or has_video else "该壁纸没有独立音频资源",
                lambda e: self.page.run_task(self.unpack, wp, "av"),
                tag=av_tag, rec=(best == "av"),
            ),
        ]
        # 非视频壁纸（场景 / 网页）多给一条「录制动画」：静态贴图没有动效，录屏才有
        if not playable:
            opts.append(self.option_card(
                ft.Icons.SCREEN_SHARE_ROUNDED, "录制动画（场景 / 网页）",
                ("让 Wallpaper Engine 渲染到窗口再录成 MP4，动效和声音都能留下；"
                 "录完自动关窗口，期间请不要最小化它"
                 if rec_ok else "没找到 wallpaper64.exe 或壁纸文件，暂不可用"),
                lambda e: self.page.run_task(self.unpack, wp, "rec"),
                enabled=rec_ok,
                tag=f"约 {self.record_seconds(wp):.0f} 秒" if rec_ok else "",
                rec=(best == "rec"),
            ))

        # 保存位置行：地址 + 设为默认 + 选择（首次启动没有默认位置时，解包就在这里选）
        if not self._unpack_dest:
            self._unpack_dest = str(self.export_dir() or "")
        path_text = txt(self._unpack_dest or "尚未选择保存位置", S_SMALL,
                        T.TEXT if self._unpack_dest else T.FAINT, max_lines=1, expand=True)
        path_text.tooltip = self._unpack_dest or None
        cb_label = ft.TextStyle(size=S_SMALL, color=T.DIM)

        def apply_default(on: bool, folder: str):
            cur = self.cfg.get("export_dir") or ""
            if on and folder:
                self.cfg["export_dir"] = folder
            elif not on and folder and cur == folder:
                self.cfg["export_dir"] = ""
            else:
                return
            save_cfg(self.cfg)
            self.sync_export_ui()

        def on_default_change(e):
            on = bool(e.control.value)
            if on and not self._unpack_dest:
                e.control.value = False
                e.control.update()
                self.toast("先选择一个保存位置", ft.Icons.INFO_ROUNDED, T.WARN)
                return
            apply_default(on, self._unpack_dest)
            if on:
                self.toast("已设为默认保存位置", ft.Icons.CHECK_CIRCLE_ROUNDED, T.OK)

        default_cb = ft.Checkbox(
            label="设为默认", value=bool(self._unpack_dest)
            and self._unpack_dest == (self.cfg.get("export_dir") or ""),
            on_change=on_default_change, label_style=cb_label,
            active_color=T.ACCENT, check_color="#04140F",
            fill_color=a(0.10, T.ACCENT),
        )

        async def choose_here(e):
            got = await self.ask_dir(persist=False)
            if got is None:
                return
            self._unpack_dest = str(got)
            path_text.value = str(got)
            path_text.color = T.TEXT
            path_text.tooltip = str(got)
            path_text.update()
            if default_cb.value:
                apply_default(True, str(got))

        save_row = ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border_radius=ft.BorderRadius.all(12),
            bgcolor=T.CARD_BG,
            border=ft.Border.all(1, T.CARD_BORDER),
            content=ft.Row(
                [ft.Icon(ft.Icons.FOLDER_OPEN_ROUNDED, size=17, color=T.ACCENT),
                 txt("保存位置", S_SMALL, T.DIM),
                 path_text,
                 default_cb,
                 th.text_button("选择", lambda e: self.page.run_task(choose_here, e),
                                icon=ft.Icons.DRIVE_FILE_MOVE_ROUNDED, height=32)],
                spacing=9,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        card = ft.Container(
            width=520,
            padding=ft.Padding.only(left=20, right=20, top=18, bottom=18),
            border_radius=ft.BorderRadius.all(18),
            bgcolor=T.PANEL,
            border=ft.Border.all(1, T.PANEL_BORDER),
            shadow=ft.BoxShadow(blur_radius=40, spread_radius=-4, color=a(0.6, "#000000"),
                                offset=ft.Offset(0, 16)),
            content=ft.Column(
                [
                    ft.Row([txt("选择解包方式", S_TITLE, T.TEXT, ft.FontWeight.W_700),
                            ft.Container(expand=True),
                            th.icon_button(ft.Icons.CLOSE_ROUNDED, lambda e: self.close_dialog(),
                                           tooltip="关闭", size=18, box=34)],
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    txt(wp.title or "未命名", S_SMALL, T.FAINT, max_lines=1),
                    ft.Container(height=2),
                    save_row,
                    ft.Container(height=4),
                    *opts,
                ],
                spacing=10,
                tight=True,
            ),
        )
        return ft.Container(
            expand=True,
            bgcolor=ft.Colors.TRANSPARENT,
            on_click=lambda e: None,
            alignment=ft.Alignment.CENTER,
            content=card,
        )

    @staticmethod
    def _clean_mux_cache():
        """清掉上次异常退出留下的合成临时文件。"""
        try:
            mux = ws.CACHE_DIR / "mux"
            if not mux.is_dir():
                return
            for f in mux.iterdir():
                if f.is_file() and time.time() - f.stat().st_mtime > 3600:
                    f.unlink(missing_ok=True)
        except Exception:
            pass

    def needs_ffmpeg(self, wp: ws.Wallpaper, mode: str) -> bool:
        """这种壁纸做「画面 + 音频」时是否需要 ffmpeg 合成。"""
        if mode != "av":
            return False
        auds = self.audio_candidates(wp)
        if not auds:
            return False
        playable = [v for v in wp.videos()
                    if ws.weparser is not None and ws.weparser.is_playable_video(v)]
        if playable:
            try:
                return not ws.weparser.mp4_probe(playable[0]).get("has_audio")
            except Exception:
                return False
        return True   # 静图 + 音频 → 需要合成 mp4

    def progress_dialog(self, title: str, subtitle: str) -> dict:
        """模态进度窗：点外部不关闭，避免中途被打断。"""
        bar = ft.ProgressBar(value=0, height=8, border_radius=ft.BorderRadius.all(6),
                             color=T.ACCENT, bgcolor=a(0.14))
        pct = txt("0%", S_SMALL, T.DIM, ft.FontWeight.W_600)
        phase = txt(subtitle, S_SMALL, T.FAINT, max_lines=2)
        card = ft.Container(
            width=440,
            padding=ft.Padding.only(left=22, right=22, top=20, bottom=20),
            border_radius=ft.BorderRadius.all(18),
            bgcolor=T.PANEL,
            border=ft.Border.all(1, T.PANEL_BORDER),
            shadow=ft.BoxShadow(blur_radius=40, spread_radius=-4, color=a(0.6, "#000000"),
                                offset=ft.Offset(0, 16)),
            content=ft.Column(
                [
                    txt(title, S_TITLE, T.TEXT, ft.FontWeight.W_700),
                    phase,
                    ft.Row([ft.Container(expand=True, content=bar), pct], spacing=12,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ],
                spacing=12,
                tight=True,
            ),
        )
        # 不加蒙版；透明层挡点击，点外面关不掉
        host = ft.Stack(
            [
                ft.Container(expand=True, bgcolor=ft.Colors.TRANSPARENT,
                             on_click=lambda e: None),
                ft.Container(expand=True, alignment=ft.Alignment.CENTER, content=card),
            ],
            expand=True,
        )
        self.show_dialog(host)
        return {"bar": bar, "pct": pct, "phase": phase}

    def _progress_update(self, dlg: dict, value: float, phase: str | None = None):
        try:
            v = max(0.0, min(1.0, float(value)))
            dlg["bar"].value = v
            dlg["pct"].value = f"{int(round(v * 100))}%"
            if phase:
                dlg["phase"].value = phase
            dlg["bar"].update()
            dlg["pct"].update()
            dlg["phase"].update()
        except Exception:
            pass

    async def run_with_progress(self, title: str, subtitle: str, worker, done_text: str = "完成"):
        """在后台线程跑 worker(state)，前台刷新进度条；返回 state。"""
        dlg = self.progress_dialog(title, subtitle)
        state = {"value": 0.0, "phase": subtitle, "done": False, "error": "", "result": None}

        def run():
            try:
                state["result"] = worker(state)
            except Exception as exc:  # noqa: BLE001
                state["error"] = str(exc) or exc.__class__.__name__
                self.log(f"任务失败：{state['error']}", "error", traceback.format_exc())
            finally:
                state["done"] = True

        threading.Thread(target=run, daemon=True).start()
        last = 0.0
        while not state["done"]:
            now = time.time()
            if now - last > 0.15:
                self._progress_update(dlg, state["value"], state["phase"])
                last = now
            await asyncio.sleep(0.1)
        self._progress_update(dlg, 1.0 if not state["error"] else state["value"],
                              done_text if not state["error"] else f"失败：{state['error'][:60]}")
        await asyncio.sleep(0.3)
        self.close_dialog()
        return state
