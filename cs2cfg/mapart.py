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
