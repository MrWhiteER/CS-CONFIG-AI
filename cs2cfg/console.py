"""Console handling for a build that is both an app and a command line tool.

The packaged binary is a Windows GUI-subsystem executable, so double-clicking it
opens a window and nothing else -- no console flashes up behind it. That alone
would make every CLI command useless, because a GUI-subsystem process starts
with no standard streams at all: ``sys.stdout`` is ``None`` and the first
``print`` raises.

So on startup it asks to attach to the console of whatever launched it. Run from
cmd or PowerShell, there is one, and output appears in that window exactly as a
console build would. Launched from a shortcut there is not, and the streams are
pointed at the null device so printing is harmless rather than fatal.

This is the same arrangement as ``python.exe`` and ``pythonw.exe``, in one file.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

ATTACH_PARENT_PROCESS = -1
ERROR_ACCESS_DENIED = 5          # already attached to a console
ERROR_INVALID_HANDLE = 6         # the parent has no console

_attached: Optional[bool] = None


def attach_parent_console() -> str:
    """Try to attach to the launching process's console.

    Returns ``"new"`` if one was just attached, ``"existing"`` if this process
    already had one, or ``"none"`` if there is no console to be had. The
    distinction matters: only a freshly attached console needs its streams
    bound, and rebinding an existing one is actively harmful.
    """
    if not sys.platform.startswith("win"):
        return "none"

    import ctypes

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError:
        return "none"

    if kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
        return "new"
    return "existing" if ctypes.get_last_error() == ERROR_ACCESS_DENIED else "none"


def _reopen(stream_name: str, device: str, mode: str) -> None:
    try:
        handle = open(device, mode, encoding="utf-8", errors="replace",
                      buffering=1 if "w" in mode else -1)
    except OSError:
        return
    setattr(sys, stream_name, handle)


def prepare_streams() -> bool:
    """Make stdout/stderr usable however the process was started.

    Returns True if a real console is attached. Safe to call more than once.
    """
    global _attached
    if _attached is not None:
        return _attached

    if not getattr(sys, "frozen", False):
        _attached = sys.stdout is not None and sys.stdout.isatty()
        return _attached

    state = attach_parent_console()

    # Only ever bind a stream that does not already have one. A working stream
    # may be a pipe -- a shell capturing output, or `| findstr` -- and CONOUT$
    # writes to the console device directly, so replacing it would send the
    # output past whatever was collecting it. That silently produced a CLI
    # that printed nothing when its output was captured.
    fallback = "CONOUT$" if state in ("new", "existing") else os.devnull
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            _reopen(name, fallback, "w")
    if getattr(sys, "stdin", None) is None:
        _reopen("stdin", "CONIN$" if state in ("new", "existing") else os.devnull, "r")

    _attached = state in ("new", "existing")
    return _attached


def has_console() -> bool:
    """Whether output will actually be seen by anyone."""
    return bool(prepare_streams())


def can_prompt() -> bool:
    """Whether it is reasonable to ask a question on stdin.

    Without a console there is nobody to answer, and blocking on input would
    hang the process with no window to explain why.
    """
    if not has_console():
        return False
    stream = getattr(sys, "stdin", None)
    if stream is None:
        return False
    try:
        return stream.readable()
    except (AttributeError, ValueError):
        return False
