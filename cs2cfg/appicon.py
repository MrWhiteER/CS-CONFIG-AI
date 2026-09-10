"""Application icon, generated rather than shipped as a binary blob.

Written with ``zlib`` and ``struct`` only. Keeping the icon as code means there
is no binary in the repo, the PyInstaller bundle stays smaller, and the icon can
be regenerated at any size without an image library.

The mark is a crosshair: four ticks around a centre gap, on a rounded dark
tile. It stays legible at 16 px, where anything more detailed turns to mush.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import List, Sequence, Tuple

RGBA = Tuple[int, int, int, int]

BACKGROUND: RGBA = (23, 27, 35, 255)      # matches the UI panel colour
ACCENT: RGBA = (110, 160, 255, 255)
ACCENT_DIM: RGBA = (60, 95, 165, 255)
TRANSPARENT: RGBA = (0, 0, 0, 0)

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


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
    centre = size / 2.0
    thickness = max(1.0, size * 0.075)
    gap = size * 0.13
    length = size * 0.26
    half = thickness / 2.0

    def paint(x0: float, y0: float, x1: float, y1: float, colour: RGBA) -> None:
        for y in range(size):
            for x in range(size):
                px, py = x + 0.5, y + 0.5
                inside_x = x0 - 0.5 <= px <= x1 + 0.5
                inside_y = y0 - 0.5 <= py <= y1 + 0.5
                if not (inside_x and inside_y):
                    continue
                # Soft edge: coverage falls off within half a pixel.
                cx = min(px - (x0 - 0.5), (x1 + 0.5) - px, 1.0)
                cy = min(py - (y0 - 0.5), (y1 + 0.5) - py, 1.0)
                coverage = max(0.0, min(1.0, cx)) * max(0.0, min(1.0, cy))
                if coverage <= 0:
                    continue
                shade = (colour[0], colour[1], colour[2], int(round(colour[3] * coverage)))
                pixels[y][x] = _blend(pixels[y][x], shade)

    # Vertical ticks.
    paint(centre - half, centre - gap - length, centre + half, centre - gap, ACCENT)
    paint(centre - half, centre + gap, centre + half, centre + gap + length, ACCENT)
    # Horizontal ticks.
    paint(centre - gap - length, centre - half, centre - gap, centre + half, ACCENT)
    paint(centre + gap, centre - half, centre + gap + length, centre + half, ACCENT)
    # Centre dot, dimmer so the gap still reads at small sizes.
    dot = max(0.5, thickness * 0.45)
    paint(centre - dot, centre - dot, centre + dot, centre + dot, ACCENT_DIM)


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
    """Return the icon path, generating it if it is not already there."""
    target = Path(directory) / name
    if not target.exists() or target.stat().st_size == 0:
        write_ico(target)
    return target


if __name__ == "__main__":  # pragma: no cover - manual generation
    import sys

    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("cs2cfg.ico")
    print(write_ico(destination))
