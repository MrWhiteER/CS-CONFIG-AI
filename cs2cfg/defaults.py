"""What CS2 binds each key to out of the box.

Read from the game's own ``cfg/user_keys_default.vcfg`` rather than a table
written here. A table written here would be a guess about somebody else's
software, it would drift every time Valve changed a default, and being wrong
means writing a wrong bind into a real config -- which is exactly the kind of
silent damage this collection is supposed to avoid. The game ships the answer;
this reads it.

The file names keys the way the game's menu does (``SPACE``, ``CTRL``,
``MOUSE1``, ``f``), while configs written by this collection bind by HID usage
id (``scancode44``). Both ends are normalised to the config form, so a script's
own bind target can be looked up directly.

Nothing here writes. The game's installation directory is opened read-only and
only this one file is touched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from . import vdf

DEFAULTS_FILE = "user_keys_default.vcfg"

# The names CS2 uses in that file, for the keys that are not a plain letter or
# digit. Letters, digits and F-keys are handled by pattern below.
_NAMED = {
    "escape": 41, "esc": 41, "tab": 43, "space": 44, "enter": 40,
    "backspace": 42, "capslock": 57, "ins": 73, "insert": 73, "del": 76,
    "delete": 76, "home": 74, "end": 77, "pgup": 75, "pgdn": 78,
    "uparrow": 82, "downarrow": 81, "leftarrow": 80, "rightarrow": 79,
    "ctrl": 224, "rctrl": 228, "shift": 225, "rshift": 229,
    "alt": 226, "ralt": 230,
    "-": 45, "=": 46, "[": 47, "]": 48, "\\": 49, ";": 51, "'": 52,
    "`": 53, ",": 54, ".": 55, "/": 56,
}

# Mouse and wheel are not HID keyboard usages; the engine names them directly
# and configs already use those names, so they only need lowercasing.
_DIRECT = {"mouse1", "mouse2", "mouse3", "mouse4", "mouse5",
           "mwheelup", "mwheeldown"}


def normalise(name: str) -> str:
    """A key name as a config would bind it: "SPACE" -> "scancode44"."""
    raw = (name or "").strip().strip('"')
    low = raw.lower()
    if not low:
        return ""
    if low in _DIRECT:
        return low
    if low.startswith("scancode") and low[8:].isdigit():
        return low
    if low in _NAMED:
        return f"scancode{_NAMED[low]}"
    if len(low) == 1:
        if "a" <= low <= "z":
            return f"scancode{4 + ord(low) - ord('a')}"
        if low == "0":
            return "scancode39"
        if "1" <= low <= "9":
            return f"scancode{29 + int(low)}"
    if low.startswith("f") and low[1:].isdigit():
        number = int(low[1:])
        if 1 <= number <= 12:
            return f"scancode{57 + number}"
    return low


def defaults_path(cs2_install: Optional[Path]) -> Optional[Path]:
    """Where the game keeps its stock binds, if the game can be found."""
    if not cs2_install:
        return None
    candidate = Path(cs2_install) / "game" / "csgo" / "cfg" / DEFAULTS_FILE
    return candidate if candidate.is_file() else None


def load(cs2_install: Optional[Path]) -> Dict[str, str]:
    """Every stock bind, keyed the way a config writes the key.

    An empty mapping when the game cannot be found or the file will not parse.
    Callers treat that as "no default known" and leave the key alone, which is
    the safe direction to be wrong in.
    """
    path = defaults_path(cs2_install)
    if path is None:
        return {}
    try:
        data = vdf.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, vdf.VdfError):
        return {}

    root = next(iter(data.values()), {})
    if not isinstance(root, dict):
        return {}
    bindings = root.get("bindings")
    if not isinstance(bindings, dict):
        return {}

    out: Dict[str, str] = {}
    for name, command in bindings.items():
        if not isinstance(command, str) or not command.strip():
            continue
        key = normalise(name)
        if key:
            out[key] = command.strip()
    return out


def for_key(table: Dict[str, str], binding: str) -> str:
    """The stock command for one key, or "" if the game does not bind it.

    A key with no default -- most of them -- gets nothing rather than a guess.
    Switching a script off there simply leaves the key doing nothing, which is
    what the game itself would do.
    """
    return table.get(normalise(binding), "")
