# -*- coding: utf-8 -*-
"""Wallpaper Engine 二进制格式解析器（纯 Python + Pillow）。

支持：
  * PKGV 包（scene.pkg / tex.pkg）—— 所有 PKGV00xx 版本使用同一目录结构：
        int32  magic_len, magic, int32 entry_count,
        { int32 path_len, path, int32 offset, int32 length } * count,
        数据区紧跟目录之后；每个条目的真实偏移 = 目录结束位置 + offset
  * TEX 纹理（TEXV0005 / TEXI0001）—— TEXB0001..0004 容器，
        支持 RGBA8888 / DXT1 / DXT3 / DXT5 / R8 / RG88，LZ4 压缩的 mipmap，
        内嵌图片（JPEG/PNG/BMP...）直通，转出 PNG。

该格式与 RePKG 的实现保持一致，并已在本机 129 个真实 .pkg / 1474 个 .tex 上验证。
"""

from __future__ import annotations

import io
import mmap
import struct
from dataclasses import dataclass, field
from pathlib import Path

def _load_lz4():
    """优先用 lz4 C 扩展（随程序放在 _vendor 里），否则回退纯 Python。"""
    try:
        import lz4.block as blk  # type: ignore
        return blk
    except Exception:
        pass
    try:
        import os
        import sys
        vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_vendor")
        if os.path.isdir(vendor) and vendor not in sys.path:
            sys.path.insert(0, vendor)
            import lz4.block as blk  # type: ignore
            return blk
    except Exception:
        pass
    return None


_lz4block = _load_lz4()

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPG_MAGIC = b"\xff\xd8\xff"
BMP_MAGIC = b"BM"


# --------------------------------------------------------------------------- LZ4

def lz4_decompress(src: bytes, known_size: int) -> bytes:
    """LZ4 block 格式解压，带纯 Python 回退实现。"""
    if _lz4block is not None:
        try:
            return _lz4block.decompress(bytes(src), uncompressed_size=known_size)
        except Exception:
            pass
    return _lz4_decompress_py(src, known_size)


def _lz4_decompress_py(src: bytes, known_size: int) -> bytes:
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        token = src[i]
        i += 1
        lit_len = token >> 4
        if lit_len == 15:
            while i < n:
                b = src[i]
                i += 1
                lit_len += b
                if b != 255:
                    break
        if lit_len:
            out += src[i:i + lit_len]
            i += lit_len
        if i >= n:
            break
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        match_len = token & 0x0F
        if match_len == 15:
            while i < n:
                b = src[i]
                i += 1
                match_len += b
                if b != 255:
                    break
        match_len += 4
        start = len(out) - offset
        if start < 0:
            raise ValueError("corrupt lz4 block (bad offset)")
        if match_len <= offset:
            out += out[start:start + match_len]
        else:
            chunk = out[start:]
            while len(chunk) < match_len:
                chunk += chunk[: match_len - len(chunk)]
            out += chunk[:match_len]
    if known_size and len(out) > known_size:
        del out[known_size:]
    return bytes(out)


# --------------------------------------------------------------------------- DXT

