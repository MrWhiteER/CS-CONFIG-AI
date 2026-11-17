"""Starting FACEIT's own programs: the FACEIT client and FACEIT Anti-Cheat.

This is a companions integration (see cs2cfg/companions.py) and it keeps the
same rule: it finds the two executables and starts them. It never opens,
reads or writes a file that belongs to FACEIT, never talks to the anti-cheat,
and never sends either program any input. Starting a program the user
installed is exactly what double-clicking its shortcut does.

Two things make FACEIT different from an arbitrary companion:

* The anti-cheat must be running *before* CS2 starts, or FACEIT refuses the
  match until the game is restarted. Companions already start before the game;
  the launcher just has to wait longer for this one, because:
* The anti-cheat asks for administrator rights, so Windows shows a UAC prompt
  first. A plain CreateProcess refuses such a program (error 740), so it is
  handed to the shell instead, which is what shows the prompt.

Where they live is not fixed -- installers move between versions -- so the
known places are tried first and then the Windows uninstall list, which every
installer writes to.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import companions

CLIENT = "faceit-client"
AC = "faceit-ac"

APPS: Dict[str, Dict[str, Any]] = {
    CLIENT: {
        "name": "FACEIT",
        "exe_names": ("FACEIT.exe",),
        # Not the anti-cheat: its uninstall entry is also called "FACEIT ...".
        "display_match": lambda name: "faceit" in name and "anti" not in name
        and " ac" not in name,
        "places": (
            ("LOCALAPPDATA", "FACEIT"),
            ("LOCALAPPDATA", "Programs/FACEIT"),
            ("ProgramFiles", "FACEIT"),
        ),
    },
    AC: {
        "name": "FACEIT AC",
        "exe_names": ("faceitclient.exe", "FACEITClient.exe"),
        "display_match": lambda name: "faceit" in name
        and ("anti" in name or name.endswith(" ac") or " ac " in name),
        "places": (
            ("ProgramFiles", "FACEIT AC"),
            ("ProgramFiles(x86)", "FACEIT AC"),
        ),
    },
}

# How long the launcher waits for the anti-cheat to come up before starting
# CS2. Long, because a person has to answer a UAC prompt in that time.
AC_WAIT = 90.0


# What "the anti-cheat is ready" means -- read from FACEIT AC itself, never
# from a timer. Recorded on the player's PC (2026-11-17, a launch that worked):
#
#   +0.0s  faceitclient.exe starts
#   +1.0s  FACEITService START_PENDING, +1.6s RUNNING
#   +1.5s  visible window "FACEIT Anti-cheat" opens
#   +4.2s  the service connects to FACEIT's servers
#   +5.1s  a second window "FACEIT AC" opens
#   +7.3s  faceitclient links to the service on 127.0.0.1; "FACEIT AC" closes
#   +8.8s  faceitclient itself connects to FACEIT's servers: ready
#   +9.4s  CS2 starts and "FACEIT Anti-cheat" closes -- possibly *because*
#          the game appeared, so that window is never waited on: it could
#          wait for us while we wait for it.
#
# On a day FACEIT AC updates itself, all of that takes longer by an amount
# nobody can know in advance, and a CS2 started in the middle is the one
# FACEIT asks you to restart. So readiness is the end state, checked live:
#
#   1. faceitclient.exe running and FACEITService RUNNING
#   2. faceitclient.exe has its own connection to FACEIT's servers
#      (an ESTABLISHED TCP connection to anything that is not this machine)
#   3. no FACEIT AC working window open ("FACEIT AC", or anything saying it
#      is updating). Only required when this launch saw the anti-cheat start;
#      an AC that was already up and connected is ready as it is.
#
# All three are read without administrator rights.
AC_PROCESS = "faceitclient.exe"
# Not "FACEIT": that name is the kernel driver, which runs from boot and so
# says nothing about whether the anti-cheat has been started. Confirmed on the
# player's PC: FACEITService, demand-start, binary faceitservice.exe.
AC_SERVICES = ("FACEITService",)

_SERVICE_RUNNING = 4      # SERVICE_RUNNING, the same in every Windows language


def _service_state(name: str) -> Optional[int]:
    """The state of a Windows service, read without administrator rights.
    None when there is no such service (or this is not Windows)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.OpenSCManagerW.restype = wintypes.HANDLE
    advapi.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    advapi.OpenServiceW.restype = wintypes.HANDLE
    advapi.OpenServiceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
    advapi.CloseServiceHandle.argtypes = [wintypes.HANDLE]

    class STATUS(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("state", wintypes.DWORD),
                    ("accepted", wintypes.DWORD), ("exit", wintypes.DWORD),
                    ("specific", wintypes.DWORD), ("checkpoint", wintypes.DWORD),
                    ("hint", wintypes.DWORD)]

    advapi.QueryServiceStatus.argtypes = [wintypes.HANDLE, ctypes.POINTER(STATUS)]
    manager = advapi.OpenSCManagerW(None, None, 0x0001)        # CONNECT
    if not manager:
        return None
    try:
        service = advapi.OpenServiceW(manager, name, 0x0004)     # QUERY_STATUS
        if not service:
            return None
        try:
            status = STATUS()
            if not advapi.QueryServiceStatus(service, ctypes.byref(status)):
                return None
            return int(status.state)
        finally:
            advapi.CloseServiceHandle(service)
    finally:
        advapi.CloseServiceHandle(manager)


