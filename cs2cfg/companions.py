"""The other applications somebody runs alongside the game.

Crosshair X was the first and was written into this project by name. That does
not generalise: the next one is a clip recorder, the one after that is a voice
changer or an overlay or a macro tool, and none of them want the same things.
So the knowledge of *a particular* application lives in an integration, and
everything here is about applications in general -- where it is, whether it is
up, and starting it when the game starts.

What this does
--------------

Finds an executable, says whether it is running, and starts it. That is the
whole of the general case, and it works for anything.

What this does not do, and why
------------------------------

It does not reach into another application's settings. Those files belong to
the program that wrote them, they are usually open while it runs, and most
rewrite themselves on exit -- so a change made from out here is either ignored
or lost, and either way somebody's configuration has been touched without
their saying so. Crosshair X is the example in front of us: its preferences
are plain JSON and perfectly readable, and writing to them would still be
wrong.

So an integration may *read* another application's state to explain what it
finds, and may use the doors that application leaves open on purpose -- a
command-line flag, a documented hotkey, a folder it publishes. Nothing else.
That is a real limit and it is worth saying out loud: "quick settings" for an
arbitrary program is not a thing that can be built generically, because there
is nothing generic to talk to. What can be built is one integration at a time,
each going exactly as far as that program allows.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_CREATE_NO_WINDOW = 0x08000000

# Process checks spawn tasklist, and the page asks often.
_SEEN: Dict[str, Any] = {"at": 0.0, "names": frozenset()}
RUNNING_TTL = 4.0


# --- what is running --------------------------------------------------------

def _all_running() -> frozenset:
    """Every process image name, lowercased. One call, not one per companion.

    The earlier code ran tasklist once per application it wanted to know
    about. With one companion that is invisible; with eight it is eight
    processes spawned every four seconds.
    """
    now = time.time()
    if now - _SEEN["at"] < RUNNING_TTL:
        return _SEEN["names"]
    names: set = set()
    if sys.platform == "win32":
        try:
            done = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=15,
                creationflags=_CREATE_NO_WINDOW,
            )
            for line in (done.stdout or "").splitlines():
                if line.startswith('"'):
                    names.add(line.split('","')[0].strip('"').lower())
        except (OSError, subprocess.SubprocessError):
            return _SEEN["names"]
    _SEEN["at"], _SEEN["names"] = time.time(), frozenset(names)
    return _SEEN["names"]


def running(exe_name: str) -> bool:
    """Whether a process with this image name is up."""
    if not exe_name:
        return False
    return Path(exe_name).name.lower() in _all_running()


def forget_running() -> None:
    """Drop the cache, for when something has just been started."""
    _SEEN["at"] = 0.0


# --- the list ---------------------------------------------------------------

def _clean(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One stored companion, with anything unusable thrown away.

    The list comes out of preferences, which are a file somebody can edit and
    which survive upgrades, so nothing in it can be assumed.
    """
    if not isinstance(entry, dict):
        return None
    exe = str(entry.get("exe") or "").strip()
    if not exe:
        return None
    name = str(entry.get("name") or Path(exe).stem).strip() or Path(exe).stem
    return {
        "id": str(entry.get("id") or "").strip() or Path(exe).stem.lower(),
        "name": name[:40],
        "exe": exe,
        "args": str(entry.get("args") or "").strip(),
        # Started when the game is launched, if it is not already up.
        "with_game": bool(entry.get("with_game", True)),
        # Which integration knows about this one, if any.
        "integration": str(entry.get("integration") or "").strip(),
    }


def listed(prefs_ui: Dict[str, Any]) -> List[Dict[str, Any]]:
    held = prefs_ui.get("companions")
    if not isinstance(held, list):
        return []
    out = []
    for entry in held:
        cleaned = _clean(entry)
        if cleaned:
            out.append(cleaned)
    return out


