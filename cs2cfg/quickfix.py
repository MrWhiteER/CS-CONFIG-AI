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
import re
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    Fix("display.restore", "graphics", "Put the resolution back",
        "Returns the desktop to its normal resolution. For when a launch "
        "narrowed it for a stretched mode and never put it back -- the game "
        "crashed, or this application was closed while it still had it. Safe "
        "to press when nothing is wrong: it says so and changes nothing.",
        allowed_in_game=True),
    Fix("steam.restart", "steam", "Restart Steam",
        "Closes Steam properly and starts it again, then waits until it has "
        "signed back in. For the client that has gone sour underneath the "
        "game: \"No Steam logon\" dropping you out of a match, a game that "
        "will not launch, a friends list stuck loading. Steam is asked to "
        "close the way its own menu closes it, so what it was holding is "
        "written out first.",
        disruptive=True,
        danger="Closes Steam, and any download it is in the middle of. CS2 has "
               "to be closed first."),
    Fix("sound.apps", "sound", "Choose CS2's sound device",
        "Opens the Windows page where CS2 can be given its own output and "
        "input, without changing what everything else uses."),
    Fix("shader.clear", "graphics", "Clear the shader cache",
        "Deletes the cached, compiled shaders for CS2's graphics driver. The "
        "game rebuilds them on its own the moment it needs them again -- the "
        "usual fix for stutter that started right after a game update or a "
        "new graphics driver, when the old cache no longer matches what is "
        "actually running.",
        disruptive=True,
        danger="CS2 will stutter again for the first few minutes while it "
               "recompiles -- that is the cache doing its job, not a new "
               "problem."),
    Fix("steam.zombie", "steam", "End a stuck CS2",
        "For when Steam insists CS2 is already running and refuses to start "
        "it again, but there is no game on screen: a copy was left behind by "
        "a crash and never let go. Checked first, so a game that is actually "
        "up is never touched."),
    Fix("steam.verify", "steam", "Verify CS2's files",
        "Opens Steam's own file check for CS2 -- the official repair for "
        "missing or corrupted files, a download that did not finish, or a "
        "crash that started after installing a workshop map. Nothing here "
        "touches a file; Steam does the checking and the fixing itself."),
    Fix("mic.privacy", "sound", "Open microphone privacy settings",
        "Opens Windows' own microphone permissions. The most common reason a "
        "working headset still cannot be heard in CS2: access is on for apps "
        "in general but off for “desktop apps” specifically, which "
        "is the category CS2 and Steam are both in."),
    Fix("startup.apps", "boost", "Open startup apps",
        "Opens Windows' list of what starts with the machine. Thinning this "
        "out is the single biggest thing a slow boot and a background-heavy "
        "session usually have in common -- which program to keep is a choice "
        "only you can make, so this opens the list rather than guessing at "
        "it."),
    Fix("defender.exclude", "boost", "Exclude CS2 from antivirus scanning",
        "Tells Windows Security to stop scanning CS2's own folder in real "
        "time. Real-time scanning re-checks files as the game reads them, "
        "which on some machines costs noticeable stutter and load times. The "
        "same switch puts it back.",
        needs_admin=True,
        danger="Anything placed in that folder stops being scanned, by "
               "Windows or by anyone else with access to this machine."),
    Fix("fullscreen.exclusive", "graphics", "Turn off Fullscreen Optimizations",
        "The Windows setting from CS2's own Properties > Compatibility tab, "
        "flipped here instead of six clicks deep in Explorer. True exclusive "
        "fullscreen reaches the display with one less layer between the game "
        "and the screen, which is lower input lag on some machines and does "
        "nothing on others. The same switch puts it back."),
    Fix("power.performance", "boost", "Switch to Ultimate Performance power",
        "Moves Windows onto its own Ultimate Performance plan, which Windows "
        "ships but keeps hidden on most machines. It goes further than High "
        "performance: parking cores, USB selective suspend and PCIe link "
        "power-saving are all the kind of thing that costs a tiny stall when "
        "a device wakes back up, and this plan asks Windows to stop doing "
        "them for as long as it stays on. Falls back to High performance if "
        "this edition of Windows will not create it. The same switch puts "
        "the previous plan back."),
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


