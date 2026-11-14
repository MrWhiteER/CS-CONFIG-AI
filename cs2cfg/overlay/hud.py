"""A small click-through layered window, owned entirely by its waiting thread."""

from __future__ import annotations

import ctypes
import math
import threading
import time
from ctypes import wintypes as w

from .settings import FIELDS, hotkey as parse_hotkey

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011
WIDTH, HEIGHT = 640, 120


class Hotkeys:
    """Register a pair together so exchanging their chords also works."""

    def __init__(self, user, hwnd):
        self.user, self.hwnd = user, hwnd
        self.desired = None
        self.registered = []
        self.warning = ""

    def configure(self, hud, panel=None):
        desired = hud, panel
        if self.desired == desired:
            return
        self.close()
        self.desired = desired
        warnings = []
        for identifier, chord in enumerate(desired, 1):
            if chord is None:
                continue
            if self.user.RegisterHotKey(self.hwnd, identifier, *chord):
                self.registered.append(identifier)
            else:
                warnings.append(f"{'HUD' if identifier == 1 else 'Panel'} shortcut unavailable (already registered)")
        self.warning = "; ".join(warnings)

    def close(self):
        for identifier in self.registered:
            self.user.UnregisterHotKey(self.hwnd, identifier)
        self.registered = []
        self.desired = None


def display_values(sample: dict) -> dict[str, str]:
    """Shared HUD/API formatting; unavailable frame data stays missing."""
    def number(key: str, suffix: str = "") -> str:
        value = sample.get(key)
        if sample.get("frame_capture_ready") is False and key in FIELDS[:3]:
            value = None
        return f"{value:.1f}{suffix}" if value is not None else "\u2014"

    return {key: number(key, suffix) for key, suffix in zip(FIELDS, ("", "", " ms", "%", "%", " C"))}


def display_lines(sample: dict, fields=FIELDS, hotkey="Ctrl+Alt+O") -> tuple[str, ...]:
    values = display_values(sample)

    labels = {"fps": "FPS", "one_percent_low": "1% low", "frame_time_ms": "Frame",
              "cpu_percent": "CPU", "gpu_percent": "GPU", "gpu_temp_c": "Temp"}
    shown = {key: f"{label} {values[key]}" for key, label in labels.items()
             if key in fields}
    return (
        "CS CONFIG AI    " + "    ".join(shown[k] for k in FIELDS[:2] if k in shown),
        "    ".join(shown[k] for k in FIELDS[2:] if k in shown),
        sample.get("status", "PresentMon: waiting for frame data"),
        f"{hotkey}: show/hide",
    )


