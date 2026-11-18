"""The real map pictures, read from the player's own CS2 install.

CS2 ships a loading-screen picture for every map at
``panorama/images/map_icons/screenshots/<size>/<map>_png.vtex_c`` inside
``pak01_dir.vpk``. Each of those compiled files is a short Source 2 header
followed by an ordinary PNG, so the picture is cut out as-is: no decoding,
no extra tools. The app ships none of Valve's pictures itself; a PC without
CS2 gets the plain fallback card instead.

Cut-out pictures are kept in the app's data folder and redone when the game
updates (the VPK's modification time moves).
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Optional

from . import maps, vpk

FOLDER = "panorama/images/map_icons/screenshots/"
SIZES = ("360p", "720p", "1080p")      # smallest that exists wins: it is a thumbnail
PNG_START = b"\x89PNG\r\n\x1a\n"
PNG_END = b"IEND\xaeB`\x82"
_SAFE = re.compile(r"^[a-z0-9_]{2,48}$")
_lock = threading.Lock()


def _entry(index, map_id: str):
    for size in SIZES:
        entry = index.get(f"{FOLDER}{size}/{map_id}_png.vtex_c")
        if entry is not None:
            return entry
    return None


def cut_png(data: bytes) -> Optional[bytes]:
    """The PNG inside one compiled texture, or None when there is none."""
    start = data.find(PNG_START)
    if start < 0:
        return None
    end = data.find(PNG_END, start)
    if end < 0:
        return None
    return data[start:end + len(PNG_END)]


def picture(dir_vpk: Optional[Path], cache_dir: Path, map_id: str) -> Optional[Path]:
    """A PNG file with the map's real picture, or None (no CS2, unknown map)."""
    key = maps.canonical(map_id)
    if not _SAFE.match(key or ""):
        return None
    cache = Path(cache_dir) / "map-art"
    out = cache / f"{key}.png"
    missing = cache / f"{key}.none"
    try:
        stamp = dir_vpk.stat().st_mtime if dir_vpk is not None else 0
    except OSError:
        stamp = 0
    with _lock:
        for done in (out, missing):
            try:
                if done.is_file() and (not stamp or done.stat().st_mtime >= stamp):
                    return out if done is out else None
            except OSError:
                pass
        if not stamp:
            return None
        try:
            index = vpk.read_index(dir_vpk)
            entry = _entry(index, key)
            png = cut_png(vpk.read_file(dir_vpk, entry)) if entry is not None else None
            cache.mkdir(parents=True, exist_ok=True)
            if png is None:
                missing.write_bytes(b"")
                return None
            tmp = out.with_suffix(".tmp")
            tmp.write_bytes(png)
            tmp.replace(out)
            missing.unlink(missing_ok=True)
            return out
        except (OSError, vpk.VpkError):
            return None


# Game-mode icons, from the same files: each ``.vsvg_c`` holds plain SVG text.
ICON_FOLDER = "panorama/images/icons/ui/"
MODE_ICONS = {
    "premier": "premier",            # a wide "Premier" wordmark, not a square
    "competitive": "competitive",
    "wingman": "scrimcomp2v2",
    "casual": "casual",
    "deathmatch": "deathmatch",
    "retakes": "retakes",
    "arms-race": "gungameprogressive",
}


def cut_svg(data: bytes) -> Optional[bytes]:
    start = data.find(b"<svg")
    end = data.rfind(b"</svg>")
    if start < 0 or end < start:
        return None
    svg = data[start:end + len(b"</svg>")]
    if b"xmlns=" not in svg[:300]:
        # A picture in an <img> only draws with the SVG namespace stated.
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"' + svg[4:]
    return svg


def mode_icon(dir_vpk: Optional[Path], cache_dir: Path, mode: str) -> Optional[Path]:
    """The game's own SVG icon for a mode ("Premier", "Wingman"...), or None."""
    key = re.sub(r"[^a-z]+", "-", maps.mode(mode).lower()).strip("-")
    name = MODE_ICONS.get(key)
    if not name:
        return None
    cache = Path(cache_dir) / "map-art"
    out = cache / f"mode-{key}.svg"
    try:
        stamp = dir_vpk.stat().st_mtime if dir_vpk is not None else 0
    except OSError:
        stamp = 0
    with _lock:
        try:
            if out.is_file() and (not stamp or out.stat().st_mtime >= stamp):
                return out
        except OSError:
            pass
        if not stamp:
            return None
        try:
            index = vpk.read_index(dir_vpk)
            entry = index.get(f"{ICON_FOLDER}{name}.vsvg_c") or \
                vpk.find(index, f"icons/ui/{name}.vsvg_c")
            svg = cut_svg(vpk.read_file(dir_vpk, entry)) if entry is not None else None
            if svg is None:
                return None
            cache.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".tmp")
            tmp.write_bytes(svg)
            tmp.replace(out)
            return out
        except (OSError, vpk.VpkError):
            return None
