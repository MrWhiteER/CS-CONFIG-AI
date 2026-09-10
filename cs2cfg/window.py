"""Borderless and stretched window control.

This replicates what Borderless Gaming and Stretched Borderless Manager do,
without the tray app: strip a window's frame and size it to the monitor, and
optionally switch the desktop mode first so the result is genuinely stretched.

The distinction that trips most guides up is worth stating plainly, because it
determines which of the two modes here you actually want:

* **Filling** a window to the monitor does not stretch anything. The game sees
  a larger client area and renders at that size, so a 4:3 window blown up to
  2560x1440 just becomes a 16:9 render. You lose the stretched look entirely.
* **Stretching** requires the display itself to be running at the narrow mode
  with the scaler pulling it across the panel. Then a borderless window filling
  that desktop is stretched, because everything on the desktop is.

So ``fill`` is for people who want borderless at native aspect, and ``stretch``
is for people who want the 4:3 look with fast alt-tab. The scaling itself is
done by the display driver, which is why GPU scaling has to be set to
full-screen in the NVIDIA or AMD control panel for either to look right.
"""

from __future__ import annotations

import ctypes
import json
import time
from ctypes import wintypes
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .kb import user_data_dir

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# --- window styles ---------------------------------------------------------
GWL_STYLE = -16
GWL_EXSTYLE = -20

WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000
WS_BORDER = 0x00800000
WS_DLGFRAME = 0x00400000

WS_EX_DLGMODALFRAME = 0x00000001
WS_EX_CLIENTEDGE = 0x00000200
WS_EX_STATICEDGE = 0x00020000
WS_EX_WINDOWEDGE = 0x00000100

FRAME_STYLES = WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU | WS_BORDER | WS_DLGFRAME
FRAME_EX_STYLES = WS_EX_DLGMODALFRAME | WS_EX_CLIENTEDGE | WS_EX_STATICEDGE | WS_EX_WINDOWEDGE

SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040

MONITOR_DEFAULTTONEAREST = 2

# --- display modes ---------------------------------------------------------
DM_BITSPERPEL = 0x00040000
DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000

CDS_UPDATEREGISTRY = 0x00000001
CDS_TEST = 0x00000002
CDS_FULLSCREEN = 0x00000004

DISP_CHANGE_SUCCESSFUL = 0
ENUM_CURRENT_SETTINGS = -1

DISP_CHANGE_REASONS = {
    0: "succeeded",
    -1: "the graphics mode is not supported",
    -2: "the mode could not be set at this time",
    -3: "the settings could not be written to the registry",
    -4: "an invalid set of flags was passed",
    -5: "an invalid parameter was passed",
    -6: "the display driver rejected the mode",
}

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class WindowError(RuntimeError):
    """A window or display operation could not be completed."""


# ---------------------------------------------------------------------------
# Structures
# ---------------------------------------------------------------------------

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]


class DISPLAY_DEVICE(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


# 64-bit safe signatures. GetWindowLongPtrW does not exist in 32-bit user32,
# so fall back to the plain variants there.
try:
    _get_long = user32.GetWindowLongPtrW
    _set_long = user32.SetWindowLongPtrW
except AttributeError:  # pragma: no cover - 32-bit Python only
    _get_long = user32.GetWindowLongW
    _set_long = user32.SetWindowLongW

_get_long.restype = ctypes.c_ssize_t
_get_long.argtypes = [wintypes.HWND, ctypes.c_int]
_set_long.restype = ctypes.c_ssize_t
_set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]


# ---------------------------------------------------------------------------
# Finding the window
# ---------------------------------------------------------------------------

@dataclass
class WindowInfo:
    hwnd: int
    title: str
    process: str
    rect: Tuple[int, int, int, int]

    @property
    def size(self) -> Tuple[int, int]:
        left, top, right, bottom = self.rect
        return right - left, bottom - top