class Hud:
    def __init__(self, exclude_from_capture: bool = False, *, corner="top_left",
                 fields=FIELDS, hotkey="Ctrl+Alt+O", panel_hotkey="Ctrl+Alt+P",
                 on_panel=None) -> None:
        self.exclude = exclude_from_capture
        self.corner, self.fields, self.hotkey = corner, tuple(fields), hotkey
        self._chord = parse_hotkey(hotkey)
        self._panel_chord = parse_hotkey(panel_hotkey)
        self.on_panel = on_panel
        self.visible = False
        self._requested = True
        self._allowed = True
        self.warning = ""
        self.error = ""
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._sample: dict = {}
        self._position = (20, 20)
        self._wake = None
        self._thread = threading.Thread(target=self._run, name="overlay-hud", daemon=True)

    def start(self) -> None:
        self._thread.start()
        if not self._ready.wait(5):
            self.stop()
            raise RuntimeError("HUD did not initialise")
        if self.error:
            raise RuntimeError(self.error)

    def update(self, sample: dict, position: tuple[int, int] = (20, 20)) -> None:
        with self._lock:
            self._sample = dict(sample)
            self._position = position
            if self._wake:
                self._kernel.SetEvent(self._wake)

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            if self._wake:
                self._kernel.SetEvent(self._wake)
        if self._thread.is_alive():
            self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise RuntimeError("HUD did not stop")

    def set_allowed(self, allowed: bool) -> None:
        """Presentation/focus gate, independent of the player's hotkey choice."""
        with self._lock:
            if self._allowed == allowed:
                return
            self._allowed = allowed
            if self._wake:
                self._kernel.SetEvent(self._wake)

    def configure(self, *, fields, hotkey: str, panel_hotkey="Ctrl+Alt+P") -> None:
        chord = parse_hotkey(hotkey)
        with self._lock:
            self.fields, self.hotkey, self._chord = tuple(fields), hotkey, chord
            self._panel_chord = parse_hotkey(panel_hotkey)
            if self._wake:
                self._kernel.SetEvent(self._wake)

    def _run(self) -> None:
        try:
            self._window_loop()
        except Exception as exc:
            self.error = str(exc)
            self.visible = False
        finally:
            self._ready.set()

    def _window_loop(self) -> None:
        user = ctypes.WinDLL("user32", use_last_error=True)
        gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel = kernel
        proc_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

        class WNDCLASS(ctypes.Structure):
            _fields_ = [("style", w.UINT), ("proc", proc_type), ("cls_extra", ctypes.c_int),
                        ("wnd_extra", ctypes.c_int), ("instance", w.HINSTANCE), ("icon", w.HICON),
                        ("cursor", w.HANDLE), ("background", w.HBRUSH), ("menu", w.LPCWSTR),
                        ("name", w.LPCWSTR)]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("size", w.DWORD), ("width", w.LONG), ("height", w.LONG),
                        ("planes", w.WORD), ("bits", w.WORD), ("compression", w.DWORD),
                        ("image_size", w.DWORD), ("xppm", w.LONG), ("yppm", w.LONG),
                        ("used", w.DWORD), ("important", w.DWORD)]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("header", BITMAPINFOHEADER), ("colors", w.DWORD * 3)]

        class BLEND(ctypes.Structure):
            _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte),
                        ("alpha", ctypes.c_ubyte), ("format", ctypes.c_ubyte)]

        def bind(lib, name, result, args):
            function = getattr(lib, name)
            function.restype, function.argtypes = result, args
            return function

        ptr = ctypes.c_void_p
        bind(kernel, "GetModuleHandleW", w.HMODULE, [w.LPCWSTR])
        bind(kernel, "CreateEventW", w.HANDLE, [ptr, w.BOOL, w.BOOL, w.LPCWSTR])
        bind(kernel, "SetEvent", w.BOOL, [w.HANDLE])
        bind(kernel, "CloseHandle", w.BOOL, [w.HANDLE])
        bind(user, "RegisterClassW", w.ATOM, [ctypes.POINTER(WNDCLASS)])
        bind(user, "UnregisterClassW", w.BOOL, [w.LPCWSTR, w.HINSTANCE])
        bind(user, "CreateWindowExW", w.HWND, [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                              w.HWND, w.HMENU, w.HINSTANCE, ptr])
        bind(user, "DefWindowProcW", ctypes.c_ssize_t, [w.HWND, w.UINT, w.WPARAM, w.LPARAM])
        bind(user, "DestroyWindow", w.BOOL, [w.HWND])
        bind(user, "ShowWindow", w.BOOL, [w.HWND, ctypes.c_int])
        bind(user, "RegisterHotKey", w.BOOL, [w.HWND, ctypes.c_int, w.UINT, w.UINT])
        bind(user, "UnregisterHotKey", w.BOOL, [w.HWND, ctypes.c_int])
        bind(user, "PeekMessageW", w.BOOL, [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT])
        bind(user, "TranslateMessage", w.BOOL, [ctypes.POINTER(w.MSG)])
        bind(user, "DispatchMessageW", ctypes.c_ssize_t, [ctypes.POINTER(w.MSG)])
        bind(user, "MsgWaitForMultipleObjectsEx", w.DWORD,
             [w.DWORD, ctypes.POINTER(w.HANDLE), w.DWORD, w.DWORD, w.DWORD])
        bind(user, "UpdateLayeredWindow", w.BOOL,
             [w.HWND, w.HDC, ctypes.POINTER(w.POINT), ctypes.POINTER(w.SIZE), w.HDC,
              ctypes.POINTER(w.POINT), w.DWORD, ctypes.POINTER(BLEND), w.DWORD])
        bind(gdi, "CreateCompatibleDC", w.HDC, [w.HDC])
        bind(gdi, "CreateDIBSection", w.HBITMAP,
             [w.HDC, ctypes.POINTER(BITMAPINFO), w.UINT, ctypes.POINTER(ptr), w.HANDLE, w.DWORD])
        bind(gdi, "SelectObject", w.HANDLE, [w.HDC, w.HANDLE])
        bind(gdi, "DeleteObject", w.BOOL, [w.HANDLE])
        bind(gdi, "DeleteDC", w.BOOL, [w.HDC])
        bind(gdi, "GetStockObject", w.HANDLE, [ctypes.c_int])
        bind(gdi, "SetTextColor", w.DWORD, [w.HDC, w.DWORD])
        bind(gdi, "SetBkMode", ctypes.c_int, [w.HDC, ctypes.c_int])
        bind(gdi, "TextOutW", w.BOOL, [w.HDC, ctypes.c_int, ctypes.c_int, w.LPCWSTR, ctypes.c_int])
        bind(gdi, "GdiFlush", w.BOOL, [])

        @proc_type
        def procedure(hwnd, message, wp, lp):
            if message == 0x0084:  # WM_NCHITTEST: every pixel is click-through.
                return -1
            if message == 0x0021:  # WM_MOUSEACTIVATE
                return 3
            return user.DefWindowProcW(hwnd, message, wp, lp)

        hwnd = dc = bitmap = old_bitmap = old_font = wake = None
        registered = False
        shortcuts = None
        instance = kernel.GetModuleHandleW(None)
        name = f"CS2CFGOverlay-{id(self)}"
        try:
            wake = kernel.CreateEventW(None, False, False, None)
            if not wake:
                raise ctypes.WinError(ctypes.get_last_error())
            with self._lock:
                self._wake = wake
            wc = WNDCLASS(proc=procedure, instance=instance, name=name)
            if not user.RegisterClassW(ctypes.byref(wc)):
                raise ctypes.WinError(ctypes.get_last_error())
            registered = True
            style = (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST |
                     WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
            hwnd = user.CreateWindowExW(style, name, "CS CONFIG AI performance HUD", 0x80000000,
                                        20, 20, WIDTH, HEIGHT, None, None, instance, None)
            if not hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            shortcuts = Hotkeys(user, hwnd)
            shortcuts.configure(self._chord, self._panel_chord if self.on_panel else None)
            self.warning = shortcuts.warning
            if self.exclude:
                try:
                    bind(user, "SetWindowDisplayAffinity", w.BOOL, [w.HWND, w.DWORD])
                    if not user.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
                        raise ctypes.WinError(ctypes.get_last_error())
                except (AttributeError, OSError) as exc:
                    self.warning += f" Capture exclusion unavailable: {exc}"
            dc = gdi.CreateCompatibleDC(None)
            info = BITMAPINFO()
            info.header = BITMAPINFOHEADER(size=ctypes.sizeof(BITMAPINFOHEADER), width=WIDTH,
                                           height=-HEIGHT, planes=1, bits=32)
            bits = ptr()
            bitmap = gdi.CreateDIBSection(dc, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
            if not dc or not bitmap:
                raise ctypes.WinError(ctypes.get_last_error())
            old_bitmap = gdi.SelectObject(dc, bitmap)
            old_font = gdi.SelectObject(dc, gdi.GetStockObject(17))  # DEFAULT_GUI_FONT
            gdi.SetBkMode(dc, 1)
            gdi.SetTextColor(dc, 0x00EEEEEE)
            pixels = (ctypes.c_ubyte * (WIDTH * HEIGHT * 4)).from_address(bits.value)
            background = bytes((22, 22, 22, 255)) * (WIDTH * HEIGHT)
            last_drawn = None
            last_at = -math.inf
            shown = False
            self._ready.set()
            handles = (w.HANDLE * 1)(wake)
            while not self._stop.is_set():
                message = w.MSG()
                while user.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                    if message.message == 0x0312 and message.wParam == 1:  # WM_HOTKEY
                        self._requested = not self._requested
                    elif message.message == 0x0312 and message.wParam == 2 and self.on_panel:
                        try:
                            self.on_panel()
                        except Exception as exc:
                            self.warning = f"Panel: {exc}"
                    else:
                        user.TranslateMessage(ctypes.byref(message))
                        user.DispatchMessageW(ctypes.byref(message))
                with self._lock:
                    desired = self._chord, self._panel_chord if self.on_panel else None
                    if shortcuts.desired != desired:
                        shortcuts.configure(*desired)
                        self.warning = shortcuts.warning
                    lines = display_lines(self._sample, self.fields, self.hotkey)
                    position = self._position
                    self.visible = self._requested and self._allowed
                if shown and not self.visible:
                    user.ShowWindow(hwnd, 0)
                    shown = False
                state = lines, position
                now = time.monotonic()
                changed = state != last_drawn
                if self.visible and changed and now - last_at >= 0.5:
                    ctypes.memmove(bits, background, len(background))
                    for index, line in enumerate(lines):
                        gdi.TextOutW(dc, 12, 9 + index * 26, line, len(line))
                    gdi.GdiFlush()
                    # GDI text clears alpha bytes. The panel is opaque in the
                    # DIB and uniformly translucent through the blend alpha.
                    pixels[3::4] = b"\xff" * (WIDTH * HEIGHT)
                    destination, size, source = w.POINT(*position), w.SIZE(WIDTH, HEIGHT), w.POINT(0, 0)
                    blend = BLEND(0, 0, 235, 1)
                    if not user.UpdateLayeredWindow(hwnd, None, ctypes.byref(destination), ctypes.byref(size),
                                                     dc, ctypes.byref(source), 0, ctypes.byref(blend), 2):
                        raise ctypes.WinError(ctypes.get_last_error())
                    last_drawn, last_at = state, now
                    changed = False
                if self.visible and not shown:
                    user.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
                    shown = True
                timeout = (max(1, math.ceil((last_at + 0.5 - time.monotonic()) * 1000))
                           if self.visible and changed else 0xFFFFFFFF)
                result = user.MsgWaitForMultipleObjectsEx(1, handles, timeout, 0x04FF, 0x0004)
                if result == 0xFFFFFFFF:
                    raise ctypes.WinError(ctypes.get_last_error())
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.visible = False
            if hwnd:
                if shortcuts:
                    shortcuts.close()
                user.DestroyWindow(hwnd)
            if old_font:
                gdi.SelectObject(dc, old_font)
            if old_bitmap:
                gdi.SelectObject(dc, old_bitmap)
            if bitmap:
                gdi.DeleteObject(bitmap)
            if dc:
                gdi.DeleteDC(dc)
            if registered:
                user.UnregisterClassW(name, instance)
            with self._lock:
                self._wake = None
                if wake:
                    kernel.CloseHandle(wake)
            self._ready.set()
