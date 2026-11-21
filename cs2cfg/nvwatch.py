"""Notice NVIDIA settings changed outside the app.

The driver keeps its 3D settings in one database file under ProgramData. When
somebody changes a setting in the NVIDIA app or the NVIDIA Control Panel, that
file is rewritten, so its timestamp is the signal: one stat call every few
seconds, and the settings themselves are only read (through cs2cfg/nvidia.py,
read-only) once the file has actually moved.

What was read last time is kept in this app's data folder. Anything different
goes into the change history and the review window asks about it.

When the app itself changes an NVIDIA setting it must call ``accept_current()``
straight after, so its own change is not reported back as an outside one.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .kb import user_data_dir

EXECUTABLES = ("cs2.exe",)
CS2_PROFILE = "Counter-Strike 2"


def drs_files() -> List[Path]:
    root = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "NVIDIA Corporation" / "Drs"
    try:
        return sorted(root.glob("nvdrsdb*.bin"))
    except OSError:
        return []


def _store() -> Path:
    return user_data_dir() / "history" / "nvidia.json"


def read_now() -> Optional[Dict[str, Dict[str, dict]]]:
    """{profile shown: {setting id: {name, value}}}, or None without a driver."""
    from . import nvidia

    result = nvidia.probe(EXECUTABLES)
    if not result.available:
        return None
    out: Dict[str, Dict[str, dict]] = {}

    def take(label: str, view) -> None:
        if view is None:
            return
        out[label] = {f"0x{s.id:08X}": {"name": s.name or f"Setting 0x{s.id:08X}",
                                        "value": s.value}
                      for s in view.settings}

    take("Every game", result.global_profile)
    for exe, view in result.app_profiles.items():
        take(CS2_PROFILE if exe == "cs2.exe" else exe, view)

    # The raw values of CS2's own profile, in the form the writer takes, so a
    # change there can be put back. Only when the NVIDIA tab's writer exists.
    reader = getattr(nvidia, "read_cs2", None)
    if reader is not None and out.get(CS2_PROFILE):
        try:
            raw = reader([int(k, 16) for k in out[CS2_PROFILE]]) or {}
        except Exception:
            raw = {}
        for key, entry in out[CS2_PROFILE].items():
            for form in (int(key, 16), key, key.lower()):
                if form in raw:
                    entry["raw"] = raw[form]
                    break
    return out


def can_write() -> bool:
    from . import nvidia

    return getattr(nvidia, "write_cs2", None) is not None


def put_back(item: dict) -> dict:
    """Write an item's old value into CS2's NVIDIA profile again."""
    from . import nvidia

    writer = getattr(nvidia, "write_cs2", None)
    if writer is None or item.get("profile") != CS2_PROFILE:
        return {"ok": False, "error": "This one can only be changed back in the NVIDIA app."}
    try:
        result = writer({int(str(item["key"]), 16): item.get("raw_was")}, record=False) or {}
    except Exception as exc:
        return {"ok": False, "error": f"Could not write the NVIDIA setting: {exc}"}
    if result.get("ok"):
        accept_current()
    return result


def compare(before: Dict[str, Dict[str, dict]], after: Dict[str, Dict[str, dict]]) -> List[dict]:
    items = []
    for profile in sorted(set(before) | set(after)):
        old, new = before.get(profile) or {}, after.get(profile) or {}
        for sid in sorted(set(old) | set(new)):
            a, b = old.get(sid), new.get(sid)
            was = a.get("value") if a else None
            now = b.get("value") if b else None
            if was == now:
                continue
            # Put back only into CS2's own profile (the only one the app
            # writes), and only when the old value is known in writable form.
            writable = (profile == CS2_PROFILE and can_write()
                        and (a is None or "raw" in a))
            items.append({"profile": profile, "key": sid,
                          "name": (b or a or {}).get("name") or sid,
                          # None reads better as the driver's own default.
                          "was": was if was is not None else "NVIDIA default",
                          "now": now if now is not None else "NVIDIA default",
                          "raw_was": a.get("raw") if a else None,
                          "can_put_back": writable})
    return items


def load() -> Optional[Dict[str, Dict[str, dict]]]:
    try:
        return json.loads(_store().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save(snapshot: Dict[str, Dict[str, dict]]) -> None:
    path = _store()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=1), encoding="utf-8")


def check(reader: Callable[[], Optional[dict]] = read_now) -> List[dict]:
    """Read now, compare with last time, remember now. Returns what moved."""
    now = reader()
    if now is None:
        return []
    before = load()
    save(now)
    if before is None:
        return []           # first look: this is the starting point
    return compare(before, now)


def accept_current() -> None:
    """Call after the app itself writes an NVIDIA setting."""
    try:
        now = read_now()
    except Exception:
        return
    if now is not None:
        save(now)


class Watcher:
    def __init__(self, on_changes: Callable[[List[dict]], None], interval: float = 5.0,
                 files: Callable[[], List[Path]] = drs_files,
                 reader: Callable[[], Optional[dict]] = read_now) -> None:
        self.on_changes = on_changes
        self.interval = interval
        self.files = files
        self.reader = reader
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _stamps(self) -> Dict[str, float]:
        out = {}
        for path in self.files():
            try:
                out[str(path)] = path.stat().st_mtime
            except OSError:
                pass
        return out

    def _run(self) -> None:
        try:
            found = check(self.reader)      # changes made while the app was closed
            if found:
                self.on_changes(found)
        except Exception:
            pass
        last = self._stamps()
        settling = None
        while not self._stop.wait(self.interval):
            now = self._stamps()
            if settling is not None:
                if now == settling:
                    settling, last = None, now
                    try:
                        found = check(self.reader)
                        if found:
                            self.on_changes(found)
                    except Exception:
                        pass
                else:
                    settling = now
            elif now != last:
                settling = now

    def start(self) -> bool:
        if not self.files():
            return False         # no NVIDIA driver settings on this PC
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="cs2cfg-nvidia-watch")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
