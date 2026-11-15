"""Lazy desktop panel. Hidden means no view refreshes or region queries."""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes as w

from .regionlock import RegionLock
from .capture import configure_panel


def return_to_game(hwnd):
    """Only hand focus back while one of our windows is foreground."""
    import os

    if not hwnd:
        return
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetForegroundWindow.restype = w.HWND
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.SetForegroundWindow.argtypes = [w.HWND]
    user.SetForegroundWindow.restype = w.BOOL
    pid = w.DWORD()
    user.GetWindowThreadProcessId(user.GetForegroundWindow(), ctypes.byref(pid))
    if pid.value == os.getpid():
        user.SetForegroundWindow(hwnd)


def monitor_bounds(hwnd):
    """Read the game's monitor bounds, including negative monitor origins."""
    try:
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
        user.MonitorFromWindow.restype = w.HANDLE
        class Info(ctypes.Structure):
            _fields_ = [("size", w.DWORD), ("monitor", w.RECT),
                        ("work", w.RECT), ("flags", w.DWORD)]
        user.GetMonitorInfoW.argtypes = [w.HANDLE, ctypes.POINTER(Info)]
        info = Info()
        info.size = ctypes.sizeof(info)
        if user.GetMonitorInfoW(user.MonitorFromWindow(hwnd, 2), ctypes.byref(info)):
            r = info.monitor
            return r.left, r.top, r.right - r.left, r.bottom - r.top
    except (AttributeError, OSError):
        pass
    return None


class Panel:
    def __init__(self, service, factory, *, focus=return_to_game, keyboard=None, setup=None, fade_seconds=.12):
        self.service, self.factory = service, factory
        self.focus, self.keyboard = focus, keyboard
        self.setup = setup
        self.window = None
        self.visible = False
        self.regions = RegionLock()
        self._lock = threading.RLock()
        self._loaded = False
        self._destroying = False
        self._close_timer = None
        self._fade_timer = None
        self._fade_seconds = fade_seconds
        self.error = ""

    def toggle(self):
        with self._lock:
            if self.visible:
                self.hide()
            elif self.service.panel_allowed():
                self.error = ""
                if self._fade_timer:
                    self._fade_timer.cancel()
                    self._fade_timer = None
                self.visible = True
                self.service.suspend_pins()
                if self.window is None:
                    try:
                        self.window = self.factory()
                    except Exception as exc:
                        self.visible = False
                        self.error = f"Panel: {exc}"
                        return
                    self._place()
                    self.window.events.loaded += self.loaded
                    self.window.events.closing += self.closing
                else:
                    self._place()
                    self.window.show()  # pywebview shows and activates its window.
                    self._script(True)

    def _place(self):
        bounds = monitor_bounds(self.service.game_hwnd())
        if bounds:
            x, y, width, height = bounds
            self.window.move(x, y)
            self.window.resize(width, height)

    def loaded(self):
        with self._lock:
            self._loaded = True
            self.configure_capture()
            self._script(self.visible)

    def configure_capture(self):
        if self.window and self._loaded:
            configure_panel(self.window, self.service._settings["overlay_hide_from_capture"])

    def _script(self, active):
        if self.window and self._loaded:
            self.window.evaluate_js(f"window.overlayPanelActive({str(active).lower()})")

    def hide(self, *, restore=True):
        with self._lock:
            if self._close_timer:
                self._close_timer.cancel()
                self._close_timer = None
            if not self.visible:
                return
            self.visible = False
            self.regions.close()
            for operation in (lambda: self._script(False),
                              lambda: self.focus(self.service.game_hwnd()) if restore else None,
                              self._fade_hide):
                try:
                    operation()
                except Exception as exc:
                    self.error = f"Panel: {exc}"

    def _fade_hide(self):
        if not self.window:
            return
        if self._fade_seconds:
            self._fade_timer = threading.Timer(self._fade_seconds, self._hide_native)
            self._fade_timer.daemon = True
            self._fade_timer.start()
        else:
            self.window.hide()

    def _hide_native(self):
        with self._lock:
            self._fade_timer = None
            if not self.visible and self.window and not self._destroying:
                self.window.hide()

    def closing(self):
        if self._destroying:
            return True
        # Native close is a blocking GUI event. Return the cancellation before
        # invoking webview APIs, as the app's tray close handler also does.
        if self.visible and self._close_timer is None:
            self._close_timer = threading.Timer(.05, self._finish_close)
            self._close_timer.daemon = True
            self._close_timer.start()
        return False

    def _finish_close(self):
        with self._lock:
            self._close_timer = None
            self.hide()

    def destroy(self):
        self.hide(restore=False)
        self._destroying = True
        if self._fade_timer:
            self._fade_timer.cancel()
            self._fade_timer = None
        if self.window:
            self.window.destroy()

    def data(self, action="poll", code=None):
        with self._lock:
            if not self.visible or not self.service.panel_allowed():
                return {"available": False, "text": "Panel hidden"}
            if action == "open":
                return self.regions.open() if not self.regions.visible else self.regions.snapshot()
            if action == "lock":
                if not code:
                    raise ValueError("Choose a listed region")
                return self.regions.request(code)
            if action == "unlock":
                return self.regions.request()
            if action != "poll":
                raise ValueError("Unknown panel action")
            return self.regions.poll()
