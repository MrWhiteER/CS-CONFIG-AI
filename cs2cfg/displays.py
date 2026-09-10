"""Per-monitor display modes: what each screen offers, and what it is using.

Refresh rate is not an NVIDIA setting -- it is a Windows display mode, so this
goes through the display API and works the same on any GPU. ``window.py``
already changes the primary display's mode for the borderless-windowed launch;
this module is the per-monitor view, which that one does not provide.

Changing a rate is applied to the registry so it survives a reboot, and the
previous mode is returned so the caller can put it back. Nothing here is called
during a launch; it is only used when someone asks for it.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

CCHDEVICENAME = 32
CCHFORMNAME = 32

ENUM_CURRENT_SETTINGS = -1
ENUM_REGISTRY_SETTINGS = -2

DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000

CDS_UPDATEREGISTRY = 0x00000001
CDS_TEST = 0x00000002

DISP_CHANGE_SUCCESSFUL = 0
_CHANGE_RESULT = {
    0: "applied",
    -1: "the display driver refused the mode",
    -2: "the mode is not supported by this display",
    -3: "the change needs a restart",
    -4: "the display driver failed the change",
    -5: "another process is changing the display",
    -6: "an internal display error",
}

DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * CCHDEVICENAME),
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
        ("dmFormName", wintypes.WCHAR * CCHFORMNAME),
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


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


try:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
except (OSError, AttributeError):        # not Windows
    _user32 = None


@dataclass
class Mode:
    width: int
    height: int
    refresh: int

    def __str__(self) -> str:
        return f"{self.width}x{self.height} @ {self.refresh} Hz"


@dataclass
class Display:
    device: str
    name: str
    primary: bool
    current: Optional[Mode]
    # resolution -> the refresh rates that resolution supports, highest first
    rates: Dict[Tuple[int, int], List[int]] = field(default_factory=dict)

    @property
    def available_here(self) -> List[int]:
        """Refresh rates offered at the resolution currently in use."""
        if self.current is None:
            return []
        return self.rates.get((self.current.width, self.current.height), [])

    @property
    def best_here(self) -> Optional[int]:
        rates = self.available_here
        return rates[0] if rates else None

    @property
    def at_best(self) -> bool:
        """Whether this screen is already at the highest rate it offers.

        Panels report rounded rates -- a 239.964 Hz mode comes back as 240 from
        this API but as 239 from WMI -- so this compares what the display API
        itself says, not a number from somewhere else.
        """
        best = self.best_here
        return best is not None and self.current is not None and self.current.refresh >= best


def _modes_for(device: str) -> Dict[Tuple[int, int], List[int]]:
    found: Dict[Tuple[int, int], set] = {}
    index = 0
    while True:
        mode = DEVMODEW()
        mode.dmSize = ctypes.sizeof(DEVMODEW)
        if not _user32.EnumDisplaySettingsW(device, index, ctypes.byref(mode)):
            break
        index += 1
        if mode.dmBitsPerPel != 32:          # 8- and 16-bit modes are not useful here
            continue
        found.setdefault((mode.dmPelsWidth, mode.dmPelsHeight), set()).add(
            mode.dmDisplayFrequency)
    return {size: sorted(rates, reverse=True) for size, rates in found.items()}


def _current_mode(device: str) -> Optional[Mode]:
    mode = DEVMODEW()
    mode.dmSize = ctypes.sizeof(DEVMODEW)
    if not _user32.EnumDisplaySettingsW(device, ENUM_CURRENT_SETTINGS, ctypes.byref(mode)):
        return None
    return Mode(mode.dmPelsWidth, mode.dmPelsHeight, mode.dmDisplayFrequency)


def list_displays() -> List[Display]:
    """Every display attached to the desktop, with the modes it offers."""
    if _user32 is None:
        return []
    out: List[Display] = []
    index = 0
    while True:
        device = DISPLAY_DEVICEW()
        device.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not _user32.EnumDisplayDevicesW(None, index, ctypes.byref(device), 0):
            break
        index += 1
        if not device.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
            continue
        out.append(Display(
            device=device.DeviceName,
            name=device.DeviceString,
            primary=bool(device.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE),
            current=_current_mode(device.DeviceName),
            rates=_modes_for(device.DeviceName),
        ))
    return out


def find(device: str) -> Optional[Display]:
    return next((d for d in list_displays() if d.device == device), None)


def _game_running() -> bool:
    """Whether CS2 currently has a window.

    A running game owns the display mode -- it set the resolution it wanted on
    the way in. Changing the mode underneath it drops the swapchain, which is
    the black screen this whole application exists to avoid.
    """
    try:
        from . import window
        return window.find_game_window("cs2.exe") is not None
    except Exception:
        return False


def set_refresh(device: str, refresh: int, apply: bool = False,
                force: bool = False) -> dict:
    """Move one display to a different refresh rate at its current resolution.

    With ``apply`` left off this only tests the mode, which is how the caller
    can offer a rate without committing to it. The mode that was in use is
    returned either way, so it can be put back.
    """
    if _user32 is None:
        return {"ok": False, "error": "display modes are a Windows feature"}

    if apply and not force and _game_running():
        return {"ok": False, "game_running": True,
                "error": "CS2 is running and owns the display mode; "
                         "changing it now would black the game out. "
                         "Close CS2 first."}

    screen = find(device)
    if screen is None:
        return {"ok": False, "error": f"no display called {device}"}
    if screen.current is None:
        return {"ok": False, "error": f"{device} did not report its current mode"}

    offered = screen.available_here
    if offered and refresh not in offered:
        return {"ok": False,
                "error": f"{device} does not offer {refresh} Hz at "
                         f"{screen.current.width}x{screen.current.height}; "
                         f"it offers {', '.join(str(r) for r in offered)}"}

    previous = screen.current
    if previous.refresh == refresh and apply:
        return {"ok": True, "changed": False, "previous": str(previous),
                "note": f"{device} was already at {refresh} Hz"}

    mode = DEVMODEW()
    mode.dmSize = ctypes.sizeof(DEVMODEW)
    if not _user32.EnumDisplaySettingsW(device, ENUM_CURRENT_SETTINGS, ctypes.byref(mode)):
        return {"ok": False, "error": f"could not read the current mode of {device}"}

    # Only the frequency changes; width and height come from the mode in use.
    mode.dmDisplayFrequency = refresh
    mode.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY

    flags = CDS_TEST if not apply else CDS_UPDATEREGISTRY
    code = _user32.ChangeDisplaySettingsExW(device, ctypes.byref(mode), None, flags, None)
    if code != DISP_CHANGE_SUCCESSFUL:
        return {"ok": False, "previous": str(previous),
                "error": _CHANGE_RESULT.get(code, f"display change failed ({code})")}

    if not apply:
        return {"ok": True, "changed": False, "tested": True,
                "previous": str(previous),
                "note": f"{refresh} Hz is accepted by {device}; not applied"}

    now = _current_mode(device)
    return {"ok": True, "changed": True, "previous": str(previous),
            "current": str(now) if now else "",
            "note": f"{device} set to {refresh} Hz"}


def summary() -> dict:
    screens = list_displays()
    return {
        "ok": True,
        "displays": [
            {
                "device": d.device,
                "name": d.name,
                "primary": d.primary,
                "current": str(d.current) if d.current else "",
                "width": d.current.width if d.current else 0,
                "height": d.current.height if d.current else 0,
                "refresh": d.current.refresh if d.current else 0,
                "rates": d.available_here,
                "best": d.best_here,
                "at_best": d.at_best,
            }
            for d in screens
        ],
        "all_at_best": all(d.at_best for d in screens) if screens else False,
    }