def _process_name(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return Path(buffer.value).name.lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def list_windows(process: Optional[str] = None) -> List[WindowInfo]:
    """Every visible top-level window, optionally filtered by process name."""
    wanted = process.lower() if process else None
    found: List[WindowInfo] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = _process_name(pid.value)
        if wanted and name != wanted:
            return True

        # A window with no title and no size is a message-only or helper
        # window, never the one someone means.
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return True
        if not wanted and not title:
            return True

        found.append(WindowInfo(
            hwnd=int(hwnd), title=title, process=name,
            rect=(rect.left, rect.top, rect.right, rect.bottom),
        ))
        return True

    user32.EnumWindows(callback, 0)
    return found


def find_game_window(process: str = "cs2.exe") -> Optional[WindowInfo]:
    """The game's main window, or None if it is not running.

    When a process owns several windows, the largest one is the render target;
    the others are splash, tooltip or IME helpers.
    """
    candidates = list_windows(process)
    if not candidates:
        return None
    return max(candidates, key=lambda w: w.size[0] * w.size[1])


def window_pid(hwnd: int) -> int:
    """Process id owning a window."""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return int(pid.value)


def foreground_hwnd() -> int:
    """Whichever window currently has focus, 0 if none."""
    return int(user32.GetForegroundWindow() or 0)


def is_responsive(hwnd: int, timeout_ms: int = 200) -> bool:
    """Whether a window is pumping messages.

    Sends a no-op and sees whether the window's thread answers. A window that
    stops answering is one whose message loop is blocked — which is exactly
    what a mode-switch stall looks like from the outside, so this is how the
    black-screen pause gets measured rather than guessed at.
    """
    result = ctypes.c_size_t()
    ok = user32.SendMessageTimeoutW(
        wintypes.HWND(hwnd), 0x0000, 0, 0,  # WM_NULL
        0x0002,                             # SMTO_ABORTIFHUNG
        wintypes.UINT(timeout_ms),
        ctypes.byref(result),
    )
    return bool(ok)


def primary_monitor_index() -> int:
    """Index of the primary display in EnumDisplayDevices order.

    CS2's ``monitor_index`` counts adapters the same way Windows does, so this
    is the number to put in the video config to pin the game to the primary
    screen.
    """
    index = 0
    device_num = 0
    while True:
        device = DISPLAY_DEVICE()
        device.cb = ctypes.sizeof(DISPLAY_DEVICE)
        if not user32.EnumDisplayDevicesW(None, device_num, ctypes.byref(device), 0):
            break
        attached = bool(device.StateFlags & 0x1)
        if attached:
            if device.StateFlags & 0x4:   # DISPLAY_DEVICE_PRIMARY_DEVICE
                return index
            index += 1
        device_num += 1
    return 0


WM_CLOSE = 0x0010
PROCESS_TERMINATE = 0x0001
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0x0
WAIT_TIMEOUT = 0x102


def request_close(hwnd: int) -> bool:
    """Ask a window to close, the way clicking its X does.

    Posted rather than sent, so a game that takes its time shutting down does
    not block this thread while it saves settings and disconnects cleanly.
    """
    return bool(user32.PostMessageW(wintypes.HWND(hwnd), WM_CLOSE, 0, 0))


def process_alive(pid: int) -> bool:
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(handle)


def terminate_process(pid: int) -> bool:
    """Kill a process outright. The last resort, never the first move."""
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not handle:
        return False
    try:
        return bool(kernel32.TerminateProcess(handle, 1))
    finally:
        kernel32.CloseHandle(handle)


def close_process_window(
    hwnd: int,
    graceful_timeout: float = 8.0,
    force: bool = True,
) -> str:
    """Close a game: politely first, forcefully only if it will not go.

    A clean WM_CLOSE lets CS2 disconnect from the server, flush its config and
    exit properly. Killing it skips all of that, so it is only reached after
    the polite route has been given real time to work. Returns a short
    description of what actually happened.
    """
    pid = window_pid(hwnd)
    if not pid:
        return "no process behind that window"

    request_close(hwnd)

    deadline = time.monotonic() + graceful_timeout
    while time.monotonic() < deadline:
        if not process_alive(pid):
            return "closed cleanly"
        time.sleep(0.25)

    if not force:
        return f"still running after {graceful_timeout:.0f}s; not forcing"

    if terminate_process(pid):
        for _ in range(20):
            if not process_alive(pid):
                return f"did not respond in {graceful_timeout:.0f}s, so it was ended"
            time.sleep(0.1)
        return "terminate was issued but the process is still there"
    return "could not terminate the process (access denied?)"


def monitor_bounds(hwnd: int) -> Tuple[int, int, int, int]:
    """Full bounds of the monitor the window is currently on."""
    handle = user32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(handle, ctypes.byref(info)):
        raise WindowError("could not read the monitor bounds for that window")
    r = info.rcMonitor
    return r.left, r.top, r.right, r.bottom


# ---------------------------------------------------------------------------
# Saved state, so a restore works even after this process exits
# ---------------------------------------------------------------------------

def _state_file() -> Path:
    return user_data_dir() / "window_state.json"


@dataclass
class SavedWindow:
    process: str
    style: int
    ex_style: int
    rect: Tuple[int, int, int, int]
    display_changed: bool = False


def _save_state(state: SavedWindow) -> None:
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def _load_state() -> Optional[SavedWindow]:
    path = _state_file()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SavedWindow(
            process=data["process"],
            style=int(data["style"]),
            ex_style=int(data["ex_style"]),
            rect=tuple(data["rect"]),
            display_changed=bool(data.get("display_changed")),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _clear_state() -> None:
    path = _state_file()
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Display mode
# ---------------------------------------------------------------------------

def current_mode() -> Tuple[int, int, int]:
    """Current desktop width, height and refresh rate."""
    mode = DEVMODEW()
    mode.dmSize = ctypes.sizeof(DEVMODEW)
    if not user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(mode)):
        raise WindowError("could not read the current display mode")
    return mode.dmPelsWidth, mode.dmPelsHeight, mode.dmDisplayFrequency


def set_mode(width: int, height: int, refresh: int = 0, test_only: bool = False,
             persist: bool = False) -> None:
    """Switch the desktop to a mode. This is what produces the stretch.

    The driver's scaler does the stretching, so GPU scaling must be set to
    full-screen in the NVIDIA or AMD control panel or the panel will letterbox
    the narrow mode instead of filling.

    By default the change is *temporary*: ``CDS_FULLSCREEN`` without
    ``CDS_UPDATEREGISTRY`` tells Windows this mode belongs to the calling
    process, so it reverts on its own if we are killed rather than exiting
    cleanly. That matters here — a crashed launcher must not leave someone's
    desktop stuck at 1550x1440 with no obvious way back. Pass ``persist`` only
    if you actually want the mode written to the registry.
    """
    mode = DEVMODEW()
    mode.dmSize = ctypes.sizeof(DEVMODEW)
    if not user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(mode)):
        raise WindowError("could not read the current display mode")

    mode.dmPelsWidth = width
    mode.dmPelsHeight = height
    mode.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_BITSPERPEL
    if refresh:
        mode.dmDisplayFrequency = refresh
        mode.dmFields |= DM_DISPLAYFREQUENCY

    if test_only:
        flags = CDS_TEST
    elif persist:
        flags = CDS_UPDATEREGISTRY | CDS_FULLSCREEN
    else:
        flags = CDS_FULLSCREEN
    result = user32.ChangeDisplaySettingsExW(None, ctypes.byref(mode), None, flags, None)
    if result != DISP_CHANGE_SUCCESSFUL:
        reason = DISP_CHANGE_REASONS.get(result, f"unknown error {result}")
        raise WindowError(f"could not set {width}x{height}: {reason}")


