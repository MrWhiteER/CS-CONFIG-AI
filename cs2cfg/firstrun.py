"""The first-run setup: what a fresh install asks before anything else.

A new install used to open straight onto the full application with nothing
configured -- no permission given, no preset chosen, no sound devices pinned,
nothing set to start with the game. Everything was reachable, and none of it
was asked for. This is the short list of questions that make the app useful
on its first launch, asked once, in order:

1. **Sync** -- if this Steam account already has settings in the cloud from
   another PC, offer to bring them across (see :mod:`autosync`). Everything
   below still applies: devices and companion apps belong to this PC.
2. **Permission** -- may the app write into CS2's cfg folder. Nothing is
   generated there until the answer is yes.
3. **Sound** -- the default speakers/headset and microphone, held there by the
   same keeper the Settings tab uses.
4. **Preset** -- Competitive, Balanced or Visual, each shown with the frame
   rate this machine is estimated to reach on it.
5. **Before the game** -- which of the companion apps found on this PC start
   when CS2 does.
6. **Theme**.

This module holds the answers' logic and nothing about how the steps look;
the page draws them. Every step can be skipped, and finishing records that
the wizard ran, so it is never shown twice on the same PC.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

DONE_KEY = "firstrun_done"
CFG_WRITE_KEY = "cfg_write_ok"     # the same key autosync reads

STEPS = ("sync", "permission", "sound", "preset", "apps", "theme")

# The page calls the third preset "Visual"; the engine has always called it
# "quality". The label is the only thing that changes.
PRESETS = (
    ("competitive", "Competitive", "Highest frame rate and clearest picture for spotting players."),
    ("balanced", "Balanced", "Good-looking and smooth. The default."),
    ("quality", "Visual", "Best picture this PC can hold at a playable frame rate."),
)

THEMES = ("violet", "ember", "carbon", "acid", "crimson", "frost", "neon",
          "daylight", "paper", "pro")


def needed(prefs: Dict[str, Any]) -> bool:
    ui = prefs.get("ui") if isinstance(prefs.get("ui"), dict) else {}
    return not ui.get(DONE_KEY)


# --- step 2: the cfg folder --------------------------------------------------

def cfg_access(cfg_root: Optional[Path]) -> Dict[str, Any]:
    """Where the app would write, and whether it actually can.

    Tested with a real throwaway file rather than an access check, because on
    Windows the answer to "may I" and the answer to "did it work" differ
    whenever a game folder sits under Program Files or a locked drive.
    """
    if cfg_root is None:
        return {"path": "", "exists": False, "writable": False,
                "reason": "CS2 was not found on this PC"}
    root = Path(cfg_root)
    if not root.is_dir():
        return {"path": str(root), "exists": False, "writable": False,
                "reason": "CS2's cfg folder does not exist yet; start the game once"}
    try:
        handle, name = tempfile.mkstemp(prefix=".cs2cfg-", suffix=".tmp", dir=str(root))
        os.close(handle)
        os.unlink(name)
    except OSError as exc:
        return {"path": str(root), "exists": True, "writable": False,
                "reason": f"Windows would not let the app write there: {exc}"}
    return {"path": str(root), "exists": True, "writable": True, "reason": ""}


# --- step 4: presets with their frame rates ---------------------------------

def presets(machine: Any, kb: Any) -> List[Dict[str, Any]]:
    """Each preset with the frame rate it is estimated to give on this PC."""
    from .profile import build_profile

    out = []
    for intent, label, blurb in PRESETS:
        entry: Dict[str, Any] = {"id": intent, "label": label, "blurb": blurb,
                                 "fps": None, "bottleneck": ""}
        if machine is not None:
            try:
                profile = build_profile(machine, kb, intent=intent)
                entry["fps"] = int(profile.estimated_fps)
                entry["bottleneck"] = profile.bottleneck
                entry["tier"] = profile.tier
            except Exception:
                pass
        out.append(entry)
    return out


# --- step 5: companion apps found on this PC ---------------------------------

def _discord() -> Optional[Dict[str, Any]]:
    """Discord's own launcher, the way its Start menu shortcut starts it.

    ``Update.exe --processStart Discord.exe`` rather than the versioned
    ``app-1.0.x\\Discord.exe``, whose folder name changes with every update.
    """
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    for flavour, name in (("Discord", "Discord"), ("DiscordPTB", "Discord PTB"),
                          ("DiscordCanary", "Discord Canary")):
        updater = Path(local) / flavour / "Update.exe"
        if updater.is_file():
            return {"id": flavour.lower(), "name": name, "exe": str(updater),
                    "args": f"--processStart {flavour}.exe"}
    return None


def _crosshairx(libraries: Iterable[Path]) -> Optional[Dict[str, Any]]:
    from . import crosshairx

    try:
        found = crosshairx.find(list(libraries))
    except Exception:
        return None
    if not found or not found.get("exe"):
        return None
    return {"id": "crosshairx", "name": "Crosshair X", "exe": found["exe"], "args": "",
            "integration": "crosshairx"}


def _faceit() -> List[Dict[str, Any]]:
    """FACEIT and its anti-cheat, once the FACEIT integration is present.

    Imported lazily: the integration lands separately, and until it does the
    wizard simply does not list FACEIT rather than guessing at its paths.
    """
    try:
        from . import faceit_apps  # type: ignore[attr-defined]
    except ImportError:
        return []
    out = []
    for kind, name in ((getattr(faceit_apps, "CLIENT", "faceit-client"), "FACEIT"),
                       (getattr(faceit_apps, "AC", "faceit-ac"), "FACEIT Anti-Cheat")):
        try:
            exe = faceit_apps.find(kind)
        except Exception:
            exe = None
        if exe:
            out.append({"id": kind, "name": name, "exe": str(exe), "args": "",
                        "integration": kind})
    return out


def known_apps(libraries: Iterable[Path], ui: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every companion app this PC has, and whether it already starts with CS2."""
    from . import companions

    found: List[Dict[str, Any]] = []
    found.extend(_faceit())
    cx = _crosshairx(libraries)
    if cx:
        found.append(cx)
    dc = _discord()
    if dc:
        found.append(dc)

    held = {c["id"]: c for c in companions.listed(ui)}
    for entry in found:
        mine = held.get(entry["id"])
        entry["with_game"] = bool(mine and mine.get("with_game"))
    return found


