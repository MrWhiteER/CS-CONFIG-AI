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
    if not on:
        return {"companions": held}

    path = Path(exe) if exe else find(kind)
    if not path or not path.is_file():
        raise companions.CompanionError(f"{APPS[kind]['name']} is not installed")
    if len(held) >= companions.MAX_COMPANIONS:
        raise companions.CompanionError("there is no room for another companion")
    held.append({"id": kind, "name": APPS[kind]["name"], "exe": str(path),
                 "args": "", "with_game": True, "integration": kind})
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
