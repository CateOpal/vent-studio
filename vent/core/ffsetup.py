# -*- coding: utf-8 -*-
"""FFmpeg 按需安装。

安装包里不再塞 100 MB 的静态 ffmpeg：第一次需要合成音视频时提示下载，
也可以提前在设置里点「下载」。

下载源有两个，自动切换：
  1. 国内镜像（阿里云 npmmirror，转的是 gyan.dev 的官方 essentials 构建）；
  2. 官方源（gyan.dev）。
每个源都会测速：开了 6 秒还跑不到 300 KB/s 就判定"太慢"，直接换下一个；
上次下成功的源会记下来，下次优先用它。
落地是 data\bin\ffmpeg.exe，之后当本地文件用。
"""
from __future__ import annotations

import gzip
import shutil
import ssl
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from ..paths import data_dir

# 顺序即优先级；"fmt" 决定怎么解包（gz 是裸 exe 的 gzip，zip 是构建包）
SOURCES: list[dict] = [
    {
        "id": "npmmirror",
        "label": "国内镜像",
        "fmt": "gz",
        "url": "https://registry.npmmirror.com/-/binary/ffmpeg-static/b6.1.1/ffmpeg-win32-x64.gz",
    },
    {
        "id": "gyan",
        "label": "官方源",
        "fmt": "zip",
        "url": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    },
]

CHUNK = 1 << 18
MIN_EXE_BYTES = 5 << 20
SLOW_SECONDS = 6.0            # 多久之后开始判定"太慢"
MIN_SPEED = 300 * 1024        # 低于 300 KB/s 换源
STALL_SECONDS = 20            # 连续这么久没有新数据也换源
SOURCE_MEMO = "ffmpeg-source.txt"


class SlowSource(Exception):
    """这个源太慢，换下一个。"""

    def __init__(self, speed: float):
        super().__init__(f"{speed / 1024:.0f} KB/s")
        self.speed = speed


def target_exe() -> Path:
    """下载后落地位置。"""
    return data_dir() / "bin" / "ffmpeg.exe"


def _contexts():
    """先试证书校验（有 certifi 就用它），失败再退回不校验——国内网络常被中间证书坑。"""
    try:
        import certifi

        yield ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        yield ssl.create_default_context()
    except Exception:
        pass
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    yield ctx


def _memo_path() -> Path:
    return data_dir() / "cache" / SOURCE_MEMO


def _read_memo() -> str:
    try:
        return _memo_path().read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _write_memo(source_id: str) -> None:
    try:
        p = _memo_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(source_id, encoding="utf-8")
    except Exception:
        pass


def ordered_sources() -> list[dict]:
    """上次成功的源排最前面，其余保持默认顺序。"""
    good = _read_memo()
    if not good:
        return list(SOURCES)
    hit = [s for s in SOURCES if s["id"] == good]
    return hit + [s for s in SOURCES if s["id"] != good]


def _download(url: str, dest: Path, progress: Callable[[int, int], None] | None) -> None:
    """下载到 dest；太慢就抛 SlowSource，网络错误抛原异常。"""
    last: Exception | None = None
    for ctx in _contexts():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Vent-Studio/1.0"})
            with urllib.request.urlopen(req, timeout=STALL_SECONDS, context=ctx) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                started = last_data = time.time()
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as fh:
                    while True:
                        buf = resp.read(CHUNK)
                        if not buf:
                            break
                        fh.write(buf)
                        done += len(buf)
                        now = time.time()
                        last_data = now
                        if progress:
                            try:
                                progress(done, total)
                            except Exception:
                                pass
                        elapsed = now - started
                        if elapsed >= SLOW_SECONDS:
                            speed = done / elapsed
                            finishing = total and done >= total * 0.92
                            if speed < MIN_SPEED and not finishing:
                                raise SlowSource(speed)
                        if now - last_data > STALL_SECONDS:
                            raise SlowSource(done / max(now - started, 0.01))
            if done <= 0:
                raise IOError("没有收到数据")
            return
        except SlowSource:
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
            raise
        except Exception as exc:  # 换下一个 SSL 策略
            last = exc
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
            continue
    raise last or IOError("下载失败")


def _looks_like_exe(path: Path) -> bool:
    try:
        if path.stat().st_size < MIN_EXE_BYTES:
            return False
        with open(path, "rb") as fh:
            return fh.read(2) == b"MZ"
    except Exception:
        return False


def _extract(src: Path, fmt: str) -> Path | None:
    """把下载回来的东西变成 data\\bin\\ffmpeg.exe。"""
    dest = target_exe()
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if fmt == "gz":
            with gzip.open(src, "rb") as fin, open(dest, "wb") as out:
                shutil.copyfileobj(fin, out, 1 << 20)
        elif fmt == "zip":
            with zipfile.ZipFile(src) as zf:
                pick = None
                for name in zf.namelist():
                    low = name.replace("\\", "/").lower()
                    if not low.endswith("ffmpeg.exe"):
                        continue
                    if "ffprobe" in low or "ffplay" in low:
                        continue
                    pick = name
                    break
                if pick is None:
                    return None
                with zf.open(pick) as fin, open(dest, "wb") as out:
                    shutil.copyfileobj(fin, out, 1 << 20)
        else:  # 直接就是 exe
            shutil.copyfile(src, dest)
    except Exception:
        return None
    return dest if _looks_like_exe(dest) else None


def download(progress: Callable[[int, int], None] | None = None,
             note: Callable[[str], None] | None = None,
             on_source: Callable[[str], None] | None = None) -> Path:
    """下载并安装 ffmpeg，返回 exe 路径；全失败时抛 RuntimeError。

    progress(done, total)：字节进度；note(text)：阶段提示；on_source(label)：当前源。
    """
    existing = target_exe()
    if _looks_like_exe(existing):
        return existing

    cache = data_dir() / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    sources = ordered_sources()
    for idx, src in enumerate(sources):
        label = src["label"]
        if on_source:
            try:
                on_source(label)
            except Exception:
                pass
        if note:
            try:
                note(f"正在从{label}下载…")
            except Exception:
                pass
        tmp = cache / f"ffmpeg-download.{src['fmt']}"
        try:
            _download(src["url"], tmp, progress)
        except SlowSource as exc:
            errors.append(f"{label}太慢（{exc}）")
            if idx + 1 < len(sources) and note:
                try:
                    note(f"{label}太慢，换{ordered_sources()[idx + 1]['label']}…")
                except Exception:
                    pass
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}失败（{str(exc)[:60]}）")
            continue
        if note:
            try:
                note("正在解压…")
            except Exception:
                pass
        exe = _extract(tmp, src["fmt"])
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        if exe is not None:
            _write_memo(src["id"])
            return exe
        errors.append(f"{label}下载的文件里没有 ffmpeg.exe")
    raise RuntimeError("；".join(errors) or "下载失败")
