"""Record what Windows and CS2 show when a match is found. Test tool only.

Run it, queue in CS2 (and/or FACEIT), tab out to the desktop, and wait for a
match to pop. Press Ctrl+C after. Everything goes to matchfound_probe.log
next to this script. It only listens; it touches no game or FACEIT files and
sends no input anywhere.

It records:
  * every taskbar flash / window activation / title change, with the program
    that owns the window (Windows shell hook, the same thing the taskbar uses)
  * every new line CS2 writes to game/csgo/console.log, if CS2 was started
    with -condebug
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LOG = Path(__file__).with_name("matchfound_probe.log")
_lock = threading.Lock()


def log(kind: str, text: str) -> None:
    line = f"{time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d}  {kind:<8} {text}"
    with _lock:
        print(line, flush=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


# --- console.log ------------------------------------------------------------

def tail_console() -> None:
    try:
        from cs2cfg import steam

        install = steam.find_cs2_install(steam.find_steam_root())
    except Exception as exc:
        log("console", f"could not find CS2: {exc}")
        return
    if not install:
        log("console", "CS2 install not found")
        return
    path = Path(install) / "game" / "csgo" / "console.log"
    log("console", f"watching {path} (needs -condebug)")
    pos = path.stat().st_size if path.is_file() else 0
    while True:
        try:
            if path.is_file():
                size = path.stat().st_size
                if size < pos:
                    pos = 0
                if size > pos:
                    with path.open("rb") as fh:
                        fh.seek(pos)
                        chunk = fh.read(size - pos)
                    pos = size
                    for raw in chunk.decode("utf-8", "replace").splitlines():
                        if raw.strip():
                            log("console", raw.rstrip())
        except OSError as exc:
            log("console", f"read error: {exc}")
        time.sleep(0.25)


# --- shell hook -------------------------------------------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                  wintypes.LPARAM]
user32.CreateWindowExW.restype = wintypes.HWND
# Declared in full: on 64-bit Windows an undeclared HWND is cut to 32 bits and
# CreateWindowExW overflows (what the first run on a real PC hit).
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.RegisterShellHookWindow.argtypes = [wintypes.HWND]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


NAMES = {1: "created", 2: "destroyed", 4: "activated", 6: "redraw",
         0x8004: "activated", 0x8006: "FLASH", 13: "monitor", 16: "endtask"}
WANTED_PROCS = {"cs2.exe", "faceit.exe", "faceitclient.exe", "steam.exe",
                "steamwebhelper.exe"}


def describe(hwnd: int) -> tuple:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        from cs2cfg.window import _process_name

        proc = _process_name(pid.value)
    except Exception:
        proc = f"pid {pid.value}"
    return proc, buf.value


def main() -> None:
    log("start", "probe running; queue now, tab out, wait for the match. Ctrl+C to stop.")
    threading.Thread(target=tail_console, daemon=True).start()

    shellhook = user32.RegisterWindowMessageW("SHELLHOOK")

    @WNDPROC
    def proc(hwnd, msg, wparam, lparam):
        if msg == shellhook:
            code = int(wparam)
            name = NAMES.get(code)
            if name:
                target = int(lparam or 0)
                exe, title = describe(target) if target else ("", "")
                # Title changes from every app are noise; keep game/FACEIT/Steam.
                if name != "redraw" or exe.lower() in WANTED_PROCS:
                    log(name, f"{exe} | {title!r}")
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    wc = WNDCLASSW()
    wc.lpfnWndProc = proc
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = "cs2cfg_matchfound_probe"
    user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "probe", 0, 0, 0, 0, 0,
                                  None, None, wc.hInstance, None)
    if not user32.RegisterShellHookWindow(hwnd):
        log("error", "RegisterShellHookWindow failed")
        return

    # PeekMessage rather than GetMessage, so Ctrl+C is not stuck behind a
    # blocking native call.
    msg = wintypes.MSG()
    try:
        while True:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.05)
    except KeyboardInterrupt:
        log("stop", "probe stopped")


if __name__ == "__main__":
    main()
