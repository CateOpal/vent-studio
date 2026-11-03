# -*- coding: utf-8 -*-
"""录制：Wallpaper Engine 窗口、capturekit / gdigrab。"""
from __future__ import annotations

from ..compat import *  # noqa: F401,F403


class RecordMixin:
    def we_exe(self) -> str:
        d = getattr(self, "engine_dir", "") or ""
        for name in ("wallpaper64.exe", "wallpaper32.exe"):
            p = Path(d) / name
            if p.is_file():
                return str(p)
        return ""

    def record_target(self, wp: ws.Wallpaper) -> Path | None:
        """交给 Wallpaper Engine 的文件：优先 project.json，其次 scene.pkg。"""
        root = Path(str(wp.root))
        proj = root / "project.json"
        if proj.is_file():
            return proj
        pkgs = [Path(p) for p in wp.pkgs()]
        if pkgs:
            return pkgs[0]
        return root if root.is_dir() else None

    def can_record(self, wp: ws.Wallpaper) -> bool:
        return bool(self.we_exe()) and self.record_target(wp) is not None

    def record_seconds(self, wp: ws.Wallpaper) -> float:
        """录多久：配置值优先，其次跟着壁纸音频长度，最后 15 秒。"""
        try:
            cfg_s = float(self.cfg.get("rec_seconds") or 0)
        except Exception:
            cfg_s = 0.0
        if cfg_s >= 3:
            return min(REC_MAX_SECONDS, cfg_s)
        auds = self.audio_candidates(wp)
        if auds:
            dur = self._audio_seconds(auds[0])
            # 跟着音频长度走，但默认只录一小段（循环用足够，文件也不会太夸张）
            if dur > 3:
                return min(45.0, max(8.0, dur))
        return REC_DEFAULT_SECONDS

    def _audio_seconds(self, res) -> float:
        ff = find_ffmpeg()
        data = self.read_resource(res)
        if not ff or not data:
            return 0.0
        tmp = ws.CACHE_DIR / "mux"
        tmp.mkdir(parents=True, exist_ok=True)
        f = tmp / f"p_{int(time.time() * 1000)}{res.ext}"
        try:
            f.write_bytes(data)
            return self._media_duration(ff, f)
        except Exception:
            return 0.0
        finally:
            f.unlink(missing_ok=True)

    @staticmethod
    def _find_hwnd(part: str) -> int:
        """EnumWindows 找一个标题含 part 的可见窗口（不依赖 capturekit）。"""
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            found: list[int] = []

            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def cb(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                buf = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, buf, 512)
                if part in buf.value:
                    found.append(int(hwnd))
                    return False
                return True

            user32.EnumWindows(cb, 0)
            return found[0] if found else 0
        except Exception:
            return 0

    def _remember_app_window(self) -> None:
        """记下软件自己的窗口（录制开始时它一定在前台），录完/录制中把它放回最前。"""
        try:
            import ctypes

            hwnd = int(ctypes.windll.user32.GetForegroundWindow() or 0)
            if hwnd and not self._find_hwnd(REC_TITLE) == hwnd:
                self._app_hwnd = hwnd
        except Exception:
            self._app_hwnd = 0

    def _keep_app_front(self) -> None:
        """软件自己留在最前：录制窗口只在后面待着，不跟它抢焦点。"""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = int(getattr(self, "_app_hwnd", 0) or 0)
            if hwnd and user32.GetForegroundWindow() != hwnd:
                user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    @staticmethod
    def _swp(hwnd: int, insert_after: int, x: int, y: int, w: int, h: int, flags: int) -> bool:
        """SetWindowPos 的安全包装：不设 argtypes 时 64 位 HWND 会被截断成 32 位。"""
        try:
            import ctypes
            from ctypes import wintypes

            u32 = ctypes.windll.user32
            u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         ctypes.c_uint]
            u32.SetWindowPos.restype = wintypes.BOOL
            return bool(u32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(insert_after),
                                         x, y, w, h, flags))
        except Exception:
            return False

    def _prepare_record_window(self, hwnd: int) -> None:
        """录制期间把渲染窗口置顶（不激活），保证全程不被盖住、持续出帧。

        踩过的两个坑：
        - SetWindowPos(HWND_BOTTOM) 压到桌面之下 → DWM 不再合成 → WGC 拿到全黑帧。
        - 「渲染窗口留在栈里、软件压在最上面」→ 短录没问题，但整窗被盖住后引擎/DWM
          会停止出帧：录个几十秒以后画面就冻在最后一帧（声音还在走，看着像卡死）。
        所以录制时让它顶在最上面、但不抢焦点；软件自己留在后面，录完再回到最前。
        """
        if not hwnd:
            return
        try:
            import ctypes

            user32 = ctypes.windll.user32
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 4)      # SW_SHOWNOACTIVATE
                time.sleep(0.25)
            # HWND_TOPMOST=-1，同时给位置和尺寸：保证整块画面在屏幕里、不被遮挡
            self._swp(hwnd, -1, 0, 0, REC_W, REC_H, 0x0010 | 0x0040)
            # 抓一次前景：引擎在前台时会一直渲染，被盖住 / 失焦才可能停
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.35)
        except Exception:
            pass

    def _unprepare_record_window(self, hwnd: int) -> None:
        """录完把置顶还回去，并把软件自己放回最前。"""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            if hwnd:
                self._swp(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception:
            pass
        self._keep_app_front()

    def _focus_window(self, hwnd: int) -> None:
        """把渲染窗口提到最前（不抢焦点、不置顶）。被挡住拍不到画面时用它。"""
        if not hwnd:
            return
        try:
            import ctypes

            user32 = ctypes.windll.user32
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 4)      # SW_SHOWNOACTIVATE
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # HWND_TOP
            time.sleep(0.3)
        except Exception:
            pass

    def _ensure_visible(self, hwnd: int) -> None:
        """录制途中用户最小化了窗口就还原，并重新顶到最上，防止被盖住后不再出帧。"""
        if not hwnd:
            return
        try:
            import ctypes

            user32 = ctypes.windll.user32
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 4)      # SW_SHOWNOACTIVATE：还原但不抢焦点
                time.sleep(0.2)
            # 每秒重申一次「置顶 + 不激活 + 不动位置尺寸」
            self._swp(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
            # 引擎在「不是前台」时可能自己停渲染，录制期间让它保持前台
            if user32.GetForegroundWindow() != hwnd:
                user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _video_real_end(self, path: Path) -> float:
        """画面最后一帧的真实时间（秒），拿不到返回 -1。

        容器的 mvhd 时长可能是错的：capturekit 写出来的时长会比实际帧长很多，
        直接拿来当截断长度，播放器就会把最后一帧一路挂到结尾（看着像卡死）。
        只有把流 demux 一遍（-c copy 到 null）才知道画面真正到哪一秒。
        """
        ff = find_ffmpeg()
        if not ff:
            return -1.0
        try:
            proc = subprocess.run(
                [ff, "-v", "error", "-i", str(path), "-map", "0:v:0", "-c", "copy",
                 "-f", "null", "-progress", "pipe:1", "-nostats", "-"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=600)
        except Exception:
            return -1.0
        end = -1.0
        for line in (proc.stdout or "").splitlines():
            if line.startswith("out_time_us="):
                v = line.split("=", 1)[1].strip()
                if v.isdigit():
                    end = int(v) / 1_000_000
        return end

    def _trim_clip(self, path: Path, seconds: float) -> bool:
        """把视频容器硬截到 seconds 秒（-c copy，不重编码）。"""
        if seconds <= 0.5:
            return False
        ff = find_ffmpeg()
        if not ff:
            return False
        out = path.with_name(path.stem + "_trim" + path.suffix)
        try:
            proc = subprocess.run(
                [ff, "-y", "-loglevel", "error", "-i", str(path), "-t", f"{seconds:.3f}",
                 "-c", "copy", "-movflags", "+faststart", str(out)],
                capture_output=True, timeout=600)
            if proc.returncode == 0 and out.is_file() and out.stat().st_size > 8192:
                out.replace(path)
                return True
        except Exception:
            pass
        out.unlink(missing_ok=True)
        return False

    def _clip_frame_count(self, path: Path) -> int:
        """数一下视频里到底有多少帧；拿不到返回 -1。

        容器时长可能还是录满的，但帧早就停了（画面冻在最后一帧），只能数帧才看得出来。
        """
        ff = find_ffmpeg()
        if not ff:
            return -1
        try:
            proc = subprocess.run(
                [ff, "-v", "error", "-i", str(path), "-map", "0:v:0", "-c", "copy",
                 "-f", "null", "-progress", "pipe:1", "-nostats", "-"],
                capture_output=True, text=True, timeout=300)
        except Exception:
            return -1
        frames = -1
        for line in (proc.stdout or "").splitlines():
            if line.startswith("frame="):
                try:
                    frames = int(line.split("=", 1)[1])
                except ValueError:
                    continue
        return frames

    @staticmethod
    def _window_alive(hwnd: int) -> bool:
        """渲染窗口还在不在：用户强关 / 引擎崩了就该立刻报错，不能继续装成在录。"""
        if not hwnd:
            return False
        try:
            import ctypes

            return bool(ctypes.windll.user32.IsWindow(hwnd))
        except Exception:
            return True

    def _clip_black(self, path: Path, dur: float) -> bool:
        """录出来是不是纯黑（Windows Graphics Capture 跨完整性级别时会返回黑帧）。"""
        ff = find_ffmpeg()
        if not ff:
            return False
        try:
            from PIL import Image

            for pos in (min(2.0, max(0.6, dur * 0.2)), max(0.8, dur * 0.7)):
                cmd = [ff, "-loglevel", "error", "-ss", f"{pos:.2f}", "-i", str(path),
                       "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"]
                proc = subprocess.run(cmd, capture_output=True, timeout=90)
                if proc.returncode != 0 or not proc.stdout:
                    continue
                with Image.open(io.BytesIO(proc.stdout)) as im:
                    # 按「亮点占比」判断：黑帧压缩后仍有 1~2 的噪点，不能只看 std
                    small = im.convert("L").resize((64, 36))
                    vals = list(small.tobytes())
                    lit = sum(1 for v in vals if v > 18) / float(len(vals))
                    mean = sum(vals) / float(len(vals))
                    if lit > 0.01 and mean > 2.5:
                        return False
            return True
        except Exception:
            return False

    def _record_window(self, dur: float, raw: Path, state: dict) -> bool:
        """等窗口出现 → 先 capturekit（能录非前台窗口），失败再退 ffmpeg gdigrab。"""
        hwnd = 0
        waited = 0.0
        while waited < 12.0:
            hwnd = self._find_hwnd(REC_TITLE)
            if hwnd:
                break
            state["phase"] = "等待 Wallpaper Engine 窗口…"
            time.sleep(0.4)
            waited += 0.4
        if not hwnd:
            return False
        # 渲染窗口置顶（不激活）：被盖住时引擎/DWM 会停止出帧，画面就冻住
        self._prepare_record_window(hwnd)
        state["phase"] = "录制中…（请不要最小化壁纸窗口）"
        ok = self._record_capturekit(dur, raw, state, hwnd)
        if state.get("aborted"):
            raw.unlink(missing_ok=True)
            raise RuntimeError(state["aborted"])
        if ok and self._clip_black(raw, dur):
            # 被软件整个盖住时 DWM 可能不给它合成画面 → 只把它提到最前（不抢焦点）再录一次
            state["phase"] = "窗口被挡住拍不到画面，把壁纸窗口提到最前重录…"
            raw.unlink(missing_ok=True)
            self._focus_window(hwnd)
            ok = self._record_capturekit(dur, raw, state, hwnd)
            self._keep_app_front()
            if state.get("aborted"):
                raw.unlink(missing_ok=True)
                raise RuntimeError(state["aborted"])
        if ok and self._clip_black(raw, dur):
            # WGC 拿不到别的进程画面时会给一整段黑帧，换成桌面截图重录
            state["phase"] = "首段录制是黑屏，改用桌面截图重录…"
            raw.unlink(missing_ok=True)
            ok = False
        if not ok:
            raw.unlink(missing_ok=True)
            if not self._window_alive(hwnd):
                raise RuntimeError("录制窗口被关闭了（录制提前结束），请重新录制")
            self._focus_window(hwnd)
            ok = self._record_gdigrab(dur, raw, state)
            self._keep_app_front()
            if not self._window_alive(hwnd):
                raw.unlink(missing_ok=True)
                raise RuntimeError("录制窗口被关闭了（录制提前结束），请重新录制")
        if not ok:
            return False
        if self._clip_black(raw, dur):
            raw.unlink(missing_ok=True)
            raise RuntimeError(
                "录制结果是黑屏：系统不允许抓取这个窗口画面"
                + ("（当前是低权限运行，请自己双击启动程序再试）"
                   if getattr(self, "low_privilege", False) else ""))
        # 帧流中途断掉时容器照样录满时长，但画面会冻在最后一帧 → 用真实帧尾判断
        end = self._video_real_end(raw)
        if end >= 0 and end < dur - 1.0:
            # 再给一次机会：把渲染窗口重新顶到最前、重录一遍
            state["phase"] = f"画面在 {end:.0f}s 就停了，重新顶到最前再录一次…"
            self.log(f"首段录制在第 {end:.1f}s 后停帧（目标 {dur:.0f}s），重录一次", "warn")
            raw.unlink(missing_ok=True)
            self._prepare_record_window(hwnd)
            ok = self._record_capturekit(dur, raw, state, hwnd)
            if ok and self._clip_black(raw, dur):
                raw.unlink(missing_ok=True)
                ok = False
            end2 = self._video_real_end(raw) if ok else -1
            if not ok:
                raw.unlink(missing_ok=True)
                raise RuntimeError("重录也失败了：壁纸窗口没有出画面")
            if end2 >= 0 and end2 < dur - 1.0:
                # 两次都提前停：按实际长度导出（短的但流畅，好过冻住的）
                self.log(f"重录仍在第 {end2:.1f}s 停帧，按实际长度导出", "warn")
        return True

    def _log_record_stats(self, res, dur: float) -> None:
        """把 capturekit 的统计写进日志：下次再出问题能直接看出是哪一环断的。"""
        try:
            st = getattr(res, "stats", None)
            v = getattr(st, "video", None) if st else None
            err = getattr(res, "error", None)
            parts = [f"状态={getattr(getattr(st, 'state', None), 'name', st and getattr(st, 'state', None))}",
                     f"容器={getattr(st, 'media_duration_s', 0) or 0:.1f}s",
                     f"实际耗时={getattr(st, 'wall_elapsed_s', 0) or 0:.1f}s",
                     f"目标={dur:.0f}s"]
            if v is not None:
                parts += [f"帧槽={v.slots}", f"新帧={v.frames_new}",
                          f"重复帧={v.frames_duplicated}", f"丢帧={v.frames_dropped}",
                          f"迟到={v.frames_late}", f"队列峰值={v.queue_depth_max}",
                          f"编码最慢={v.encoder_write_ms_max:.0f}ms",
                          f"丢目标={bool(v.target_lost)}"]
            line = " · ".join(parts)
            if err:
                line += f" · 错误={err!r}"
            self.log("录制统计：" + line, "warn" if err or (v and v.target_lost) else "debug")
        except Exception:
            pass

    def _record_capturekit(self, dur: float, raw: Path, state: dict,
                           hwnd: int = 0) -> bool:
        try:
            import capturekit as ck
        except Exception:
            return False
        target = None
        try:
            for _ in range(24):
                for w in ck.list_windows():
                    if REC_TITLE in str(getattr(w, "title", "") or ""):
                        target = w
                        break
                if target is not None:
                    break
                time.sleep(0.4)
        except Exception:
            return False
        if target is None:
            return False
        rec = None
        try:
            # 第二个参数是音频源：留空 = 只录画面，声音后期用 ffmpeg 从壁纸资源里合成
            rec = ck.Recorder(ck.WindowSource(target, client_area_only=True), (),
                              str(raw), ck.RecordingConfig(fps=30),
                              on_error=lambda _m: None)
            rec.start()
            steps = max(1, int(dur * 10))
            last_slots = -1
            stall = 0.0
            fixes = 0
            for i in range(steps):
                time.sleep(0.1)
                # 每 0.5 秒看一眼输出帧数是否还在涨：停了就把窗口重新顶到最前
                if i % 5 == 0:
                    try:
                        st_now = rec.stats()
                        slots = st_now.video.slots if st_now.video else -1
                    except Exception:
                        slots = -1
                    if slots >= 0:
                        stall = stall + 0.5 if slots == last_slots else 0.0
                        last_slots = slots
                        if stall >= 2.0 and fixes < 3:
                            fixes += 1
                            stall = 0.0
                            self.log(f"录制中帧流停了 2 秒（第 {i / 10:.0f}s），重新顶窗口", "warn")
                            self._prepare_record_window(hwnd)
                # 窗口被强制关掉：立刻中止，别让进度条继续骗人
                if not self._window_alive(hwnd):
                    state["aborted"] = ("录制窗口被关闭了（录制提前结束）"
                                        f"，已录 {i * 0.1:.0f}s / {dur:.0f}s")
                    try:
                        rec.stop()
                    except Exception:
                        pass
                    rec = None
                    raw.unlink(missing_ok=True)
                    return False
                frac = (i + 1) / steps
                state["value"] = 0.12 + 0.70 * frac
                state["phase"] = (f"录制中  {dur * frac:.0f}s / {dur:.0f}s"
                                  + " · 请不要最小化窗口")
                if i % 10 == 0:
                    self._ensure_visible(hwnd)
            try:
                res = rec.stop()
                self._log_record_stats(res, dur)
            except Exception:
                pass
            rec = None
        except Exception:
            return False
        finally:
            if rec is not None:
                try:
                    rec.stop()
                except Exception:
                    pass
        return raw.is_file() and raw.stat().st_size > 8192

    def _record_gdigrab(self, dur: float, raw: Path, state: dict) -> bool:
        ff = find_ffmpeg()
        if not ff:
            return False
        self._ensure_visible(self._find_hwnd(REC_TITLE))
        # -an：只录画面，不录系统声音（音轨后期由 _mux 用壁纸自带音频合成）
        cmd = [ff, "-y", "-loglevel", "error", "-f", "gdigrab", "-framerate", "30",
               "-i", f"title={REC_TITLE}", "-t", f"{dur:.2f}", "-an",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(raw)]
        ok = self._run_ffmpeg_progress(cmd, dur, state, "录制中（请不要最小化窗口）",
                                       lo=0.12, hi=0.82)
        return bool(ok and raw.is_file() and raw.stat().st_size > 8192)

    def _close_we_window(self, exe: str, target: Path) -> None:
        """收尾：先让引擎关掉壁纸，再把残留的渲染窗口关掉。"""
        try:
            subprocess.Popen([exe, "-control", "closeWallpaper", "-file", str(target)])
        except Exception:
            pass
        # 引擎一般会自己把窗口收掉，留 1.8 秒给它
        for _ in range(6):
            time.sleep(0.3)
            if not self._find_hwnd(REC_TITLE):
                return
        hwnd = self._find_hwnd(REC_TITLE)
        if not hwnd:
            return
        try:
            import ctypes

            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)       # WM_CLOSE
        except Exception:
            pass
        for _ in range(5):
            time.sleep(0.25)
            if not self._find_hwnd(REC_TITLE):
                return
        try:
            import ctypes

            ctypes.windll.user32.DestroyWindow(self._find_hwnd(REC_TITLE))
        except Exception:
            pass

    def _record_worker(self, wp: ws.Wallpaper, state: dict) -> Path:
        exe = self.we_exe()
        target = self.record_target(wp)
        if not exe:
            raise RuntimeError("没有找到 wallpaper64.exe（Wallpaper Engine 未安装）")
        if target is None:
            raise RuntimeError("壁纸目录不存在，无法录制")
        dur = self.record_seconds(wp)
        tmp = ws.CACHE_DIR / "mux"
        tmp.mkdir(parents=True, exist_ok=True)
        raw = tmp / f"rec_{int(time.time() * 1000)}.mp4"
        state["phase"] = "启动 Wallpaper Engine 渲染窗口…"
        state["value"] = 0.05
        self.log(f"开始录制「{wp.title}」{dur:.0f} 秒…", "info")
        # 记下软件自己的窗口：录制窗口只在后面待着，软件全程留在最前
        self._remember_app_window()
        try:
            subprocess.Popen([exe, "-control", "openWallpaper", "-file", str(target),
                              "-playInWindow", REC_TITLE,
                              "-width", str(REC_W), "-height", str(REC_H)])
        except Exception as exc:
            raise RuntimeError(f"无法启动 Wallpaper Engine：{exc}")
        try:
            ok = self._record_window(dur, raw, state)
        finally:
            self._unprepare_record_window(self._find_hwnd(REC_TITLE))
            state["phase"] = "录制结束，正在关闭壁纸窗口…"
            state["value"] = 0.84
            self._close_we_window(exe, target)
        if not ok or not raw.is_file() or raw.stat().st_size < 8192:
            raw.unlink(missing_ok=True)
            raise RuntimeError("录制失败：壁纸窗口没有出现或被其它窗口盖住了")
        # 画面真正录到第几秒：容器写的时长不可信，必须 demux 一遍
        end = self._video_real_end(raw)
        self._last_record_dur = float(dur)
        self._last_record_end = end
        cap = min(float(dur), end) if end > 0 else float(dur)
        if end > 0 and end < dur - 1.0:
            self.log(f"画面在第 {end:.1f}s 就停了（目标 {dur:.0f}s），按实际长度导出", "warn")
        # 容器时长比真实帧尾长的话，播放器会把最后一帧一路挂到结尾 → 硬截掉
        try:
            container = float(ws.weparser.mp4_duration(raw) or 0)
        except Exception:
            container = 0.0
        if container > cap + 0.2 and self._trim_clip(raw, cap):
            self.log(f"已把视频截到 {cap:.1f}s（容器原本写了 {container:.1f}s）", "debug")
        self.log(f"录制完成：{raw.name}（{raw.stat().st_size // 1024} KB）", "info")
        state["value"] = 0.86
        state["phase"] = "录制完成，准备写入…"
        return raw
