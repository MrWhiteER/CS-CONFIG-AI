"""What happens by itself after a region lock or unlock (Edy, Nov 2026).

Locking used to leave three manual steps: raise CS2's matchmaking max ping so
the locked region counts as "near", turn on the console log the wrong-server
check reads, and restart Steam so matchmaking measures the relays again. This
does all three:

* Launch options get ``+mm_dedicated_search_maxping N`` (just above the locked
  region's measured ping) and ``-condebug``. A launch option is used rather
  than editing CS2's own convar file, because Steam Cloud syncs that file and
  CS2 rewrites it while running; ``+`` commands apply on every start.
* Steam is closed with its own ``-shutdown`` (never killed unless it refuses),
  the options are written, and Steam is started again.
* Unlocking removes the max-ping option, so CS2's own setting applies again.
  ``-condebug`` stays: it is harmless and keeps match detection working.

Never runs while CS2 is open: the lock itself waits for CS2 to close.
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

MAXPING_TOKEN = re.compile(r"(?:^|\s)\+mm_dedicated_search_maxping\s+\d+(?=\s|$)", re.I)
CONDEBUG = re.compile(r"(?:^|\s)-condebug(?=\s|$)", re.I)
MARGIN_MS = 15
FLOOR_MS = 40
CEILING_MS = 350
UNKNOWN_MS = 150


def max_ping_for(region_ping: Optional[float]) -> int:
    """Just above the locked region's ping, so it counts as a near server."""
    if region_ping is None:
        return UNKNOWN_MS
    return int(min(CEILING_MS, max(FLOOR_MS, round(region_ping) + MARGIN_MS)))


def launch_options_for(current: str, max_ping: Optional[int]) -> str:
    """The launch options with our max ping (or none) and -condebug."""
    text = MAXPING_TOKEN.sub(" ", current or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not CONDEBUG.search(text):
        text = (text + " -condebug").strip()
    if max_ping is not None:
        text = (text + f" +mm_dedicated_search_maxping {int(max_ping)}").strip()
    return text


def _active_user():
    from . import steam, whoami
    from .cli import load_prefs

    root = steam.find_steam_root()
    users = steam.list_users(root)
    known = [u.account_id for u in users]
    pinned = str(load_prefs().get("ui", {}).get("pinned_account") or "")
    account = pinned if pinned in known else whoami.current(root, known)[0]
    return next((u for u in users if u.account_id == account), users[0] if users else None)


def _cs2_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq cs2.exe", "/NH"],
                             capture_output=True, text=True, timeout=15,
                             creationflags=0x08000000 if sys.platform == "win32" else 0).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "cs2.exe" in out.lower()


def run(action: str, region_ping: Optional[float] = None) -> Dict[str, Any]:
    """Apply the follow-up for ``apply`` or ``unlock``. Never raises."""
    from . import backup, launcher, quickfix, steam

    steps: List[str] = []
    try:
        if _cs2_running():
            return {"ok": False, "steps": steps, "detail": "CS2 is open; close it and restart Steam yourself."}
        user = _active_user()
        if user is None:
            return {"ok": False, "steps": steps, "detail": "No Steam account found to update."}
        max_ping = max_ping_for(region_ping) if action == "apply" else None
        wanted = launch_options_for(steam.read_launch_options(user), max_ping)

        exe = launcher.steam_exe()
        was_running = quickfix._steam_running()
        if was_running and exe is not None:
            subprocess.Popen([str(exe), "-shutdown"],
                             creationflags=0x08000000 if sys.platform == "win32" else 0)
            if not quickfix._wait_until(lambda: not quickfix._steam_running(), quickfix.STEAM_SHUTDOWN_WAIT):
                return {"ok": False, "steps": steps,
                        "detail": "Steam did not close, so launch options were not changed. Restart Steam yourself."}
            steps.append("closed Steam")

        if steam.read_launch_options(user) != wanted:
            session = backup.BackupSession(note="region lock: max matchmaking ping and console log")
            steam.write_launch_options(user, wanted, session)
            steps.append(f"max matchmaking ping {max_ping} ms" if max_ping else "max matchmaking ping back to CS2's setting")

        if exe is not None and (was_running or action == "apply"):
            subprocess.Popen([str(exe)], creationflags=0x08000000 if sys.platform == "win32" else 0)
            steps.append("started Steam")
        return {"ok": True, "steps": steps, "max_ping": max_ping,
                "detail": "Done for you: " + ", ".join(steps) + "." if steps else ""}
    except Exception as exc:  # the lock itself already succeeded
        return {"ok": False, "steps": steps, "detail": f"Lock is on, but the follow-up stopped: {exc}"}
