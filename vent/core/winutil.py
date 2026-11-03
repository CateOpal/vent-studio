# -*- coding: utf-8 -*-
"""Windows 外壳交互：在资源管理器里定位 / 打开、启动进程。"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

EXPLORE_ERROR = ""     # 上一次打开资源管理器失败的原因（写进日志方便排查）


def process_integrity_rid() -> int:
    """当前进程的完整性级别 RID（Medium=0x2000，Low=0x1000）。

    Low 级别下 Windows 会挡掉截屏 API 和 shell 启动：录制出来是黑帧、
    资源管理器也打不开。启动时用它给一句人话提示，省得以为是程序坏了。
    """
    try:
        import ctypes
        from ctypes import wintypes

        adv = ctypes.windll.advapi32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        TOKEN_QUERY = 0x0008
        TokenIntegrityLevel = 25
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                         ctypes.POINTER(wintypes.HANDLE)]
        h = wintypes.HANDLE()
        if not adv.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY,
                                    ctypes.byref(h)):
            return 0
        try:
            need = wintypes.DWORD(0)
            adv.GetTokenInformation(h, TokenIntegrityLevel, None, 0, ctypes.byref(need))
            buf = ctypes.create_string_buffer(max(64, need.value))
            if not adv.GetTokenInformation(h, TokenIntegrityLevel, buf, need.value,
                                           ctypes.byref(need)):
                return 0
            # TOKEN_MANDATORY_LABEL = { SID_AND_ATTRIBUTES { PSID Sid; DWORD Attrs } }
            sid_ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
            sub_auths = ctypes.cast(sid_ptr, ctypes.POINTER(ctypes.c_ubyte))
            count = sub_auths[1]
            raw = bytes(sub_auths[0:8 + max(1, count) * 4])
            rid = 0
            for i in range(max(1, count)):
                off = 8 + i * 4
                rid = int.from_bytes(raw[off:off + 4], "little")
            return rid
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        return 0


def _explorer_window_titled(name: str) -> bool:
    """有没有标题里带这个路径的 Explorer 窗口（用来确认「真的打开了」）。"""
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        needle = (name or "").lower().strip()
        if not needle:
            return False
        found: list[bool] = []

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        PROCESS_QUERY_LIMITED = 0x1000

        def _owner_is_explorer(hwnd) -> bool:
            pid = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid.value)
            if not h:
                return False
            try:
                size = ctypes.c_ulong(1024)
                buf = ctypes.create_unicode_buffer(1024)
                if not kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    return False
                return buf.value.lower().endswith("explorer.exe")
            finally:
                kernel32.CloseHandle(h)

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)  # type: ignore[attr-defined]
        def _cb(hwnd, _lp):
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if needle in buf.value.lower() and _owner_is_explorer(hwnd):
                found.append(True)
                return False
            return True

        user32.EnumWindows(_cb, 0)
        return bool(found)
    except Exception:
        return False


def _start_via_cmd(path: str, confirm_name: str = "", timeout: float = 2.4) -> bool:
    """`cmd /c start` 兜底：受限令牌 / 无交互桌面时，这条也常常能真把窗口叫出来。

    DETACHED_PROCESS 是关键——不继承本进程的控制台，start 才会真正交给 shell。
    """
    try:
        subprocess.Popen(  # noqa: S603,S607
            ["cmd", "/c", "start", "", path],
            creationflags=0x00000008,      # DETACHED_PROCESS
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except Exception:
        return False
    if not confirm_name:
        return True
    end = time.time() + timeout
    while time.time() < end:
        if _explorer_window_titled(confirm_name):
            return True
        time.sleep(0.2)
    return False


def _spawn_explorer(args: list[str]) -> bool:
    """起一个 explorer 进程；失败（起不来 / 立刻异常退出）返回 False。"""
    try:
        proc = subprocess.Popen(args)  # noqa: S603,S607
    except Exception:
        return False
    try:
        code = proc.wait(timeout=2.0)
    except Exception:
        return True          # 还在跑 = 交给 shell 转交了
    return code in (0, 1)    # explorer 正常会返回 0/1；0xC0000142 之类算失败


def open_in_explorer(path: str | Path) -> bool:
    """用资源管理器打开目录 / 定位文件，成功返回 True。

    依次尝试四条路，任何一条成功就返回：
      1) explorer 命令行（/select, 定位文件）—— 最常见、最稳
      2) ShellExecuteW "open"
      3) ShellExecuteW "explore"（部分环境只认这个动词）
      4) os.startfile（受限令牌环境会抛 WinError 5）
    失败原因记到 EXPLORE_ERROR，调用方可以在日志里看到到底哪一步不行。
    """
    global EXPLORE_ERROR
    p = Path(path)
    if not p.exists():
        EXPLORE_ERROR = f"路径不存在：{path}"
        return False
    target = str(p)
    is_dir = p.is_dir()
    sel = [target] if is_dir else ["/select,", target]
    errors: list[str] = []

    # 1) explorer 命令行（带 /select, 能直接定位到文件）
    for cmd in (["explorer"] + sel, ["explorer.exe"] + sel):
        try:
            if _spawn_explorer(cmd):
                EXPLORE_ERROR = ""
                return True
            errors.append(" ".join(cmd[:2]) + " 失败")
        except Exception as exc:
            errors.append(f"explorer 命令行: {exc}")

    # 2/3) ShellExecuteW 两个动词
    for verb in ("open", "explore"):
        try:
            import ctypes

            target_arg = target if (is_dir or verb == "explore") else target
            rc = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
                None, verb, target_arg, None, None, 1)
            if int(rc) > 32:
                EXPLORE_ERROR = ""
                return True
            errors.append(f"ShellExecuteW({verb}) 返回 {int(rc)}")
        except Exception as exc:
            errors.append(f"ShellExecuteW({verb}): {exc}")

    # 4) os.startfile
    try:
        os.startfile(target if is_dir else str(p.parent))  # noqa: S606
        EXPLORE_ERROR = ""
        return True
    except Exception as exc:
        errors.append(f"startfile: {exc}")

    # 5) 最后的兜底：cmd /c start（DETACHED），并确认真的冒出一个对应标题的窗口
    fallback_target = target if is_dir else str(p.parent)
    confirm = Path(fallback_target).name or fallback_target
    if _start_via_cmd(fallback_target, confirm):
        EXPLORE_ERROR = ""
        return True
    errors.append("cmd start 没叫出窗口")

    EXPLORE_ERROR = "；".join(errors) or "未知原因"
    return False


def open_with_system(path: str | Path) -> bool:
    """用系统默认程序打开文件（外部播放器），成功返回 True。"""
    target = str(path)
    try:
        import ctypes

        rc = ctypes.windll.shell32.ShellExecuteW(None, "open", target, None, None, 1)  # type: ignore[attr-defined]
        if int(rc) > 32:
            return True
    except Exception:
        pass
    try:
        os.startfile(target)  # noqa: S606
        return True
    except Exception:
        pass
    # 受限环境兜底：交给 cmd start，让 shell 去挑默认程序
    try:
        if Path(target).is_file():
            return _start_via_cmd(target)
    except Exception:
        pass
    return False


def file_uri(path) -> str:
    """视频必须用 file:// URI 交给媒体内核；直接给本地路径只会出一张静帧。"""
    try:
        return Path(path).resolve().as_uri()
    except Exception:
        return str(path)