def ac_service_running() -> Optional[bool]:
    """True/False for the anti-cheat's service; None if no such service was
    found under any known name, in which case the process alone has to do."""
    seen = False
    for name in AC_SERVICES:
        state = _service_state(name)
        if state is None:
            continue
        seen = True
        if state == _SERVICE_RUNNING:
            return True
    return False if seen else None


def _pids(exe: str) -> List[int]:
    """Process ids with this image name (case-insensitive)."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class ENTRY(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ENTRY)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ENTRY)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)            # PROCESSES
    if not snap or snap == wintypes.HANDLE(-1).value:
        return []
    out: List[int] = []
    try:
        entry = ENTRY()
        entry.dwSize = ctypes.sizeof(ENTRY)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == exe.lower():
                out.append(int(entry.th32ProcessID))
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return out


def _remote_connections(pids: Iterable[int]) -> int:
    """ESTABLISHED TCP connections owned by these processes to anything that
    is not this machine. Read from Windows' own TCP table, no admin needed."""
    wanted = set(pids)
    if sys.platform != "win32" or not wanted:
        return 0
    import ctypes
    from ctypes import wintypes

    iphlp = ctypes.WinDLL("iphlpapi", use_last_error=True)
    iphlp.GetExtendedTcpTable.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                                          wintypes.BOOL, wintypes.ULONG,
                                          ctypes.c_int, wintypes.ULONG]
    ESTABLISHED = 5
    count = 0

    def table(family: int) -> bytes:
        size = wintypes.DWORD(0)
        iphlp.GetExtendedTcpTable(None, ctypes.byref(size), False, family, 5, 0)
        for _ in range(3):
            buf = ctypes.create_string_buffer(size.value or 4)
            if iphlp.GetExtendedTcpTable(buf, ctypes.byref(size), False, family, 5, 0) == 0:
                return buf.raw
        return b""

    import struct

    raw = table(2)                                   # IPv4, owner pid
    if len(raw) >= 4:
        rows = struct.unpack_from("<I", raw, 0)[0]
        for i in range(rows):
            off = 4 + i * 24
            if off + 24 > len(raw):
                break
            state, _la, _lp, remote, _rp, pid = struct.unpack_from("<IIIIII", raw, off)
            first = remote & 0xFF                    # network order: first octet
            if state == ESTABLISHED and pid in wanted and first not in (127, 0):
                count += 1
    raw = table(23)                                  # IPv6, owner pid
    if len(raw) >= 4:
        rows = struct.unpack_from("<I", raw, 0)[0]
        for i in range(rows):
            off = 4 + i * 56
            if off + 56 > len(raw):
                break
            remote = raw[off + 24:off + 40]
            state, pid = struct.unpack_from("<II", raw, off + 48)
            loop = remote == b"\0" * 15 + b"\1" or (
                remote[:12] == b"\0" * 10 + b"\xff\xff" and remote[12] == 127)
            if state == ESTABLISHED and pid in wanted and not loop and any(remote):
                count += 1
    return count