# --- Steam ------------------------------------------------------------------
#
# "No Steam logon" mid-match is the client's session having gone bad, not the
# game and not this application: it happens launching straight from Steam too,
# and a restart of the client clears it. So the repair is a restart of the
# client, in the one place somebody already looks when something has gone
# wrong mid-session.

STEAM_PROCESS = "steam.exe"
# How long Steam is given to close on its own before it is ended. Generous on
# purpose: it is flushing files on the way out, and cutting that short to save
# ten seconds is how somebody loses the settings Steam was holding.
STEAM_SHUTDOWN_WAIT = 30.0
STEAM_READY_WAIT = 90.0

# Steam writes this the moment a sign-in completes. Watched rather than
# guessed at, because "the process exists" is true a second after launching it
# and says nothing about whether it can start a game yet.
_LOGON_MARK = "RecvMsgClientLogOnResponse() : processing complete"
_LOG_STAMP = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")


def _steam_running() -> bool:
    try:
        done = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {STEAM_PROCESS}", "/NH"],
            capture_output=True, text=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return STEAM_PROCESS.lower() in (done.stdout or "").lower()


def _wait_until(condition, limit: float, step: float = 1.0) -> bool:
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(step)
    return bool(condition())


def _signed_in_since(started: float) -> bool:
    """Whether Steam has completed a sign-in since ``started``.

    Read out of Steam's own connection log rather than the registry.
    the ``ActiveUser`` value under ``ActiveProcess`` is the documented-looking answer and is
    simply wrong here -- it reads 0 on this machine with Steam running and
    signed in -- so it is not trusted. The log line is dated, which also makes
    this survive Steam rotating the file to connection_log.previous.txt on
    restart: a stale entry cannot be mistaken for a fresh one.
    """
    from . import steam as steam_mod

    try:
        root = steam_mod.find_steam_root()
    except Exception:
        return False
    if root is None:
        return False
    try:
        text = (root / "logs" / "connection_log.txt").read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return False
    for line in reversed(text.splitlines()):
        if _LOGON_MARK not in line:
            continue
        found = _LOG_STAMP.match(line)
        if not found:
            continue
        try:
            when = time.mktime(time.strptime(found.group(1), "%Y-%m-%d %H:%M:%S"))
        except (ValueError, OverflowError):
            continue
        # Two seconds of slack: the log is second-resolution local time.
        return when >= started - 2.0
    return False


