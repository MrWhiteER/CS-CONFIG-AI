"""Where things live, in development and when frozen into a single exe.

Two separate questions, often confused:

* **Bundled resources** — the PowerShell probe, the knowledge JSON, the web
  page. Read-only, shipped with the code. Under PyInstaller's one-file mode
  these are unpacked to a temporary directory that vanishes on exit, so they
  must be found via ``sys._MEIPASS`` rather than relative to the source tree.

* **User data** — preferences, backups, session history. Read-write, and the
  part that decides whether this counts as "installed".

For a portable build the second one goes *beside the exe*, not in ``%APPDATA%``.
Put the exe on a USB stick and the whole tool travels with its data and leaves
nothing on the machine it ran on. ``%APPDATA%`` is only the fallback for when
the exe sits somewhere unwritable, which is the one case where refusing to
store anything would be worse than storing it in the usual place.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

PORTABLE_DIR_NAME = "cs2cfg-data"
ENV_OVERRIDE = "CS2CFG_DATA"

_resolved: Optional[Path] = None


def is_frozen() -> bool:
    """True when running from a PyInstaller build rather than source."""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Directory holding bundled read-only resources."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / "cs2cfg"
        return Path(sys.executable).parent / "cs2cfg"
    return Path(__file__).parent


def app_dir() -> Path:
    """Directory the executable itself sits in."""
    if is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


# The installer's identity, fixed forever. Must match AppId in installer.iss:
# Windows uses it to recognise a later Setup.exe as an update to the same
# installation rather than a second copy of the program.
APP_ID = "{52CB95CD-82DB-40CA-8E48-7DDE2C72820D}"
UNINSTALL_KEY = (r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
                 rf"\{APP_ID}_is1")

PORTABLE = "portable"
INSTALLED = "installed"
SOURCE = "source"


def _registered_install() -> Optional[Path]:
    """Where the installer says it put this program, if it ever did.

    Per-user installs are recorded under HKCU, which needs no elevation to
    read. Anything unexpected -- no key, no value, a non-Windows machine --
    means "not installed", which is the safe answer: a portable copy that
    updates itself by copying files can do no harm to an installed one.
    """
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            location, _ = winreg.QueryValueEx(key, "InstallLocation")
    except OSError:
        return None
    return Path(location) if location else None


def install_kind() -> str:
    """Which edition this copy is, which decides how it updates itself.

    * ``source``    -- running from a checkout; updates are a git pull
    * ``installed`` -- put here by the installer; updates run the next Setup.exe
    * ``portable``  -- unpacked from the zip; updates copy files into place

    Decided by asking the registry where the installer put things and seeing
    whether that is here. The uninstaller sitting next to the executable is
    accepted as a second opinion, for the case where the registry entry has
    been cleaned away but the installation is still in use.
    """
    if not is_frozen():
        return SOURCE
    here = app_dir().resolve()
    registered = _registered_install()
    if registered is not None:
        try:
            if registered.resolve() == here:
                return INSTALLED
        except OSError:
            pass
    if (here / "unins000.exe").is_file():
        return INSTALLED
    return PORTABLE


def _writable(directory: Path) -> bool:
    """Can we actually create files here? Ask, rather than assume.

    A USB stick can be read-only, and a folder under Program Files will fail
    silently into VirtualStore on some configurations. Writing a real file is
    the only honest test.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def user_data_dir() -> Path:
    """Where preferences, backups and session history are kept.

    Resolved once per process and cached, so a mid-run failure cannot split
    the data across two locations.
    """
    global _resolved
    if _resolved is not None:
        return _resolved

    override = os.environ.get(ENV_OVERRIDE)
    if override:
        candidate = Path(override).expanduser()
        if _writable(candidate):
            _resolved = candidate
            return _resolved

    if is_frozen():
        portable = app_dir() / PORTABLE_DIR_NAME
        if _writable(portable):
            _resolved = portable
            return _resolved

    roaming = os.environ.get("APPDATA")
    fallback = Path(roaming) / "cs2-autoconfig" if roaming else Path.home() / ".cs2-autoconfig"
    if _writable(fallback):
        _resolved = fallback
        return _resolved

    # Last resort, so the tool still runs even if nothing durable is writable.
    _resolved = Path(tempfile.gettempdir()) / "cs2-autoconfig"
    _resolved.mkdir(parents=True, exist_ok=True)
    return _resolved


def storage_kind() -> str:
    """A short description of where data ended up, for the UI to show."""
    directory = user_data_dir()
    if os.environ.get(ENV_OVERRIDE):
        return "custom location"
    if is_frozen() and directory.parent == app_dir():
        return "portable, beside the executable"
    if "AppData" in str(directory) or ".cs2-autoconfig" in str(directory):
        return "user profile"
    return "temporary"
