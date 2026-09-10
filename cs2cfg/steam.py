"""Steam integration: finding the install, the user, and patching its files.

The important rule in this module is that ``localconfig.vdf`` is Steam's file,
not ours. It holds friends state, per-app settings and a lot else besides, so
we never parse and re-emit it. We locate one line and rewrite that line,
leaving every other byte exactly as Steam wrote it.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import vdf
from .backup import BackupSession

APP_ID = "730"
STEAM_ID64_BASE = 76561197960265728

LAUNCH_PATH = ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps", APP_ID]


class SteamError(RuntimeError):
    """Steam could not be located, or one of its files could not be changed safely."""


@dataclass
class SteamUser:
    account_id: str
    path: Path
    persona: Optional[str] = None
    most_recent: bool = False

    @property
    def steam_id64(self) -> int:
        return STEAM_ID64_BASE + int(self.account_id)

    @property
    def localconfig(self) -> Path:
        return self.path / "config" / "localconfig.vdf"

    @property
    def video_cfg(self) -> Path:
        return self.path / APP_ID / "local" / "cfg" / "cs2_video.txt"

    @property
    def has_cs2(self) -> bool:
        return (self.path / APP_ID).is_dir()

    @property
    def label(self) -> str:
        name = self.persona or "unknown account"
        flag = "  (last signed in)" if self.most_recent else ""
        return f"{name} [{self.account_id}]{flag}"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def find_steam_root() -> Path:
    """Locate the Steam installation."""
    try:
        import winreg

        for hive, key in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
        ):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    for value_name in ("SteamPath", "InstallPath"):
                        try:
                            raw, _ = winreg.QueryValueEx(handle, value_name)
                        except FileNotFoundError:
                            continue
                        candidate = Path(str(raw))
                        if candidate.exists():
                            return candidate
            except OSError:
                continue
    except ImportError:
        pass  # not Windows

    for guess in (
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
        Path.home() / ".steam" / "steam",
    ):
        if guess.exists():
            return guess

    raise SteamError("Steam installation not found. Pass --steam-root to point at it.")


def find_libraries(steam_root: Path) -> List[Path]:
    """Every Steam library folder, including the install itself."""
    libraries = [steam_root]
    manifest = steam_root / "steamapps" / "libraryfolders.vdf"
    if not manifest.exists():
        return libraries

    try:
        data = vdf.parse(manifest.read_text(encoding="utf-8", errors="replace"))
    except vdf.VdfError:
        return libraries

    root = next(iter(data.values()), {})
    if not isinstance(root, dict):
        return libraries

    for entry in root.values():
        path_value = entry.get("path") if isinstance(entry, dict) else entry
        if isinstance(path_value, str):
            candidate = Path(path_value)
            if candidate.exists() and candidate not in libraries:
                libraries.append(candidate)
    return libraries


def find_cs2_install(steam_root: Path) -> Optional[Path]:
    """Path to the Counter-Strike install directory, if the game is installed."""
    for library in find_libraries(steam_root):
        manifest = library / "steamapps" / f"appmanifest_{APP_ID}.acf"
        if not manifest.exists():
            continue
        try:
            data = vdf.parse(manifest.read_text(encoding="utf-8", errors="replace"))
        except vdf.VdfError:
            continue
        state = next(iter(data.values()), {})
        install_dir = state.get("installdir") if isinstance(state, dict) else None
        if install_dir:
            candidate = library / "steamapps" / "common" / install_dir
            if candidate.exists():
                return candidate
    return None


def cfg_dir(cs2_install: Path) -> Path:
    """The game's cfg folder, where exec'd configs have to live."""
    return cs2_install / "game" / "csgo" / "cfg"


def _personas(steam_root: Path) -> Dict[str, Dict[str, str]]:
    login = steam_root / "config" / "loginusers.vdf"
    if not login.exists():
        return {}
    try:
        data = vdf.parse(login.read_text(encoding="utf-8", errors="replace"))
    except vdf.VdfError:
        return {}

    users = next(iter(data.values()), {})
    out: Dict[str, Dict[str, str]] = {}
    if isinstance(users, dict):
        for steam_id64, info in users.items():
            if not isinstance(info, dict) or not steam_id64.isdigit():
                continue
            account_id = str(int(steam_id64) - STEAM_ID64_BASE)
            out[account_id] = {
                "persona": info.get("PersonaName") or info.get("AccountName") or "",
                "most_recent": info.get("MostRecent", "0"),
                "timestamp": info.get("Timestamp", "0"),
            }
    return out


def list_users(steam_root: Path, cs2_only: bool = True) -> List[SteamUser]:
    """Steam accounts on this machine, most recently used first."""
    userdata = steam_root / "userdata"
    if not userdata.exists():
        raise SteamError(f"no userdata folder under {steam_root}; has Steam ever signed in here?")

    personas = _personas(steam_root)
    users: List[SteamUser] = []
    for entry in userdata.iterdir():
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        info = personas.get(entry.name, {})
        user = SteamUser(
            account_id=entry.name,
            path=entry,
            persona=info.get("persona") or None,
            most_recent=info.get("most_recent") == "1",
        )
        if cs2_only and not user.has_cs2:
            continue
        users.append(user)

    def rank(user: SteamUser) -> tuple:
        info = personas.get(user.account_id, {})
        try:
            stamp = int(info.get("timestamp", "0"))
        except ValueError:
            stamp = 0
        mtime = user.localconfig.stat().st_mtime if user.localconfig.exists() else 0
        return (user.most_recent, stamp, mtime)

    return sorted(users, key=rank, reverse=True)


# ---------------------------------------------------------------------------
# Steam process
# ---------------------------------------------------------------------------

def steam_running() -> bool:
    """True if steam.exe is up.

    Steam holds localconfig.vdf in memory and rewrites it on exit, so any edit
    made while it is running will be silently reverted.
    """
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return "steam.exe" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Launch options
# ---------------------------------------------------------------------------

def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def read_launch_options(user: SteamUser) -> str:
    """Current launch options for CS2, or an empty string if none are set."""
    if not user.localconfig.exists():
        return ""
    text = user.localconfig.read_text(encoding="utf-8", errors="replace")
    value = vdf.read_value(text, LAUNCH_PATH, "LaunchOptions")
    return value or ""


def write_launch_options(
    user: SteamUser,
    value: str,
    session: Optional[BackupSession] = None,
    force: bool = False,
) -> str:
    """Rewrite exactly one line of localconfig.vdf.

    Returns a short description of what was done. Raises if Steam is running,
    unless ``force`` is set, because Steam would overwrite the change on exit.
    """
    if steam_running() and not force:
        raise SteamError(
            "Steam is running. It keeps localconfig.vdf in memory and rewrites it when it exits, "
            "so it would discard this change. Close Steam completely and try again."
        )

    path = user.localconfig
    if not path.exists():
        raise SteamError(f"localconfig.vdf not found for account {user.account_id}: {path}")

    if session is not None:
        session.add(path)

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    location = vdf.find_key_line(text, LAUNCH_PATH, "LaunchOptions")
    escaped = _escape(value)

    key_line = location["key_line"]
    if key_line is not None:
        original = lines[key_line - 1]
        indent = re.match(r"[\t ]*", original).group(0)
        ending = "\r\n" if original.endswith("\r\n") else "\n" if original.endswith("\n") else ""
        lines[key_line - 1] = f'{indent}"LaunchOptions"\t\t"{escaped}"{ending}'
        action = f"replaced line {key_line}"
    elif location["block_open_line"] is not None:
        open_line = location["block_open_line"]
        indent = "\t" * int(location["block_indent"] or 7)
        ending = "\r\n" if lines[open_line - 1].endswith("\r\n") else "\n"
        lines.insert(open_line, f'{indent}"LaunchOptions"\t\t"{escaped}"{ending}')
        action = f"inserted after line {open_line}"
    else:
        raise SteamError(
            f"could not find the app {APP_ID} block in {path}. "
            "Launch CS2 from Steam once so it creates the entry, then re-run."
        )

    path.write_text("".join(lines), encoding="utf-8")
    return action


# ---------------------------------------------------------------------------
# Video config
# ---------------------------------------------------------------------------

def read_video_cfg(user: SteamUser) -> Dict[str, str]:
    """The contents of cs2_video.txt as a flat dict."""
    path = user.video_cfg
    if not path.exists():
        return {}
    try:
        data = vdf.parse(path.read_text(encoding="utf-8", errors="replace"))
    except vdf.VdfError:
        return {}
    root = next(iter(data.values()), {})
    return {k: v for k, v in root.items() if isinstance(v, str)} if isinstance(root, dict) else {}


def write_video_cfg(
    user: SteamUser,
    changes: Dict[str, int],
    session: Optional[BackupSession] = None,
) -> Dict[str, tuple]:
    """Apply ``changes`` to cs2_video.txt, leaving every other key alone.

    Returns ``{key: (before, after)}`` for the keys that actually moved.
    """
    path = user.video_cfg
    if not path.exists():
        raise SteamError(
            f"cs2_video.txt not found at {path}. Launch CS2 once so it writes its video settings, then re-run."
        )

    if session is not None:
        session.add(path)

    text = path.read_text(encoding="utf-8", errors="replace")
    document = vdf.parse(text)
    root_key = next(iter(document), "video.cfg")
    root = document[root_key]
    if not isinstance(root, dict):
        raise SteamError(f"{path} has an unexpected shape; refusing to write to it.")

    diff: Dict[str, tuple] = {}
    for key, value in changes.items():
        before = root.get(key)
        after = str(value)
        if before != after:
            diff[key] = (before, after)
        root[key] = after

    body = vdf.dumps({root_key: root})
    path.write_text(body + "\n", encoding="utf-8")
    return diff
