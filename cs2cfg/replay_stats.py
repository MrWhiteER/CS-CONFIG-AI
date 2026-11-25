"""Read the utility columns of the scoreboard from a local CS2 match demo."""
from __future__ import annotations

import bz2
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

MAX_DEMO = 2 * 1024 ** 3
PROPERTIES = {"enemies_flashed_total": "enemies_flashed",
              "utility_damage_total": "utility_damage"}


class ReplayError(ValueError):
    pass


@contextmanager
def _demo_file(path: Path):
    if path.suffix.lower() == ".dem":
        yield path
        return
    if not path.name.lower().endswith(".dem.bz2"):
        raise ReplayError("Choose a CS2 .dem or .dem.bz2 replay.")
    with TemporaryDirectory(prefix="cs2cfg-stats-") as scratch:
        demo = Path(scratch) / "match.dem"
        total = 0
        with bz2.open(path, "rb") as source, demo.open("wb") as output:
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_DEMO:
                    raise ReplayError("The unpacked demo is larger than 2 GB.")
                output.write(chunk)
        yield demo


def read(path: Path) -> dict:
    path = path.resolve()
    size = path.stat().st_size
    if not 0 < size <= MAX_DEMO:
        raise ReplayError("Choose a complete CS2 demo under 2 GB.")
    return _read(path, size, path.stat().st_mtime_ns)


@lru_cache(maxsize=8)
def _read(path: Path, _size: int, _modified: int) -> dict:
    try:
        from demoparser2 import DemoParser
    except (ImportError, OSError) as exc:
        raise ReplayError("This build is missing the CS2 replay reader.") from exc

    try:
        with _demo_file(path) as demo:
            parser = DemoParser(str(demo))
            header = parser.parse_header()
            rounds = parser.parse_event("round_end")
            if "tick" not in rounds or rounds.empty:
                raise ReplayError("This replay has no completed rounds.")
            # Totals update at a round boundary. Small snapshots on both
            # sides of each boundary also retain players who leave early.
            ticks = sorted({int(tick) + offset for tick in rounds["tick"].dropna()
                            for offset in (0, 1, 16, 64, 192)})
            rows = parser.parse_ticks(list(PROPERTIES), ticks=ticks)
    except ReplayError:
        raise
    except BaseException as exc:
        if not isinstance(exc, Exception) and type(exc).__name__ != "PanicException":
            raise
        raise ReplayError("This replay could not be read. Choose a complete CS2 match demo.") from exc

    if "tick" not in rows.columns:
        raise ReplayError("This demo does not contain the utility scoreboard totals.")
    players = {}
    for record in rows.sort_values("tick").to_dict("records"):
        steamid = str(record.get("steamid"))
        if len(steamid) != 17 or not steamid.isdecimal():
            continue
        player = players.setdefault(steamid, {"steamid": steamid, "name": ""})
        name = record.get("name")
        if isinstance(name, str) and name:
            player["name"] = name
        for source, key in PROPERTIES.items():
            try:
                number = int(record[source])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if number >= 0:
                player[key] = number

    players = [player for player in players.values()
               if any(key in player for key in PROPERTIES.values())]
    if not players:
        raise ReplayError("This demo does not contain the utility scoreboard totals.")
    return {"map": header.get("map_name", ""), "players": players}
