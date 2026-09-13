"""The config a fresh account does not have yet.

A machine that has never had a config written on it has no ``cfg/<folder>`` at
all: no autoexec, no binds file, nothing to exec. Every view in this app is
built on scanning a collection of files, so on that machine they all correctly
report that there is nothing to show -- and the Keyboard tab has nowhere to
write a bind to, which is the point at which it stops being a fair description
of reality and starts being a dead end.

This builds the smallest collection that actually works: an entry point that
execs the others, a file for binds, one for settings, one for aliases. It is
the shape of a hand-written config rather than a generated blob, because the
whole point is that the player edits it from here on.

Two rules, and the second one matters more than it looks:

* **nothing is ever overwritten.** Only missing files are written. A folder
  that already has an autoexec keeps its autoexec, and the exec lines are
  added to it rather than replacing it.
* **no ``unbindall``.** A hand-written autoexec usually opens with it, because
  it then binds every key it wants. Here the binds file starts empty, so
  clearing the defaults first would leave the player in a game where nothing
  is bound -- unable to move, shoot, or open the console to fix it. The
  defaults stay, and a bind written from the Keyboard tab overrides the one it
  replaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Where the Keyboard tab writes when a collection has no binds in it yet.
BINDS_FILE = "mainsettings/key_binds.vcfg"
SETTINGS_FILE = "mainsettings/gamesettings.vcfg"
ALIAS_FILE = "tools/alias.vcfg"
AUTOEXEC = "autoexec.vcfg"

_HEADER = "// ---------------------------------------------"


def _banner(title: str) -> str:
    return f"{_HEADER}\n// {title}\n{_HEADER}\n"


_BINDS = _banner("Key binds") + """
// Your key binds live here. The Keyboard tab writes to this file, and you can
// edit it by hand just as happily -- it is a plain list of bind lines.
//
// Nothing is bound yet, so CS2's own defaults are all still in effect. A bind
// written here overrides the default for that key; the rest stay as they are.
//
//   bind "scancode4"  "+moveleft"      // A
//   bind "mouse1"     "+attack"
//
// Keys are written as HID scancodes so the bind follows the physical key on
// any keyboard layout. The Keyboard tab does that conversion for you.
"""

_SETTINGS = _banner("Game settings") + """
// Crosshair, viewmodel, radar, sound -- the settings you would otherwise set
// in the console every time. Anything you put here is applied at startup.
//
//   cl_crosshairsize 2
//   cl_radar_always_centered 0
//   volume 0.5
"""

_ALIASES = _banner("Aliases") + """
// Aliases give a name to a sequence of commands, which is what turns a key
// into something more interesting than a single console command. The Scripts
// tab reads this file, and anything you define here can be bound from the
// Keyboard tab by name.
//
//   alias "+jumpthrow" "+jump; -attack"
//   alias "-jumpthrow" "-jump"
"""


@dataclass
class Piece:
    """One file the starter can create."""
    relative: str
    content: str
    purpose: str
    exists: bool = False

    @property
    def name(self) -> str:
        return self.relative.rsplit("/", 1)[-1]


@dataclass
class Plan:
    """What is there, what is missing, and where it would go."""
    cfg_root: Path
    folder: str
    pieces: List[Piece] = field(default_factory=list)
    autoexec_exists: bool = False

    @property
    def missing(self) -> List[Piece]:
        return [p for p in self.pieces if not p.exists]

    @property
    def complete(self) -> bool:
        return not self.missing and self.autoexec_exists

    @property
    def root(self) -> Path:
        return self.cfg_root / self.folder

    @property
    def launch_target(self) -> str:
        """What the Steam launch options have to exec for any of this to run.

        The autoexec, not the generated performance file -- the autoexec is
        what execs everything else, so pointing the launch options at anything
        else means the binds never load.
        """
        return f"{self.folder}\\{AUTOEXEC}"


def _pieces() -> List[Piece]:
    """In load order, which is the order the autoexec will exec them.

    Aliases first, because a bind can name one. Binds last, so a key that
    changes a setting wins over that setting's own line rather than being
    quietly undone by it. This is the order a hand-written config uses.
    """
    return [
        Piece(ALIAS_FILE, _ALIASES, "aliases for the Scripts tab"),
        Piece(SETTINGS_FILE, _SETTINGS, "crosshair, viewmodel, sound"),
        Piece(BINDS_FILE, _BINDS, "where your key binds go"),
    ]


def _autoexec_text(folder: str, pieces: List[Piece]) -> str:
    """An entry point that execs the others, in the order they should load.

    Aliases first: a bind can refer to an alias, so the alias has to exist by
    the time the binds file runs. Settings before binds for the same reason --
    a bind that changes a setting should win over the setting's own line.
    """
    lines = [
        _HEADER,
        "// Loaded at startup. This file execs the others, so anything you add",
        "// needs an exec line here to run at all.",
        "//",
        "// Deliberately no `unbindall`: the binds file starts empty, and",
        "// clearing CS2's defaults before an empty binds file would leave you",
        "// unable to move or open the console. Add it yourself once you have",
        "// bound everything you need.",
        _HEADER,
        "",
    ]
    for piece in pieces:
        caption = piece.name.rsplit(".", 1)[0].replace("_", " ").upper()
        lines += [
            "echo",
            f'echo "Loading {caption}"',
            f'exec "{folder}/{piece.relative}"',
            f'echo "{caption} loaded"',
            "echo",
            _HEADER,
            "",
        ]
    lines += [
        "echo",
        'echo "Config loaded."',
        "echo",
        "",
    ]
    return "\n".join(lines)


def plan(cfg_root: Path, folder: str) -> Plan:
    """What a starter collection would add, without writing anything."""
    cfg_root = Path(cfg_root)
    root = cfg_root / folder
    pieces = _pieces()
    for piece in pieces:
        piece.exists = (root / piece.relative).is_file()
    return Plan(cfg_root=cfg_root, folder=folder, pieces=pieces,
                autoexec_exists=(root / AUTOEXEC).is_file())


def create(cfg_root: Path, folder: str, session: Optional[Any] = None) -> Dict[str, Any]:
    """Write whatever is missing, and make sure the autoexec runs it.

    Safe to call on every start: a collection that is already there is left
    exactly as it is, and the result says nothing was created.

    ``session`` is a :class:`~cs2cfg.backup.BackupSession`. Only files that
    already existed are added to it -- a file this created has no previous
    version to restore, and recording one would make an undo delete work the
    player had done since.
    """
    from . import cfgsource

    outcome = plan(cfg_root, folder)
    root = outcome.root
    created: List[str] = []
    steps: List[Dict[str, Any]] = []

    for piece in outcome.pieces:
        if piece.exists:
            continue
        target = root / piece.relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(piece.content, encoding="utf-8")
        created.append(piece.relative)
        steps.append({"file": piece.relative, "action": "created",
                      "purpose": piece.purpose})

    autoexec = root / AUTOEXEC
    if not outcome.autoexec_exists:
        autoexec.parent.mkdir(parents=True, exist_ok=True)
        autoexec.write_text(_autoexec_text(folder, outcome.pieces), encoding="utf-8")
        created.append(AUTOEXEC)
        steps.append({"file": AUTOEXEC, "action": "created",
                      "purpose": "execs the files above at startup"})
    else:
        # An autoexec that was already there is the player's. Each new file
        # gets an exec line added to it; nothing else about it is touched.
        if session is not None and created:
            session.add(autoexec)
        for relative in created:
            if relative == AUTOEXEC:
                continue
            result = cfgsource.ensure_exec(autoexec, cfg_root, root / relative)
            if result.get("changed"):
                steps.append({"file": AUTOEXEC, "action": result["action"],
                              "purpose": f"so {relative} runs"})

    return {
        "ok": True,
        "created": created,
        "steps": steps,
        "folder": str(root),
        "binds_file": BINDS_FILE,
        "launch_target": outcome.launch_target,
        "already": not created,
    }

def launch_exec_path(cfg_root, folder: str, generated: str) -> str:
    """What the Steam launch options should exec, in Windows path form.

    The autoexec when there is one, because it is what execs everything else
    -- aliases, settings, binds, and the generated performance file too.

    Pointing the launch options straight at the generated file instead loads
    the performance settings and nothing else. On an account that already had
    an autoexec the launch options usually already named it and were carried
    across untouched, so this never showed; on a fresh one there is nothing to
    carry across, the generated file becomes the entry point, and the player's
    binds silently never run.

    Falls back to the generated file only when there is genuinely no autoexec.
    """
    try:
        if (Path(cfg_root) / folder / AUTOEXEC).is_file():
            return f"{folder}\\{AUTOEXEC}"
    except OSError:
        pass
    return f"{folder}\\{generated}"
