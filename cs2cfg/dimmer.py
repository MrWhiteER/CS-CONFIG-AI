"""Dim every screen while the match-found alert is up.

One black, half-transparent window per monitor, always on top, that the mouse
goes straight through and that never takes focus. The alert window is then put
above them, so it is the one bright thing on any screen.

Plain Win32 on a thread of its own, because these windows need a message loop
and must not wait on the web view. Nothing here touches another program: they
are this application's own windows, laid over the desktop.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import List, Optional, Tuple

ALPHA = 165          # 0..255: how dark the dim gets
FADE = 0.18          # seconds to fade in

Rect = Tuple[int, int, int, int]

_lock = threading.Lock()
_state = {"thread": None, "stop": None}


def monitors() -> List[Rect]:
    """Every monitor's full rectangle, in virtual-screen coordinates."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    found: List[Rect] = []
    PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                              ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def cb(_mon, _dc, rect, _lp):
        r = rect.contents
        found.append((r.left, r.top, r.right, r.bottom))
        return True

    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, PROC,
                                           wintypes.LPARAM]
    user32.EnumDisplayMonitors(None, None, PROC(cb), 0)
    return found


def show() -> bool:
    """Dim every screen. Safe to call again while already dimmed."""
    if sys.platform != "win32":
        return False
    with _lock:
        if _state["thread"] and _state["thread"].is_alive():
            return True
        stop = threading.Event()
        ready = threading.Event()
        thread = threading.Thread(target=_run, args=(stop, ready),
                                  name="dimmer", daemon=True)
        _state.update(thread=thread, stop=stop)
        thread.start()
    ready.wait(1.0)
    return True


def hide() -> None:
    with _lock:
        stop: Optional[threading.Event] = _state["stop"]
        _state.update(thread=None, stop=None)
    if stop is not None:
        stop.set()


def _run(stop: threading.Event, ready: threading.Event) -> None:  # pragma: no cover
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)
    user32.DefWindowProcW.restype = LRESULT
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.DWORD,
                                                  ctypes.c_ubyte, wintypes.DWORD]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                    wintypes.UINT, wintypes.UINT, wintypes.UINT]
    gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR)]

    @WNDPROC
    def proc(hwnd, msg, wparam, lparam):
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    instance = kernel32.GetModuleHandleW(None)
    wc = WNDCLASSW()
    wc.lpfnWndProc = proc
    wc.hInstance = instance
    wc.hbrBackground = gdi32.CreateSolidBrush(0)          # black
    wc.lpszClassName = "cs2cfg_dimmer"
    user32.RegisterClassW(ctypes.byref(wc))               # fails harmlessly if registered

    WS_POPUP = 0x80000000
    EX = (0x00080000      # LAYERED
          | 0x00000008    # TOPMOST
          | 0x00000020    # TRANSPARENT: clicks go through
          | 0x00000080    # TOOLWINDOW: no taskbar button
          | 0x08000000)   # NOACTIVATE: never takes focus
    windows = []
    for left, top, right, bottom in monitors():
        hwnd = user32.CreateWindowExW(EX, wc.lpszClassName, "dim", WS_POPUP,
                                      left, top, right - left, bottom - top,
                                      None, None, instance, None)
        if hwnd:
            user32.SetLayeredWindowAttributes(hwnd, 0, 0, 2)   # LWA_ALPHA
            user32.ShowWindow(hwnd, 4)                          # SW_SHOWNOACTIVATE
            windows.append(hwnd)
    ready.set()

    def pump():
        msg = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def set_alpha(value: int):
        for hwnd in windows:
            user32.SetLayeredWindowAttributes(hwnd, 0, max(0, min(255, value)), 2)

    start = time.monotonic()
    while not stop.is_set():
        progress = min(1.0, (time.monotonic() - start) / FADE)
        set_alpha(int(ALPHA * progress))
        pump()
        time.sleep(0.016 if progress < 1.0 else 0.05)

    # Fade out as quickly as it came in.
    end = time.monotonic()
    while True:
        progress = min(1.0, (time.monotonic() - end) / FADE)
        set_alpha(int(ALPHA * (1.0 - progress)))
        pump()
        if progress >= 1.0:
            break
        time.sleep(0.016)
    for hwnd in windows:
        user32.DestroyWindow(hwnd)
    pump()
