"""The things people reboot for, done without rebooting.

Most of what ruins a session is a device or a service that has got itself into
a bad state: the adapter that started dropping packets an hour ago, the driver
that hung and left the picture frozen, the mouse that stopped reporting, the
headset Windows quietly switched away from. Every one of them has a fix that is
faster than a restart, and every one is buried somewhere different.

This is that set of fixes, with the safety each one actually needs.

Three rules run through all of it:

* **Nothing runs while CS2 is in a match it could lose.** Restarting a network
  adapter mid-round disconnects you; that is not a fix, it is the problem.
* **Anything disabled is re-enabled in the same breath.** ``Disable-PnpDevice``
  persists across reboots, so a disable that does not reach its enable does not
  inconvenience somebody, it takes their keyboard away until they find another
  one. Every such action re-enables in a ``finally``, and reports whether the
  device actually came back.
* **Nothing undocumented is written.** Per-app audio routing is the obvious
  example: the interface behind it (``IPolicyConfig2``) is private, and the
  registry it lands in is an opaque blob. So that one opens the exact Windows
  page instead of guessing at the format -- the same reason the driver profile
  in :mod:`cs2cfg.nvidia` is read-only.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_CREATE_NO_WINDOW = 0x08000000

# How long to wait for an elevated one-shot to publish its result. Generous:
# the wait includes the user reading and answering the UAC prompt.
ELEVATED_TIMEOUT = 120.0

# Windows device classes worth offering. Everything else on a PnP list is
# system plumbing that nobody wants a button for.
PERIPHERAL_CLASSES = ("Mouse", "Keyboard", "HIDClass", "AudioEndpoint",
                      "Media", "USB", "Bluetooth", "Image")

# Classes where taking the last one away leaves somebody unable to answer the
# dialog telling them what happened.
ESSENTIAL_CLASSES = ("Mouse", "Keyboard")

# What to show without being asked. A real machine reports about 145 devices
# across the classes above, and a list that long hides the mouse rather than
# offering it.
COMMON_CLASSES = ("Mouse", "Keyboard", "AudioEndpoint")


class FixError(RuntimeError):
    pass


@dataclass
class Fix:
    """One repair, and what it costs to run."""
    id: str
    family: str
    title: str
    blurb: str
    needs_admin: bool = False
    # Whether running it during a match would cost the match.
    disruptive: bool = False
    # ...and whether it is nonetheless allowed then. Restarting the display
    # driver is the one repair whose whole purpose is a game that has frozen,
    # so refusing it while the game is up would withhold it exactly when it is
    # wanted. Windows closes nothing when it resets the driver.
    allowed_in_game: bool = False
    danger: str = ""


CATALOGUE: List[Fix] = [
    Fix("net.flush", "network", "Flush the DNS cache",
        "Clears the resolver. Worth doing first when the game connects slowly "
        "or fails to reach a server it reached yesterday.",
        needs_admin=True),
    Fix("net.restart", "network", "Restart the connection",
        "Takes the adapter down and brings it back, which clears a link that "
        "has been dropping packets. The most common fix for loss that started "
        "mid-session.",
        needs_admin=True, disruptive=True,
        danger="Drops every connection on this machine for a few seconds."),
    Fix("gpu.restart", "graphics", "Restart the graphics driver",
        "Resets the display driver and the desktop compositor, which clears a "
        "hung GPU: a frozen picture, artefacts, a black screen, or frames that "
        "stopped arriving. The screen blinks; nothing closes.",
        disruptive=True, allowed_in_game=True),
    Fix("device.restart", "devices", "Restart a device",
        "Takes one device down and brings it straight back, the same as "
        "unplugging and replugging it. For a mouse that stopped reporting, a "
        "keyboard with a stuck key, or a headset Windows has lost.",
        needs_admin=True,
        danger="The device is unavailable for a moment."),
    Fix("sound.restart", "sound", "Restart Windows audio",
        "Restarts the audio service, which brings back sound that has gone "
        "silent or crackly without anything else changing.",
        needs_admin=True, disruptive=True,
        danger="Audio stops for a second or two everywhere."),
    Fix("sound.apps", "sound", "Choose CS2's sound device",
        "Opens the Windows page where CS2 can be given its own output and "
        "input, without changing what everything else uses."),
]


def catalogue() -> List[Dict[str, Any]]:
    return [{"id": f.id, "family": f.family, "title": f.title, "blurb": f.blurb,
             "needs_admin": f.needs_admin, "disruptive": f.disruptive,
             "allowed_in_game": f.allowed_in_game, "danger": f.danger}
            for f in CATALOGUE]


def _elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _powershell(script: str, timeout: int = 60) -> str:
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
            creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (done.stdout or "").strip()


def _game_running() -> bool:
    try:
        from . import window

        return window.find_game_window("cs2.exe") is not None
    except Exception:
        return False


def _run_elevated(body: str, timeout: float = ELEVATED_TIMEOUT) -> Dict[str, Any]:
    """Run one script as administrator and wait for what it reported.

    The script writes a small JSON result to a temporary file and this reads
    it. Going through a file rather than the exit code means a fix can say what
    it actually did -- which adapter, whether the device came back -- instead of
    only whether it returned zero.
    """
    if sys.platform != "win32":
        return {"ok": False, "error": "these repairs are Windows-only"}

    handle, result_path = tempfile.mkstemp(prefix="cs2fix-", suffix=".json")
    os.close(handle)
    script_path = result_path[:-5] + ".ps1"
    wrapped = (
        "$out = @{ ok = $false; detail = ''; }\n"
        "try {\n" + body + "\n}\n"
        "catch { $out.ok = $false; $out.detail = $_.Exception.Message }\n"
        "finally {\n"
        "  ($out | ConvertTo-Json -Compress) | "
        f"  Set-Content -Encoding utf8 -LiteralPath '{result_path}'\n"
        "}\n"
    )
    try:
        with open(script_path, "w", encoding="utf-8") as handle:
            handle.write(wrapped)

        arguments = f'-NoProfile -ExecutionPolicy Bypass -File "{script_path}"'
        if _elevated():
            # Already administrator, so no prompt is needed or wanted.
            _powershell(f'& "{script_path}"', timeout=int(timeout))
        else:
            code = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", "powershell", arguments, None, 0)
            if int(code) <= 32:
                if int(code) == 5:
                    return {"ok": False, "declined": True,
                            "error": "the administrator prompt was declined"}
                return {"ok": False,
                        "error": f"Windows would not start the repair ({code})"}

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = open(result_path, encoding="utf-8-sig").read().strip()
            except OSError:
                raw = ""
            if raw:
                try:
                    return json.loads(raw)
                except ValueError:
                    return {"ok": False, "error": "the repair returned nothing readable"}
            time.sleep(0.4)
        return {"ok": False, "error": "the repair did not finish in time"}
    finally:
        for path in (script_path, result_path):
            try:
                os.unlink(path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def adapters() -> List[Dict[str, Any]]:
    """Every connected adapter, with enough to tell Wi-Fi from a cable."""
    out = _powershell(
        "Get-NetAdapter | Where-Object Status -eq 'Up' | "
        "Select-Object Name,InterfaceDescription,LinkSpeed,PhysicalMediaType,"
        "ifIndex,InterfaceMetric | ConvertTo-Json -Compress")
    if not out:
        return []
    try:
        data = json.loads(out)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]

    found = []
    for row in data:
        media = f"{row.get('PhysicalMediaType') or ''} {row.get('InterfaceDescription') or ''}".lower()
        wireless = any(w in media for w in ("802.11", "wi-fi", "wifi", "wireless"))
        found.append({
            "name": str(row.get("Name") or ""),
            "description": str(row.get("InterfaceDescription") or ""),
            "speed": str(row.get("LinkSpeed") or ""),
            "wireless": wireless,
            "metric": row.get("InterfaceMetric"),
        })
    # The lowest metric is the one Windows actually routes through.
    found.sort(key=lambda a: (a["metric"] if a["metric"] is not None else 9999))
    return found


def _fix_flush_dns() -> Dict[str, Any]:
    return _run_elevated(
        "  ipconfig /flushdns | Out-Null\n"
        "  $out.ok = $true\n"
        "  $out.detail = 'DNS cache cleared'\n")


def _fix_restart_adapter(name: str) -> Dict[str, Any]:
    if not name:
        return {"ok": False, "error": "no adapter chosen"}
    if _game_running():
        return {"ok": False, "blocked": True,
                "error": "CS2 is running. Restarting the adapter now would "
                         "disconnect you mid-match. Close the game first."}
    safe = name.replace("'", "''")
    return _run_elevated(
        f"  $a = Get-NetAdapter -Name '{safe}' -ErrorAction Stop\n"
        "  Restart-NetAdapter -InputObject $a -Confirm:$false -ErrorAction Stop\n"
        "  Start-Sleep -Seconds 4\n"
        f"  $now = Get-NetAdapter -Name '{safe}' -ErrorAction SilentlyContinue\n"
        "  $out.ok = ($now -and $now.Status -eq 'Up')\n"
        "  $out.detail = if ($out.ok) "
        f"{{ '{safe} came back up' }} else {{ '{safe} has not come back yet' }}\n",
        timeout=ELEVATED_TIMEOUT)


# ---------------------------------------------------------------------------
# Graphics
# ---------------------------------------------------------------------------

# Win + Ctrl + Shift + B. Windows resets the display driver and the compositor
# on this combination; it is the documented way to clear a hung GPU without a
# reboot, and it closes nothing. There is no API for it, so the keys are sent.
_VK = {"win": 0x5B, "ctrl": 0x11, "shift": 0x10, "b": 0x42}
_KEYEVENTF_KEYUP = 0x0002


# ULONG_PTR: pointer-width, and not the same as a pointer TO a long. Getting
# this wrong changes the size of every structure below it.
_ULONG_PTR = wintypes.WPARAM

_INPUT_KEYBOARD = 1
_ERROR_ACCESS_DENIED = 5


class _KeyInput(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", _ULONG_PTR)]


class _MouseInput(ctypes.Structure):
    """Never sent -- declared because it is the union's largest member.

    SendInput rejects the whole call unless cbSize is exactly sizeof(INPUT),
    and sizeof(INPUT) is set by the biggest arm of its union, which is this
    one and not the keyboard arm. Padding the union by hand to a number that
    happened to be right on one architecture is what broke this before.
    """

    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", _ULONG_PTR)]


class _HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", _MouseInput), ("ki", _KeyInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _InputUnion)]


# What Windows will accept: 40 bytes on x64, 28 on x86. Checked at import so a
# structure that has drifted is a loud failure here rather than a silent zero
# from SendInput at the moment somebody needs their screen back.
INPUT_SIZE = ctypes.sizeof(_Input)
EXPECTED_INPUT_SIZE = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28


def _send_keys(sequence) -> int:
    """Send the sequence. Returns the Windows error code, or 0 for success."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.c_void_p, ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT

    events = []
    for code, up in sequence:
        item = _Input(type=_INPUT_KEYBOARD)
        item.u.ki = _KeyInput(wVk=code, wScan=0,
                              dwFlags=_KEYEVENTF_KEYUP if up else 0,
                              time=0, dwExtraInfo=0)
        events.append(item)
    block = (_Input * len(events))(*events)

    ctypes.set_last_error(0)
    sent = user32.SendInput(len(events), ctypes.byref(block), INPUT_SIZE)
    if sent == len(events):
        return 0
    return ctypes.get_last_error() or -1


