"""Application icon, generated rather than shipped as a binary blob.

Written with ``zlib`` and ``struct`` only. Keeping the icon as code means there
is no binary in the repo, the PyInstaller bundle stays smaller, and the icon can
be regenerated at any size without an image library.

The mark is the CS CONFIG AI one: an open violet bracket with an ivory
targeting cross sitting in its mouth, on a rounded dark tile. It stays legible
at 16 px, where anything more detailed turns to mush -- which is the whole
reason the small sizes are drawn rather than scaled down from a large one.

The artwork comes from the project's own brand set, and this file is the
source of it rather than a copy of it: the bytes this produces are identical
to the cs-config-ai.ico in that set, which the tests check. Changing a number
here changes the application icon, the window icon, the notification area icon
and the installer's icon together, because all four come from here.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path
from typing import List, Sequence, Tuple

RGBA = Tuple[int, int, int, int]

BACKGROUND: RGBA = (19, 12, 31, 255)      # #130C1F, the dark tile
ACCENT: RGBA = (167, 139, 250, 255)       # #A78BFA, the interface violet
CROSS: RGBA = (236, 236, 236, 255)        # #ECECEC, the targeting mark
TRANSPARENT: RGBA = (0, 0, 0, 0)

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

# The artwork itself, on the 16-unit grid it was drawn on. Out here rather
# than inside the drawing function so the fingerprint below can see it: these
# six names are the whole definition of the mark, and nothing else about it
# can change without one of them changing.
BRACKET = ((12, 3), (6, 3), (3, 6), (3, 10), (6, 13),
           (12, 13), (12, 11), (7, 11), (5, 9), (5, 7),
           (7, 5), (12, 5))
# The cross, as (x0, x1, y0, y1) bars.
CROSS_BARS = ((8, 14, 7, 9), (10, 12, 5, 11))


def fingerprint() -> str:
    """A cheap identity for the current artwork.

    Generating the icon to find out whether it has changed costs about two
    seconds, almost all of it in the 256 px rendering -- fine once at build
    time and far too much on every start of the application, which is where
    the check actually happens. This is the same question answered from the
    handful of constants that define the drawing, which is instant.
    """
    material = repr((BACKGROUND, ACCENT, CROSS, ICO_SIZES, BRACKET, CROSS_BARS))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _rounded_tile(size: int) -> List[List[RGBA]]:
    """A dark rounded square, anti-aliased at the corners."""
    radius = max(2.0, size * 0.22)
    pixels = [[TRANSPARENT for _ in range(size)] for _ in range(size)]

    for y in range(size):
        for x in range(size):
            # Distance outside the rounded rectangle, for a soft edge.
            dx = max(radius - (x + 0.5), (x + 0.5) - (size - radius), 0.0)
            dy = max(radius - (y + 0.5), (y + 0.5) - (size - radius), 0.0)
            distance = (dx * dx + dy * dy) ** 0.5
            coverage = 1.0 if distance <= radius - 0.5 else max(0.0, radius + 0.5 - distance)
            if coverage <= 0:
                continue
            alpha = int(round(BACKGROUND[3] * min(1.0, coverage)))
            pixels[y][x] = (BACKGROUND[0], BACKGROUND[1], BACKGROUND[2], alpha)
    return pixels


def _blend(base: RGBA, top: RGBA) -> RGBA:
    """Source-over compositing, so ticks anti-alias onto the tile."""
    ta = top[3] / 255.0
    if ta <= 0:
        return base
    if ta >= 1:
        return top
    return (
        int(round(top[0] * ta + base[0] * (1 - ta))),
        int(round(top[1] * ta + base[1] * (1 - ta))),
        int(round(top[2] * ta + base[2] * (1 - ta))),
        max(base[3], top[3]),
    )


def _draw_crosshair(pixels: List[List[RGBA]], size: int) -> None:
    """The bracket and the cross, sampled at 4x.

    Both shapes are described once, in the 16-unit grid the artwork was drawn
    on, and sampled into whatever size is being rendered. Sixteen samples a
    pixel is what keeps the bracket's diagonals smooth at 24 and 32 px, where
    scaling a large rendering down leaves them visibly stepped.
    """
    polygon = BRACKET

    def inside(px, py):
        result = False
        j = len(polygon) - 1
        for i, (xi, yi) in enumerate(polygon):
            xj, yj = polygon[j]
            if (yi > py) != (yj > py) and px < (xj-xi)*(py-yi)/(yj-yi)+xi:
                result = not result
            j = i
        return result

    for y in range(size):
        for x in range(size):
            purple = white = 0
            for sy in range(4):
                for sx in range(4):
                    px = (x + (sx + .5)/4) * 16 / size
                    py = (y + (sy + .5)/4) * 16 / size
                    # The cross wins where the two meet: it sits in front.
                    if any(x0 <= px < x1 and y0 <= py < y1
                           for x0, x1, y0, y1 in CROSS_BARS):
                        white += 1
                    elif inside(px, py):
                        purple += 1
            base = pixels[y][x]
            p, w = purple/16, white/16
            # The tile's own alpha is kept, so the rounded corners stay soft
            # and nothing is painted outside them.
            pixels[y][x] = tuple(
                round(base[c] * (1 - p - w) + ACCENT[c] * p + CROSS[c] * w)
                for c in range(3)) + (base[3],)


def render(size: int) -> List[List[RGBA]]:
    pixels = _rounded_tile(size)
    _draw_crosshair(pixels, size)
    return pixels


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data)) + tag + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def to_png(pixels: Sequence[Sequence[RGBA]]) -> bytes:
    """Encode RGBA rows as a PNG."""
    height = len(pixels)
    width = len(pixels[0]) if height else 0

    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter type 0 (None)
        for r, g, b, a in row:
            raw += bytes((r, g, b, a))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )


def to_ico(sizes: Sequence[int] = ICO_SIZES) -> bytes:
    """A multi-resolution .ico with PNG-compressed entries.

    PNG payloads inside .ico are understood by Windows Vista and later, which
    covers everything this tool runs on and keeps the file a fraction of the
    size of the equivalent uncompressed DIBs.
    """
    images = [to_png(render(size)) for size in sizes]

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)

    entries = bytearray()
    for size, data in zip(sizes, images):
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(data), offset
        )
        offset += len(data)

    return bytes(header + entries + b"".join(images))


def write_ico(path: Path, sizes: Sequence[int] = ICO_SIZES) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(to_ico(sizes))
    return path


def ensure_icon(directory: Path, name: str = "cs2cfg.ico") -> Path:
    """Return the icon path, writing it if it is missing or out of date.

    The cached file lives in the user's data directory and outlives upgrades,
    so checking only that it exists -- which is what this used to do -- left
    every existing installation showing the previous icon for good after the
    artwork changed.

    What it does not do is generate the icon in order to compare it. That
    costs about two seconds, and this runs on every start. A stamp file beside
    the icon holds the fingerprint of the artwork it was drawn from, so the
    usual answer -- nothing has changed -- is two small reads.
    """
    target = Path(directory) / name
    stamp = target.with_name(target.name + ".id")
    wanted = fingerprint()

    if target.exists() and target.stat().st_size:
        try:
            if stamp.read_text(encoding="utf-8").strip() == wanted:
                return target
        except OSError:
            pass                      # no stamp: treat it as out of date

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(to_ico())
    try:
        stamp.write_text(wanted, encoding="utf-8")
    except OSError:
        # Without the stamp it is redrawn next time. Slow, not wrong.
        pass
    return target


if __name__ == "__main__":  # pragma: no cover - manual generation
    import sys

    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("cs2cfg.ico")
    print(write_ico(destination))
