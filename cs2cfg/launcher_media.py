"""Local screenshot and optional agent frames for the Launcher scene."""

from __future__ import annotations

import json
from tempfile import NamedTemporaryFile
from pathlib import Path

from .paths import user_data_dir

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_SIZE = 20 * 1024 * 1024
AGENT_FILES = {"ct": "ct.png", "t": "t.png"}


def _config() -> Path:
    return user_data_dir() / "launcher-screenshot.json"


def screenshot() -> Path | None:
    try:
        path = Path(json.loads(_config().read_text(encoding="utf-8")))
        if _valid(path):
            return path
    except (OSError, ValueError, TypeError):
        pass
    return None


def agent_sheet(side: str) -> Path | None:
    filename = AGENT_FILES.get(side)
    if filename:
        path = user_data_dir() / "launcher-agents" / filename
        try:
            if _valid(path):
                return path
        except OSError:
            pass
    return None


def _valid(path: Path) -> bool:
    return (path.is_absolute() and path.suffix.lower() in IMAGE_EXTENSIONS
            and path.is_file() and 0 < path.stat().st_size <= MAX_SIZE)


def choose(path: Path | None) -> None:
    config = _config()
    if path is None:
        config.unlink(missing_ok=True)
        return
    if not _valid(path):
        raise ValueError("Choose a PNG, JPEG or WebP screenshot under 20 MB.")
    config.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=config.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(str(path), stream)
    try:
        temporary.replace(config)
    finally:
        temporary.unlink(missing_ok=True)