def _fix_restart_gpu() -> Dict[str, Any]:
    if sys.platform != "win32":
        return {"ok": False, "error": "this repair is Windows-only"}
    if INPUT_SIZE != EXPECTED_INPUT_SIZE:
        return {"ok": False,
                "error": f"the keyboard structure is {INPUT_SIZE} bytes and "
                         f"Windows wants {EXPECTED_INPUT_SIZE}; this is a bug"}
    order = ["win", "ctrl", "shift", "b"]
    sequence = [(_VK[k], False) for k in order]
    sequence += [(_VK[k], True) for k in reversed(order)]
    try:
        code = _send_keys(sequence)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    if code == _ERROR_ACCESS_DENIED:
        # UIPI: a window running as administrator is in front, and input may
        # not be injected past it from down here.
        return {"ok": False,
                "error": "Windows blocked the keystroke because a program "
                         "running as administrator is in the foreground. "
                         "Click your desktop first, then try again."}
    if code:
        return {"ok": False,
                "error": f"Windows did not accept the keystroke (error {code})"}
    return {"ok": True, "detail": "Display driver reset. The screen blinks; "
                                  "nothing was closed."}


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

def devices() -> List[Dict[str, Any]]:
    """The peripherals worth offering a restart for."""
    classes = ",".join(f"'{c}'" for c in PERIPHERAL_CLASSES)
    out = _powershell(
        f"Get-PnpDevice -PresentOnly -Status OK | Where-Object {{ $_.Class -in {classes} }} | "
        "Select-Object FriendlyName,Class,InstanceId | ConvertTo-Json -Compress", 60)
    if not out:
        return []
    try:
        data = json.loads(out)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]

    counts: Dict[str, int] = {}
    for row in data:
        klass = str(row.get("Class") or "")
        counts[klass] = counts.get(klass, 0) + 1

    found = []
    for row in data:
        klass = str(row.get("Class") or "")
        name = str(row.get("FriendlyName") or "").strip()
        if not name:
            continue
        # Taking away the only mouse or the only keyboard leaves somebody
        # unable to answer the dialog explaining what just happened.
        last_one = klass in ESSENTIAL_CLASSES and counts.get(klass, 0) <= 1
        found.append({
            "name": name,
            "class": klass,
            "id": str(row.get("InstanceId") or ""),
            "restartable": not last_one,
            # The ones a player would name if asked what is plugged in. The
            # rest -- three dozen HID collections, every Bluetooth radio
            # sub-node -- are real devices but not ones anybody goes looking
            # for, so they sit behind "show everything" rather than burying
            # the mouse in a list of 145.
            "common": klass in COMMON_CLASSES,
            "why_not": ("This is the only " + klass.lower() + " on the machine. "
                        "Restarting it could leave you unable to put it back.")
                       if last_one else "",
        })
    found.sort(key=lambda d: (not d["common"], d["class"], d["name"].lower()))
    return found


