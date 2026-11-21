"""A picture out of one compiled CS2 texture (``.vtex_c``), as PNG bytes.

Most of the game's menu pictures (``panorama/images/..._png.vtex_c``) are a
short Source 2 header followed by an ordinary PNG, which is cut out as-is
(:func:`cs2cfg.mapart.cut_png`). A few are stored as raw pixels instead
(uncompressed RGBA/BGRA, or BC1/BC3 blocks, sometimes LZ4 or Zstandard
packed); those are decoded here with plain Python and written back out as a
PNG. Anything else is left alone and the caller shows its plain card.

Same decoder as the lineups radar reader (codex/lineups), kept in one place
so both can share it once that work lands.
"""

from __future__ import annotations

import struct
import zlib
from typing import List, Optional

from .mapart import PNG_START, cut_png

MAX_SIDE = 4096


def lz4_block(raw: bytes, expected: int) -> bytes:
    """Decode one raw LZ4 block of a known decoded size."""
    at, out = 0, bytearray()

    def more(n: int) -> int:
        nonlocal at
        if n == 15:
            while True:
                if at >= len(raw):
                    raise ValueError("truncated")
                extra = raw[at]
                at += 1
                n += extra
                if extra != 255:
                    break
        return n

    while at < len(raw):
        token = raw[at]
        at += 1
        length = more(token >> 4)
        if at + length > len(raw) or len(out) + length > expected:
            raise ValueError("bad length")
        out += raw[at:at + length]
        at += length
        if at == len(raw):
            break
        if at + 2 > len(raw):
            raise ValueError("truncated")
        offset = int.from_bytes(raw[at:at + 2], "little")
        at += 2
        count = more(token & 15) + 4
        if not offset or offset > len(out) or len(out) + count > expected:
            raise ValueError("bad match")
        for _ in range(count):
            out.append(out[-offset])
    if len(out) != expected:
        raise ValueError("bad size")
    return bytes(out)


def to_png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data)))
    row = width * 4
    scan = b"".join(b"\0" + rgba[y * row:(y + 1) * row] for y in range(height))
    return (PNG_START + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(scan, 6)) + chunk(b"IEND", b""))


def _rgb565(n: int) -> List[int]:
    return [(n >> 11) * 255 // 31, ((n >> 5) & 63) * 255 // 63, (n & 31) * 255 // 31, 255]


def decode_bc(data: bytes, width: int, height: int, alpha: bool) -> bytes:
    """BC1 (alpha=False) or BC3 (alpha=True) blocks -> RGBA."""
    stride = 16 if alpha else 8
    if len(data) != ((width + 3) // 4) * ((height + 3) // 4) * stride:
        raise ValueError("bad size")
    out = bytearray(width * height * 4)
    offset = 0
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            block = data[offset:offset + stride]
            offset += stride
            alphas, bits = [255] * 8, 0
            if alpha:
                a, b = block[0], block[1]
                if a > b:
                    alphas = [a, b] + [((7 - i) * a + i * b) // 7 for i in range(1, 7)]
                else:
                    alphas = [a, b] + [((5 - i) * a + i * b) // 5 for i in range(1, 5)] + [0, 255]
                bits = int.from_bytes(block[2:8], "little")
                block = block[8:]
            c0, c1, indices = struct.unpack("<HHI", block)
            colors = [_rgb565(c0), _rgb565(c1)]
            if c0 > c1 or alpha:
                colors.append([(2 * colors[0][k] + colors[1][k]) // 3 for k in range(4)])
                colors.append([(colors[0][k] + 2 * colors[1][k]) // 3 for k in range(4)])
            else:
                colors.append([(colors[0][k] + colors[1][k]) // 2 for k in range(4)])
                colors.append([0, 0, 0, 0])
            for i in range(16):
                x, y = bx + i % 4, by + i // 4
                if x < width and y < height:
                    c = colors[(indices >> (i * 2)) & 3]
                    a_ = alphas[(bits >> (i * 3)) & 7] if alpha else c[3]
                    p = (y * width + x) * 4
                    out[p:p + 4] = bytes((c[0], c[1], c[2], a_))
    return bytes(out)


# Source 2 image formats this reads: 1 = BC1, 2 = BC3, 4 = RGBA8888, 28 = BGRA8888.
_FORMATS = (1, 2, 4, 28)


def _raw_size(fmt: int, w: int, h: int) -> int:
    if fmt in (4, 28):
        return w * h * 4
    return ((w + 3) // 4) * ((h + 3) // 4) * (8 if fmt == 1 else 16)


def _decode_raw(raw: bytes) -> Optional[bytes]:
    if len(raw) < 16:
        return None
    start, count = struct.unpack_from("<II", raw, 8)
    if count > 64:
        return None
    for i in range(count):
        at = 8 + start + i * 12
        tag, off, size = struct.unpack_from("<4sII", raw, at)
        if tag != b"DATA":
            continue
        pos = at + 4 + off
        version = struct.unpack_from("<H", raw, pos)[0]
        width, height, depth, fmt, mips = struct.unpack_from("<HHHBB", raw, pos + 20)
        extras = struct.unpack_from("<I", raw, pos + 36)[0]
        if version != 1 or depth != 1 or extras > 32 or fmt not in _FORMATS or not 1 <= mips <= 14:
            return None
        if not (1 <= width <= MAX_SIDE and 1 <= height <= MAX_SIDE):
            return None
        sizes = [_raw_size(fmt, max(1, width >> m), max(1, height >> m)) for m in range(mips)]
        compression = 0
        extra_offset = struct.unpack_from("<I", raw, pos + 32)[0]
        for n in range(extras):
            at2 = pos + 32 + extra_offset + n * 12
            kind, offset, _extra_size = struct.unpack_from("<III", raw, at2)
            if kind == 4:  # compressed mip sizes
                where = at2 + 4 + offset
                compression, mip_offset, mip_count = struct.unpack_from("<III", raw, where)
                if compression not in (0, 1, 2) or mip_count != mips:
                    return None
                sizes = list(struct.unpack_from("<" + "I" * mips, raw, where + 4 + mip_offset))
        # Smallest mips come first in the file; the full-size picture is last.
        begin = pos + size + sum(sizes[1:])
        data = raw[begin:begin + sizes[0]]
        if len(data) != sizes[0]:
            return None
        want = _raw_size(fmt, width, height)
        if len(data) != want:
            if compression == 1:
                data = lz4_block(data, want)
            elif compression == 2:
                import zstandard
                data = zstandard.ZstdDecompressor().decompress(data, max_output_size=want)
            else:
                return None
        if fmt == 28:
            swapped = bytearray(data)
            swapped[0::4], swapped[2::4] = data[2::4], data[0::4]
            rgba = bytes(swapped)
        elif fmt == 4:
            rgba = data
        else:
            rgba = decode_bc(data, width, height, fmt == 2)
        return to_png(width, height, rgba) if len(rgba) == width * height * 4 else None
    return None


def picture(raw: bytes) -> Optional[bytes]:
    """PNG bytes for one compiled texture, or None when it cannot be read."""
    embedded = cut_png(raw)
    if embedded:
        return embedded
    try:
        return _decode_raw(raw)
    except (ValueError, struct.error, IndexError, ImportError, Exception):  # noqa: BLE001
        # One unreadable picture must never take the page down with it.
        return None