# --- adding, removing, and the one setting that is generic ------------------
#
# "Twenty quick tools per companion" is not buildable generically -- said
# plainly in the module's own docstring, and still true. What every companion
# shares, whatever it turns out to do, is a path, a name, and whether it comes
# up with the game. That is the whole of what lives here.

MAX_COMPANIONS = 20


class CompanionError(Exception):
    """The companion cannot be added, or there is no such one to change."""


def add(ui: Dict[str, Any], exe: str, name: str = "", args: str = "",
       with_game: bool = True) -> Dict[str, Any]:
    """Register a companion. Returns the preferences change to write."""
    exe = str(exe or "").strip()
    if not exe:
        raise CompanionError("choose a program first")
    if not Path(exe).is_file():
        raise CompanionError(f"{exe} was not found")

    held = listed(ui)
    if len(held) >= MAX_COMPANIONS:
        raise CompanionError(f"there is room for {MAX_COMPANIONS} companions; "
                             "remove one first")
    companion_id = Path(exe).stem.lower()
    if any(c["id"] == companion_id for c in held):
        raise CompanionError(f"{Path(exe).stem} is already added")

    cleaned = _clean({"id": companion_id, "name": name or Path(exe).stem,
                      "exe": exe, "args": args, "with_game": with_game})
    held.append(cleaned)
    return {"companions": held}


def remove_one(ui: Dict[str, Any], companion_id: str) -> Dict[str, Any]:
    companion_id = str(companion_id or "").strip()
    held = listed(ui)
    kept = [c for c in held if c["id"] != companion_id]
    if len(kept) == len(held):
        raise CompanionError("that companion was already removed")
    return {"companions": kept}


def set_with_game(ui: Dict[str, Any], companion_id: str, with_game: bool) -> Dict[str, Any]:
    """Whether this one is started automatically when the game is."""
    companion_id = str(companion_id or "").strip()
    held = listed(ui)
    found = False
    for entry in held:
        if entry["id"] == companion_id:
            entry["with_game"] = bool(with_game)
            found = True
    if not found:
        raise CompanionError("that companion was not found")
    return {"companions": held}


def describe(entry: Dict[str, Any]) -> Dict[str, Any]:
    """A companion plus the things only this machine can answer."""
    exe = Path(entry["exe"])
    return {
        **entry,
        "installed": exe.is_file(),
        "running": running(exe.name),
        "icon": icon_name(entry["exe"]),
    }


