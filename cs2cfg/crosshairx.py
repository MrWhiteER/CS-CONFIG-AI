"""Crosshair X: find it, say whether it is up, and start it.

Crosshair X draws its own crosshair over whatever is on screen. People who use
one want the game's crosshair gone -- two crosshairs a pixel apart is worse
than either alone -- so turning this on here also writes ``crosshair 0`` into
the generated config. That is the whole integration: notice it, offer to start
it with the game, and stop the game drawing a second one.

It is a Steam app (1366800), so it is found the way every other Steam app in
this project is found: by its manifest in the libraries Steam already told us
about. No hardcoded path, nothing in the registry, and nothing that breaks
when somebody installs to a different drive.

Two things this deliberately does not do:

* claim it is allowed. An external overlay is against the rules of some
  leagues and fine in others, and that is not a question this application can
  answer for somebody. The interface says so and leaves the decision where it
  belongs.
* touch Crosshair X's own settings. Its configuration is its own; this starts
  it and otherwise leaves it completely alone.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

APP_ID = "1366800"
APP_NAME = "Crosshair X"
EXE = "CrosshairX.exe"

# What CS2 is told when the overlay is in charge of the crosshair.
CONVAR = "crosshair"
OFF = "0"
ON = "1"
REASON = "Crosshair X is drawing one; two crosshairs a pixel apart is worse than either"

# The launcher writes this one file, execed from the same autoexec as the
# generated config. Its own file rather than a line in autoperf.vcfg, because
# autoperf.vcfg is a whole performance profile: rewriting it on every launch
# would apply a set of settings nobody pressed Apply for.
CFG_NAME = "crosshair.vcfg"

_RUNNING_SEEN = (0.0, False)


def _manifest(library: Path) -> Optional[Path]:
    found = library / "steamapps" / f"appmanifest_{APP_ID}.acf"
    return found if found.is_file() else None


def find(libraries: List[Path]) -> Optional[Dict[str, Any]]:
    """Where Crosshair X is installed, or None.

    ``libraries`` are the Steam library roots the caller already knows about,
    so this never has to guess at drives.
    """
    from . import vdf

    for library in libraries:
        manifest = _manifest(Path(library))
        if manifest is None:
            continue
        try:
            data = vdf.parse(manifest.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        root = next(iter(data.values()), {})
        if not isinstance(root, dict):
            continue
        folder = str(root.get("installdir") or "CrosshairX")
        home = Path(library) / "steamapps" / "common" / folder
        exe = home / EXE
        return {
            "installed": True,
            "name": str(root.get("name") or APP_NAME),
            "folder": str(home),
            "exe": str(exe) if exe.is_file() else "",
            "app_id": APP_ID,
        }
    return None


def running(max_age: float = 4.0) -> bool:
    """Whether Crosshair X is up.

    Cached like the CS2 check for the same reason: it spawns tasklist, and the
    page asks often enough that doing it for real each time would be felt.
    """
    global _RUNNING_SEEN
    now = time.time()
    when, answer = _RUNNING_SEEN
    if now - when < max_age:
        return answer
    fresh = _running_now()
    _RUNNING_SEEN = (time.time(), fresh)
    return fresh


def _running_now() -> bool:
    if sys.platform != "win32":
        return False
    try:
        done = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {EXE}", "/NH"],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return EXE.lower() in (done.stdout or "").lower()


def start() -> Dict[str, Any]:
    """Ask Steam to start it.

    Through Steam rather than the executable directly: it is a Steam app, and
    launching one behind Steam's back is how people end up with an app that
    thinks it is unlicensed.
    """
    if running():
        return {"ok": True, "already": True, "detail": f"{APP_NAME} is already running"}
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", f"steam://rungameid/{APP_ID}"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": f"could not ask Steam to start it: {exc}"}
    # Deliberately not waiting to confirm: it takes its time to appear, and a
    # blocking wait here would hold up the launch it is meant to accompany.
    return {"ok": True, "already": False,
            "detail": f"Asked Steam to start {APP_NAME}"}


def decide(hide: bool, installed: bool, up: bool, starting: bool) -> Dict[str, Any]:
    """What the game's crosshair should be set to for this launch.

    The interesting case is the refusal. Somebody can leave "turn off CS2's
    crosshair" ticked and then launch on a day the overlay is not there -- it
    was closed, or uninstalled, or Steam will not start it. Honouring the tick
    would drop them into a match with no crosshair at all, which is far worse
    than the duplicate it was meant to avoid. So the tick only takes effect
    when something is actually going to draw the other one.
    """
    if not hide:
        return {"value": ON, "hidden": False, "warning": "",
                "why": "CS2 draws its own crosshair"}
    if not installed:
        return {"value": ON, "hidden": False,
                "why": "CS2 draws its own crosshair",
                "warning": f"{APP_NAME} is not installed, so the game keeps its crosshair"}
    if not (up or starting):
        return {"value": ON, "hidden": False,
                "why": "CS2 draws its own crosshair",
                "warning": f"{APP_NAME} is not running, so the game keeps its crosshair "
                           "rather than leaving you with none"}
    return {"value": OFF, "hidden": True, "warning": "", "why": REASON}


def render_cfg(value: str, why: str) -> str:
    """The one-setting config the launcher writes before the game starts."""
    from .emit import GENERATED_MARKER

    return "\n".join([
        GENERATED_MARKER,
        f"// Written by the launcher each time you press Play, from the {APP_NAME}",
        "// switch. Delete it and it comes back; untick the switch and it stops.",
        "",
        f'{CONVAR} "{value}"   // {why}',
        "",
    ])


def summary(libraries: List[Path]) -> Dict[str, Any]:
    """Everything the page needs to draw the card."""
    found = find(libraries)
    if not found:
        return {"installed": False, "running": False, "app_id": APP_ID,
                "name": APP_NAME, "store": f"https://store.steampowered.com/app/{APP_ID}/"}
    return {**found, "running": running()}


# ---------------------------------------------------------------------------
# Waking the overlay broker
# ---------------------------------------------------------------------------

# Crosshair X almost certainly draws over the game through the same
# overlay-hook broker Windows uses for the Xbox Game Bar. On a machine where
# Game Bar has never been opened since boot, that broker has not attached to
# anything yet, and no third-party overlay sharing it -- Crosshair X
# included -- draws until it has. Opening Game Bar (Win+G) wakes the broker;
# a foreground-window change is what then makes Windows re-evaluate which
# overlays are allowed to draw over which window, which is why alt-tabbing
# once is what finally makes the crosshair appear. There is no API for
# either half, so both are reproduced the way they were found: a keystroke,
# then a focus change on the game's own window.
_VK_WIN = 0x5B
_VK_G = 0x47
_KEYEVENTF_KEYUP = 0x0002
WARMUP_SECONDS = 6.0


class _KeyInput(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.WPARAM)]


class _MouseInput(ctypes.Structure):
    """Never sent -- declared only because it is the union's largest member.

    SendInput rejects the whole call unless cbSize is exactly sizeof(INPUT),
    and that size is set by the union's biggest arm, which is this one and
    not the keyboard arm actually used below.
    """

    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", wintypes.WPARAM)]


class _HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", _MouseInput), ("ki", _KeyInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _InputUnion)]


_INPUT_KEYBOARD = 1
_INPUT_SIZE = ctypes.sizeof(_Input)


def _press_win_g() -> int:
    """Send Win+G down and up. Returns the Windows error code, 0 on success."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.c_void_p, ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT

    sequence = [(_VK_WIN, False), (_VK_G, False), (_VK_G, True), (_VK_WIN, True)]
    events = []
    for code, up in sequence:
        item = _Input(type=_INPUT_KEYBOARD)
        item.u.ki = _KeyInput(wVk=code, wScan=0,
                              dwFlags=_KEYEVENTF_KEYUP if up else 0,
                              time=0, dwExtraInfo=0)
        events.append(item)
    block = (_Input * len(events))(*events)

    ctypes.set_last_error(0)
    sent = user32.SendInput(len(events), ctypes.byref(block), _INPUT_SIZE)
    if sent == len(events):
        return 0
    return ctypes.get_last_error() or -1