def _fix_restart_steam(body: Dict[str, Any]) -> Dict[str, Any]:
    from . import launcher

    if sys.platform != "win32":
        raise FixError("restarting Steam is only implemented on Windows")
    exe = launcher.steam_exe()
    if exe is None:
        raise FixError("Steam could not be found on this machine")

    started = time.time()
    steps: List[str] = []
    forced = False

    if _steam_running():
        # Steam's own shutdown, which is what its File > Exit does. A kill
        # here would lose whatever it had not yet written -- localconfig.vdf
        # among it, which is where the launch options live.
        try:
            subprocess.Popen(
                [str(exe), "-shutdown"],
                creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        except (OSError, subprocess.SubprocessError) as exc:
            raise FixError(f"could not ask Steam to close: {exc}")
        steps.append("asked Steam to close")

        if _wait_until(lambda: not _steam_running(), STEAM_SHUTDOWN_WAIT):
            steps.append("Steam closed")
        else:
            # Only now, and only after it has had its full chance to flush.
            forced = True
            subprocess.run(["taskkill", "/IM", STEAM_PROCESS, "/F", "/T"],
                           capture_output=True, text=True, timeout=30,
                           creationflags=_CREATE_NO_WINDOW)
            steps.append(f"Steam did not close within {int(STEAM_SHUTDOWN_WAIT)}s, "
                         "so it was ended")
            if not _wait_until(lambda: not _steam_running(), 10.0):
                raise FixError("Steam would not close, so it has not been restarted")
    else:
        steps.append("Steam was not running")

    try:
        subprocess.Popen([str(exe)],
                         creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except (OSError, subprocess.SubprocessError) as exc:
        raise FixError(f"Steam was closed but would not start again: {exc}")
    steps.append("started Steam")

    signed_in = _wait_until(lambda: _signed_in_since(started), STEAM_READY_WAIT)
    if signed_in:
        steps.append("Steam signed back in")
        detail = "Steam was restarted and has signed back in"
    else:
        # Not an error. Steam may be waiting on a password or a phone
        # confirmation, and saying "failed" over that would be a lie.
        steps.append("Steam is up, but no sign-in has completed yet")
        detail = ("Steam was restarted. It has not finished signing in -- it may "
                  "be waiting for your password or a confirmation on your phone.")

    return {"ok": True, "steps": steps, "forced": forced, "signed_in": signed_in,
            # The page starts the ordinary launch when this comes back true,
            # so the game still goes through the whole borderless preparation
            # rather than a second, lesser launch path living here.
            "then_play": bool(body.get("then_play")) and signed_in,
            "detail": detail}


# ---------------------------------------------------------------------------
# CS2 itself -- the fixes for the game's own well-known problems, as opposed
# to the device and driver repairs above.
# ---------------------------------------------------------------------------

def _cs2_install_dir() -> Optional[Path]:
    from . import steam as steam_mod

    try:
        root = steam_mod.find_steam_root()
        if root is None:
            return None
        return steam_mod.find_cs2_install(root)
    except Exception:
        return None


# Every vendor's own documented shader-cache location, all under this
# account's own AppData. Nothing here needs administrator, and nothing here
# is a file CS2 or the driver cannot simply rebuild -- which is the same
# reasoning that makes it safe to delete in the first place.
SHADER_CACHE_DIRS = (
    ("NVIDIA", ("NVIDIA", "DXCache")),
    ("NVIDIA", ("NVIDIA", "GLCache")),
    ("AMD", ("AMD", "DxCache")),
    ("AMD", ("AMD", "DxcCache")),
    ("AMD", ("AMD", "VkCache")),
    ("Intel", ("Intel", "ShaderCache")),
    ("Windows", ("D3DSCache",)),
)


def _fix_clear_shader_cache(_body: Dict[str, Any]) -> Dict[str, Any]:
    """Empty every shader cache folder this machine actually has.

    The folders themselves are left in place and only their contents are
    removed -- the vendors' own guidance, and cheap insurance against
    whatever first-run behaviour assumes the folder already exists.
    """
    base = os.environ.get("LOCALAPPDATA") or ""
    if not base or not Path(base).is_dir():
        raise FixError("could not find this account's AppData folder")

    cleared: List[str] = []
    freed = 0
    for vendor, parts in SHADER_CACHE_DIRS:
        folder = Path(base).joinpath(*parts)
        if not folder.is_dir():
            continue
        count = 0
        for child in folder.iterdir():
            try:
                if child.is_dir():
                    size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    size = child.stat().st_size
                    child.unlink()
                freed += size
                count += 1
            except OSError:
                continue
        if count:
            cleared.append(f"{vendor} ({parts[-1]})")

    if not cleared:
        return {"ok": True, "cleared": [],
                "detail": "Nothing was cached -- there was nothing to clear."}
    mb = freed / (1024 * 1024)
    return {"ok": True, "cleared": cleared,
            "detail": f"Cleared {', '.join(cleared)} ({mb:.0f} MB). The first "
                      "few minutes back in CS2 will stutter while it rebuilds "
                      "what it needs -- that is expected."}


def _cs2_process_running() -> bool:
    out = _powershell(
        "if (Get-Process -Name cs2 -ErrorAction SilentlyContinue) "
        "{ 'yes' } else { 'no' }")
    return out.strip().lower() == "yes"


def _fix_end_zombie_cs2(_body: Dict[str, Any]) -> Dict[str, Any]:
    """Ends a cs2.exe Steam has lost track of, and nothing else.

    Checked twice before anything is touched: once for a process at all, and
    once for a window on screen. A real window means a real game, and a real
    game is never the one this ends -- the person playing it closes it
    themselves.
    """
    if not _cs2_process_running():
        return {"ok": True, "ended": False,
                "detail": "No CS2 process was found -- there is nothing to end."}
    if _game_running():
        raise FixError("CS2 looks like it is actually running, with a window "
                        "on screen. Close it the ordinary way instead.")
    done = subprocess.run(["taskkill", "/IM", "cs2.exe", "/F"],
                          capture_output=True, text=True, timeout=15,
                          creationflags=_CREATE_NO_WINDOW)
    if done.returncode != 0:
        raise FixError((done.stderr or done.stdout or "taskkill failed").strip())
    return {"ok": True, "ended": True,
            "detail": "The stuck process has been ended. Steam should let CS2 "
                      "start again now."}


def _fix_open_verify(_body: Dict[str, Any]) -> Dict[str, Any]:
    """Opens Steam's own integrity check for CS2 -- the official repair.

    Nothing here touches a file. Steam does the checking and the fixing
    itself, through the same page its own Properties menu opens.
    """
    if sys.platform != "win32":
        raise FixError("this opens a Steam window, which needs Windows")
    try:
        os.startfile("steam://validate/730")
    except OSError as exc:
        raise FixError(f"could not ask Steam to open: {exc}")
    return {"ok": True,
            "detail": "Steam is checking CS2's files now. Watch its own "
                      "Downloads page for progress."}


def _fix_open_settings_page(uri: str, what: str) -> Dict[str, Any]:
    if sys.platform != "win32":
        raise FixError(f"this opens {what}, which needs Windows")
    try:
        os.startfile(uri)
    except OSError as exc:
        raise FixError(f"could not open {what}: {exc}")
    return {"ok": True, "detail": f"Opened {what}."}


def _fix_open_mic_privacy(_body: Dict[str, Any]) -> Dict[str, Any]:
    return _fix_open_settings_page("ms-settings:privacy-microphone",
                                   "the microphone privacy settings")


def _fix_open_startup_apps(_body: Dict[str, Any]) -> Dict[str, Any]:
    return _fix_open_settings_page("ms-settings:startupapps",
                                   "the startup apps list")


# ---------------------------------------------------------------------------
# Antivirus exclusion, Fullscreen Optimizations, and the power plan -- three
# settings that are not about a device or a driver misbehaving, but about
# Windows costing CS2 performance on purpose. Each is a straightforward
# toggle: the same id puts it back that turned it on.
# ---------------------------------------------------------------------------

def _defender_exclusions() -> List[str]:
    out = _powershell("(Get-MpPreference).ExclusionPath -join '|'")
    return [p for p in out.split("|") if p]


def _probe_cs2_and_defender() -> Dict[str, Any]:
    """One PowerShell call standing in for two, for the survey's sake.

    The survey runs on every Fix It page open, and every separate
    PowerShell call costs a few hundred milliseconds just to start the
    interpreter -- measurable on a page meant to feel instant. The two
    functions above still make their own separate calls, because they run
    once, when a button is pressed, and correctness matters more there than
    a few hundred milliseconds does.
    """
    out = _powershell(
        "$p = Get-Process -Name cs2 -ErrorAction SilentlyContinue;"
        "$d = @((Get-MpPreference -ErrorAction SilentlyContinue).ExclusionPath);"
        "(@{ cs2 = [bool]$p; exclusions = $d } | ConvertTo-Json -Compress -Depth 2)")
    try:
        data = json.loads(out) if out else {}
    except ValueError:
        data = {}
    exclusions = data.get("exclusions")
    if exclusions is None:
        exclusions = []
    elif isinstance(exclusions, str):
        exclusions = [exclusions]
    return {"cs2_running": bool(data.get("cs2")),
            "exclusions": [str(x) for x in exclusions]}


def defender_status() -> Dict[str, Any]:
    """Whether CS2's folder is currently excluded. Read-only, for the survey."""
    install = _cs2_install_dir()
    if sys.platform != "win32" or install is None:
        return {"supported": False}
    path = str(install)
    excluded = any(path.lower() == p.lower() for p in _defender_exclusions())
    return {"supported": True, "excluded": excluded}


def _fix_toggle_defender(_body: Dict[str, Any]) -> Dict[str, Any]:
    install = _cs2_install_dir()
    if install is None:
        raise FixError("CS2's install folder could not be found")
    path = str(install)
    now_excluded = any(path.lower() == p.lower() for p in _defender_exclusions())
    verb = "Remove-MpPreference" if now_excluded else "Add-MpPreference"
    escaped = path.replace("'", "''")
    result = _run_elevated(
        f"{verb} -ExclusionPath '{escaped}'\n"
        "$out.ok = $true\n")
    if not result.get("ok"):
        return result
    return {"ok": True, "excluded": not now_excluded,
            "detail": ("The exclusion has been removed -- CS2's folder is "
                       "scanned normally again." if now_excluded else
                       "CS2's folder is excluded from real-time scanning now.")}


FS_OPT_KEY = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
FS_OPT_TOKEN = "DISABLEDXMAXIMIZEDWINDOWEDMODE"


def _fullscreen_exe() -> Optional[Path]:
    from . import wingraphics

    return wingraphics.exe_path(_cs2_install_dir())


def _fs_opt_read(exe: Path) -> str:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, FS_OPT_KEY) as key:
            value, _ = winreg.QueryValueEx(key, str(exe))
        return str(value)
    except OSError:
        return ""


def fullscreen_status() -> Dict[str, Any]:
    exe = _fullscreen_exe()
    if sys.platform != "win32" or exe is None:
        return {"supported": False}
    return {"supported": True, "disabled": FS_OPT_TOKEN in _fs_opt_read(exe)}


def _fix_toggle_fullscreen_opt(_body: Dict[str, Any]) -> Dict[str, Any]:
    exe = _fullscreen_exe()
    if exe is None:
        raise FixError("CS2's executable was not found")
    current = _fs_opt_read(exe)
    now_disabled = FS_OPT_TOKEN in current
    # Anything else already in the value -- HIGHDPIAWARE is common -- is kept;
    # only the one token this fix owns is added or removed.
    tokens = [t for t in current.split() if t not in ("~", FS_OPT_TOKEN)]
    if not now_disabled:
        tokens.append(FS_OPT_TOKEN)
    try:
        import winreg

        if tokens:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, FS_OPT_KEY, 0,
                                    winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, str(exe), 0, winreg.REG_SZ,
                                  "~ " + " ".join(tokens))
        else:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, FS_OPT_KEY, 0,
                                    winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, str(exe))
            except OSError:
                pass
    except OSError as exc:
        raise FixError(f"could not write the setting: {exc}")
    return {"ok": True, "disabled": not now_disabled,
            "detail": ("Fullscreen Optimizations are back on for CS2."
                       if now_disabled else
                       "Fullscreen Optimizations are off for CS2 -- it will "
                       "run in true exclusive fullscreen.")}