def survey(prefs_ui: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Everything the rail needs, in one pass over one process listing."""
    return [describe(e) for e in listed(prefs_ui)]


# --- starting ---------------------------------------------------------------

def start(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Start a companion, unless it is already up.

    Never raises: a clip recorder that will not start is not a reason to stop
    somebody launching their game.
    """
    exe = Path(entry.get("exe") or "")
    if not exe.is_file():
        return {"ok": False, "error": f"{entry.get('name') or exe.name} is not where it was"}
    if running(exe.name):
        return {"ok": True, "already": True,
                "detail": f"{entry.get('name') or exe.stem} is already running"}

    argv = [str(exe)]
    if entry.get("args"):
        import shlex

        argv += shlex.split(entry["args"])
    try:
        subprocess.Popen(argv, cwd=str(exe.parent),
                         creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {"ok": False, "error": f"could not start {exe.name}: {exc}"}
    forget_running()
    return {"ok": True, "already": False,
            "detail": f"Started {entry.get('name') or exe.stem}"}


def start_all(prefs_ui: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Everything marked to come up with the game. Order is not significant,
    and one failing does not stop the next."""
    out = []
    for entry in listed(prefs_ui):
        if not entry["with_game"]:
            continue
        result = start(entry)
        out.append({"name": entry["name"], **result})
    return out


# --- icons ------------------------------------------------------------------

def icon_name(exe: str) -> str:
    """A stable filename for this executable's extracted icon."""
    import hashlib

    return hashlib.sha256(str(exe).lower().encode("utf-8")).hexdigest()[:16] + ".png"


def icon_path(exe: str) -> Path:
    from .paths import user_data_dir

    return user_data_dir() / "companions" / icon_name(exe)


def extract_icon(exe: str, size: int = 32) -> Optional[Path]:
    """Pull the application's own icon out of its executable.

    The rail shows the real icon rather than a letter in a circle, because the
    whole point of a companion being in the rail is recognising it without
    reading. Windows keeps it in the binary, so this asks Windows.

    Cached: the extraction is cheap but not free, and an executable's icon
    changes about as often as the executable does.
    """
    if sys.platform != "win32":
        return None
    target = icon_path(exe)
    source = Path(exe)
    if not source.is_file():
        return None
    try:
        if target.is_file() and target.stat().st_mtime >= source.stat().st_mtime:
            return target
    except OSError:
        pass

    try:
        rows = _icon_pixels(str(source), size)
    except Exception:
        return None
    if not rows:
        return None

    try:
        from .appicon import to_png

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(to_png(rows))
    except OSError:
        return None
    return target


def _icon_pixels(exe: str, size: int):
    """The executable's icon as RGBA rows, or None.

    Drawn into a 32-bit top-down DIB and read straight back out. Windows hands
    icons back as a pair of bitmaps -- colour and mask -- and the colour one
    already carries an alpha channel for anything modern, so drawing onto a
    cleared surface and taking the result is both simpler and more correct
    than trying to combine the two by hand.
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    user32.LoadImageW.restype = wintypes.HANDLE
    shell32.ExtractIconExW.restype = ctypes.c_uint
    shell32.ExtractIconExW.argtypes = [wintypes.LPCWSTR, ctypes.c_int,
                                       ctypes.POINTER(wintypes.HICON),
                                       ctypes.POINTER(wintypes.HICON), ctypes.c_uint]
    # Every handle declared, both ways. ctypes assumes a 32-bit int for
    # anything undeclared and a GDI handle on 64-bit Windows is 64 bits, so an
    # undeclared return truncates silently and an undeclared argument raises
    # outright -- which is how this was found, on the first executable tried.
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_void_p),
                                       wintypes.HANDLE, wintypes.DWORD]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int,
                                  wintypes.HICON, ctypes.c_int, ctypes.c_int,
                                  wintypes.UINT, wintypes.HANDLE, wintypes.UINT]
    user32.DestroyIcon.argtypes = [wintypes.HICON]

    big = (wintypes.HICON * 1)()
    small = (wintypes.HICON * 1)()
    if shell32.ExtractIconExW(exe, 0, big, small, 1) == 0 or not big[0]:
        return None
    icon = big[0]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    head = BITMAPINFOHEADER()
    head.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    head.biWidth = size
    head.biHeight = -size          # negative: top-down, so rows come out in order
    head.biPlanes = 1
    head.biBitCount = 32
    head.biCompression = 0

    screen = user32.GetDC(None)
    dc = gdi32.CreateCompatibleDC(screen)
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(dc, ctypes.byref(head), 0,
                                    ctypes.byref(bits), None, 0)
    try:
        if not bitmap or not bits:
            return None
        gdi32.SelectObject(dc, bitmap)
        # DrawIconEx with a cleared surface keeps the icon's own alpha.
        if not user32.DrawIconEx(dc, 0, 0, icon, size, size, 0, None, 0x0003):
            return None

        raw = ctypes.string_at(bits, size * size * 4)
        rows = []
        for y in range(size):
            row = []
            for x in range(size):
                i = (y * size + x) * 4
                b, g, r, a = raw[i], raw[i + 1], raw[i + 2], raw[i + 3]
                row.append((r, g, b, a))
            rows.append(row)
        # An icon with no alpha anywhere came back fully transparent, which
        # would show as nothing at all. Treat it as opaque instead.
        if not any(px[3] for row in rows for px in row):
            rows = [[(r, g, b, 255) for (r, g, b, _a) in row] for row in rows]
        return rows
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(dc)
        user32.ReleaseDC(None, screen)
        user32.DestroyIcon(big[0])
        if small[0]:
            user32.DestroyIcon(small[0])
