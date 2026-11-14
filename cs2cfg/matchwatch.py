"""Notice when a match is found, in FACEIT or in CS2, and say so loudly.

How it notices -- by listening, never by reaching in
------------------------------------------------------

Windows tells every program that asks when another program's window changes
its title or flashes its taskbar button. That is the shell hook, the same
signal the taskbar itself runs on. Nothing here opens a game or FACEIT file,
reads another process's memory, or hooks into anything.

* **FACEIT** -- captured live on 2026-11-14. When a match pops, the FACEIT
  client blinks its window title between "\U0001F534 <Match found>",
  "⚫ <Match found>" and its normal title, about once a second, until the
  match is accepted. It does *not* flash the taskbar. The words follow the
  client's language (it was Russian on the machine this was captured on), so
  the coloured-dot prefix is what is matched, not the words.

* **CS2** -- not captured yet. CS2 flashes its taskbar button when a match is
  found while it is not focused. It also flashes twice while starting up, so
  flashes in the first minute after its window appears are ignored.

What "accept" does is decided elsewhere (see accept()), and was chosen by the
user: in CS2 it clicks the game's Accept button -- only when they press ours --
and for FACEIT it only brings the FACEIT window to the front.
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

FACEIT = "faceit"
CS2 = "cs2"

FACEIT_EXE = "faceit.exe"
CS2_EXE = "cs2.exe"

# The dots FACEIT blinks in front of its "match found" title.
_FACEIT_DOTS = ("\U0001F534", "⚫", "⬤", "●")

# How long a pop stays up without a fresh sign of it. FACEIT gives ~30s to
# accept and CS2 ~20s; the blink is about once a second, so a few seconds of
# normal title means it was accepted (or declined) in the FACEIT window.
FACEIT_QUIET = 3.0
FACEIT_MAX = 45.0
CS2_MAX = 25.0
CS2_STARTUP_GRACE = 60.0


def faceit_title_says_found(title: str) -> bool:
    text = (title or "").lstrip()
    return any(text.startswith(dot) for dot in _FACEIT_DOTS)


@dataclass
class Alert:
    source: str
    hwnd: int
    started: float
    seen: float
    deadline: float

    def public(self, now: Optional[float] = None) -> Dict[str, object]:
        now = time.time() if now is None else now
        return {"source": self.source,
                "seconds_left": max(0, int(round(self.deadline - now)))}


@dataclass
class Tracker:
    """The decision part, with no Windows in it, so it can be tested.

    Feed it what the shell hook reports; it says when an alert starts and
    when it is over. Wall-clock seconds in, so tests can drive time.
    """

    alert: Optional[Alert] = None
    # When CS2's window appeared, if this saw it happen. None when CS2 was
    # already running before this started -- then its startup is long over.
    cs2_born: Optional[float] = None
    _dismissed_until: Dict[str, float] = field(default_factory=dict)

    def title(self, exe: str, title: str, hwnd: int, now: float) -> Optional[str]:
        """A window's title changed. Returns 'start' when a pop begins."""
        if exe != FACEIT_EXE or not faceit_title_says_found(title):
            return None
        if self.alert and self.alert.source == FACEIT:
            self.alert.seen = now
            return None
        return self._start(FACEIT, hwnd, now, now + FACEIT_MAX)

    def flash(self, exe: str, hwnd: int, now: float, foreground_exe: str = "") -> Optional[str]:
        if exe != CS2_EXE:
            return None
        if self.cs2_born is not None and now - self.cs2_born < CS2_STARTUP_GRACE:
            return None
        if foreground_exe == CS2_EXE:
            return None          # already looking at it
        if self.alert and self.alert.source == CS2:
            self.alert.seen = now
            return None
        return self._start(CS2, hwnd, now, now + CS2_MAX)

    def created(self, exe: str, now: float) -> None:
        if exe == CS2_EXE and self.cs2_born is None:
            self.cs2_born = now

    def destroyed(self, exe: str, now: float) -> None:
        if exe == CS2_EXE:
            self.cs2_born = None

    def activated(self, exe: str, now: float) -> Optional[str]:
        """Somebody went to the game themselves: the alert has done its job."""
        if self.alert and self.alert.source == CS2 and exe == CS2_EXE:
            return self._end()
        return None

    def tick(self, now: float) -> Optional[str]:
        if not self.alert:
            return None
        a = self.alert
        if now >= a.deadline:
            return self._end()
        if a.source == FACEIT and now - a.seen > FACEIT_QUIET:
            return self._end()
        return None

    def dismiss(self, now: float) -> Optional[str]:
        if not self.alert:
            return None
        # Ignore the rest of this pop's blinking.
        self._dismissed_until[self.alert.source] = self.alert.deadline
        return self._end()

    def _start(self, source: str, hwnd: int, now: float, deadline: float) -> Optional[str]:
        if now < self._dismissed_until.get(source, 0.0):
            return None
        if self.alert:           # one alert at a time; the newer one wins
            self.alert = None
        self.alert = Alert(source, hwnd, now, now, deadline)
        return "start"

    def _end(self) -> str:
        self.alert = None
        return "end"


