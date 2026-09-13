"""Where an account's configuration lives, and what is actually in it.

Two jobs.

**Pointing at it.** A folder or a single file are both reasonable answers to
"where are your settings". A file is treated as a way of naming the folder it
sits in, and remembered as the entry point, because a config is almost never
one file: an autoexec execs scripts, binds and settings from beside it, and
reading only the file named would leave the scripts and keyboard views nearly
empty.

**Telling .cfg and .vcfg apart.** CS2 uses ``.vcfg`` for two entirely
different things, and confusing them would damage a file the game owns:

* *console script* -- the kind people write. Lines of commands: ``unbindall``,
  ``alias``, ``bind``. This is also exactly what a ``.cfg`` contains, so
  converting one is a change of extension and nothing else.
* *KeyValues* -- the kind CS2 writes for itself, like
  ``user_keys_default.vcfg``: ``"config" { "bindings" { ... } }``.

So a file is classified by reading it rather than by its name. A ``.cfg``
holding a console script can become a ``.vcfg``; anything that parses as
KeyValues is left alone and said so, because a file the game writes is not
ours to rewrite.

Converting copies and never moves. The original stays exactly where it was, so
a conversion that turns out wrong costs nothing.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import vdf

SCRIPT = "script"        # lines of console commands: what a .cfg holds
KEYVALUES = "keyvalues"  # the game's own format
EMPTY = "empty"
UNKNOWN = "unknown"

# What a config is allowed to be, in the order a folder should offer them.
CONFIG_SUFFIXES = (".vcfg", ".cfg")


def looks_like(path: Path) -> str:
    """What kind of file this is, decided by reading it.

    The extension is not evidence: the game and the user both write ``.vcfg``
    and they are not the same format.
    """
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return UNKNOWN
    if not text.strip():
        return EMPTY

    # KeyValues opens with a quoted key and a brace. Parsing is the honest
    # test, but a cheap look first avoids trying it on every console script.
    stripped = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//"))
    if stripped.lstrip().startswith('"') and "{" in stripped:
        try:
            vdf.parse(text)
            return KEYVALUES
        except vdf.VdfError:
            pass

    for line in stripped.splitlines():
        if line.strip():
            return SCRIPT
    return EMPTY


def convertible(path: Path) -> bool:
    """Whether this is a .cfg that could sensibly become a .vcfg."""
    path = Path(path)
    return path.suffix.lower() == ".cfg" and looks_like(path) == SCRIPT


def converted_name(path: Path) -> Path:
    return Path(path).with_suffix(".vcfg")


def convert(path: Path, overwrite: bool = False) -> Path:
    """Copy a console-script .cfg to .vcfg, leaving the original alone.

    A copy rather than a rename: nothing the user had is removed, so a
    conversion that turns out to be wrong has cost them nothing, and anything
    elsewhere that execs the old name still finds it.
    """
    path = Path(path)
    kind = looks_like(path)
    if kind == KEYVALUES:
        raise ValueError(
            f"{path.name} is one of CS2's own KeyValues files, not a console "
            "script; it is not ours to rewrite")
    if path.suffix.lower() != ".cfg":
        raise ValueError(f"{path.name} is not a .cfg")

    target = converted_name(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"{target.name} already exists")
    shutil.copy2(path, target)
    return target


def exec_target(cfg_root: Path, path: Path) -> str:
    """How a config names another one: relative to cfg/, with forward slashes.

    Taken from what real configs do -- ``exec "mrwhiteer/tools/alias.vcfg"`` --
    rather than invented. The path is relative to the cfg root, not to the file
    doing the exec.
    """
    try:
        relative = Path(path).resolve().relative_to(Path(cfg_root).resolve())
    except (ValueError, OSError):
        relative = Path(path).name
    return str(relative).replace("\\", "/")


def _execs_in(line: str) -> str:
    """What an exec line runs, or "" if the line is not one."""
    bare = line.split("//", 1)[0].strip()
    if not bare.lower().startswith("exec"):
        return ""
    rest = bare[4:].strip()
    if not rest:
        return ""
    return rest.strip('"').strip().replace("\\", "/")


def ensure_exec(autoexec: Path, cfg_root: Path, created: Path,
                replaced: Optional[Path] = None) -> Dict[str, Any]:
    """Make sure the autoexec runs a file this tool just made.

    A file nothing execs never runs, so creating one without this is creating
    nothing. Two things have to be true afterwards: the new file is exec'd, and
    it is not exec'd *as well as* the file it replaced -- which would run the
    same commands twice. So an existing line pointing at the old file is
    rewritten rather than added beside.

    The new line goes with the other execs rather than at the end of the file,
    because that is where someone reading it will look.
    """
    autoexec = Path(autoexec)
    out: Dict[str, Any] = {"changed": False, "action": "", "line": "",
                           "target": ""}
    if not autoexec.is_file():
        out["action"] = "no autoexec to add it to"
        return out

    wanted = exec_target(cfg_root, created)
    out["target"] = wanted
    old = exec_target(cfg_root, replaced) if replaced else ""

    from . import cfglang

    raw = autoexec.read_bytes().decode("utf-8", errors="replace")
    flat = cfglang.restore_newlines(raw, "\n", False)
    lines = flat.split("\n")

    last_exec = None
    for index, line in enumerate(lines):
        runs = _execs_in(line)
        if not runs:
            continue
        last_exec = index
        if runs.lower() == wanted.lower():
            out["action"] = "already there"
            return out
        # The line that ran the file this one replaces. Rewritten, so the
        # commands do not run twice.
        if old and runs.lower() == old.lower():
            lines[index] = line.replace(old, wanted, 1)
            out.update(changed=True, action="pointed at the new file",
                       line=lines[index].strip())
            _write_back(autoexec, lines, raw)
            return out

    new_line = f'exec "{wanted}"'
    at = last_exec + 1 if last_exec is not None else len(lines)
    lines.insert(at, new_line)
    out.update(changed=True, action="added", line=new_line)
    _write_back(autoexec, lines, raw)
    return out


def _write_back(path: Path, lines: List[str], original: str) -> None:
    """Save, keeping the file's own line endings and final newline."""
    from . import cfglang

    document = cfglang.parse(original)
    body = cfglang.restore_newlines(
        "\n".join(lines), document.newline, document.trailing_newline)
    cfglang.write_config_text(path, body, document.encoding)


