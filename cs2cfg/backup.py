"""Backups.

Every run that writes anything creates one backup set. A set is restorable as
a unit, because the three files this tool touches are only consistent with
each other: rolling back the video config but not the launch options would
leave a state the user never actually had.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .kb import user_data_dir


def backups_root() -> Path:
    return user_data_dir() / "backups"


@dataclass
class BackupSet:
    stamp: str
    path: Path
    files: Dict[str, str]
    note: str = ""

    @property
    def when(self) -> str:
        try:
            return datetime.strptime(self.stamp, "%Y%m%d-%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return self.stamp

    @property
    def originals(self) -> List[str]:
        return sorted(self.files)


class BackupSession:
    """Collects the originals of everything a single run is about to change."""

    def __init__(self, note: str = "") -> None:
        self.stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.dir = backups_root() / self.stamp
        self.files: Dict[str, str] = {}
        self.note = note
        self._started = False

    def _start(self) -> None:
        if not self._started:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._started = True

    def add(self, path: Path) -> Optional[Path]:
        """Copy ``path`` into the set. Missing files are recorded, not copied.

        A file that did not exist before is still worth recording: restoring
        the set has to delete it again, or a rollback leaves debris behind.
        """
        path = Path(path)
        key = str(path)
        if key in self.files:
            return None

        self._start()
        if not path.exists():
            self.files[key] = ""
            self._write_manifest()
            return None

        stored = f"{len(self.files):02d}_{path.name}"
        shutil.copy2(path, self.dir / stored)
        self.files[key] = stored
        self._write_manifest()
        return self.dir / stored

    def _write_manifest(self) -> None:
        manifest = {
            "stamp": self.stamp,
            "note": self.note,
            "created": datetime.now().isoformat(timespec="seconds"),
            "files": self.files,
        }
        (self.dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    @property
    def empty(self) -> bool:
        return not self.files


def list_sets() -> List[BackupSet]:
    """All backup sets, newest first."""
    root = backups_root()
    if not root.exists():
        return []

    out: List[BackupSet] = []
    for entry in sorted(root.iterdir(), reverse=True):
        manifest = entry / "manifest.json"
        if not entry.is_dir() or not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append(BackupSet(
            stamp=data.get("stamp", entry.name),
            path=entry,
            files=data.get("files", {}),
            note=data.get("note", ""),
        ))
    return out


def find_set(stamp: str) -> Optional[BackupSet]:
    if stamp in ("latest", "last"):
        sets = list_sets()
        return sets[0] if sets else None
    return next((s for s in list_sets() if s.stamp == stamp), None)


def restore(backup: BackupSet) -> List[str]:
    """Put a backup set back. Returns a line per file describing what happened."""
    report: List[str] = []
    for original, stored in sorted(backup.files.items()):
        target = Path(original)
        if not stored:
            # The file did not exist when the backup was taken.
            if target.exists():
                target.unlink()
                report.append(f"removed  {target}  (did not exist before)")
            else:
                report.append(f"skipped  {target}  (still absent, as before)")
            continue

        source = backup.path / stored
        if not source.exists():
            report.append(f"MISSING  {target}  (backup file {stored} is gone)")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        report.append(f"restored {target}")
    return report


def prune(keep: int = 20) -> int:
    """Delete all but the newest ``keep`` sets. Returns how many went."""
    sets = list_sets()
    removed = 0
    for old in sets[keep:]:
        shutil.rmtree(old.path, ignore_errors=True)
        removed += 1
    return removed