def restore_mode() -> None:
    """Return the desktop to the mode stored in the registry."""
    result = user32.ChangeDisplaySettingsExW(None, None, None, 0, None)
    if result != DISP_CHANGE_SUCCESSFUL:
        raise WindowError(f"could not restore the display mode: "
                          f"{DISP_CHANGE_REASONS.get(result, result)}")


# ---------------------------------------------------------------------------
# The operations
# ---------------------------------------------------------------------------

def make_borderless(window: WindowInfo, bounds: Optional[Tuple[int, int, int, int]] = None,
                    remember: bool = True) -> Tuple[int, int]:
    """Strip the frame and size the window to ``bounds`` (default: its monitor).

    Returns the resulting width and height.
    """
    hwnd = wintypes.HWND(window.hwnd)
    style = _get_long(hwnd, GWL_STYLE)
    ex_style = _get_long(hwnd, GWL_EXSTYLE)

    if remember:
        _save_state(SavedWindow(
            process=window.process, style=int(style),
            ex_style=int(ex_style), rect=window.rect,
        ))

    _set_long(hwnd, GWL_STYLE, (style & ~FRAME_STYLES) | WS_POPUP | WS_VISIBLE)
    _set_long(hwnd, GWL_EXSTYLE, ex_style & ~FRAME_EX_STYLES)

    left, top, right, bottom = bounds or monitor_bounds(window.hwnd)
    width, height = right - left, bottom - top

    if not user32.SetWindowPos(hwnd, None, left, top, width, height,
                               SWP_NOZORDER | SWP_FRAMECHANGED | SWP_SHOWWINDOW):
        raise WindowError(f"SetWindowPos failed (error {ctypes.get_last_error()})")
    return width, height


