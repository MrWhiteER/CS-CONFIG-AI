"""What CS2 itself currently has set, as opposed to what the configs say.

There are two answers to "what is F bound to". The config files say what would
happen if they were exec'd. The game's own files say what is actually bound
right now, and the two disagree more often than people expect:

* a bind made in the game's settings menu never touches a config file
* a config that is not exec'd -- a missing launch option, a renamed folder --
  describes a machine state that does not exist
* the game writes its files on exit, so they also carry anything changed
  during the last session

CS2 keeps them per account, under ``userdata/<id>/730/local/cfg``, and writes
them when it shuts down. This reads them. Nothing here writes: the game owns
these files, and it rewrites them wholesale on exit, so anything put there
while it is running would be lost anyway.

Key names are the game's own -- ``MOUSE4``, ``f``, ``MWHEELUP`` -- the same
spelling as its default binds file, so they are normalised through the same
function the rest of this collection uses and come out as the scancodes the
configs are written in.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from . import defaults, gamewatch, keys

KEYS_FILE = "cs2_user_keys_0_slot0.vcfg"
CONVARS_FILE = "cs2_user_convars_0_slot0.vcfg"
VIDEO_FILE = "cs2_video.txt"

# What CS2 writes for a key that has been deliberately cleared.
UNBOUND = "<unbound>"


def binds(folder: Path) -> Dict[str, str]:
    """Every key the game currently has bound, keyed as a config would write it.

    An empty mapping when the file is not there, which is normal: CS2 writes it
    on exit, so an account that has never played has none.
    """
    found = gamewatch._read_map(Path(folder) / KEYS_FILE, ("config", "bindings"))
    # The stick and mouse axes live in their own section. They are bindings
    # like any other -- a config sets yaw and pitch with the same syntax -- so
    # leaving them out reported every one as missing from the game.
    analog = gamewatch._read_map(Path(folder) / KEYS_FILE,
                                 ("config", "analogbindings"))
    if not found and not analog:
        return {}
    found = dict(found or {})
    found.update(analog or {})
    out: Dict[str, str] = {}
    for name, command in found.items():
        binding = defaults.normalise(str(name))
        value = str(command or "").strip()
        # The game writes this for a key deliberately cleared. Counting it as
        # a binding would claim the key does something when the file is saying
        # the opposite.
        if value.lower() == UNBOUND:
            continue
        if binding and value:
            out[binding] = value
    return out


def convars(folder: Path) -> Dict[str, str]:
    """Every setting the game currently holds for this account."""
    found = gamewatch._read_map(Path(folder) / CONVARS_FILE, ("config", "convars"))
    return {str(k): str(v) for k, v in (found or {}).items()}


def _same_command(one: str, two: str) -> bool:
    """Whether two bind bodies do the same thing.

    Compared loosely on purpose. ``slot3; slot7`` and ``slot3;slot7`` are the
    same bind, and a difference in spacing or case is not worth reporting as a
    disagreement -- it would bury the ones that matter.
    """
    def tidy(value: str) -> str:
        parts = [p.strip() for p in str(value or "").strip().strip('"').split(";")]
        return ";".join(p for p in parts if p).lower()

    return tidy(one) == tidy(two)


def compare(live: Dict[str, str], configured: Dict[str, str]) -> List[Dict[str, Any]]:
    """Where the game and the configs disagree about a key.

    Three kinds, and they mean different things:

    * ``differs``  -- both have the key, running different things. Usually a
      bind made in the game since the config was last exec'd.
    * ``only_game``   -- bound in the game, absent from the configs. It will
      survive until something unbinds it, but nothing in the collection
      describes it.
    * ``only_config`` -- the config binds it and the game does not, which
      normally means the file never ran.
    """
    out: List[Dict[str, Any]] = []
    for binding in sorted(set(live) | set(configured)):
        in_game = live.get(binding)
        in_config = configured.get(binding)
        if in_game and in_config:
            if _same_command(in_game, in_config):
                continue
            kind = "differs"
        elif in_game:
            kind = "only_game"
        else:
            kind = "only_config"
        out.append({
            "key": binding,
            "label": keys.label(binding),
            "game": in_game or "",
            "config": in_config or "",
            "kind": kind,
        })
    return out


def summary(folder: Path, configured: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """What the game has, and how it lines up with the configs.

    ``configured`` is the effective bind per key as the collection would load
    it; leave it out to just read the game.
    """
    folder = Path(folder)
    in_game = binds(folder)
    settings = convars(folder)
    written = None
    source = folder / KEYS_FILE
    try:
        written = source.stat().st_mtime
    except OSError:
        written = None

    out: Dict[str, Any] = {
        "folder": str(folder),
        "available": bool(in_game),
        "written": written,
        "binds": in_game,
        "count": len(in_game),
        "settings": settings,
        "setting_count": len(settings),
    }
    if configured is not None:
        differences = compare(in_game, configured)
        out["differences"] = differences
        out["agrees"] = not differences
    return out