def resolve(given: str) -> Dict[str, Any]:
    """Turn what the user pointed at into a folder, and an entry point.

    Naming a file selects its folder and marks the file. Naming a folder
    leaves the entry point to be guessed from what is in it.
    """
    raw = (given or "").strip().strip('"')
    out: Dict[str, Any] = {"given": raw, "folder": None, "entry": None,
                           "exists": False, "error": ""}
    if not raw:
        out["error"] = "nothing given"
        return out

    path = Path(raw).expanduser()
    if path.is_dir():
        out.update(folder=str(path), exists=True, entry=guess_entry(path))
        return out
    if path.is_file():
        out.update(folder=str(path.parent), entry=path.name, exists=True)
        if path.suffix.lower() not in CONFIG_SUFFIXES:
            out["error"] = (f"{path.name} is not a .cfg or .vcfg; its folder "
                            "was used")
            out["entry"] = guess_entry(path.parent)
        return out

    out["error"] = f"there is nothing at {path}"
    return out


def guess_entry(folder: Path) -> Optional[str]:
    """The file CS2 would exec first, if one is obvious.

    Only an autoexec counts. Picking the largest file, or the first
    alphabetically, would be a guess dressed up as an answer.
    """
    folder = Path(folder)
    for suffix in CONFIG_SUFFIXES:
        candidate = folder / ("autoexec" + suffix)
        if candidate.is_file():
            return candidate.name
    return None


def survey(folder: Path) -> List[Dict[str, Any]]:
    """Every config in a folder, with what it actually is.

    Sorted with anything convertible first: those are the ones the user is
    being asked to decide about.
    """
    folder = Path(folder)
    found: List[Dict[str, Any]] = []
    try:
        # The whole collection: an autoexec at the root execs the scripts and
        # binds beside it, and those are where a .cfg is most likely to be.
        entries = sorted(folder.rglob("*"))
    except OSError:
        return found

    for item in entries:
        if not item.is_file() or item.suffix.lower() not in CONFIG_SUFFIXES:
            continue
        kind = looks_like(item)
        twin = converted_name(item)
        try:
            shown = str(item.relative_to(folder)).replace("\\", "/")
        except ValueError:
            shown = item.name
        found.append({
            "name": shown,
            "kind": kind,
            "size": item.stat().st_size,
            "convertible": item.suffix.lower() == ".cfg" and kind == SCRIPT,
            "already": twin.name if (item.suffix.lower() == ".cfg"
                                     and twin.exists()) else "",
        })
    found.sort(key=lambda f: (not f["convertible"], f["name"].lower()))
    return found