def _fix_restart_device(instance_id: str) -> Dict[str, Any]:
    if not instance_id:
        return {"ok": False, "error": "no device chosen"}

    known = {d["id"]: d for d in devices()}
    entry = known.get(instance_id)
    if entry is None:
        return {"ok": False, "error": "that device is not connected"}
    if not entry["restartable"]:
        return {"ok": False, "blocked": True, "error": entry["why_not"]}

    safe = instance_id.replace("'", "''")
    # The enable is in a finally of its own: Disable-PnpDevice persists across
    # reboots, so a disable that does not reach its enable does not inconvenience
    # somebody, it takes the device away until they find another one.
    return _run_elevated(
        f"  $id = '{safe}'\n"
        "  $d = Get-PnpDevice -InstanceId $id -ErrorAction Stop\n"
        "  try {\n"
        "    Disable-PnpDevice -InstanceId $id -Confirm:$false -ErrorAction Stop\n"
        "    Start-Sleep -Milliseconds 900\n"
        "  } finally {\n"
        "    Enable-PnpDevice -InstanceId $id -Confirm:$false -ErrorAction SilentlyContinue\n"
        "  }\n"
        "  Start-Sleep -Seconds 2\n"
        "  $back = Get-PnpDevice -InstanceId $id -ErrorAction SilentlyContinue\n"
        "  $out.ok = ($back -and $back.Status -eq 'OK')\n"
        "  $out.detail = if ($out.ok) { $d.FriendlyName + ' is back' } "
        "else { $d.FriendlyName + ' has not come back -- unplug and replug it' }\n")


