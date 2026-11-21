"""Give the PC back the way it was whenever the app is not running (Edy, Nov 2026).

The app changes a handful of things outside CS2's own config files: Steam's
launch options, CS2's window mode (the borderless window that makes Alt+Tab
instant), Windows' per-game graphics settings, fullscreen optimisations, the
power plan, a Windows Security exclusion, NVIDIA's screen scaling and the
refresh rate. Those used to stay changed for good -- after the app was closed
and even after it was uninstalled.

The rule now: **those settings are only in place while the app is running.**

* Every change the app makes goes through :func:`note`, which writes down what
  the setting was *before* the app first touched it (the original) and what the
  app set (ours). A first-run snapshot of the whole lot is kept as well.
* When the app stops -- Quit, a crash, Task Manager, a Windows restart, an
  update or an uninstall -- every setting still holding *ours* is put back to
  the original. A setting the player changed themselves since is left alone.
* The next time the app starts it puts *ours* back, again only where the
  setting still holds the original.

What triggers the put-back:

* a small watcher (``cs2cfg pc-guard``) started with the app, which waits on the
  app's process and runs the put-back the moment it is gone, however it ended;
* a Windows "run once at next sign-in" entry, written while the app's settings
  are in place, for a PC that was shut down or restarted with the app open;
* the uninstaller, through ``cs2cfg uninstall-cleanup``.

Two settings live in files their own program rewrites on exit: Steam rewrites
``localconfig.vdf`` (launch options) when Steam closes, and CS2 rewrites
``cs2_video.txt`` (window mode) when CS2 closes. Those are put back once that
program is closed, by a small script that waits for it (see
:func:`_write_file_waiter`), because nothing may be left running out of the
app's own folder: the updater waits for every such process before it swaps
files.

Nothing here prompts, and nothing here touches the configs inside CS2's cfg
folder or any picture setting other than the window mode.
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

STORE = "pc-originals.json"
WAITER_DIR_NAME = "cs2-autoconfig-restore"
UPDATING_MARK = "pc-updating.flag"
RUN_ONCE_KEY = r"Software\Microsoft\Windows\CurrentVersion\RunOnce"
RUN_ONCE_NAME = "CS2 Launcher - put PC settings back"
WAITER_RUN_ONCE_NAME = "CS2 Launcher - put Steam settings back"
_CREATE_NO_WINDOW = 0x08000000
_DETACHED = 0x00000008 | 0x00000200  # detached, new process group
_BREAKAWAY = 0x01000000                # outlive a job object the app was started in

# The window-mode keys of cs2_video.txt that the launcher sets for the
# borderless window. Every other picture setting is the player's and stays.
WINDOW_KEYS = ("setting.fullscreen", "setting.nowindowborder",
               "setting.fullscreen_min_on_focus_loss", "setting.monitor_index")

KIND_LABELS = {
    "launch_options": "Steam launch options for CS2",
    "window_mode": "CS2 window mode",
    "win_graphics": "Windows graphics setting for CS2",
    "fullscreen_opt": "Windows fullscreen optimisations for CS2",
    "power_plan": "Windows power plan",
    "defender": "Windows Security scan of the CS2 folder",
    "scaling": "NVIDIA screen scaling",
    "refresh": "Screen refresh rate",
}

WINDOW_KEY_LABELS = {
    "setting.fullscreen": "CS2 fullscreen or window",
    "setting.nowindowborder": "CS2 window border",
    "setting.fullscreen_min_on_focus_loss": "CS2 minimising on Alt+Tab",
    "setting.monitor_index": "Screen CS2 opens on",
}

_enabled = False
_lock = threading.RLock()
_local = threading.local()


# ---------------------------------------------------------------------------
# Switches and storage
# ---------------------------------------------------------------------------

def enable(on: bool = True) -> None:
    """Turn recording on for this process.

    Off by default so a test suite that drives real writers never files its
    throwaway changes as the player's own settings. The app and the shipped
    command line turn it on.
    """
    global _enabled
    _enabled = bool(on)


def enabled() -> bool:
    return _enabled


def store_path() -> Path:
    from .paths import user_data_dir

    return user_data_dir() / STORE


@contextlib.contextmanager
def restoring() -> Iterator[None]:
    """Writes made inside this block are the put-back itself, not changes to note."""
    previous = getattr(_local, "quiet", False)
    _local.quiet = True
    try:
        yield
    finally:
        _local.quiet = previous


def _load() -> Dict[str, Any]:
    try:
        data = json.loads(store_path().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("parts"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"version": 1, "parts": {}}


def _save(data: Dict[str, Any]) -> None:
    path = store_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        pass


def _key(kind: str, ident: str) -> str:
    return f"{kind}|{ident}"


# ---------------------------------------------------------------------------
# Recording a change
# ---------------------------------------------------------------------------

def note(kind: str, ident: str, before: Any, after: Any, reapply: bool = True) -> None:
    """Record that the app just changed a setting from ``before`` to ``after``.

    The first change keeps ``before`` as the original; later changes only move
    what the app wants. A change that lands back on the original drops the
    record, because there is nothing left to put back. Never raises.

    ``reapply`` is False for a change that only lasts one game session (the
    launcher's own scaling), which is put back but never set again at start.
    """
    if not _enabled or getattr(_local, "quiet", False):
        return
    try:
        with _lock:
            data = _load()
            parts = data["parts"]
            key = _key(kind, str(ident))
            part = parts.get(key)
            if part is None or part.get("state") != "ours":
                original = before
            else:
                original = part.get("original")
            if after == original:
                parts.pop(key, None)
            else:
                parts[key] = {"kind": kind, "ident": str(ident), "original": original,
                              "ours": after, "state": "ours", "reapply": bool(reapply),
                              "at": time.time()}
            _save(data)
        if any(p.get("state") == "ours" for p in parts.values()):
            arm_next_sign_in()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Reading and writing each kind of setting
# ---------------------------------------------------------------------------

class Waiting(Exception):
    """The setting cannot be written right now; ``args[0]`` says why, in plain words."""


def _steam_user(ident: str):
    from . import steam

    path = Path(ident)
    return steam.SteamUser(account_id=path.name, path=path)


def _reg_read(subkey: str, name: str) -> Optional[str]:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as key:
            value, _ = winreg.QueryValueEx(key, name)
        return str(value)
    except FileNotFoundError:
        return None


def _reg_write(subkey: str, name: str, value: Optional[str]) -> None:
    import winreg

    if value is None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass
        return
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _split_window_ident(ident: str) -> Tuple[str, str]:
    path, _, setting = ident.rpartition("|")
    return path, setting


def _read(kind: str, ident: str) -> Any:
    from . import steam

    if kind == "launch_options":
        return steam.read_launch_options(_steam_user(ident))
    if kind == "window_mode":
        user_path, setting = _split_window_ident(ident)
        return steam.read_video_cfg(_steam_user(user_path)).get(setting)
    if kind == "win_graphics":
        from .wingraphics import KEY
        return _reg_read(KEY, ident)
    if kind == "fullscreen_opt":
        from .quickfix import FS_OPT_KEY
        return _reg_read(FS_OPT_KEY, ident)
    if kind == "power_plan":
        from .quickfix import _active_scheme_guid
        return _active_scheme_guid()
    if kind == "defender":
        from .quickfix import _defender_exclusions
        return any(ident.lower() == p.lower() for p in _defender_exclusions())
    if kind == "scaling":
        from . import scaling
        report = scaling.read()
        if not report.available:
            raise RuntimeError(report.reason or "NVIDIA driver not available")
        found = next((s for s in report.screens if s.display_id == int(ident)), None)
        if found is None:
            raise RuntimeError("that screen is not connected")
        return found.scaling
    if kind == "refresh":
        from . import displays
        screen = displays.find(ident)
        if screen is None or screen.current is None:
            raise RuntimeError("that screen is not connected")
        return [screen.current.width, screen.current.height, screen.current.refresh]
    raise RuntimeError(f"unknown setting {kind}")


def _write(kind: str, ident: str, value: Any, *, live_ok: bool, persist: bool) -> None:
    from . import steam

    if kind == "launch_options":
        if steam.steam_running():
            raise Waiting("waiting for Steam to close")
        steam.write_launch_options(_steam_user(ident), str(value or ""))
        return
    if kind == "window_mode":
        if value is None:
            return       # the key did not exist before; CS2 uses its own default
        if steam.cs2_running():
            raise Waiting("waiting for CS2 to close")
        user_path, setting = _split_window_ident(ident)
        steam.write_video_cfg(_steam_user(user_path), {setting: value})
        return
    if kind == "win_graphics":
        from .wingraphics import KEY
        _reg_write(KEY, ident, value)
        return
    if kind == "fullscreen_opt":
        from .quickfix import FS_OPT_KEY
        _reg_write(FS_OPT_KEY, ident, value)
        return
    if kind == "power_plan":
        _set_power_plan(str(value))
        return
    if kind == "defender":
        _set_defender(ident, bool(value))
        return
    if kind == "scaling":
        if not live_ok and steam.cs2_running():
            raise Waiting("waiting for CS2 to close")
        from . import scaling
        result = scaling.set_scaling(int(ident), int(value), apply=True, persist=persist)
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "the driver refused")
        return
    if kind == "refresh":
        from . import displays
        result = displays.set_refresh(ident, int(value[2]), apply=True, force=live_ok)
        if result.get("game_running"):
            raise Waiting("waiting for CS2 to close")
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "Windows refused")
        return
    raise RuntimeError(f"unknown setting {kind}")


def _set_power_plan(guid: str) -> None:
    """Switch plans with no prompt: plainly, then through the one-time helper."""
    from . import quickfix

    if quickfix._powercfg(["/setactive", guid])["ok"]:
        return
    result = quickfix._helper("power.set", {"guid": guid})
    if result is None:
        raise RuntimeError("Windows needs the one-time setup permission to change the power plan")
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "Windows would not switch the power plan")


def _set_defender(install: str, on: bool) -> None:
    from . import quickfix

    program = str(Path(install) / "game" / "bin" / "win64" / "cs2.exe")
    result = quickfix._helper("defender.cs2", {"program": program, "on": on})
    if result is None:
        raise RuntimeError("needs the one-time setup permission")
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "Windows Security refused")


def _current(part: Dict[str, Any], assume: str) -> Any:
    """The setting's value now.

    Windows only shows Security exclusions to an administrator, so that one is
    taken from the record instead: the helper's add and remove are both safe
    to repeat.
    """
    if part["kind"] == "defender":
        return part.get(assume)
    return _read(part["kind"], part["ident"])


MAXPING = "+mm_dedicated_search_maxping"


def restore_target(part: Dict[str, Any], uninstalling: bool = False) -> Any:
    """What a setting goes back to.

    The original, with one exception: a region lock stays on while the app is
    closed (it is a choice the player makes and undoes in the app, and the
    uninstaller removes it), so the match-search ping limit the lock added to
    the launch options stays with it. Uninstalling removes both.
    """
    original = part.get("original")
    if part.get("kind") != "launch_options" or uninstalling:
        return original
    have = _option_groups(str(original or ""))
    if any(g.split()[0].lower() == MAXPING for g in have):
        return original
    keep = [g for g in _option_groups(str(part.get("ours") or ""))
            if g.split()[0].lower() == MAXPING]
    return " ".join(have + keep) if keep else original


def _refresh_matches(kind: str, a: Any, b: Any) -> bool:
    if kind == "refresh":
        # Same resolution and same rate; a changed resolution means somebody
        # else has moved the screen since, which is theirs to keep.
        return list(a or []) == list(b or [])
    return a == b


# ---------------------------------------------------------------------------
# Putting back and setting again
# ---------------------------------------------------------------------------

def label(part: Dict[str, Any]) -> str:
    if part.get("kind") == "window_mode":
        _, setting = _split_window_ident(part.get("ident", ""))
        return WINDOW_KEY_LABELS.get(setting, KIND_LABELS["window_mode"])
    return KIND_LABELS.get(part.get("kind"), "A PC setting")


def restore_all(live_ok: bool = False) -> Dict[str, Any]:
    """Put every setting still holding the app's value back to the original.

    ``live_ok`` lets screen settings change while CS2 is running (the
    uninstaller uses it: there is no later to wait for). Returns a plain list
    of what happened per setting, and ``waiting`` for those that have to wait
    for Steam or CS2 to close.
    """
    done: List[Dict[str, Any]] = []
    with _lock, restoring():
        data = _load()
        parts = data["parts"]
        for key in list(parts):
            part = parts[key]
            if part.get("state") != "ours":
                continue
            kind, ident = part["kind"], part["ident"]
            entry = {"key": key, "label": label(part)}
            try:
                current = _current(part, assume="ours")
                target = restore_target(part, live_ok)
                if _refresh_matches(kind, current, part.get("ours")):
                    _write(kind, ident, target, live_ok=live_ok,
                           persist=bool(part.get("reapply")))
                    entry.update(result="restored", text="Put back to how it was")
                elif _refresh_matches(kind, current, target) or \
                        _refresh_matches(kind, current, part.get("original")):
                    entry.update(result="restored", text="Already how it was")
                else:
                    parts.pop(key, None)
                    entry.update(result="left", text="You changed it yourself, so it was left as you set it")
                    done.append(entry)
                    continue
                if part.get("reapply"):
                    part["state"] = "original"
                else:
                    parts.pop(key, None)
            except Waiting as wait:
                entry.update(result="waiting", text=_plain_error(wait))
            except Exception as exc:
                entry.update(result="failed", text=_plain_error(exc))
            done.append(entry)
        data["restored_at"] = time.time()
        _save(data)

    # The desktop resolution the launcher narrows for a stretched game keeps
    # its own record (deskmode). Gave it back only while the game is closed.
    try:
        from . import deskmode, steam
        if deskmode.outstanding() is not None:
            if live_ok or not steam.cs2_running():
                result = deskmode.restore()
                done.append({"key": "desktop", "label": "Screen resolution",
                             "result": "restored" if result.get("ok") else "failed",
                             "text": "Put back to how it was" if result.get("ok")
                             else _plain_error(result.get("error"))})
            else:
                done.append({"key": "desktop", "label": "Screen resolution",
                             "result": "waiting", "text": "Waiting for CS2 to close"})
    except Exception:
        pass

    waiting = [d for d in done if d["result"] == "waiting"]
    if not any(p.get("state") == "ours" for p in _load()["parts"].values()) and not waiting:
        disarm_next_sign_in()
    return {"ok": not any(d["result"] == "failed" for d in done),
            "items": done, "waiting": bool(waiting)}


def reapply_all(keys: Optional[List[str]] = None) -> Dict[str, Any]:
    """Set the app's values again, where the setting still holds the original."""
    done: List[Dict[str, Any]] = []
    with _lock, restoring():
        data = _load()
        parts = data["parts"]
        for key in list(parts):
            part = parts[key]
            if keys is not None and key not in keys:
                continue
            if not part.get("reapply"):
                continue
            kind, ident = part["kind"], part["ident"]
            entry = {"key": key, "label": label(part)}
            try:
                current = _current(part, assume="original")
                if _refresh_matches(kind, current, part.get("original")) or \
                        _refresh_matches(kind, current, restore_target(part, False)):
                    _write(kind, ident, part.get("ours"), live_ok=False, persist=True)
                    part["state"] = "ours"
                    entry.update(result="applied", text="The app's setting is on again")
                elif _refresh_matches(kind, current, part.get("ours")):
                    part["state"] = "ours"
                    entry.update(result="applied", text="The app's setting is on")
                else:
                    parts.pop(key, None)
                    entry.update(result="left", text="You changed it while the app was closed, so it was left as you set it")
            except Waiting as wait:
                entry.update(result="waiting", text=_plain_error(wait))
            except Exception as exc:
                entry.update(result="failed", text=_plain_error(exc))
            done.append(entry)
        _save(data)
    if any(p.get("state") == "ours" for p in _load()["parts"].values()):
        arm_next_sign_in()
    return {"ok": not any(d["result"] == "failed" for d in done), "items": done,
            "waiting": [d["key"] for d in done if d["result"] == "waiting"]}


def _plain_error(exc: Any) -> str:
    text = str(exc or "").strip()
    if not text:
        return "It could not be changed"
    return text[0].upper() + text[1:]


def status() -> Dict[str, Any]:
    """What the Settings page shows: every setting the app has changed."""
    data = _load()
    items = []
    for key, part in sorted(data["parts"].items()):
        items.append({
            "key": key,
            "label": label(part),
            "on": part.get("state") == "ours",
            "text": ("The app's setting is on. It goes back when you quit the app."
                     if part.get("state") == "ours" else
                     "Back to your own setting. The app sets it again when it starts."),
        })
    return {"ok": True, "items": items,
            "snapshot_taken": bool(data.get("first_run")),
            "snapshot_at": (data.get("first_run") or {}).get("at")}


# ---------------------------------------------------------------------------
# First-run snapshot
# ---------------------------------------------------------------------------

def ensure_snapshot(cs2_install: Optional[Path] = None) -> bool:
    """Write down how this PC is set up, once, the first time the app runs.

    This is the backup Edy asked for. The put-back itself works from the value
    each setting had right before the app's first change, which is the same
    thing on a fresh install and more accurate if the player changed something
    in between.
    """
    with _lock:
        data = _load()
        if data.get("first_run"):
            return False
    snap: Dict[str, Any] = {"at": time.time()}
    with contextlib.suppress(Exception):
        from . import steam
        root = steam.find_steam_root()
        for user in steam.list_users(root):
            snap.setdefault("launch_options", {})[str(user.path)] = steam.read_launch_options(user)
            video = steam.read_video_cfg(user)
            snap.setdefault("window_mode", {})[str(user.path)] = {k: video.get(k) for k in WINDOW_KEYS}
        if cs2_install is None:
            cs2_install = steam.find_cs2_install(root)
    if sys.platform == "win32":
        with contextlib.suppress(Exception):
            from . import wingraphics, quickfix
            exe = wingraphics.exe_path(cs2_install)
            if exe is not None:
                snap["win_graphics"] = {str(exe): _reg_read(wingraphics.KEY, str(exe))}
                snap["fullscreen_opt"] = {str(exe): _reg_read(quickfix.FS_OPT_KEY, str(exe))}
        with contextlib.suppress(Exception):
            from . import quickfix
            snap["power_plan"] = quickfix._active_scheme_guid()
        with contextlib.suppress(Exception):
            from . import scaling
            report = scaling.read()
            if report.available:
                snap["scaling"] = {str(s.display_id): s.scaling for s in report.screens}
        with contextlib.suppress(Exception):
            from . import displays
            snap["refresh"] = {d.device: [d.current.width, d.current.height, d.current.refresh]
                               for d in displays.list_displays() if d.current}
    with _lock:
        data = _load()
        if not data.get("first_run"):
            data["first_run"] = snap
            _save(data)
    return True


# ---------------------------------------------------------------------------
# Windows plumbing: next-sign-in safety net, the watcher, the file waiter
# ---------------------------------------------------------------------------

def _cli_command() -> Optional[List[str]]:
    """How to start this program's command-line side, or None if it cannot be."""
    from .paths import app_dir, is_frozen

    if is_frozen():
        # The windowed executable, not cs2cfg.exe: the console one would put a
        # black window on screen for as long as the watcher runs.
        exe = app_dir() / "CS2 Launcher.exe"
        return [str(exe)] if exe.is_file() else None
    return [sys.executable, "-m", "cs2cfg"]


def _quote(parts: List[str]) -> str:
    return subprocess.list2cmdline(parts)


def arm_next_sign_in() -> None:
    """If Windows shuts down with the app's settings on, put them back at next sign-in."""
    if sys.platform != "win32":
        return
    cmd = _cli_command()
    if cmd is None:
        return
    with contextlib.suppress(OSError):
        _reg_write(RUN_ONCE_KEY, RUN_ONCE_NAME, _quote(cmd + ["pc-restore"]))


def disarm_next_sign_in() -> None:
    if sys.platform != "win32":
        return
    with contextlib.suppress(OSError):
        _reg_write(RUN_ONCE_KEY, RUN_ONCE_NAME, None)


def mark_updating() -> None:
    """Called right before the updater ends the app: skip the put-back.

    The new version starts a moment later and would only set everything again,
    and the watcher must be gone fast so the updater can swap the files.
    """
    from .paths import user_data_dir

    with contextlib.suppress(OSError):
        (user_data_dir() / UPDATING_MARK).write_text(str(time.time()), encoding="utf-8")


def _take_updating_mark() -> bool:
    from .paths import user_data_dir

    path = user_data_dir() / UPDATING_MARK
    try:
        stamp = float(path.read_text(encoding="utf-8") or 0)
    except (OSError, ValueError):
        return False
    with contextlib.suppress(OSError):
        path.unlink()
    return time.time() - stamp < 600


def app_running() -> bool:
    """Whether the desktop app holds its single-instance lock right now."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        from .desktop import MUTEX_NAME

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenMutexW.restype = wintypes.HANDLE
        kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        handle = kernel32.OpenMutexW(0x00100000, False, MUTEX_NAME)  # SYNCHRONIZE
        if handle:
            kernel32.CloseHandle(handle)
            return True
    except Exception:
        pass
    return False


def _wait_for_pid(pid: int) -> None:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x00100000, False, int(pid))  # SYNCHRONIZE
        if handle:
            kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
            kernel32.CloseHandle(handle)
        return
    while True:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(1.0)


def start_guard() -> bool:
    """Start the watcher that puts everything back when this process ends."""
    cmd = _cli_command()
    if cmd is None:
        return False
    flags = [_CREATE_NO_WINDOW | _DETACHED | _BREAKAWAY, _CREATE_NO_WINDOW | _DETACHED] \
        if sys.platform == "win32" else [0]
    for creation in flags:
        try:
            subprocess.Popen(cmd + ["pc-guard", "--pid", str(os.getpid())],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True,
                             creationflags=creation)
            return True
        except OSError:
            # A job that does not allow breaking away refuses the first try.
            continue
    return False


def guard(pid: int, poll: float = 5.0, sleep: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """The watcher: wait for the app to end, then give the PC back."""
    _wait_for_pid(pid)
    if _take_updating_mark():
        return {"ok": True, "skipped": "update"}
    sleep(1.0)
    if app_running():
        return {"ok": True, "skipped": "app open again"}
    return put_back(wait_for_game=True, poll=poll, sleep=sleep)


def put_back(wait_for_game: bool = False, live_ok: bool = False, poll: float = 5.0,
             sleep: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """Restore everything; hand Steam's and CS2's own files to the waiter.

    With ``wait_for_game`` the screen settings wait (in this process) for CS2
    to close, since changing them under a running game would black it out.
    Stops waiting the moment the app is opened again.
    """
    result = restore_all(live_ok=live_ok)
    while wait_for_game and _screen_parts_waiting(result):
        sleep(poll)
        if app_running():
            return {"ok": True, "skipped": "app open again", "items": result["items"]}
        result = restore_all(live_ok=live_ok)
    if _file_parts_waiting(result):
        _write_file_waiter(uninstalling=live_ok)
    return result


def _screen_parts_waiting(result: Dict[str, Any]) -> bool:
    return any(d["result"] == "waiting" and not _is_file_part(d["key"]) for d in result.get("items", []))


def _file_parts_waiting(result: Dict[str, Any]) -> bool:
    return any(d["result"] == "waiting" and _is_file_part(d["key"]) for d in result.get("items", []))


def _is_file_part(key: str) -> bool:
    return key.startswith("launch_options|") or key.startswith("window_mode|")


def waiter_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / WAITER_DIR_NAME


def _escape_vdf(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _write_file_waiter(uninstalling: bool = False) -> Optional[Path]:
    """Hand Steam's and CS2's files to a script that waits for them to close.

    Steam rewrites launch options from memory when it exits, and CS2 does the
    same with its window mode, so writing either while it runs is undone. The
    script lives outside the app's folder (the updater and the uninstaller
    must be free to replace or delete that folder), changes only a line that
    still holds the app's value, and deletes itself when done.
    """
    jobs = []
    with _lock:
        for part in _load()["parts"].values():
            if part.get("state") != "ours":
                continue
            if part["kind"] == "launch_options":
                jobs.append({"type": "launch", "path": str(_steam_user(part["ident"]).localconfig),
                             "ours": str(part.get("ours") or ""),
                             "original": _escape_vdf(str(restore_target(part, uninstalling) or ""))})
            elif part["kind"] == "window_mode" and part.get("original") is not None:
                user_path, setting = _split_window_ident(part["ident"])
                jobs.append({"type": "video", "path": str(_steam_user(user_path).video_cfg),
                             "key": setting, "ours": str(part.get("ours")),
                             "original": str(part.get("original"))})
    if not jobs:
        return None
    folder = waiter_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        script = folder / "put-back.ps1"
        (folder / "jobs.json").write_text(json.dumps({"jobs": jobs}, indent=1), encoding="utf-8")
        script.write_text(WAITER_SCRIPT, encoding="utf-8")
    except OSError:
        return None
    if sys.platform == "win32":
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                   "-ExecutionPolicy", "Bypass", "-File", str(script)]
        with contextlib.suppress(OSError):
            _reg_write(RUN_ONCE_KEY, WAITER_RUN_ONCE_NAME, _quote(command))
        with contextlib.suppress(OSError):
            subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True,
                             creationflags=_CREATE_NO_WINDOW | _DETACHED)
    return script


def mark_waiter_done() -> None:
    """The app is open again and owns these files: the waiter must stand down."""
    folder = waiter_dir()
    with contextlib.suppress(OSError):
        (folder / "jobs.json").unlink()
    if sys.platform == "win32":
        with contextlib.suppress(OSError):
            _reg_write(RUN_ONCE_KEY, WAITER_RUN_ONCE_NAME, None)


# The waiter. Plain PowerShell, no downloads, no other programs: it waits for
# Steam / CS2 to close, then edits one line per job, and only if that line
# still holds the value the app set.
WAITER_SCRIPT = r'''# CS2 Launcher: put Steam's launch options and CS2's window mode back once
# Steam and CS2 are closed. Written by the app; deletes itself when done.
$ErrorActionPreference = 'SilentlyContinue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$jobsFile = Join-Path $here 'jobs.json'
$runOnce = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce'
$name = 'CS2 Launcher - put Steam settings back'
function Unescape([string]$s) { return $s.Replace('\"', '"').Replace('\\', '\') }
while ($true) {
  if (-not (Test-Path $jobsFile)) { break }
  # Read as an object with a list inside: Windows PowerShell 5.1 hands a
  # top-level JSON list over as one item, not as the list.
  $data = ConvertFrom-Json (Get-Content -Raw -Encoding UTF8 $jobsFile)
  $jobs = @($data.jobs)
  $needSteam = @($jobs | Where-Object { $_.type -eq 'launch' }).Count -gt 0
  $needCs2 = @($jobs | Where-Object { $_.type -eq 'video' }).Count -gt 0
  $steamUp = [bool](Get-Process -Name steam -ErrorAction SilentlyContinue)
  $cs2Up = [bool](Get-Process -Name cs2 -ErrorAction SilentlyContinue)
  if (($needSteam -and $steamUp) -or ($needCs2 -and $cs2Up)) { Start-Sleep -Seconds 5; continue }
  Start-Sleep -Seconds 2
  foreach ($job in $jobs) {
    if (-not (Test-Path -LiteralPath $job.path)) { continue }
    $raw = [System.IO.File]::ReadAllText($job.path)
    $nl = if ($raw.Contains("`r`n")) { "`r`n" } else { "`n" }
    $lines = $raw -split "`r?`n"
    $changed = $false
    if ($job.type -eq 'launch') {
      $stack = New-Object System.Collections.ArrayList
      $pending = $null
      for ($i = 0; $i -lt $lines.Length; $i++) {
        $t = $lines[$i].Trim()
        if ($t -match '^"([^"]+)"$') { $pending = $Matches[1]; continue }
        if ($t -eq '{') { [void]$stack.Add([string]$pending); $pending = $null; continue }
        if ($t -eq '}') { if ($stack.Count) { $stack.RemoveAt($stack.Count - 1) }; continue }
        if ($stack.Count -ge 2 -and $stack[$stack.Count - 1] -eq '730' -and $stack[$stack.Count - 2] -ieq 'apps' -and
            $lines[$i] -match '^(\s*"LaunchOptions"\s+)"(.*)"\s*$') {
          if ((Unescape $Matches[2]) -ceq $job.ours) {
            $lines[$i] = $Matches[1] + '"' + $job.original + '"'
            $changed = $true
          }
        }
      }
    } else {
      $key = [regex]::Escape($job.key)
      for ($i = 0; $i -lt $lines.Length; $i++) {
        if ($lines[$i] -match ('^(\s*"' + $key + '"\s+)"([^"]*)"\s*$') -and $Matches[2] -ceq $job.ours) {
          $lines[$i] = $Matches[1] + '"' + $job.original + '"'
          $changed = $true
        }
      }
    }
    if ($changed) { [System.IO.File]::WriteAllText($job.path, ($lines -join $nl), (New-Object System.Text.UTF8Encoding($false))) }
  }
  Remove-Item -LiteralPath $jobsFile -Force
  break
}
Remove-ItemProperty -Path $runOnce -Name $name -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force
'''


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

_pending_reapply: List[str] = []
_guard_started = False
_retry_thread: Optional[threading.Thread] = None


def on_app_start(cs2_install: Optional[Path] = None, retry_every: float = 30.0) -> None:
    """Called once when the desktop app starts: snapshot, set ours again, watch.

    Runs in the background so a slow driver call never holds up the window.
    """
    enable(True)

    def work() -> None:
        global _pending_reapply
        mark_waiter_done()
        global _guard_started
        with contextlib.suppress(Exception):
            ensure_snapshot(cs2_install)
        _guard_started = start_guard()
        with contextlib.suppress(Exception):
            result = reapply_all()
            _pending_reapply = list(result.get("waiting") or [])
        # Steam's launch options can only be set while Steam is closed, and
        # the window mode while CS2 is closed. Try those again now and then.
        while _pending_reapply:
            time.sleep(retry_every)
            with contextlib.suppress(Exception):
                result = reapply_all(list(_pending_reapply))
                _pending_reapply = [k for k in _pending_reapply if k in (result.get("waiting") or [])]

    global _retry_thread
    _retry_thread = threading.Thread(target=work, name="pc-settings", daemon=True)
    _retry_thread.start()


def on_app_exit() -> None:
    """A normal Quit. The watcher does the put-back; this only covers a PC
    where the watcher could not be started."""
    if not _enabled or _guard_started:
        return
    with contextlib.suppress(Exception):
        put_back()


def put_back_now() -> Dict[str, Any]:
    """The Settings button: give the PC back now, while the app stays open."""
    global _pending_reapply
    _pending_reapply = []
    result = restore_all()
    if _file_parts_waiting(result):
        # The app is open, so its own retry is the waiter: written now, it
        # runs once Steam / CS2 close.
        _write_file_waiter()
    return result


def for_launch(user) -> str:
    """Launch options to pass to this one launch when Steam's own can't be set yet.

    Steam was open when the app started, so the app's launch options are still
    waiting. Steam adds whatever ``-applaunch`` carries to the stored options,
    so the app's extra flags still reach the game.
    """
    try:
        key = _key("launch_options", str(user.path))
        part = _load()["parts"].get(key)
        if not part or part.get("state") != "original" or not part.get("reapply"):
            return ""
        have = set(_option_groups(str(part.get("original") or "")))
        return " ".join(g for g in _option_groups(str(part.get("ours") or "")) if g not in have)
    except Exception:
        return ""


def _option_groups(line: str) -> List[str]:
    """``-w 1280 -high +exec x`` -> ``["-w 1280", "-high", "+exec x"]``."""
    groups: List[str] = []
    for token in line.split():
        if token[:1] in "-+" or not groups:
            groups.append(token)
        else:
            groups[-1] += " " + token
    return groups
