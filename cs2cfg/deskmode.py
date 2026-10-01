"""The desktop mode this application borrowed, and giving it back.

The launcher narrows the desktop so a stretched resolution fills the panel,
and puts it back when the game exits. That works as long as the launcher gets
to run its restore. Two things stop it:

* the game dies in a way that leaves the launcher waiting, or the launcher is
  itself closed or killed while the desktop is still narrow;
* the restore runs and fails -- it asks Windows for the mode in the registry,
  and if that call does not take, the old code reported it and gave up.

Either way somebody is left on a 1550x1440 desktop with no obvious way back,
which is a worse state than any setting this application exists to fix.

``set_mode`` already asks Windows for a *temporary* mode, which Windows is
supposed to drop when the process that asked for it goes away. That is a real
safety net and it is not a complete one: it does nothing when the process is
still alive and merely no longer watching, which is exactly the case here.

So the mode is written down before it is changed, in a file rather than in
memory, because memory is the thing that does not survive what this is for.
The record says what the desktop was and what it was changed to, and both
matter: putting a desktop back is only safe while it still holds the mode we
put there. If it holds something else, somebody or something has moved it
since, and the right thing is to leave it alone and drop the record.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

RECORD = "desktop_mode.json"

Mode = Tuple[int, int, int]


def record_path() -> Path:
    from .paths import user_data_dir

    return user_data_dir() / RECORD


def remember(before: Mode, changed_to: Mode) -> Optional[Path]:
    """Note the mode being borrowed, before it is borrowed.

    Written before the change rather than after, so a failure *during* the
    change still leaves something to put back.
    """
    path = record_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "before": list(before),
            "changed_to": list(changed_to),
            "at": time.time(),
        }, indent=1), encoding="utf-8")
    except OSError:
        # Not fatal. Losing the safety net is not a reason to refuse a launch.
        return None
    return path


def forget() -> None:
    try:
        record_path().unlink()
    except OSError:
        pass


def outstanding() -> Optional[Dict[str, Any]]:
    """The borrowed mode nobody has given back, or None."""
    try:
        raw = record_path().read_text(encoding="utf-8")
    except OSError:
        return None                      # nothing recorded, which is normal
    try:
        data = json.loads(raw)
    except ValueError:
        # Half a file is not something to set somebody's resolution from, and
        # it will not repair itself.
        forget()
        return None
    try:
        before = tuple(int(n) for n in data["before"])
        changed = tuple(int(n) for n in data["changed_to"])
    except (KeyError, TypeError, ValueError):
        forget()
        return None
    if len(before) != 3 or len(changed) != 3:
        forget()
        return None
    return {"before": before, "changed_to": changed, "at": float(data.get("at") or 0)}


def _matches(a: Mode, b: Mode) -> bool:
    """Same picture, ignoring refresh rate.

    Refresh is compared loosely on purpose: Windows reports 165 for a mode
    requested as 164.998, and a desktop that is the right size at a slightly
    differently-reported rate is not a desktop somebody is stuck on.
    """
    return (a[0], a[1]) == (b[0], b[1])


def tidy(game_running: bool) -> Dict[str, Any]:
    """Put the desktop back if the game is gone and we still have it.

    Called from the status poll, so it has to be cheap and it has to be silent
    when there is nothing to do -- which is almost always. The file not
    existing is one failed stat, and that is the whole cost on a normal tick.
    """
    held = outstanding()
    if held is None:
        return {}
    if game_running:
        # The session owns the desktop. Leave it be.
        return {}

    from . import window

    try:
        now = window.current_mode()
    except Exception:
        return {}

    if _matches(now, held["before"]):
        # Already back -- Windows dropped the temporary mode itself, most
        # likely. Nothing to do but stop watching for it.
        forget()
        return {}

    if not _matches(now, held["changed_to"]):
        # The desktop is in neither mode, so something else has moved it since
        # and this record is describing a situation that no longer exists.
        # Forcing our idea of "before" onto it would be the wrong call.
        forget()
        return {}

    before = held["before"]
    try:
        window.set_mode(before[0], before[1], before[2])
    except Exception as exc:
        # Kept, not dropped: the next tick tries again, and the manual repair
        # still has something to work from.
        return {"ok": False, "error": str(exc), "restored": False}

    forget()
    return {"ok": True, "restored": True, "mode": list(before),
            "detail": f"desktop put back to {before[0]}x{before[1]}"
                      f"@{before[2]} after the game ended"}


def restore() -> Dict[str, Any]:
    """Put the desktop back now, asked for by hand.

    The emergency version of :func:`tidy`, and deliberately less careful about
    whether the current mode is one we recognise: somebody pressing this is
    telling us the desktop is wrong, and second-guessing them is not useful.

    With no record to work from it falls back to the mode Windows has in the
    registry, which is what the desktop is supposed to be between sessions.
    """
    from . import window

    try:
        now = window.current_mode()
    except Exception as exc:
        return {"ok": False, "error": f"could not read the display mode: {exc}"}

    held = outstanding()
    target: Optional[Mode] = held["before"] if held else None
    source = "the mode this application borrowed"

    if target is None:
        try:
            target = window.registry_mode()
            source = "the mode Windows has saved for this display"
        except Exception as exc:
            return {"ok": False,
                    "error": f"nothing recorded to go back to, and Windows "
                             f"would not say what the saved mode is: {exc}"}

    if _matches(now, target):
        forget()
        return {"ok": True, "changed": False,
                "detail": f"the desktop is already {target[0]}x{target[1]}"}

    try:
        window.set_mode(target[0], target[1], target[2], persist=True)
    except Exception as exc:
        return {"ok": False, "error": f"could not set {target[0]}x{target[1]}: {exc}"}

    forget()
    return {"ok": True, "changed": True, "mode": list(target),
            "detail": f"desktop set back to {target[0]}x{target[1]}@{target[2]}, "
                      f"from {source}"}