# ---------------------------------------------------------------------------
# Sound
# ---------------------------------------------------------------------------

def sound_devices() -> Dict[str, Any]:
    """What Windows is playing through, and whether anything unusual is here.

    Read-only on purpose. Routing one application to one endpoint goes through
    ``IPolicyConfig2``, which Microsoft has never documented, into a registry
    blob whose format is not published. Writing it would be guesswork of
    exactly the kind this project refuses elsewhere, and getting it wrong on a
    mixer someone streams through is not a small mistake.
    """
    out = _powershell(
        "Get-CimInstance Win32_SoundDevice | "
        "Select-Object Name,Status | ConvertTo-Json -Compress", 45)
    names: List[Dict[str, str]] = []
    if out:
        try:
            data = json.loads(out)
        except ValueError:
            data = []
        if isinstance(data, dict):
            data = [data]
        for row in data:
            names.append({"name": str(row.get("Name") or ""),
                          "status": str(row.get("Status") or "")})

    # Interfaces that route audio themselves. Changing the Windows default on a
    # machine with one of these can silence a stream rather than fix a game.
    watch = ("goxlr", "elgato", "wave xlr", "focusrite", "scarlett", "rode",
             "rodecaster", "virtual audio", "voicemeeter", "steinberg", "motu")
    special = [n["name"] for n in names
               if any(w in n["name"].lower() for w in watch)]
    return {"devices": names, "special": special}