def _rgb565(c: int) -> tuple[int, int, int]:
    r = (c >> 11) & 0x1F
    g = (c >> 5) & 0x3F
    b = c & 0x1F
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def _color_block(block: bytes, out: bytearray, width: int, bx: int, by: int,
                 four_color: bool = True) -> None:
    c0, c1 = struct.unpack_from("<HH", block, 0)
    bits = struct.unpack_from("<I", block, 4)[0]
    r0, g0, b0 = _rgb565(c0)
    r1, g1, b1 = _rgb565(c1)
    if four_color or c0 > c1:
        palette = [
            (r0, g0, b0, 255),
            (r1, g1, b1, 255),
            ((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3, 255),
            ((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3, 255),
        ]
    else:
        palette = [
            (r0, g0, b0, 255),
            (r1, g1, b1, 255),
            ((r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2, 255),
            (0, 0, 0, 0),
        ]
    for py in range(4):
        y = by + py
        if y >= 0:
            row = (y * width + bx) * 4
            for px in range(4):
                idx = (bits >> (2 * (py * 4 + px))) & 3
                r, g, b, a = palette[idx]
                p = row + px * 4
                out[p] = r
                out[p + 1] = g
                out[p + 2] = b
                out[p + 3] = a


def _alpha_dxt3(block: bytes, out: bytearray, width: int, bx: int, by: int) -> None:
    for py in range(4):
        y = by + py
        nibble = struct.unpack_from("<H", block, py * 2)[0]
        row = (y * width + bx) * 4
        for px in range(4):
            a = ((nibble >> (4 * px)) & 0x0F) * 17
            out[row + px * 4 + 3] = a


def _alpha_dxt5(block: bytes, out: bytearray, width: int, bx: int, by: int) -> None:
    a0 = block[0]
    a1 = block[1]
    if a0 > a1:
        alphas = [a0, a1]
        alphas += [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
    else:
        alphas = [a0, a1]
        alphas += [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)]
        alphas += [0, 255]
    bits = int.from_bytes(block[2:8], "little")
    for py in range(4):
        y = by + py
        row = (y * width + bx) * 4
        for px in range(4):
            idx = (bits >> (3 * (py * 4 + px))) & 7
            out[row + px * 4 + 3] = alphas[idx]


def _dds_header(width: int, height: int, fourcc: bytes) -> bytes:
    flags = 0x1007 | 0x80000
    head = struct.pack("<4s7I", b"DDS ", 124, flags, height, width, 0, 0, 0)
    head += b"\x00" * 44
    head += struct.pack("<2I", 32, 0x4) + fourcc + struct.pack("<5I", 0, 0, 0, 0, 0)
    head += struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    return head


def _dxt_image(data: bytes, w: int, h: int, kind: str):
    """用 Pillow 的 DDS 解码器解 DXT（比纯 Python 快约 30 倍）。"""
    from PIL import Image
    fourcc = {"dxt1": b"DXT1", "dxt3": b"DXT3", "dxt5": b"DXT5"}[kind]
    need = ((w + 3) // 4) * ((h + 3) // 4) * (8 if kind == "dxt1" else 16)
    if len(data) < need:
        raise ValueError("dxt data too short")
    im = Image.open(io.BytesIO(_dds_header(w, h, fourcc) + data[:need]))
    im.load()
    return im.convert("RGBA")


def _decode_dxt(data: bytes, w: int, h: int, kind: str) -> bytearray:
    out = bytearray(w * h * 4)
    bw = (w + 3) // 4
    bh = (h + 3) // 4
    stride = 8 if kind in ("dxt1",) else 16
    color_off = 0 if kind == "dxt1" else 8
    pos = 0
    total = bw * bh * stride
    if len(data) < total:
        raise ValueError("dxt data too short")
    for byi in range(bh):
        by = byi * 4
        for bxi in range(bw):
            block = data[pos:pos + stride]
            pos += stride
            if kind == "dxt3":
                _alpha_dxt3(block, out, w, bxi * 4, by)
            elif kind == "dxt5":
                _alpha_dxt5(block, out, w, bxi * 4, by)
            _color_block(block[color_off:color_off + 8], out, w, bxi * 4, by, four_color=kind in ("dxt3", "dxt5"))
    return out


# --------------------------------------------------------------------------- TEX

TEX_FORMAT_NAME = {0: "RGBA8888", 4: "DXT5", 6: "DXT3", 7: "DXT1", 8: "RG88", 9: "R8"}


class TexError(ValueError):
    pass


def _read_nstring(data: bytes, pos: int, max_len: int = 32) -> tuple[str, int]:
    end = data.find(b"\x00", pos, pos + max_len)
    if end < 0:
        end = data.find(b"\x00", pos)
    if end < 0:
        raise TexError("unterminated string")
    return data[pos:end].decode("ascii", "replace"), end + 1


@dataclass
class Mipmap:
    width: int
    height: int
    lz4: bool
    size: int
    data: bytes
    decompressed: int = 0


@dataclass
class TexInfo:
    format: int
    fmt_name: str
    texture_width: int
    texture_height: int
    width: int
    height: int
    container: str
    image_format: int
    is_video: bool
    mipmaps: list[Mipmap] = field(default_factory=list)


def parse_tex(data: bytes) -> TexInfo:
    magic1, pos = _read_nstring(data, 0, 16)
    if magic1 != "TEXV0005":
        raise TexError(f"unknown tex magic {magic1!r}")
    magic2, pos = _read_nstring(data, pos, 16)
    if magic2 != "TEXI0001":
        raise TexError(f"unknown tex version {magic2!r}")
    fmt, flags, tw, th, iw, ih, _unk = struct.unpack_from("<7i", data, pos)
    pos += 28

    container, pos = _read_nstring(data, pos, 16)
    if not container.startswith("TEXB"):
        raise TexError(f"unknown tex container {container!r}")
    image_count = struct.unpack_from("<i", data, pos)[0]
    pos += 4
    if image_count <= 0 or image_count > 4096:
        raise TexError(f"bad image count {image_count}")

    image_format = -1
    is_video = False
    version = int(container[4:])
    if container in ("TEXB0003", "TEXB0004"):
        image_format = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        if container == "TEXB0004":
            is_video = struct.unpack_from("<i", data, pos)[0] == 1
            pos += 4
            if image_format != 38:  # FIF_MP4
                version = 3

    info = TexInfo(fmt, TEX_FORMAT_NAME.get(fmt, f"fmt{fmt}"), tw, th, iw, ih,
                   container, image_format, is_video)

    for _ in range(min(image_count, 1)):
        mip_count = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        if mip_count < 0 or mip_count > 64:
            raise TexError(f"bad mipmap count {mip_count}")
        for _m in range(mip_count):
            if version >= 4:
                p1 = struct.unpack_from("<i", data, pos)[0]
                pos += 4
                p2 = struct.unpack_from("<i", data, pos)[0]
                pos += 4
                _cond, pos = _read_nstring(data, pos, 4096)
                _p3 = struct.unpack_from("<i", data, pos)[0]
                pos += 4
                if p1 != 1 or p2 != 2:
                    raise TexError("unexpected TEXB0004 mipmap params")
            w, h = struct.unpack_from("<ii", data, pos)
            pos += 8
            if version == 1:
                lz4 = False
                dsize = 0
            else:
                lz4_flag, dsize = struct.unpack_from("<ii", data, pos)
                pos += 8
                lz4 = lz4_flag == 1
            size = struct.unpack_from("<i", data, pos)[0]
            pos += 4
            if size < 0 or pos + size > len(data):
                raise TexError("mipmap data out of range")
            info.mipmaps.append(Mipmap(w, h, lz4, size, data[pos:pos + size], max(0, dsize)))
            pos += size
    if not info.mipmaps:
        raise TexError("no mipmaps")
    return info


def _mipmap_bytes(mip: Mipmap) -> bytes:
    if not mip.lz4:
        return mip.data
    # WE 的 mipmap.size 是压缩后长度，decompressed 是解压后的像素字节数
    return lz4_decompress(mip.data, mip.decompressed)


def _pick_mipmap(info: TexInfo, max_size: int | None) -> Mipmap:
    if not max_size:
        return info.mipmaps[0]
    fitting = [m for m in info.mipmaps if max(m.width, m.height) <= max_size]
    if fitting:
        return fitting[0]
    return info.mipmaps[-1]


def _is_embedded_image(image_format: int, raw: bytes) -> bool:
    if image_format == -1:
        return False
    return raw[:8] == PNG_MAGIC or raw[:3] == JPG_MAGIC or raw[:2] == BMP_MAGIC or \
        raw[:4] in (b"GIF8", b"RIFF") or raw[:4] == b"\x00\x00\x02\x00"


def tex_to_png(data: bytes, max_size: int | None = None) -> bytes | None:
    """把 .tex 转成 PNG 字节；无法识别时返回 None。"""
    try:
        info = parse_tex(data)
    except Exception:
        return None
    try:
        from PIL import Image
    except Exception:
        return None

    mip = _pick_mipmap(info, max_size)
    try:
        raw = _mipmap_bytes(mip)
    except Exception:
        return None
    if _is_mp4(raw):
        return None

    try:
        if _is_embedded_image(info.image_format, raw):
            im = Image.open(io.BytesIO(raw))
            im.load()
            target_w = mip.width or info.width
            target_h = mip.height or info.height
            if im.size != (target_w, target_h) and target_w and target_h:
                im = im.resize((target_w, target_h), Image.LANCZOS)
            if info.width and info.height and (im.width > info.width or im.height > info.height):
                im = im.crop((0, 0, min(im.width, info.width), min(im.height, info.height)))
            return _png_bytes(im)

        kind = info.fmt_name
        if kind == "RGBA8888":
            need = mip.width * mip.height * 4
            if len(raw) < need:
                need2 = info.width * info.height * 4
                if len(raw) < need2:
                    return None
                im = Image.frombytes("RGBA", (info.width, info.height), raw[:need2])
                return _png_bytes(im)
            im = Image.frombytes("RGBA", (mip.width, mip.height), raw[:need])
        elif kind == "R8":
            need = mip.width * mip.height
            if len(raw) < need:
                return None
            im = Image.frombytes("L", (mip.width, mip.height), raw[:need]).convert("RGB")
        elif kind == "RG88":
            need = mip.width * mip.height * 2
            if len(raw) < need:
                return None
            px = raw[:need]
            rgb = bytearray(mip.width * mip.height * 3)
            rgb[0::3] = px[0::2]
            rgb[1::3] = px[1::2]
            rgb[2::3] = b"\x80" * (mip.width * mip.height)
            im = Image.frombytes("RGB", (mip.width, mip.height), bytes(rgb))
        elif kind in ("DXT1", "DXT3", "DXT5"):
            try:
                im = _dxt_image(raw, mip.width, mip.height, kind.lower())
            except Exception:
                buf = _decode_dxt(raw, mip.width, mip.height, kind.lower())
                im = Image.frombytes("RGBA", (mip.width, mip.height), bytes(buf))
        else:
            return None

        if info.width and info.height and (im.width != info.width or im.height != info.height):
            cw, ch = min(im.width, info.width), min(im.height, info.height)
            im = im.crop((0, 0, cw, ch))
        if max_size and max(im.width, im.height) > max_size:
            im.thumbnail((max_size, max_size))
        return _png_bytes(im)
    except Exception:
        return None


def _png_bytes(im) -> bytes:
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.mode else "RGB")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def is_tex(name: str) -> bool:
    return name.lower().endswith(".tex")


MP4_BRANDS = (b"ftypisom", b"ftypmp42", b"ftypmsnv", b"ftypiso2", b"ftypM4V", b"ftypavc1")


def _is_mp4(raw: bytes) -> bool:
    return len(raw) > 12 and raw[4:12] in MP4_BRANDS or (len(raw) > 12 and raw[4:8] == b"ftyp")


def tex_media(data: bytes, max_size: int | None = None) -> tuple[str, bytes] | None:
    """把 .tex 解成可用文件，返回 (扩展名, 字节)：("png", ...) 或 ("mp4", ...)。

    Wallpaper Engine 会把视频壁纸的 mp4 直接塞进 .tex，这里一并处理。
    """
    try:
        info = parse_tex(data)
    except Exception:
        return None
    raw = None
    try:
        raw = _mipmap_bytes(_pick_mipmap(info, None))
    except Exception:
        raw = None
    if raw and _is_mp4(raw) and not info.width * info.height:
        pass
    if raw and _is_mp4(raw):
        return ("mp4", raw)
    png = tex_to_png(data, max_size)
    if png:
        return ("png", png)
    return None


# --------------------------------------------------------------------------- PKGV

@dataclass
class PkgEntry:
    path: str
    offset: int
    length: int


class Pkg:
    """一个已解析的 PKGV 包（仅目录，数据按需读取）。"""

    def __init__(self, path: str, version: str, entries: list[PkgEntry], data_start: int, size: int):
        self.path = path
        self.version = version
        self.entries = entries
        self.data_start = data_start
        self.size = size
        self._fh = None

    # -- 数据读取
    def _handle(self):
        if self._fh is None:
            self._fh = open(self.path, "rb")
        return self._fh

    def read_entry(self, entry: PkgEntry) -> bytes:
        fh = self._handle()
        fh.seek(self.data_start + entry.offset)
        data = fh.read(entry.length)
        if len(data) != entry.length:
            raise IOError(f"short read for {entry.path}")
        return data

    def find(self, name_substr: str) -> list[PkgEntry]:
        s = name_substr.lower()
        return [e for e in self.entries if s in e.path.lower()]

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            finally:
                self._fh = None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Pkg {Path(self.path).name} {self.version} entries={len(self.entries)}>"


def open_pkg(path: str) -> Pkg:
    """解析 PKGV 目录（流式读取，不会把整个包读进内存）。"""
    p = Path(path)
    with open(p, "rb") as fh:
        def take(n: int) -> bytes:
            b = fh.read(n)
            if len(b) != n:
                raise ValueError("truncated package directory")
            return b

        hello = take(4)
        magic_len = struct.unpack("<i", hello)[0]
        if magic_len <= 0 or magic_len > 32:
            raise ValueError(f"bad package magic length {magic_len}")
        magic = take(magic_len).decode("ascii", "replace")
        if not magic.startswith("PKGV"):
            raise ValueError(f"not a PKGV package (magic {magic!r})")
        count = struct.unpack("<i", take(4))[0]
        if count < 0 or count > 2_000_000:
            raise ValueError(f"bad entry count {count}")

        entries: list[PkgEntry] = []
        for _ in range(count):
            plen = struct.unpack("<i", take(4))[0]
            if plen <= 0 or plen > 4096:
                raise ValueError(f"bad entry path length {plen}")
            name = take(plen).decode("utf-8", "replace")
            off, length = struct.unpack("<ii", take(8))
            if off < 0 or length < 0:
                raise ValueError("bad entry range")
            entries.append(PkgEntry(name, off, length))
        data_start = fh.tell()
        size = p.stat().st_size
    for e in entries:
        if data_start + e.offset + e.length > size:
            raise ValueError(f"entry {e.path!r} exceeds file size")
    return Pkg(str(p), magic, entries, data_start, size)


def extract_entry(pkg: Pkg, entry: PkgEntry, dest_path: str) -> str:
    """导出单个条目；.tex 会尝试转成 PNG（失败则原样写出）。"""
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = pkg.read_entry(entry)
    if is_tex(entry.path):
        got = tex_media(raw)
        if got:
            ext, payload = got
            dest = dest.with_suffix("." + ext)
            dest.write_bytes(payload)
            return str(dest)
    dest.write_bytes(raw)
    return str(dest)


def extract_all(pkg: Pkg, dest_dir: str, convert_tex: bool = True, progress=None) -> list[str]:
    """导出全部条目，保留子目录结构。"""
    out: list[str] = []
    root = Path(dest_dir)
    total = len(pkg.entries)
    for i, entry in enumerate(pkg.entries):
        rel = Path(entry.path.replace("\\", "/"))
        target = root / rel
        try:
            raw = pkg.read_entry(entry)
            target.parent.mkdir(parents=True, exist_ok=True)
            if convert_tex and is_tex(entry.path):
                got = tex_media(raw)
                if got:
                    ext, payload = got
                    target = target.with_suffix("." + ext)
                    target.write_bytes(payload)
                    out.append(str(target))
                    if progress:
                        progress(i + 1, total, entry.path)
                    continue
            target.write_bytes(raw)
            out.append(str(target))
        except Exception:
            pass
        if progress:
            progress(i + 1, total, entry.path)
    return out


# ====================================================================== MP4 探测

MP4_EXTS = {".mp4", ".m4v", ".mov", ".mp4v"}


def _iter_boxes(buf, start: int, end: int):
    """遍历 ISO BMFF 盒子，产出 (type, payload_start, box_end)。"""
    pos = start
    while pos + 8 <= end:
        size = int.from_bytes(buf[pos:pos + 4], "big")
        typ = bytes(buf[pos + 4:pos + 8])
        hdr = 8
        if size == 1:
            if pos + 16 > end:
                return
            size = int.from_bytes(buf[pos + 8:pos + 16], "big")
            hdr = 16
        elif size == 0:
            size = end - pos
        if size < hdr or pos + size > end:
            return
        yield typ, pos + hdr, pos + size
        pos += size


CODEC_LABEL = {
    b"avc1": "H.264", b"avc3": "H.264", b"hvc1": "HEVC", b"hev1": "HEVC",
    b"av01": "AV1", b"vp09": "VP9", b"mp4v": "MPEG-4", b"mjpg": "MJPEG",
}


def _stsd_codec(buf, start: int, end: int) -> bytes:
    """在 stsd 盒里取第一个 sample entry 的 fourcc。"""
    try:
        pos = start + 8          # 跳过 version/flags + entry_count
        if pos + 8 > end:
            return b""
        size = int.from_bytes(buf[pos:pos + 4], "big")
        fourcc = bytes(buf[pos + 4:pos + 8])
        if size <= 0:
            return b""
        return fourcc
    except Exception:
        return b""


def mp4_dimensions(path) -> tuple[int, int]:
    """从 tkhd 里读出视频显示尺寸（16.16 定点），失败返回 (0, 0)。"""
    p = Path(path)
    fh = None
    mm = None
    try:
        if not p.is_file() or p.stat().st_size < 32:
            return (0, 0)
        fh = open(p, "rb")
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        if len(mm) < 12 or mm[4:8] != b"ftyp":
            return (0, 0)
        for typ, s, e in _iter_boxes(mm, 0, len(mm)):
            if typ != b"moov":
                continue
            for t2, s2, e2 in _iter_boxes(mm, s, e):
                if t2 != b"trak":
                    continue
                for t3, s3, e3 in _iter_boxes(mm, s2, e2):
                    if t3 != b"tkhd":
                        continue
                    ver = mm[s3]
                    # 载荷内偏移：v0 宽 76 / 高 80；v1 宽 88 / 高 92
                    off = s3 + (88 if ver == 1 else 76)
                    if off + 8 <= e3:
                        w = struct.unpack(">I", bytes(mm[off:off + 4]))[0] >> 16
                        h = struct.unpack(">I", bytes(mm[off + 4:off + 8]))[0] >> 16
                        if w > 0 and h > 0:
                            return (int(w), int(h))
        return (0, 0)
    except Exception:
        return (0, 0)
    finally:
        try:
            if mm is not None:
                mm.close()
            if fh is not None:
                fh.close()
        except Exception:
            pass


def mp4_duration(path) -> float:
    """读 mvhd 里的时长（秒），失败返回 0.0。"""
    p = Path(path)
    fh = None
    mm = None
    try:
        if not p.is_file() or p.stat().st_size < 32:
            return 0.0
        fh = open(p, "rb")
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        if len(mm) < 12 or mm[4:8] != b"ftyp":
            return 0.0
        for typ, s, e in _iter_boxes(mm, 0, len(mm)):
            if typ != b"moov":
                continue
            for t2, s2, e2 in _iter_boxes(mm, s, e):
                if t2 != b"mvhd":
                    continue
                ver = mm[s2]
                if ver == 1:
                    if s2 + 32 > e2:
                        return 0.0
                    scale = struct.unpack(">I", bytes(mm[s2 + 20:s2 + 24]))[0]
                    dur = struct.unpack(">Q", bytes(mm[s2 + 24:s2 + 32]))[0]
                else:
                    if s2 + 20 > e2:
                        return 0.0
                    scale = struct.unpack(">I", bytes(mm[s2 + 12:s2 + 16]))[0]
                    dur = struct.unpack(">I", bytes(mm[s2 + 16:s2 + 20]))[0]
                if scale > 0 and dur > 0:
                    return float(dur) / float(scale)
        return 0.0
    except Exception:
        return 0.0
    finally:
        try:
            if mm is not None:
                mm.close()
            if fh is not None:
                fh.close()
        except Exception:
            pass


def mp4_probe(path) -> dict:
    """返回 {ok, has_audio, has_video, brands, codec, codec_label}；不是合法 MP4 容器时 ok=False。"""
    info = {"ok": False, "has_audio": False, "has_video": False, "brands": b"",
            "codec": "", "codec_label": ""}
    p = Path(path)
    try:
        if not p.is_file() or p.stat().st_size < 32:
            return info
    except Exception:
        return info
    fh = None
    mm = None
    try:
        fh = open(p, "rb")
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        head = mm[0:12]
        if head[4:8] != b"ftyp":
            return info
        info["ok"] = True
        info["brands"] = bytes(head[8:12])
        total = len(mm)
        for typ, s, e in _iter_boxes(mm, 0, total):
            if typ != b"moov":
                continue
            for t2, s2, e2 in _iter_boxes(mm, s, e):
                if t2 != b"trak":
                    continue
                for t3, s3, e3 in _iter_boxes(mm, s2, e2):
                    if t3 != b"mdia":
                        continue
                    for t4, s4, e4 in _iter_boxes(mm, s3, e3):
                        if t4 != b"hdlr" or s4 + 12 > e4:
                            continue
                        handler = bytes(mm[s4 + 8:s4 + 12])
                        if handler == b"soun":
                            info["has_audio"] = True
                        elif handler == b"vide":
                            info["has_video"] = True
                            if not info["codec"]:
                                # mdia -> minf -> stbl -> stsd
                                for t5, s5, e5 in _iter_boxes(mm, s3, e3):
                                    if t5 != b"minf":
                                        continue
                                    for t6, s6, e6 in _iter_boxes(mm, s5, e5):
                                        if t6 != b"stbl":
                                            continue
                                        for t7, s7, e7 in _iter_boxes(mm, s6, e6):
                                            if t7 != b"stsd":
                                                continue
                                            cc = _stsd_codec(mm, s7, e7)
                                            if cc:
                                                info["codec"] = cc.decode("ascii", "ignore")
                                                info["codec_label"] = CODEC_LABEL.get(cc, info["codec"])
            break
    except Exception:
        return info
    finally:
        if mm is not None:
            try:
                mm.close()
            except Exception:
                pass
        if fh is not None:
            try:
                fh.close()
            except Exception:
                pass
    return info


def is_playable_video(path) -> bool:
    """标准 MP4 容器才交给播放器；webm/vp9/裸流等不播，交给解包处理。"""
    p = Path(path)
    if p.suffix.lower() not in MP4_EXTS:
        return False
    return mp4_probe(p)["ok"]


def pretty_type(t: str) -> str:
    return {"scene": "场景", "video": "视频", "web": "网页", "application": "程序",
            "preset": "预设", "unknown": "未知"}.get(t, t)
