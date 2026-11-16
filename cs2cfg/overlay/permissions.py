"""Read frame-capture permissions; setup owns all permission requests."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

SETUP_HINT = "Finish setup to enable frame stats"
SIGN_OUT_HINT = "Sign out of Windows and back in once to enable frame stats"
DISMISSED_KEY = "overlay_sign_out_hint_dismissed"


def _token_has_sid(sid: str) -> bool:
    """Check enabled token membership without localized group names."""
    try:
        security = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        convert = security.ConvertStringSidToSidW
        convert.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
        convert.restype = wintypes.BOOL
        check = security.CheckTokenMembership
        check.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL)]
        check.restype = wintypes.BOOL
        free = kernel.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        value = ctypes.c_void_p()
        if not convert(sid, ctypes.byref(value)):
            return False
        try:
            member = wintypes.BOOL()
            return bool(check(None, value, ctypes.byref(member)) and member.value)
        finally:
            free(value)
    except (AttributeError, OSError):
        return False


def frame_capture_ready() -> bool:
    # Administrators are enabled in an elevated token, disabled in a filtered
    # one. Performance Log Users membership takes effect at the next sign-in.
    return _token_has_sid("S-1-5-32-544") or _token_has_sid("S-1-5-32-559")


def request_frame_capture() -> str:
    return "handled by setup wizard"


def frame_capture_hint(ui: dict | None = None, *, ready: bool | None = None) -> str:
    if ready is None:
        ready = frame_capture_ready()
    if ready:
        return ""
    try:
        from .. import elevated
    except ImportError:
        return SETUP_HINT
    if not elevated.ready():
        return SETUP_HINT
    return "" if (ui or {}).get(DISMISSED_KEY, False) else SIGN_OUT_HINT