# Windows FACEIT AC shows while it is still working: the transient "FACEIT AC"
# window seen at startup, and anything announcing an update. Its main
# "FACEIT Anti-cheat" window is deliberately not here (see above).
_BUSY_TITLES = ("faceit ac",)
_BUSY_WORDS = ("updat", "download", "install")


def _is_busy_title(title: str) -> bool:
    text = (title or "").strip().lower()
    return text in _BUSY_TITLES or any(w in text for w in _BUSY_WORDS)


def _visible_windows(pids: Iterable[int]) -> int:
    """FACEIT AC's visible "still working" windows (see _BUSY_TITLES)."""
    wanted = set(pids)
    if sys.platform != "win32" or not wanted:
        return 0
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    found = [0]

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lp):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in wanted:
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                if _is_busy_title(buf.value):
                    found[0] += 1
        return True

    user32.EnumWindows(callback, 0)
    return found[0]


class AcReadiness:
    """Answers "is FACEIT AC ready for CS2 yet?" from what FACEIT AC itself
    shows -- see the notes above. No timers: on an update day it simply stays
    not-ready for longer.

    ``started_here`` is set by the launcher when this launch started the
    anti-cheat (or found it still starting); then its startup window must have
    closed as well.
    """

    def __init__(self, pids=None, service=None, online=None, windows=None):
        self._pids = pids or (lambda: _pids(AC_PROCESS))
        self._service = service or ac_service_running
        self._online = online or _remote_connections
        self._windows = windows or _visible_windows
        self.started_here = False
        self.last = ""           # what it is waiting on, for the status line

    def _state(self, need_window_closed: bool) -> bool:
        pids = self._pids()
        if not pids:
            self.last = "FACEIT AC is not running yet"
            return False
        if self._service() is False:
            self.last = "FACEIT AC's service is starting"
            return False
        if self._online(pids) <= 0:
            self.last = "FACEIT AC is connecting to FACEIT"
            return False
        if need_window_closed and self._windows(pids) > 0:
            self.last = "FACEIT AC is still starting (or updating)"
            return False
        self.last = "ready"
        return True

    def up_now(self) -> bool:
        """Already up before this launch touched it: running, service up,
        connected. Its window may be open -- the player may have opened it."""
        return self._state(need_window_closed=False)

    def __call__(self) -> bool:
        return self._state(need_window_closed=self.started_here)


# --- finding them -----------------------------------------------------------

def _known_places(kind: str) -> Iterable[Path]:
    app = APPS[kind]
    for env, sub in app["places"]:
        root = os.environ.get(env)
        if not root:
            continue
        for exe in app["exe_names"]:
            yield Path(root) / sub / exe


