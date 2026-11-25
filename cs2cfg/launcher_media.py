"""The user's local gameplay clip for the Launcher scene."""

from __future__ import annotations

import json
import re
from tempfile import NamedTemporaryFile
from pathlib import Path

from .paths import user_data_dir

VIDEO_FORMATS = {".mp4": "video/mp4", ".webm": "video/webm"}


def _config() -> Path:
    return user_data_dir() / "launcher-clip.json"


def clip() -> Path | None:
    try:
        path = Path(json.loads(_config().read_text(encoding="utf-8")))
        if path.is_absolute() and path.suffix.lower() in VIDEO_FORMATS and path.is_file():
            return path
    except (OSError, ValueError, TypeError):
        pass
    return None


def choose(path: Path | None) -> None:
    config = _config()
    if path is None:
        config.unlink(missing_ok=True)
        return
    if not path.is_absolute() or path.suffix.lower() not in VIDEO_FORMATS or not path.is_file():
        raise ValueError("Choose an existing MP4 or WebM gameplay clip.")
    config.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=config.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(str(path), stream)
    try:
        temporary.replace(config)
    finally:
        temporary.unlink(missing_ok=True)


def byte_range(header: str, size: int) -> tuple[int, int] | None:
    """Return inclusive bounds for a single HTTP media seek."""
    if size <= 0:
        return None
    if not header:
        return 0, size - 1
    match = re.fullmatch(r"bytes=([0-9]{0,20})-([0-9]{0,20})", header)
    if not match or not any(match.groups()):
        return None
    first, last = match.groups()
    if not first:
        suffix = int(last)
        return (max(0, size - suffix), size - 1) if suffix else None
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    return (start, end) if start <= end else None
