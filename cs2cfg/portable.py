"""Carry a whole setup to another machine, in one file.

The problem this solves happened for real: a fresh Windows install, a fresh
Steam account, and nothing to carry over -- no config folder, no binds, none
of the choices that had been made here over months. Reproducing that by hand
means remembering what you did, which nobody does.

So a setup is a single ``.cs2setup`` file: a zip holding the account's own
preferences and a copy of the configuration folder as it stands. It is written
where the user asks and read back the same way. Nothing in it is secret -- no
tokens, no Steam credentials, no account ids that mean anything off this
machine -- so it can be handed to somebody else, which is the other thing
people want it for.

Importing never writes to a config folder on its own. It unpacks, says what it
found, and leaves the writing to the same apply path everything else goes
through, with the same backup behind it.
"""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__

SUFFIX = ".cs2setup"
MANIFEST = "setup.json"
CFG_PREFIX = "cfg/"

# A setup written by a much later version may hold things this one would
# silently drop. The number goes up only when that becomes true.
FORMAT = 1

# Preferences worth carrying. Deliberately not everything: where the rail was
# dragged to and which tab was open describe this window, not this setup, and
# arriving on a new machine with somebody else's rail width is noise. The
# config folder is excluded because it is a path on the machine it came from.
CARRIED = (
    "intent",
    "target_fps",
    "stretch_mode",
    "patch_video",
    "write_video",
    "write_cfg",
    "write_launch",
    "link_autoexec",
    "fix_scaling",
    "favourites",
    "mouse_shape",
)

# Never carried, named so the omission is a decision rather than an oversight.
WITHHELD = ("account", "pinned_account", "cfg_folder", "rail_width", "tab")

MAX_FILE = 2 * 1024 * 1024          # a .vcfg far larger than this is not one
MAX_FILES = 400


class SetupError(Exception):
    """The file is not one of ours, or not one we can read."""


def _safe_members(names: List[str]) -> List[str]:
    """The entries under cfg/ that are safe to unpack.

    A zip can name ``../`` or an absolute path and land a file anywhere the
    process can write. That is the whole of the zip-slip bug, and it does not
    stop being real because we also wrote the file.
    """
    out = []
    for name in names:
        if not name.startswith(CFG_PREFIX) or name.endswith("/"):
            continue
        rest = name[len(CFG_PREFIX):]
        if not rest or rest.startswith("/") or ".." in Path(rest).parts:
            continue
        if Path(rest).is_absolute() or (len(rest) > 1 and rest[1] == ":"):
            continue
        out.append(name)
    return out


def write(target: Path, ui: Dict[str, Any], folder: Optional[Path],
          note: str = "") -> Dict[str, Any]:
    """Write a setup file. Returns what went into it."""
    target = Path(target)
    if target.suffix.lower() != SUFFIX:
        target = target.with_suffix(SUFFIX)
    target.parent.mkdir(parents=True, exist_ok=True)

    carried = {k: ui[k] for k in CARRIED if k in ui}
    manifest = {
        "format": FORMAT,
        "written_by": __version__,
        "written_at": time.time(),
        "note": str(note or "")[:400],
        "prefs": carried,
    }

    files: List[str] = []
    skipped: List[str] = []
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        if folder and Path(folder).is_dir():
            root = Path(folder)
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                if len(files) >= MAX_FILES:
                    skipped.append(str(path.relative_to(root)))
                    continue
                try:
                    if path.stat().st_size > MAX_FILE:
                        skipped.append(str(path.relative_to(root)))
                        continue
                    rel = path.relative_to(root).as_posix()
                    zf.write(path, CFG_PREFIX + rel)
                    files.append(rel)
                except OSError:
                    skipped.append(str(path.relative_to(root)))
        manifest["files"] = files
        zf.writestr(MANIFEST, json.dumps(manifest, indent=1))

    return {
        "path": str(target),
        "files": len(files),
        "skipped": skipped,
        "settings": len(carried),
        "bytes": target.stat().st_size,
    }


def read(source: Path) -> Dict[str, Any]:
    """What a setup file holds, without unpacking any of it."""
    source = Path(source)
    if not source.is_file():
        raise SetupError(f"no file at {source}")
    try:
        with zipfile.ZipFile(source) as zf:
            try:
                raw = zf.read(MANIFEST)
            except KeyError:
                raise SetupError("this is a zip, but not a saved setup")
            manifest = json.loads(raw.decode("utf-8"))
            members = _safe_members(zf.namelist())
    except zipfile.BadZipFile:
        raise SetupError("this file is not a saved setup")
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SetupError("the setup's description could not be read")

    if int(manifest.get("format", 0)) > FORMAT:
        raise SetupError(
            f"written by version {manifest.get('written_by', '?')}, which "
            "saves setups this copy cannot read yet -- update first")

    prefs = manifest.get("prefs") or {}
    return {
        "path": str(source),
        "written_by": manifest.get("written_by", "?"),
        "written_at": manifest.get("written_at", 0),
        "note": manifest.get("note", ""),
        "prefs": {k: v for k, v in prefs.items() if k in CARRIED},
        "files": [m[len(CFG_PREFIX):] for m in members],
    }


def unpack(source: Path, into: Path) -> Dict[str, Any]:
    """Put the setup's config files into a folder.

    The caller decides where, and is expected to have taken a backup: this
    overwrites files of the same name, which is the point of restoring one.
    """
    into = Path(into)
    into.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    with zipfile.ZipFile(source) as zf:
        for member in _safe_members(zf.namelist()):
            rel = member[len(CFG_PREFIX):]
            dest = into / rel
            # Belt and braces over _safe_members: resolve and check it really
            # landed inside, in case a name survived the filter.
            if into.resolve() not in dest.resolve().parents:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(dest, "wb") as out:
                out.write(src.read(MAX_FILE + 1)[:MAX_FILE])
            written.append(rel)
    return {"folder": str(into), "written": written}
