"""What a key can be set to, and how it is currently set.

The keyboard view shows what every key does. This is the other half: the list
of things it could do instead, grouped the way the game groups them, so a key
can be reassigned by picking from a list rather than by knowing the console
command by heart.

Three sources, kept separate because they mean different things:

* **the catalogue** -- engine commands, from the knowledge file. Every one is
  either bound by CS2 itself or already listed in cfgscan as an engine command,
  so nothing offered here is a guess about what the engine accepts. Binding a
  command that does not exist would succeed silently and then do nothing when
  the key is pressed.
* **your scripts** -- the aliases found in the collection being edited. These
  are the user's own, and are the most likely thing they want on a key.
* **the stock bind** -- what CS2 itself puts on this particular key, read from
  the game's own defaults. Offered as a way back rather than as a choice among
  equals.

Nothing here writes. It only reports what is available.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import defaults, keys
from .paths import bundle_root

CATALOGUE = "bindable_commands.json"

_cache: Optional[Dict[str, Any]] = None


def catalogue() -> Dict[str, Any]:
    """The engine commands worth offering, grouped. Read once and kept."""
    global _cache
    if _cache is not None:
        return _cache
    path = bundle_root() / "knowledge" / CATALOGUE
    try:
        _cache = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # A missing catalogue costs the picker its engine commands; the user's
        # own scripts and the stock bind still work, which is better than the
        # whole panel failing.
        _cache = {"groups": []}
    return _cache


def _script_group(scan) -> Optional[Dict[str, Any]]:
    """The user's own aliases, as a group of their own at the top."""
    if scan is None:
        return None
    from . import plugins

    entries: List[Dict[str, Any]] = []
    seen = set()
    for feature in plugins.find(scan):
        if not feature.entry or feature.entry.lower() in seen:
            continue
        seen.add(feature.entry.lower())
        entries.append({
            "command": feature.entry,
            "label": feature.name,
            "hold": feature.entry.startswith("+"),
            "note": feature.description or "",
            "script": True,
            "enabled": feature.enabled,
        })
    if not entries:
        return None
    return {"id": "scripts", "name": "Your scripts", "commands": entries}


def bound_to(scan, binding: str) -> Optional[Dict[str, Any]]:
    """What this key runs now, according to the last bind that loads."""
    if scan is None or not binding:
        return None
    entries = scan.binds.get(binding) or []
    if not entries:
        return None
    winner = max(entries, key=lambda b: b.order)
    return {
        "command": (winner.body or "").strip().strip('"'),
        "file": winner.file,
        "line": winner.line,
        "shadowed": len(entries) - 1,
    }


def options(scan, binding: str, cs2_install=None) -> Dict[str, Any]:
    """Everything the picker needs for one key.

    The stock bind is reported separately rather than mixed into the groups:
    "put it back the way CS2 has it" is a different kind of choice from "make
    it do this instead", and reads better as its own button.
    """
    groups: List[Dict[str, Any]] = []
    mine = _script_group(scan)
    if mine:
        groups.append(mine)
    groups.extend(catalogue().get("groups", []))

    table = defaults.load(cs2_install) if cs2_install else {}
    stock = defaults.for_key(table, binding) if table else ""
    current = bound_to(scan, binding)

    return {
        "binding": binding,
        "label": keys.label(binding),
        "current": current,
        "stock": stock,
        "groups": groups,
        "hold_note": catalogue().get("hold_note", ""),
    }


def is_offered(command: str) -> bool:
    """Whether a command is one this collection knows about.

    Used to warn rather than to refuse. Somebody binding a console command the
    catalogue has never heard of is probably right and this list is probably
    incomplete -- but it is worth saying so, because a typo behaves exactly the
    same way as a real command right up until the key does nothing.
    """
    wanted = (command or "").strip().strip('"').lower()
    if not wanted:
        return False
    for group in catalogue().get("groups", []):
        for entry in group.get("commands", []):
            if str(entry.get("command", "")).lower() == wanted:
                return True
    return False