def wake_overlay(
    should_stop: Optional[Callable[[], bool]] = None,
    warmup: float = WARMUP_SECONDS,
    interval: float = 0.5,
) -> Dict[str, Any]:
    """Nudge Windows into attaching the overlay broker to the game window.

    Meant to run once, right after the game window is confirmed up. Sends
    Win+G to wake Game Bar's broker, waits for it to settle, then minimizes
    and restores the game window to produce the foreground-change event the
    broker waits for before it decides what it is allowed to draw over.
    Cancellable the same way the rest of the launch sequence is: checked
    between ticks rather than slept through in one call.
    """
    if sys.platform != "win32":
        return {"ok": False, "error": "this is Windows-only"}

    code = _press_win_g()
    if code:
        return {"ok": False, "error": f"Windows did not accept the keystroke (error {code})"}

    deadline = time.monotonic() + warmup
    while time.monotonic() < deadline:
        if should_stop and should_stop():
            return {"ok": False, "error": "cancelled"}
        time.sleep(interval)

    from . import window as windowmod

    target = windowmod.find_game_window()
    if target is None:
        return {"ok": False, "error": "the game window was gone by the time the overlay warmed up"}
    windowmod.nudge_focus(target.hwnd)
    return {"ok": True, "detail": "woke the overlay broker and refocused the game"}
