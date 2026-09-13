"""Which Steam account is in use right now.

Everything this application shows belongs to one account: its config folder,
its binds, its scripts, its video settings. So it has to know which account it
is looking at, and it should follow the one signed in rather than ask.

Four signals, in the order they deserve to be trusted:

1. **the live one** -- Steam writes the signed-in account to
   ``ActiveProcess\\ActiveUser`` while it is running. Definitive when it is
   not zero, which is most of the time Steam is up.
2. **the auto-login name** -- who Steam signs in as when it starts, by account
   name rather than id, so it needs the login list to resolve.
3. **the newest login** -- the most recent ``Timestamp`` in ``loginusers.vdf``.
4. **the folder** -- whichever userdata directory was written to last.

The cascade exists because none of them is reliable alone. ``ActiveUser`` is
zero whenever Steam is closed, and it was zero on the machine this was written
against even with Steam running. ``MostRecent``, which the earlier code relied
on, is not written at all by current Steam versions -- the key simply is not
there, so every account claimed not to be the recent one.

Nothing here writes, and nothing here reads any credential: an account name
and a numeric id are all these files are asked for.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import vdf

STEAM_ID64_BASE = 76561197960265728

# How the answer was reached, so the interface can say why it thinks this.
LIVE = "signed in to Steam now"
AUTOLOGIN = "Steam's auto-login account"
NEWEST = "most recently signed in"
FOLDER = "most recently used folder"
UNKNOWN = ""


def _registry(path: str, name: str) -> Optional[str]:
    """One value out of HKCU, or None. Never raises."""
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            value, _kind = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return str(value) if value is not None else None


def active_user_id() -> Optional[str]:
    """The account Steam says is signed in, or None.

    Steam keeps this at zero while nobody is signed in, and clears it on exit,
    so a zero here is "ask something else" rather than "no such account".
    """
    raw = _registry(r"Software\Valve\Steam\ActiveProcess", "ActiveUser")
    if raw is None:
        return None
    try:
        number = int(raw)
    except (TypeError, ValueError):
        return None
    return str(number) if number else None


def autologin_name() -> Optional[str]:
    """The account name Steam signs in as, which is not an id."""
    name = _registry(r"Software\Valve\Steam", "AutoLoginUser")
    return name.strip() or None if name else None


def login_records(steam_root: Path) -> Dict[str, Dict[str, str]]:
    """What loginusers.vdf knows, keyed by account id.

    Deliberately does not look for "MostRecent": current Steam versions do not
    write it, and reading a key that is never there is how the earlier code
    came to believe no account had ever been used.
    """
    path = Path(steam_root) / "config" / "loginusers.vdf"
    try:
        data = vdf.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, vdf.VdfError):
        return {}

    users = next(iter(data.values()), {})
    out: Dict[str, Dict[str, str]] = {}
    if not isinstance(users, dict):
        return out
    for steam_id64, info in users.items():
        if not isinstance(info, dict) or not str(steam_id64).isdigit():
            continue
        account_id = str(int(steam_id64) - STEAM_ID64_BASE)
        out[account_id] = {
            "account_name": str(info.get("AccountName") or ""),
            "persona": str(info.get("PersonaName")
                           or info.get("AccountName") or ""),
            "timestamp": str(info.get("Timestamp") or "0"),
            "autologin": str(info.get("AutoLogin") or "0"),
        }
    return out


def _newest_login(records: Dict[str, Dict[str, str]]) -> Optional[str]:
    best, when = None, -1
    for account_id, info in records.items():
        try:
            stamp = int(info.get("timestamp") or 0)
        except ValueError:
            stamp = 0
        if stamp > when:
            best, when = account_id, stamp
    return best if when > 0 else None


def _newest_folder(steam_root: Path) -> Optional[str]:
    userdata = Path(steam_root) / "userdata"
    best, when = None, -1.0
    try:
        entries = list(userdata.iterdir())
    except OSError:
        return None
    for entry in entries:
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        try:
            stamp = entry.stat().st_mtime
        except OSError:
            continue
        if stamp > when:
            best, when = entry.name, stamp
    return best


def current(steam_root: Path, known: Optional[List[str]] = None) -> Tuple[Optional[str], str]:
    """The account in use, and how that was decided.

    ``known`` limits the answer to accounts this machine actually has CS2 for;
    without it, a signal naming an account with no CS2 would be taken at its
    word and the interface would have nothing to show.
    """
    records = login_records(steam_root)

    def acceptable(account_id: Optional[str]) -> Optional[str]:
        if not account_id:
            return None
        if known is not None and account_id not in known:
            return None
        return account_id

    live = acceptable(active_user_id())
    if live:
        return live, LIVE

    name = autologin_name()
    if name:
        for account_id, info in records.items():
            if info.get("account_name", "").lower() == name.lower():
                chosen = acceptable(account_id)
                if chosen:
                    return chosen, AUTOLOGIN

    newest = acceptable(_newest_login(records))
    if newest:
        return newest, NEWEST

    folder = acceptable(_newest_folder(steam_root))
    if folder:
        return folder, FOLDER

    return None, UNKNOWN
