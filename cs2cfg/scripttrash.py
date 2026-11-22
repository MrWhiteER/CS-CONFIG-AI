"""Deleted scripts wait in a Trash for seven days before they are gone.

Deleting a script takes its lines out of the config file at once (so the game
and every tab stop seeing it), but the lines, the file they came from and the
keys that ran it are kept here. Restoring puts all of that back. After seven
days the entry is dropped and nothing of the script is left anywhere.

The Trash lives in the app's own data folder, never in the config folder, so
CS2 never reads it.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

KEEP_DAYS = 7
_KEEP_SECONDS = KEEP_DAYS * 24 * 3600


def _file() -> Path:
    from .paths import user_data_dir

    return user_data_dir() / "script_trash.json"


def _read() -> List[Dict[str, Any]]:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def _write(items: List[Dict[str, Any]]) -> None:
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=1), encoding="utf-8")


def items(now: Optional[float] = None) -> List[Dict[str, Any]]:
    """What is in the Trash, newest first. Anything older than seven days is
    removed for good on the way."""
    now = time.time() if now is None else now
    kept, dropped = [], False
    for item in _read():
        if now - float(item.get("deleted", 0)) >= _KEEP_SECONDS:
            dropped = True
            continue
        item["gone_on"] = float(item.get("deleted", 0)) + _KEEP_SECONDS
        kept.append(item)
    if dropped:
        _write([{k: v for k, v in i.items() if k != "gone_on"} for i in kept])
    return sorted(kept, key=lambda i: -float(i.get("deleted", 0)))


def add(entry: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    entry = dict(entry)
    entry["id"] = uuid.uuid4().hex[:12]
    entry["deleted"] = time.time() if now is None else now
    current = [{k: v for k, v in i.items() if k != "gone_on"} for i in items(now)]
    _write([entry] + current)
    return entry


def take(item_id: str) -> Optional[Dict[str, Any]]:
    """Take one entry out of the Trash (to restore it)."""
    found = None
    rest = []
    for item in items():
        if item.get("id") == item_id and found is None:
            found = item
        else:
            rest.append(item)
    if found is not None:
        _write([{k: v for k, v in i.items() if k != "gone_on"} for i in rest])
    return found


def put_back(entry: Dict[str, Any]) -> None:
    """Undo a ``take`` when restoring failed, keeping its original date."""
    current = [{k: v for k, v in i.items() if k != "gone_on"} for i in items()]
    _write([{k: v for k, v in entry.items() if k != "gone_on"}] + current)