def _fix_restart_audio() -> Dict[str, Any]:
    return _run_elevated(
        "  Restart-Service -Name audiosrv -Force -ErrorAction Stop\n"
        "  Start-Sleep -Seconds 2\n"
        "  $s = Get-Service -Name audiosrv\n"
        "  $out.ok = ($s.Status -eq 'Running')\n"
        "  $out.detail = if ($out.ok) { 'Windows Audio restarted' } "
        "else { 'Windows Audio did not come back' }\n")


def _fix_open_app_volume() -> Dict[str, Any]:
    """Open the page where CS2 can be given its own output and input.

    Deliberately opening the page rather than writing the setting: see
    :func:`sound_devices`. It is also the page that shows a per-app choice
    without touching what the rest of Windows uses, which is the distinction
    that matters on a machine with a mixer on it.
    """
    if sys.platform != "win32":
        return {"ok": False, "error": "this is a Windows settings page"}
    try:
        os.startfile("ms-settings:apps-volume")  # noqa: S606 - a settings URI
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True,
            "detail": "Opened Volume mixer. Find Counter-Strike 2 in the list "
                      "and set its output and input there; everything else "
                      "keeps the device it already had."}


# ---------------------------------------------------------------------------

_RUNNERS = {
    "net.flush": lambda body: _fix_flush_dns(),
    "net.restart": lambda body: _fix_restart_adapter(str(body.get("adapter") or "")),
    "gpu.restart": lambda body: _fix_restart_gpu(),
    "device.restart": lambda body: _fix_restart_device(str(body.get("device") or "")),
    "sound.restart": lambda body: _fix_restart_audio(),
    "sound.apps": lambda body: _fix_open_app_volume(),
}


def run(fix_id: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run one repair by id."""
    runner = _RUNNERS.get(fix_id)
    if runner is None:
        return {"ok": False, "error": f"no repair called {fix_id!r}"}

    fix = next((f for f in CATALOGUE if f.id == fix_id), None)
    if fix is not None and fix.disruptive and not fix.allowed_in_game and _game_running():
        return {"ok": False, "blocked": True,
                "error": "CS2 is running, and this would interrupt it. "
                         "Close the game first."}
    try:
        return runner(body or {})
    except Exception as exc:                 # a repair must not take the app down
        return {"ok": False, "error": str(exc)}


def survey() -> Dict[str, Any]:
    """Everything the page needs to draw the tab."""
    return {
        "ok": True,
        "fixes": catalogue(),
        "adapters": adapters(),
        "devices": devices(),
        "sound": sound_devices(),
        "game_running": _game_running(),
        "elevated": _elevated(),
    }