def companions_change(ui: Dict[str, Any], available: List[Dict[str, Any]],
                      chosen: Iterable[str]) -> List[Dict[str, Any]]:
    """The companions list after the wizard's choices.

    Ticked apps are added (or switched on) to start with the game; unticked
    ones that were already listed are kept but switched off -- removing them
    would throw away a path somebody may have chosen by hand.
    """
    from . import companions

    chosen = {str(c) for c in chosen}
    held = companions.listed(ui)
    by_id = {c["id"]: c for c in held}
    for app in available:
        if app["id"] in by_id:
            by_id[app["id"]]["with_game"] = app["id"] in chosen
        elif app["id"] in chosen and len(held) < companions.MAX_COMPANIONS:
            entry = {"id": app["id"], "name": app["name"], "exe": app["exe"],
                     "args": app.get("args", ""), "with_game": True,
                     "integration": app.get("integration", "")}
            held.append(entry)
            by_id[app["id"]] = entry
    return held


# --- finishing ---------------------------------------------------------------

def answers_to_changes(answers: Dict[str, Any], ui: Dict[str, Any],
                       available: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Turn what was picked into preference changes. Unanswered steps change
    nothing, so skipping a step leaves whatever was there."""
    changes: Dict[str, Any] = {}

    if "cfg_write" in answers:
        allowed = bool(answers["cfg_write"])
        changes[CFG_WRITE_KEY] = allowed
        changes["write_cfg"] = allowed
        changes["link_autoexec"] = allowed

    sound = answers.get("sound")
    if isinstance(sound, dict):
        if sound.get("output"):
            changes["audio_output"] = str(sound["output"])
        if sound.get("input"):
            changes["audio_input"] = str(sound["input"])
        if sound.get("output") or sound.get("input"):
            changes["audio_enforce"] = True

    intent = answers.get("preset")
    if intent in {p[0] for p in PRESETS}:
        changes["intent"] = intent

    if isinstance(answers.get("apps"), list):
        changes["companions"] = companions_change(ui, available, answers["apps"])

    theme = answers.get("theme")
    if theme in THEMES:
        changes["theme"] = theme

    if "sync" in answers:
        from . import autosync

        changes[autosync.AUTO_KEY] = bool(answers["sync"])

    changes[DONE_KEY] = True
    return changes


MACHINE_KEYS = (DONE_KEY, CFG_WRITE_KEY, "sync_auto")