POWER_RECORD = "power_plan.json"


def _power_record_path() -> Path:
    from .paths import user_data_dir

    return user_data_dir() / POWER_RECORD


def _powercfg(args: List[str], timeout: int = 20) -> Dict[str, Any]:
    """Run powercfg and report what actually happened.

    A first version of this kept only stdout and assumed success, which is
    how a ``/setactive`` that Windows refused -- a policy on a managed
    machine, a scheme this edition does not offer -- went unnoticed: the
    command returned instantly, said nothing useful on stdout, and the only
    sign anything was wrong was the scheme not having changed a few lines
    later. Keeping the exit code and stderr is what lets a caller tell "did
    not run" from "ran and changed nothing" from "worked".
    """
    try:
        done = subprocess.run(["powercfg", *args], capture_output=True, text=True,
                              timeout=timeout,
                              creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "out": "", "error": str(exc)}
    return {"ok": done.returncode == 0,
            "out": (done.stdout or "").strip(),
            "error": (done.stderr or done.stdout or "").strip()}


_GUID_RE = re.compile(r"GUID:\s*([0-9a-fA-F-]{36})")
_SCHEME_LINE_RE = re.compile(r"Power Scheme GUID:\s*([0-9a-fA-F-]{36})\s*\(([^)]*)\)")

