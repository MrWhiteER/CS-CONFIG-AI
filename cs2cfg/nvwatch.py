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
        take("Counter-Strike 2" if exe == "cs2.exe" else exe, view)
    return out


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
            items.append({"profile": profile, "key": sid,
                          "name": (b or a or {}).get("name") or sid,
                          # None reads better as the driver's own default.
                          "was": was if was is not None else "NVIDIA default",
                          "now": now if now is not None else "NVIDIA default",
                          "can_put_back": False})
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