def restore_window(process: Optional[str] = None) -> str:
    """Undo a borderless change, and the display mode if one was set."""
    state = _load_state()
    if state is None:
        return "nothing to restore; no saved window state"

    report: List[str] = []
    window = find_game_window(state.process if process is None else process)
    if window is not None:
        hwnd = wintypes.HWND(window.hwnd)
        _set_long(hwnd, GWL_STYLE, state.style)
        _set_long(hwnd, GWL_EXSTYLE, state.ex_style)
        left, top, right, bottom = state.rect
        user32.SetWindowPos(hwnd, None, left, top, right - left, bottom - top,
                            SWP_NOZORDER | SWP_FRAMECHANGED | SWP_SHOWWINDOW)
        report.append(f"restored the frame and position of {state.process}")
    else:
        report.append(f"{state.process} is not running; window state discarded")

    if state.display_changed:
        try:
            restore_mode()
            report.append("restored the desktop resolution")
        except WindowError as exc:
            report.append(f"could not restore the desktop resolution: {exc}")

    _clear_state()
    return "; ".join(report)


def apply_stretch(
    width: int,
    height: int,
    process: str = "cs2.exe",
    refresh: int = 0,
    change_display: bool = True,
) -> Dict[str, object]:
    """The full stretched-borderless routine.

    With ``change_display`` the desktop switches to ``width x height`` first,
    which is what makes the result genuinely stretched rather than merely
    borderless. Without it the window is only filled to the monitor.
    """
    window = find_game_window(process)
    if window is None:
        raise WindowError(f"{process} does not appear to be running")

    result: Dict[str, object] = {"process": process, "title": window.title,
                                 "was": window.size, "display_changed": False}

    if change_display:
        before = current_mode()
        result["display_before"] = before
        set_mode(width, height, refresh, test_only=True)   # probe before committing
        set_mode(width, height, refresh)
        result["display_changed"] = True
        result["display_after"] = (width, height, refresh or before[2])
        # Give the driver a moment before measuring the new desktop bounds.
        time.sleep(0.4)

    size = make_borderless(window)
    result["now"] = size

    if change_display:
        state = _load_state()
        if state is not None:
            state.display_changed = True
            _save_state(state)

    return result


def check_stretch(width: int, height: int, process: str = "cs2.exe") -> Dict[str, object]:
    """Compare the live desktop mode and game window against the target.

    Cheap enough to call once a second: two ctypes calls and no allocation of
    consequence. Reports what has drifted without changing anything.
    """
    result: Dict[str, object] = {
        "running": False, "mode_ok": True, "window_ok": True,
        "want": (width, height),
    }
    found = find_game_window(process)
    if found is None:
        return result
    result["running"] = True

    try:
        now = current_mode()
    except WindowError:
        return result
    result["mode"] = (now[0], now[1])
    result["mode_ok"] = (now[0], now[1]) == (width, height)

    left, top, right, bottom = monitor_bounds(found.hwnd)
    want_rect = (left, top, right, bottom)
    result["rect"] = found.rect
    result["want_rect"] = want_rect
    result["window_ok"] = found.rect == want_rect
    return result