# Ships inside Windows itself but stays off the list in /list until it has
# been duplicated in -- the documented way to reach it, and confirmed on a
# real machine: a GUID already present there did not match this one, which is
# what duplicating it once looks like afterward.
ULTIMATE_TEMPLATE_GUID = "e9a42b02-d5df-448d-aa00-03f14749eb61"


def _active_scheme_guid() -> Optional[str]:
    found = _GUID_RE.search(_powercfg(["/getactivescheme"])["out"])
    return found.group(1) if found else None


def _schemes() -> List[Tuple[str, str]]:
    """Every power scheme Windows currently lists, as (guid, name) pairs."""
    out = _powercfg(["/list"])["out"]
    return [(m.group(1), m.group(2).strip()) for m in _SCHEME_LINE_RE.finditer(out)]


def _find_or_create_ultimate_scheme() -> Optional[str]:
    """The Ultimate Performance plan's GUID, duplicating it in if this is
    the first time. None if this edition of Windows refuses to -- rare, and
    the caller falls back to High performance rather than failing outright.
    """
    for guid, name in _schemes():
        if name.lower() == "ultimate performance":
            return guid
    created = _powercfg(["-duplicatescheme", ULTIMATE_TEMPLATE_GUID])
    if not created["ok"]:
        return None
    found = _GUID_RE.search(created["out"])
    return found.group(1) if found else None