def _uninstall_entries() -> List[Dict[str, str]]:
    """DisplayName / InstallLocation / DisplayIcon of every installed program."""
    if sys.platform != "win32":
        return []
    import winreg

    out: List[Dict[str, str]] = []
    roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for hive, path in roots:
        try:
            parent = winreg.OpenKey(hive, path)
        except OSError:
            continue
        with parent:
            index = 0
            while True:
                try:
                    sub = winreg.EnumKey(parent, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(parent, sub) as key:
                        row = {}
                        for value in ("DisplayName", "InstallLocation", "DisplayIcon"):
                            try:
                                row[value] = str(winreg.QueryValueEx(key, value)[0] or "")
                            except OSError:
                                row[value] = ""
                except OSError:
                    continue
                if row.get("DisplayName"):
                    out.append(row)
    return out


def _from_uninstall(kind: str, entries: List[Dict[str, str]]) -> Optional[Path]:
    app = APPS[kind]
    for row in entries:
        if not app["display_match"](row["DisplayName"].strip().lower()):
            continue
        icon = row.get("DisplayIcon", "").split(",")[0].strip().strip('"')
        if icon.lower().endswith(".exe") and Path(icon).name.lower() in {
                n.lower() for n in app["exe_names"]} and Path(icon).is_file():
            return Path(icon)
        folder = row.get("InstallLocation", "").strip().strip('"')
        if folder:
            for exe in app["exe_names"]:
                if (Path(folder) / exe).is_file():
                    return Path(folder) / exe
    return None


def find(kind: str, entries: Optional[List[Dict[str, str]]] = None) -> Optional[Path]:
    """Where this one is installed, or None."""
    for candidate in _known_places(kind):
        if candidate.is_file():
            return candidate
    return _from_uninstall(kind, _uninstall_entries() if entries is None else entries)


# --- what the page shows ----------------------------------------------------

def _added(prefs_ui: Dict[str, Any], kind: str) -> Optional[Dict[str, Any]]:
    return next((c for c in companions.listed(prefs_ui)
                 if c.get("integration") == kind), None)


def survey(prefs_ui: Dict[str, Any]) -> Dict[str, Any]:
    """Both programs: installed where, running or not, and whether they are
    set to come up with the game."""
    entries = _uninstall_entries()
    out = {}
    for kind, app in APPS.items():
        added = _added(prefs_ui, kind)
        exe = Path(added["exe"]) if added else find(kind, entries)
        out[kind] = {
            "name": app["name"],
            "exe": str(exe) if exe else "",
            "installed": bool(exe and exe.is_file()),
            "running": bool(exe) and companions.running(exe.name),
            "with_game": bool(added and added["with_game"]),
        }
    return out


# --- settings ---------------------------------------------------------------

def set_with_game(prefs_ui: Dict[str, Any], kind: str, on: bool,
                  exe: str = "") -> Dict[str, Any]:
    """Turn 'start with the game' on or off. Returns the preferences change.

    Stored as an ordinary companion so the launcher starts it the same way it
    starts everything else; the integration tag is what marks it as FACEIT.
    """
    if kind not in APPS:
        raise companions.CompanionError(f"unknown FACEIT program: {kind}")
    held = companions.listed(prefs_ui)
    current = next((c for c in held if c.get("integration") == kind), None)
    if current:
        current["with_game"] = bool(on)
        if exe:
            current["exe"] = exe
        return {"companions": held}
    if not on and not exe:
        return {"companions": held}

    path = Path(exe) if exe else find(kind)
    if not path or not path.is_file():
        raise companions.CompanionError(f"{APPS[kind]['name']} is not installed")
    if len(held) >= companions.MAX_COMPANIONS:
        raise companions.CompanionError("there is no room for another companion")
    held.append({"id": kind, "name": APPS[kind]["name"], "exe": str(path),
                 "args": "", "with_game": bool(on), "integration": kind})
    return {"companions": held}


def launch(prefs_ui: Dict[str, Any], kind: str) -> Dict[str, Any]:
    """Start one of them now. Never raises."""
    if kind not in APPS:
        return {"ok": False, "error": f"unknown FACEIT program: {kind}"}
    added = _added(prefs_ui, kind)
    exe = Path(added["exe"]) if added else find(kind)
    if not exe:
        return {"ok": False, "error": f"{APPS[kind]['name']} is not installed"}
    return companions.start({"name": APPS[kind]["name"], "exe": str(exe), "args": ""})
