"""Settings that belong to a Steam account, and settings that belong here.

Everything this application configures belongs to one account -- its config
folder, its scripts, what it optimises for, what gets written when you apply.
Six accounts on one machine is ordinary, and until now they shared one set of
settings, so signing in as somebody else showed the previous account's folder
and the previous account's favourites.

So preferences are split in two:

* **per account** -- anything describing that account's CS2 setup. Kept under
  the account id, and swapped when the signed-in account changes.
* **this machine** -- how the application itself is arranged and behaves: the
  width of the rail, where the keyboard models sit on the desk, whether
  updates download on their own. The same person at the same desk wants these
  the same whichever account they are playing on.

Getting the split wrong is not symmetrical. A machine-wide setting stored per
account is a small annoyance -- it resets when you switch. An account setting
stored machine-wide points one account's tools at another account's files,
which is the thing this exists to stop. Anything not named below is treated as
belonging to the account, because that is the safer half to be wrong in.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Settings about this installation rather than about any account.
MACHINE_KEYS = frozenset({
    "tab",              # which section was open
    "rail_width",       # how wide the rail was left
    "mouse_shape",      # which mouse the keyboard view draws
    "kb_layout",        # where the models sit on the desk
    "kb_shown",         # whether each model is drawn
    "update_auto_download",
    "update_skip",
    # Which sound devices to hold on to. Machine-wide rather than per-account:
    # the endpoints belong to the hardware in front of you, and signing into a
    # second Steam account does not change which headset is plugged in.
    "audio_output",
    "audio_input",
    "audio_enforce",
    "settings_sub",   # which settings category was open
})

# The account whose settings are shown, which is itself machine-wide: it is a
# record of what this copy is currently looking at.
ACTIVE_KEY = "account"

# Set only when somebody chooses an account, never by the application working
# one out. The difference matters: a record of which account the settings were
# moved to is not a request to stop following Steam.
PINNED_KEY = "pinned_account"


def is_machine(key: str) -> bool:
    return key in MACHINE_KEYS or key in (ACTIVE_KEY, PINNED_KEY)


def accounts(prefs: Dict[str, Any]) -> Dict[str, Any]:
    store = prefs.get("accounts")
    return store if isinstance(store, dict) else {}


def ui_for(prefs: Dict[str, Any], account_id: Optional[str]) -> Dict[str, Any]:
    """What the page should be shown for this account.

    The machine-wide settings are folded in, so the page receives one flat
    object and does not have to know which half a setting came from.
    """
    machine = prefs.get("ui")
    machine = dict(machine) if isinstance(machine, dict) else {}
    out = {key: value for key, value in machine.items() if is_machine(key)}

    if account_id:
        mine = accounts(prefs).get(str(account_id))
        if isinstance(mine, dict):
            out.update(mine)
        out[ACTIVE_KEY] = str(account_id)
    return out


def remember(prefs: Dict[str, Any], account_id: Optional[str],
             changes: Dict[str, Any]) -> Dict[str, Any]:
    """Write changes into whichever half each one belongs to."""
    prefs.setdefault("ui", {})
    store = prefs.setdefault("accounts", {})

    mine: Optional[Dict[str, Any]] = None
    if account_id:
        mine = store.setdefault(str(account_id), {})

    for key, value in changes.items():
        if is_machine(key) or mine is None:
            prefs["ui"][key] = value
        else:
            mine[key] = value
    return prefs


def migrate(prefs: Dict[str, Any], account_id: Optional[str]) -> bool:
    """Move a single shared set of settings onto the account using them.

    Everything was machine-wide before this existed, so a first run finds one
    account's real setup sitting in the shared half. Left there it would be
    handed to every other account -- pointing them at a config folder that is
    not theirs -- so it is moved to whichever account is signed in now, which
    is the one it was almost certainly describing.

    Returns whether anything moved, so the caller knows to save.
    """
    if not account_id:
        return False
    machine = prefs.get("ui")
    if not isinstance(machine, dict):
        return False

    strays = {key: value for key, value in machine.items() if not is_machine(key)}
    if not strays:
        return False

    store = prefs.setdefault("accounts", {})
    mine = store.setdefault(str(account_id), {})
    for key, value in strays.items():
        # An account that already has its own answer keeps it.
        mine.setdefault(key, value)
        machine.pop(key, None)
    return True
