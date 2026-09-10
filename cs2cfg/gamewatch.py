"""Notice what you changed inside CS2, without touching anything the game owns.

CS2 does not keep its per-user settings in the game folder -- it writes them to
Steam userdata when it shuts down:

    userdata/<id>/730/local/cfg/cs2_user_convars_0_slot0.vcfg   in-game settings
    userdata/<id>/730/local/cfg/cs2_user_keys_0_slot0.vcfg      key binds
    userdata/<id>/730/local/cfg/cs2_video.txt                   picture quality
    userdata/<id>/730/local/cfg/cs2_machine_convars.vcfg        machine settings

So the whole feature is reading those four files twice and comparing. This
module never writes to any of them; the snapshots it keeps live in this
application's own data directory, next to its backups.

Because the game writes them on exit, a snapshot taken while CS2 is running
still describes the session before it. That is why the comparison is made after
the game has closed, not during.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import vdf
from .kb import user_data_dir

# label, filename, path to the map of values inside the file
SOURCES: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("In-game settings", "cs2_user_convars_0_slot0.vcfg", ("config", "convars")),
    ("Key binds", "cs2_user_keys_0_slot0.vcfg", ("config", "bindings")),
    ("Stick binds", "cs2_user_keys_0_slot0.vcfg", ("config", "analogbindings")),
    ("Picture quality", "cs2_video.txt", ("video.cfg",)),
    ("Machine settings", "cs2_machine_convars.vcfg", ("config", "convars")),
)

# Values the game rewrites on its own. Reporting these as "you changed" would
# be wrong, and would bury the changes that were actually deliberate.
NOISE = {
    "Picture quality": {"Autoconfig", "setting.knowndevice", "Version",
                        "VendorID", "DeviceID"},
    "Machine settings": set(),
}


@dataclass
class Change:
    source: str
    key: str
    kind: str           # "changed", "added" or "removed"
    was: Optional[str]
    now: Optional[str]
    label: str = ""

    def describe(self) -> str:
        name = self.label or self.key
        if self.kind == "changed":
            # ASCII: this string reaches the console binary too, and a cp1252
            # terminal cannot encode an arrow.
            return f"{name}: {self.was} -> {self.now}"
        if self.kind == "added":
            return f"{name}: set to {self.now}"
        return f"{name}: cleared (was {self.was})"


@dataclass
class Snapshot:
    taken: float = field(default_factory=time.time)
    values: Dict[str, Dict[str, str]] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"taken": self.taken, "values": self.values, "missing": self.missing}

    @classmethod
    def from_dict(cls, data: dict) -> "Snapshot":
        return cls(taken=float(data.get("taken") or 0),
                   values=dict(data.get("values") or {}),
                   missing=list(data.get("missing") or []))


def _labels() -> Dict[str, str]:
    """Friendly names for the convars the catalogue already knows about."""
    path = Path(__file__).with_name("knowledge") / "cfg_settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for name, spec in (data.get("settings") or {}).items():
        label = spec.get("label")
        if label:
            out[name.lower()] = str(label)
    return out


def cfg_dir(steam_root: Path, account_id: str) -> Path:
    return Path(steam_root) / "userdata" / str(account_id) / "730" / "local" / "cfg"


def _read_map(path: Path, route: Tuple[str, ...]) -> Optional[Dict[str, str]]:
    """Pull one section out of a KeyValues file, flattened to strings."""
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None
    try:
        data = vdf.parse(text)
    except vdf.VdfError:
        return None

    node = data
    for step in route:
        if not isinstance(node, dict):
            return None
        # KeyValues keys are case-insensitive in practice.
        match = next((k for k in node if k.lower() == step.lower()), None)
        if match is None:
            return None
        node = node[match]

    if not isinstance(node, dict):
        return None
    return {k: v for k, v in node.items() if not isinstance(v, dict)}


def take(folder: Path) -> Snapshot:
    """Read every source once. Nothing is written."""
    snap = Snapshot()
    for label, filename, route in SOURCES:
        found = _read_map(Path(folder) / filename, route)
        if found is None:
            snap.missing.append(label)
        else:
            snap.values[label] = found
    return snap


def compare(before: Snapshot, after: Snapshot,
            include_machine: bool = False) -> List[Change]:
    """What changed between two snapshots, most interesting sources first."""
    labels = _labels()
    changes: List[Change] = []

    for source, _filename, _route in SOURCES:
        if source == "Machine settings" and not include_machine:
            continue
        old = before.values.get(source)
        new = after.values.get(source)
        if old is None or new is None:
            # A file that was unreadable one side of the session says nothing
            # useful; claiming every key changed would be worse than silence.
            continue
        skip = NOISE.get(source, set())

        for key in sorted(set(old) | set(new)):
            if key in skip:
                continue
            was, now = old.get(key), new.get(key)
            if was == now:
                continue
            kind = "changed" if was is not None and now is not None else (
                "added" if was is None else "removed")
            changes.append(Change(
                source=source, key=key, kind=kind, was=was, now=now,
                label=labels.get(key.lower(), ""),
            ))
    return changes


# -- keeping snapshots between runs -----------------------------------------

def _store() -> Path:
    return user_data_dir() / "ingame"


def baseline_path(account_id: str) -> Path:
    return _store() / f"{account_id}.json"


def save_baseline(account_id: str, snap: Snapshot) -> Path:
    path = baseline_path(account_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap.as_dict(), indent=1), encoding="utf-8")
    return path


def load_baseline(account_id: str) -> Optional[Snapshot]:
    path = baseline_path(account_id)
    try:
        return Snapshot.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def as_dict(changes: List[Change], before: Snapshot, after: Snapshot) -> dict:
    by_source: Dict[str, List[dict]] = {}
    for change in changes:
        by_source.setdefault(change.source, []).append({
            "key": change.key, "label": change.label, "kind": change.kind,
            "was": change.was, "now": change.now, "text": change.describe(),
        })
    return {
        "count": len(changes),
        "sources": by_source,
        "before": before.taken,
        "after": after.taken,
        "missing": sorted(set(before.missing) | set(after.missing)),
    }


# -- watching for changes without being asked --------------------------------

class Watcher:
    """Notice CS2's settings files changing, and work out what moved.

    CS2 rewrites these files when it shuts down, so their modification time is
    the signal: when it moves, the game has just saved a session. Polling four
    timestamps costs four stat calls, which is cheap enough to do every few
    seconds forever.

    A write is only acted on once it has settled -- the game touches several
    files in quick succession, and comparing halfway through would report a
    file that had been written against three that had not.
    """

    def __init__(self, folder: Path, account_id: str, interval: float = 3.0) -> None:
        self.folder = Path(folder)
        self.account_id = str(account_id)
        self.interval = interval
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._pending: Optional[dict] = None
        self._checked: float = 0.0

    # -- state the server reads -------------------------------------------
    @property
    def pending(self) -> Optional[dict]:
        with self._lock:
            return dict(self._pending) if self._pending else None

    @property
    def last_checked(self) -> float:
        with self._lock:
            return self._checked

    def clear(self) -> None:
        """Forget the current finding, after it has been shown and accepted."""
        with self._lock:
            self._pending = None

    def summary(self) -> dict:
        found = self.pending
        return {
            "count": found["count"] if found else 0,
            "at": found["after"] if found else 0,
            "watching": bool(self._thread and self._thread.is_alive()),
            "checked": self.last_checked,
        }

    # -- the loop ----------------------------------------------------------
    def _stamps(self) -> Dict[str, float]:
        out = {}
        for _label, filename, _route in SOURCES:
            path = self.folder / filename
            try:
                out[filename] = path.stat().st_mtime
            except OSError:
                out[filename] = 0.0
        return out

    def _compare_now(self) -> None:
        baseline = load_baseline(self.account_id)
        current = take(self.folder)
        if baseline is None:
            save_baseline(self.account_id, current)
            return
        changes = compare(baseline, current)
        with self._lock:
            self._checked = time.time()
            if changes:
                self._pending = as_dict(changes, baseline, current)
        if changes:
            # The baseline moves forward so the same session is not reported
            # again on the next write; the finding itself is kept above.
            save_baseline(self.account_id, current)

    def _run(self) -> None:
        last = self._stamps()
        settling: Optional[Dict[str, float]] = None
        while not self._stop.wait(self.interval):
            now = self._stamps()
            if settling is not None:
                if now == settling:            # quiet for a full cycle: done
                    settling = None
                    last = now
                    try:
                        self._compare_now()
                    except Exception:
                        # A watcher that dies takes the feature with it; a
                        # single bad read is not worth that.
                        pass
                else:
                    settling = now
            elif now != last:
                settling = now

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="cs2cfg-ingame-watch")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