# --- the running watcher ----------------------------------------------------

Listener = Callable[[str, Optional[Dict[str, object]]], None]

_lock = threading.RLock()
_tracker = Tracker()
_listeners: List[Listener] = []
_thread: Optional[threading.Thread] = None
_enabled = {"on": True}


def add_listener(fn: Listener) -> None:
    """fn('start', alert) when a pop begins, fn('end', None) when it is over."""
    with _lock:
        _listeners.append(fn)


def _emit(what: Optional[str]) -> None:
    if not what:
        return
    with _lock:
        alert = _tracker.alert.public() if _tracker.alert else None
        listeners = list(_listeners)
    for fn in listeners:
        try:
            fn(what, alert)
        except Exception:
            pass


def current() -> Optional[Dict[str, object]]:
    with _lock:
        return _tracker.alert.public() if _tracker.alert else None


def current_hwnd() -> int:
    with _lock:
        return _tracker.alert.hwnd if _tracker.alert else 0


def set_enabled(on: bool) -> None:
    _enabled["on"] = bool(on)
    if not on:
        dismiss()


def enabled() -> bool:
    return _enabled["on"]


def dismiss() -> None:
    with _lock:
        what = _tracker.dismiss(time.time())
    _emit(what)


def _feed(code: int, exe: str, title: str, hwnd: int, foreground_exe: str) -> None:
    now = time.time()
    with _lock:
        if code == HSHELL_REDRAW:
            what = _tracker.title(exe, title, hwnd, now) if _enabled["on"] else None
        elif code == HSHELL_FLASH:
            what = _tracker.flash(exe, hwnd, now, foreground_exe) if _enabled["on"] else None
        elif code == HSHELL_WINDOWCREATED:
            _tracker.created(exe, now)
            what = None
        elif code == HSHELL_WINDOWDESTROYED:
            _tracker.destroyed(exe, now)
            what = None
        elif code in (HSHELL_WINDOWACTIVATED, HSHELL_RUDEAPPACTIVATED):
            what = _tracker.activated(exe, now)
        else:
            what = None
    _emit(what)


HSHELL_WINDOWCREATED = 1
HSHELL_WINDOWDESTROYED = 2
HSHELL_WINDOWACTIVATED = 4
HSHELL_REDRAW = 6
HSHELL_RUDEAPPACTIVATED = 0x8004
HSHELL_FLASH = 0x8006


def start() -> bool:
    """Start listening, once. False where there is no shell hook (not Windows)."""
    global _thread
    if sys.platform != "win32":
        return False
    with _lock:
        if _thread and _thread.is_alive():
            return True
        _thread = threading.Thread(target=_run, name="matchwatch", daemon=True)
        _thread.start()
    return True


def _run() -> None:  # pragma: no cover - Windows message loop
    import ctypes
    from ctypes import wintypes

    from . import window as winmod

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)
    # Every handle declared: on 64-bit Windows an undeclared HWND is cut to
    # 32 bits and CreateWindowExW overflows (found by the probe on the
    # player's PC).
    user32.DefWindowProcW.restype = LRESULT
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.RegisterShellHookWindow.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                ctypes.POINTER(wintypes.DWORD)]
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                    wintypes.UINT, wintypes.UINT, wintypes.UINT]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR)]

    def owner(hwnd) -> str:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            return winmod._process_name(pid.value)
        except Exception:
            return ""

    shellhook = user32.RegisterWindowMessageW("SHELLHOOK")
    interesting = {HSHELL_WINDOWCREATED, HSHELL_WINDOWDESTROYED,
                   HSHELL_WINDOWACTIVATED, HSHELL_REDRAW,
                   HSHELL_RUDEAPPACTIVATED, HSHELL_FLASH}

    @WNDPROC
    def proc(hwnd, msg, wparam, lparam):
        if msg == shellhook and int(wparam) in interesting and lparam:
            try:
                target = wintypes.HWND(lparam)
                exe = owner(target)
                if exe in (FACEIT_EXE, CS2_EXE):
                    buf = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(target, buf, 256)
                    fg = ""
                    if int(wparam) == HSHELL_FLASH:
                        fg = winmod.foreground_process()
                    _feed(int(wparam), exe, buf.value, int(lparam), fg)
            except Exception:
                pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    wc = WNDCLASSW()
    wc.lpfnWndProc = proc
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = "cs2cfg_matchwatch"
    user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "matchwatch", 0, 0, 0, 0, 0,
                                  None, None, wc.hInstance, None)
    if not hwnd or not user32.RegisterShellHookWindow(hwnd):
        return

    msg = wintypes.MSG()
    while True:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        with _lock:
            what = _tracker.tick(time.time())
        _emit(what)
        time.sleep(0.1)