def power_status() -> Dict[str, Any]:
    if sys.platform != "win32":
        return {"supported": False}
    guid = _active_scheme_guid()
    boosted = False
    try:
        record = json.loads(_power_record_path().read_text(encoding="utf-8"))
        boosted = bool(record.get("active")) and guid == record.get("changed_to")
    except (OSError, ValueError):
        pass
    return {"supported": guid is not None, "boosted": boosted}


def _powercfg_setactive(scheme: str) -> Dict[str, Any]:
    """Switch the active scheme, trying the ordinary way first.

    Most machines let a standard user switch power plans; a few do not --
    seen on a real machine, failing in under a second with nothing on
    stdout, which is exactly what a policy refusal looks like rather than a
    crash. So a plain refusal is retried elevated before this gives up,
    rather than reported as the final answer.
    """
    plain = _powercfg(["/setactive", scheme])
    if plain["ok"]:
        return {"ok": True}
    elevated = _run_elevated(
        # Through cmd rather than called directly: PowerShell wraps a native
        # command's own stderr as an ErrorRecord rather than plain text,
        # which is how the real reason powercfg refused was getting lost.
        f'$msg = cmd /c "powercfg /setactive {scheme} 2>&1"\n'
        "if ($LASTEXITCODE -ne 0) { throw ($msg -join \"`n\") }\n"
        "$out.ok = $true\n")
    if elevated.get("ok"):
        return {"ok": True}
    # Whichever attempt has something to say. A decline is its own answer and
    # takes priority over powercfg's own wording, which would otherwise be
    # the stale message from the plain attempt that was never the real cause.
    if elevated.get("declined"):
        return {"ok": False, "declined": True, "error": elevated.get("error")}
    # error covers a prompt that never ran at all (declined, timed out);
    # detail covers the powercfg call itself failing inside the elevated
    # script, which is the case this was written for.
    return {"ok": False,
            "error": elevated.get("error") or elevated.get("detail") or
                     plain.get("error") or "Windows would not switch the power plan"}


def _fix_toggle_power(_body: Dict[str, Any]) -> Dict[str, Any]:
    if sys.platform != "win32":
        raise FixError("power plans are a Windows setting")
    guid = _active_scheme_guid()
    if guid is None:
        raise FixError("could not read the current power plan")

    record_path = _power_record_path()
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}

    if record.get("active") and guid == record.get("changed_to"):
        previous = record.get("before")
        if previous:
            result = _powercfg_setactive(previous)
            if not result["ok"]:
                if result.get("declined"):
                    return {"ok": False, "declined": True,
                            "error": "the administrator prompt was declined"}
                raise FixError(result.get("error") or
                               "Windows would not put the previous plan back")
        try:
            record_path.unlink()
        except OSError:
            pass
        return {"ok": True, "boosted": False,
                "detail": "Back on the power plan this machine had before."}

    before = guid
    target_name = "Ultimate Performance"
    target = _find_or_create_ultimate_scheme()
    if target is None:
        # Rare: duplicating the template itself failed. High performance is
        # the fallback rather than giving up, since it is the one every
        # edition of Windows ships with already.
        target_name = "High performance"
        target = "SCHEME_MIN"
    result = _powercfg_setactive(target)
    if not result["ok"]:
        if result.get("declined"):
            return {"ok": False, "declined": True,
                    "error": "the administrator prompt was declined"}
        raise FixError(result.get("error") or
                       "Windows would not switch the power plan")
    after = _active_scheme_guid()
    if after is None:
        raise FixError("powercfg accepted the change but the new plan "
                       "could not be read back")
    if after == before:
        # powercfg reported success and the scheme genuinely did not move --
        # overwhelmingly because it was already the active one. Nothing to
        # remember putting back, since nothing here actually changed.
        return {"ok": True, "boosted": True, "plan": target_name,
                "detail": f"Already on {target_name}."}
    try:
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(
            {"before": before, "changed_to": after, "active": True},
            indent=1), encoding="utf-8")
    except OSError:
        pass
    return {"ok": True, "boosted": True, "plan": target_name,
            "detail": f"Switched to {target_name}. The same button puts "
                      "the previous plan back."}


