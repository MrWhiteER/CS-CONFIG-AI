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
