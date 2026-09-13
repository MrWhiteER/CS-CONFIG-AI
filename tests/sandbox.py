"""Keep tests that write for real out of the player's own data.

Several tests drive the web handlers rather than a stand-in, which is the right
call -- they exercise the shipped code. But those handlers write for real: a
bind takes a backup before editing, then prunes to the newest twenty sets.
Pointed at the live store, one full run files twenty throwaway backups of
temporary files and evicts the player's actual undo history for their real
config. That has happened.

``CS2CFG_DATA`` looks like the answer and is not: the location is resolved once
per process and cached the first time anything asks for it, so whether the
variable arrives in time depends on which test module imported first. Patching
the one function that names the directory does not care about import order.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from cs2cfg import backup


def redirect_backups(case) -> Path:
    """Send backups somewhere disposable for the lifetime of ``case``.

    Call from ``setUp``. Returns the directory, for a test that wants to look
    at what was filed.
    """
    tmp = tempfile.TemporaryDirectory(prefix="cs2cfg-backups-")
    case.addCleanup(tmp.cleanup)
    root = Path(tmp.name)
    patch = mock.patch.object(backup, "backups_root", return_value=root)
    patch.start()
    case.addCleanup(patch.stop)
    return root