# --- accepting --------------------------------------------------------------

def accept() -> Dict[str, object]:
    """What our Accept button does. Chosen by the user:

    * FACEIT: bring the FACEIT window to the front. The player clicks Accept
      there themselves; nothing is clicked inside FACEIT's client.
    * CS2: bring CS2 to the front and click its Accept button -- once, and
      only because the player pressed ours.
    """
    with _lock:
        alert = _tracker.alert
        source = alert.source if alert else ""
        hwnd = alert.hwnd if alert else 0
    if not source:
        return {"ok": False, "error": "there is no match waiting"}

    from . import window as winmod

    if source == FACEIT:
        target = _main_window(winmod, FACEIT_EXE, hwnd)
        raised = _raise(target)
        dismiss()
        return {"ok": True, "source": FACEIT, "raised": raised,
                "detail": "FACEIT is in front: press Accept there"}

    target = _main_window(winmod, CS2_EXE, hwnd)
    # Our own window goes first: it sits on top, in the middle of the screen,
    # which is right where the game's Accept button is.
    dismiss()
    time.sleep(0.3)
    raised = _raise(target)
    clicked = False
    if raised:
        time.sleep(0.35)         # let the game draw itself in front first
        clicked = click_cs2_accept(target)
    return {"ok": True, "source": CS2, "raised": raised, "clicked": clicked,
            "detail": "Accepted" if clicked else "CS2 is in front: press Accept"}


def _main_window(winmod, exe: str, hint: int) -> int:
    try:
        found = winmod.list_windows(exe)
    except Exception:
        found = []
    if not found:
        return hint
    return max(found, key=lambda w: w.size[0] * w.size[1]).hwnd


def _raise(hwnd: int) -> bool:
    if not hwnd or sys.platform != "win32":
        return False
    try:
        import ctypes

        from .desktop import _to_front

        return _to_front(ctypes.WinDLL("user32", use_last_error=True), hwnd)
    except Exception:
        return False


# CS2's Accept button is a large green button in the middle of the screen.
# Found by colour rather than a fixed position, because the position moves
# with resolution, aspect ratio and stretching.
def _is_accept_green(r: int, g: int, b: int) -> bool:
    return g >= 120 and g - r >= 50 and g - b >= 40


def find_green_button(pixels, width: int, height: int):
    """Centre of the biggest run of Accept-green in the middle of the frame.

    ``pixels(x, y) -> (r, g, b)``. Scans a coarse grid over the central part
    of the window and returns the centre of the green cells, or None when
    there are too few to be a button.
    """
    step = max(4, min(width, height) // 120)
    x0, x1 = int(width * 0.25), int(width * 0.75)
    y0, y1 = int(height * 0.2), int(height * 0.8)
    xs, ys = [], []
    for y in range(y0, y1, step):
        for x in range(x0, x1, step):
            if _is_accept_green(*pixels(x, y)):
                xs.append(x)
                ys.append(y)
    cells = len(xs)
    area = ((x1 - x0) // step) * ((y1 - y0) // step)
    # A button: more than a few cells, far less than the whole screen.
    if cells < 12 or cells > area * 0.25:
        return None
    xs.sort()
    ys.sort()
    return xs[cells // 2], ys[cells // 2]


def click_cs2_accept(hwnd: int) -> bool:  # pragma: no cover - needs a screen
    """Read the game's window off the screen, find the green Accept button and
    click it once. False when no button is visible -- then nothing is clicked."""
    if sys.platform != "win32" or not hwnd:
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.GetPixel.restype = wintypes.DWORD

    rect = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
    left, top = rect.left, rect.top
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return False

    # The screen, not the window: a DirectX game's own DC is usually black,
    # while what is on screen is what the player sees.
    screen = user32.GetDC(None)
    try:
        def pixel(x, y):
            value = gdi32.GetPixel(screen, left + x, top + y)
            return value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF

        spot = find_green_button(pixel, width, height)
    finally:
        user32.ReleaseDC(None, screen)
    if not spot:
        return False

    x, y = left + spot[0], top + spot[1]
    user32.SetCursorPos(x, y)
    time.sleep(0.05)

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 32)]
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    down, up = INPUT(), INPUT()
    down.type = up.type = 0               # INPUT_MOUSE
    down.mi.dwFlags = 0x0002              # LEFTDOWN
    up.mi.dwFlags = 0x0004                # LEFTUP
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
    user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
    time.sleep(0.04)
    user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
    return True
