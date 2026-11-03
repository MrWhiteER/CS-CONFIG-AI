"""Which keys a keyboard/mouse layout profile is not allowed to take over.

A match profile like ``warmup.vcfg`` only overrides the handful of binds it
actually writes; everything else keeps whatever the standard layout last set.
Pinning a key asks for more than that: for *this* profile, force that key
back to its standard binding even though the profile's own file rebinds it --
e.g. keeping ping working while a practice profile takes over smoke/noclip
binds.

This is a preference about how this app generates a profile's switch script,
not a game setting, so it lives in the app's own data directory next to its
other state -- not in the scanned collection.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

from .paths import user_data_dir


def _store() -> Path:
    return user_data_dir() / "layouts"


def _collection_key(root: Path) -> str:
    return hashlib.sha256(str(Path(root).resolve()).lower().encode("utf-8")).hexdigest()[:16]


def sync_key(root: Path) -> str:
    """A name for this collection that means the same thing on another
    machine. ``_collection_key`` hashes the absolute path, which is exactly
    wrong for the cloud: the same collection on two computers lives at two
    different paths, so matching on the path would never line them up.

    The collection folder's own name -- what CS2's launch options exec, e.g.
    "mrwhiteer" -- is the one thing that is actually shared between devices
    that are meant to see the same profiles.
    """
    return Path(root).name.strip().lower() or "default"


def _pins_path(root: Path) -> Path:
    return _store() / f"{_collection_key(root)}.json"


def load_pins(root: Path) -> Dict[str, List[str]]:
    """``{profile_file: [pinned_key, ...]}`` for this scanned collection."""
    try:
        data = json.loads(_pins_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(file): sorted({str(key) for key in keys})
        for file, keys in data.items() if isinstance(keys, list)
    }


def _baseline_path(root: Path) -> Path:
    return _store() / f"{_collection_key(root)}.baseline.json"


def load_baseline(root: Path) -> Dict[str, Dict[str, str]]:
    """``{standard_file: {key: original_body}}`` -- what each key a profile
    has ever overridden looked like the first time that happened, so the
    Keyboard tab's "Default" option can put it back.
    """
    try:
        data = json.loads(_baseline_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for file, keys in data.items():
        if isinstance(keys, dict):
            out[str(file)] = {str(k): str(v) for k, v in keys.items()}
    return out


def record_baseline(root: Path, file: str, bodies: Dict[str, str]) -> None:
    """Remember what each of these keys was bound to in ``file``, right
    before a profile is about to override it for the first time.

    Never overwrites a key already recorded -- the whole point is to keep
    the *original* value even after several different profiles have since
    taken turns overriding it.
    """
    baseline = load_baseline(root)
    known = baseline.setdefault(file, {})
    changed = False
    for key, body in bodies.items():
        if key not in known:
            known[key] = body
            changed = True
    if not changed:
        return

    path = _baseline_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, indent=1), encoding="utf-8")


def save_pins(root: Path, profile_file: str, keys: List[str]) -> Dict[str, List[str]]:
    """Set (or clear, with an empty list) the pins for one profile file."""
    all_pins = load_pins(root)
    if keys:
        all_pins[profile_file] = sorted(set(keys))
    else:
        all_pins.pop(profile_file, None)

    path = _pins_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(all_pins, indent=1), encoding="utf-8")
    return all_pins


# ---------------------------------------------------------------------------
# Which profile the switcher last pointed at. The Keyboard tab's tabs used to
# light up by checking whether a profile's own binds happened to match the
# standard layout -- which lit up every profile sharing those binds (a copy
# alongside its original) and stayed lit for Default even after switching, as
# long as nothing had ever been baselined. This is the one explicit pointer
# that makes the switcher behave like a single choice instead of a guess.
# ---------------------------------------------------------------------------

def _current_path(root: Path) -> Path:
    return _store() / f"{_collection_key(root)}.current.json"


def load_current(root: Path) -> Optional[str]:
    """The profile file last switched to, or ``None`` for Default."""
    try:
        data = json.loads(_current_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    file = data.get("file")
    return str(file) if isinstance(file, str) and file else None


def save_current(root: Path, profile_file: Optional[str]) -> None:
    """Remember ``profile_file`` (or ``None`` for Default) as current."""
    path = _current_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"file": profile_file}, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------
# Profile registry: which profiles this app made, and which the user has
# dismissed from the Keyboard tab's selector.
#
# Both are opinions about the *list*, not the files themselves, so they live
# here next to the pins rather than anywhere in the scanned collection.
# ---------------------------------------------------------------------------

def _registry_path(root: Path) -> Path:
    return _store() / f"{_collection_key(root)}.profiles.json"


def load_registry(root: Path) -> Dict[str, List[str]]:
    """``{"created": [...], "hidden": [...]}`` for this scanned collection."""
    try:
        data = json.loads(_registry_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    out: Dict[str, List[str]] = {}
    for key in ("created", "hidden"):
        values = data.get(key)
        out[key] = sorted({str(v) for v in values}) if isinstance(values, list) else []
    return out


def _save_registry(root: Path, registry: Dict[str, List[str]]) -> None:
    path = _registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=1), encoding="utf-8")


def mark_created(root: Path, profile_file: str) -> None:
    """Record that this app wrote ``profile_file``, so it may later be deleted
    outright rather than only removed from the list."""
    registry = load_registry(root)
    registry["created"] = sorted(set(registry["created"]) | {profile_file})
    _save_registry(root, registry)


def is_created(root: Path, profile_file: str) -> bool:
    return profile_file in load_registry(root)["created"]


def hide_profile(root: Path, profile_file: str) -> None:
    """Drop ``profile_file`` from the selector without touching its file."""
    registry = load_registry(root)
    registry["hidden"] = sorted(set(registry["hidden"]) | {profile_file})
    _save_registry(root, registry)


def forget_profile(root: Path, profile_file: str) -> None:
    """Clear all app state for a profile file: its pins and both registry
    flags -- used once the file itself is gone, so nothing stale lingers."""
    registry = load_registry(root)
    changed = False
    for key in ("created", "hidden"):
        if profile_file in registry[key]:
            registry[key] = [f for f in registry[key] if f != profile_file]
            changed = True
    if changed:
        _save_registry(root, registry)
    save_pins(root, profile_file, [])
    if load_current(root) == profile_file:
        save_current(root, None)