def repair_stretch(width: int, height: int, process: str = "cs2.exe",
                   refresh: int = 0, change_display: bool = True) -> Dict[str, object]:
    """Put the stretch back after Windows has undone it.

    The desktop mode is set with ``CDS_FULLSCREEN`` and no ``CDS_UPDATEREGISTRY``
    so a crash cannot strand the desktop at 1550x1440. The cost of that choice
    is that the mode belongs to the process and Windows drops it on its own
    whenever the display topology is re-evaluated -- a monitor sleeping, the
    session locking, another application taking and releasing exclusive
    fullscreen. On a multi-monitor desk that happens routinely, the desktop
    snaps back to native, and the game keeps rendering at its old window size
    with the stretch gone.

    Nothing was watching for that, so this re-asserts only what has actually
    drifted. Re-applying a mode that is already correct would drop the game's
    swapchain for no reason, which is the very stall this tool exists to avoid.
    """
    found = find_game_window(process)
    if found is None:
        raise WindowError(f"{process} does not appear to be running")

    state = check_stretch(width, height, process)
    done: List[str] = []

    if change_display and not state["mode_ok"]:
        was = state.get("mode")
        set_mode(width, height, refresh, test_only=True)
        set_mode(width, height, refresh)
        done.append(f"desktop {was[0]}x{was[1]} -> {width}x{height}")
        time.sleep(0.4)
        found = find_game_window(process) or found
        saved = _load_state()
        if saved is not None and not saved.display_changed:
            saved.display_changed = True
            _save_state(saved)

    # Re-measure: moving the desktop mode moves the monitor bounds too.
    fresh = check_stretch(width, height, process)
    if not fresh["window_ok"]:
        old = fresh.get("rect")
        # The frame was already saved by the original launch; saving again here
        # would record the stretched geometry as the thing to restore to.
        new_w, new_h = make_borderless(found, remember=False)
        done.append(f"window {old[2] - old[0]}x{old[3] - old[1]} -> {new_w}x{new_h} at the origin")

    return {
        "process": process,
        "repaired": bool(done),
        "actions": done,
        "before": state,
        "after": check_stretch(width, height, process),
    }


def watch(
    width: int,
    height: int,
    process: str = "cs2.exe",
    refresh: int = 0,
    change_display: bool = True,
    interval: float = 2.0,
    on_event: Optional[Callable[[str], None]] = None,
) -> None:
    """Apply the treatment whenever the game appears, and undo it when it goes.

    This is the tray-app behaviour of the original tools, as a foreground loop.
    Ctrl+C exits cleanly and restores whatever was changed.
    """
    say = on_event or (lambda message: None)
    applied = False
    say(f"watching for {process}; press Ctrl+C to stop")

    try:
        while True:
            running = find_game_window(process) is not None
            if running and not applied:
                try:
                    result = apply_stretch(width, height, process, refresh, change_display)
                    say(f"applied: {result['was'][0]}x{result['was'][1]} -> "
                        f"{result['now'][0]}x{result['now'][1]}")
                    applied = True
                except WindowError as exc:
                    say(f"could not apply: {exc}")
            elif running and applied:
                # Keep checking. The mode is temporary by design, so Windows can
                # take it back mid-session; latching on `applied` meant nothing
                # ever noticed.
                try:
                    fix = repair_stretch(width, height, process, refresh, change_display)
                    for line in fix["actions"]:
                        say(f"restored: {line}")
                except WindowError as exc:
                    say(f"could not restore: {exc}")
            elif not running and applied:
                say(restore_window(process))
                applied = False
            time.sleep(interval)
    except KeyboardInterrupt:
        if applied:
            say(restore_window(process))
        say("stopped")
