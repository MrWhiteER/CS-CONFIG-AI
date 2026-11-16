"""Best-effort capture exclusion for our own two overlay windows."""

import ctypes
from ctypes import wintypes as w

WDA_EXCLUDEFROMCAPTURE = 0x11


def set_capture_exclusion(hwnd, enabled):
    # Only a real integer handle reaches user32; anything else (no native
    # window yet, a stand-in object) is skipped, never raised.
    if isinstance(hwnd, bool) or not isinstance(hwnd, int) or hwnd <= 0:
        return
    try:
        user = ctypes.WinDLL("user32", use_last_error=True)
        affinity = user.SetWindowDisplayAffinity
        affinity.argtypes = [w.HWND, w.DWORD]
        affinity.restype = w.BOOL
        affinity(hwnd, WDA_EXCLUDEFROMCAPTURE if enabled else 0)
    except (AttributeError, OSError, TypeError, ValueError, ctypes.ArgumentError):
        pass


def configure_panel(window, enabled):
    try:
        # pywebview's Windows backend exposes its own Form, never a game handle.
        native = window.native
        set_capture_exclusion(native.Handle.ToInt64(), enabled)
    except (AttributeError, OSError, TypeError, ValueError):
        pass
