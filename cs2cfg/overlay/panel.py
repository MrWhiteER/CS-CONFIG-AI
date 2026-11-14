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


class Panel:
    def __init__(self, service, factory, *, focus=return_to_game, keyboard=None, setup=None):
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
        self.error = ""

    def toggle(self):
        with self._lock:
            if self.visible:
                self.hide()
            elif self.service.panel_allowed():
                self.error = ""
                self.visible = True
                if self.window is None:
                    try:
                        self.window = self.factory()
                    except Exception as exc:
                        self.visible = False
                        self.error = f"Panel: {exc}"
                        return
                    self.window.events.loaded += self.loaded
                    self.window.events.closing += self.closing
                else:
                    self.window.show()  # pywebview shows and activates its window.
                    self._script(True)

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
                              lambda: self.window.hide() if self.window else None):
                try:
                    operation()
                except Exception as exc:
                    self.error = f"Panel: {exc}"

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