# ---------------------------------------------------------------------------

def _fix_restore_display(_body: Dict[str, Any]) -> Dict[str, Any]:
    """The manual version of the automatic put-back.

    Allowed during a game on purpose. The automatic one stands off while the
    game is running, because a running game is presumed to want the mode it
    was launched with -- but if somebody is looking at a wrong desktop with
    the game up, that presumption is already wrong and they are the ones who
    can see it.
    """
    from . import deskmode

    return deskmode.restore()


_RUNNERS = {
    "display.restore": _fix_restore_display,
    "steam.restart": _fix_restart_steam,
    "net.flush": lambda body: _fix_flush_dns(),
    "net.restart": lambda body: _fix_restart_adapter(str(body.get("adapter") or "")),
    "gpu.restart": lambda body: _fix_restart_gpu(),
    "device.restart": lambda body: _fix_restart_device(str(body.get("device") or "")),
    "sound.restart": lambda body: _fix_restart_audio(),
    "sound.apps": lambda body: _fix_open_app_volume(),
    "shader.clear": lambda body: _fix_clear_shader_cache(body),
    "steam.zombie": lambda body: _fix_end_zombie_cs2(body),
    "steam.verify": lambda body: _fix_open_verify(body),
    "mic.privacy": lambda body: _fix_open_mic_privacy(body),
    "startup.apps": lambda body: _fix_open_startup_apps(body),
    "defender.exclude": lambda body: _fix_toggle_defender(body),
    "fullscreen.exclusive": lambda body: _fix_toggle_fullscreen_opt(body),
    "power.performance": lambda body: _fix_toggle_power(body),
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
    """Everything the page needs to draw the tab.

    Each piece below is an independent read: nothing writes anything, and
    none of them depends on what another one finds. Run one after another
    they cost their sum -- on the machine this was measured on, five
    PowerShell processes started in turn came to five seconds, on a tab meant
    to feel instant. Run together the wall-clock cost is whichever one is
    slowest, which is the whole reason to bother.
    """
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=6) as pool:
        f_adapters = pool.submit(adapters)
        f_devices = pool.submit(devices)
        f_sound = pool.submit(sound_devices)
        f_probe = pool.submit(_probe_cs2_and_defender)
        f_fullscreen = pool.submit(fullscreen_status)
        f_power = pool.submit(power_status)

        adapters_result = f_adapters.result()
        devices_result = f_devices.result()
        sound_result = f_sound.result()
        probe = f_probe.result()
        fullscreen = f_fullscreen.result()
        power = f_power.result()

    game_up = _game_running()
    install = _cs2_install_dir()
    defender: Dict[str, Any] = {"supported": False}
    if sys.platform == "win32" and install is not None:
        path = str(install)
        defender = {"supported": True,
                    "excluded": any(path.lower() == p.lower()
                                    for p in probe["exclusions"])}
    return {
        "ok": True,
        "fixes": catalogue(),
        "adapters": adapters_result,
        "devices": devices_result,
        "sound": sound_result,
        "game_running": game_up,
        "elevated": _elevated(),
        "zombie_cs2": probe["cs2_running"] and not game_up,
        "defender": defender,
        "fullscreen": fullscreen,
        "power": power,
    }
