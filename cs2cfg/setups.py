"""Named setups: several answers to "what is this machine for right now".

One person wants different things at different times. Practice wants every
frame it can get and does not care how it looks; a match wants the same but
with the launch mode that keeps alt-tab instant; recording wants the picture
back. Until now that meant re-choosing all of it each time and remembering
what the last combination was, which is the thing peripheral software solved
years ago with profiles.

A setup is a name and the handful of choices that actually differ between
those cases. Deliberately not everything:

* not the config folder -- switching what you are tuning for should never
  quietly point the tools at another folder;
* not the account, for the same reason twice over;
* not anything machine-wide, which is about this desk rather than this setup.

Switching is just writing those values back, so it goes through the same path
a manual change does and is undone the same way. Nothing is applied to the
game by switching: a setup decides what the next Apply will write, not what is
on disk now.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# What a setup remembers. Each one is a choice somebody would genuinely make
# differently between practising, playing and recording.
KEYS = (
    "intent",           # what the generated config optimises for
    "target_fps",       # the number everything else is chosen to reach
    "stretch_mode",     # borderless or exclusive fullscreen
    "patch_video",      # set CS2 to borderless before launching
    "write_video",      # what an Apply is allowed to write
    "write_cfg",
    "write_launch",
    "link_autoexec",
    "fix_scaling",
)

STORE = "setups"        # name -> {key: value}
LIVE = "setup_live"     # the name last switched to, if it still exists

MAX_NAME = 40
MAX_SETUPS = 20


class SetupError(Exception):
    """The name is unusable, or there is no room for another."""


def clean_name(raw: str) -> str:
    name = " ".join(str(raw or "").split())[:MAX_NAME].strip()
    if not name:
        raise SetupError("a setup needs a name")
    return name


def _store(ui: Dict[str, Any]) -> Dict[str, Any]:
    found = ui.get(STORE)
    return dict(found) if isinstance(found, dict) else {}


def snapshot(ui: Dict[str, Any]) -> Dict[str, Any]:
    """The values a setup would hold, taken from what is chosen now."""
    return {key: ui[key] for key in KEYS if key in ui}


def listing(ui: Dict[str, Any]) -> Dict[str, Any]:
    """Every saved setup, and which one is being followed.

    "Followed" stops being true the moment something is changed by hand, which
    the caller works out by comparing -- saying a setup is live when the
    settings no longer match it would be a lie the user can see through.
    """
    saved = _store(ui)
    now = snapshot(ui)
    live = str(ui.get(LIVE) or "")
    if live not in saved:
        live = ""

    out: List[Dict[str, Any]] = []
    for name in sorted(saved, key=str.lower):
        values = saved[name] if isinstance(saved[name], dict) else {}
        matches = all(str(values.get(k, "")) == str(now.get(k, "")) for k in KEYS)
        out.append({"name": name, "values": values, "matches": matches})

    return {"setups": out, "live": live,
            "changed": bool(live) and not next(
                (s["matches"] for s in out if s["name"] == live), True)}


def save(ui: Dict[str, Any], name: str) -> Dict[str, Any]:
    """Keep what is chosen now under this name. Returns the prefs to write."""
    name = clean_name(name)
    saved = _store(ui)
    if name not in saved and len(saved) >= MAX_SETUPS:
        raise SetupError(f"there is room for {MAX_SETUPS} setups; delete one first")
    saved[name] = snapshot(ui)
    return {STORE: saved, LIVE: name}


def use(ui: Dict[str, Any], name: str) -> Dict[str, Any]:
    """The settings this setup stands for, ready to be written back."""
    name = clean_name(name)
    saved = _store(ui)
    if name not in saved:
        raise SetupError(f"there is no setup called {name}")
    values = saved[name]
    if not isinstance(values, dict):
        raise SetupError(f"{name} is stored wrong and cannot be used")
    # Only keys we recognise: a setup written by a later version may hold more,
    # and applying something this copy does not understand is how a setting
    # ends up set to a value nothing can show or undo.
    out = {key: values[key] for key in KEYS if key in values}
    out[LIVE] = name
    return out


def rename(ui: Dict[str, Any], old: str, new: str) -> Dict[str, Any]:
    old, new = clean_name(old), clean_name(new)
    saved = _store(ui)
    if old not in saved:
        raise SetupError(f"there is no setup called {old}")
    if new in saved and new != old:
        raise SetupError(f"there is already a setup called {new}")
    saved[new] = saved.pop(old)
    live = str(ui.get(LIVE) or "")
    return {STORE: saved, LIVE: new if live == old else live}


def remove(ui: Dict[str, Any], name: str) -> Dict[str, Any]:
    name = clean_name(name)
    saved = _store(ui)
    if name not in saved:
        raise SetupError(f"there is no setup called {name}")
    saved.pop(name)
    live = str(ui.get(LIVE) or "")
    return {STORE: saved, LIVE: "" if live == name else live}
