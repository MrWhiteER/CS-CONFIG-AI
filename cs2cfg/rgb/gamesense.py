"""SteelSeries, through GameSense in SteelSeries GG / Engine.

GG writes the address of its local server to coreProps.json. A game registers,
binds events to lighting handlers, and fires them; a heartbeat keeps the game
in control, and ``stop_game`` hands the lights back to GG.

GameSense paints per-key by HID usage id ("custom-zone-keys"), which is the
same numbering the configs use, so no key table is needed. Each colour on the
board becomes one event whose handler lists the keys of that colour.
"""

from __future__ import annotations

import json
import os
import urllib.error
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from .base import Provider, http_json
from .palette import RGB, Frame

GAME = "CS2CONFIG"
_EVENTS = ("KEYS_0", "KEYS_1", "KEYS_2", "KEYS_3", "KEYS_4", "KEYS_5")
# Every usage a full-size board can have that GameSense accepts.
ALL_KEYS = list(range(4, 102)) + list(range(224, 232))


def core_props() -> Optional[Path]:
    root = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
    for engine in ("SteelSeries Engine 3", "GG"):
        path = Path(root) / "SteelSeries" / engine / "coreProps.json"
        if path.is_file():
            return path
    return None


def _colour(c: RGB) -> dict:
    return {"red": c[0], "green": c[1], "blue": c[2]}


def groups(frame: Frame) -> List[tuple]:
    """[(colour, [usages...])], the base colour taking every unlisted key."""
    by_colour: Dict[RGB, List[int]] = defaultdict(list)
    for usage in ALL_KEYS:
        by_colour[frame.key(usage)].append(usage)
    return sorted(by_colour.items(), key=lambda kv: -len(kv[1]))


class GameSenseProvider(Provider):
    id = "steelseries"
    name = "SteelSeries GG"
    vendors = ("steelseries",)

    def __init__(self, props: Optional[Path] = None) -> None:
        super().__init__()
        self.props = props
        self.base_url: Optional[str] = None
        self._fired: List[str] = []

    def probe(self) -> bool:
        path = self.props or core_props()
        if not path:
            self.why = "SteelSeries GG is not installed"
            return False
        try:
            address = json.loads(path.read_text(encoding="utf-8")).get("address")
        except (OSError, ValueError):
            address = None
        if not address:
            self.why = "SteelSeries GG has not started its lighting server"
            return False
        self.base_url = "http://" + address
        try:
            http_json("POST", self.base_url + "/game_heartbeat", {"game": GAME}, timeout=1.5)
        except urllib.error.HTTPError:
            pass   # an HTTP error still means GG is there (game not known yet)
        except OSError:
            # The file outlives GG; only a server that answers counts.
            self.why = "SteelSeries GG is not running"
            return False
        self.why = ""
        return True

    def start(self) -> None:
        http_json("POST", self.base_url + "/game_metadata", {
            "game": GAME, "game_display_name": "CS2 Config",
            "developer": "CS2 Config", "deinitialize_timer_length_ms": 60000})
        self.active = True

    def apply(self, frame: Frame) -> None:
        fired = []
        for event, (colour, keys) in zip(_EVENTS, groups(frame)):
            http_json("POST", self.base_url + "/bind_game_event", {
                "game": GAME, "event": event, "value_optional": True,
                "handlers": [{"device-type": "rgb-per-key-zones",
                              "custom-zone-keys": keys, "mode": "color",
                              "color": _colour(colour)}]})
            fired.append(event)
        http_json("POST", self.base_url + "/bind_game_event", {
            "game": GAME, "event": "MOUSE", "value_optional": True,
            "handlers": [
                {"device-type": "mouse", "zone": "wheel", "mode": "color",
                 "color": _colour(frame.wheel)},
                {"device-type": "mouse", "zone": "logo", "mode": "color",
                 "color": _colour(frame.body)}]})
        fired.append("MOUSE")
        # Fewer colours than last time: drop the events nobody fires now, or
        # their keys would keep an old colour until GG times them out.
        for event in set(self._fired) - set(fired):
            http_json("POST", self.base_url + "/remove_game_event",
                      {"game": GAME, "event": event})
        self._fired = fired
        self._fire()

    def _fire(self) -> None:
        for event in self._fired:
            http_json("POST", self.base_url + "/game_event",
                      {"game": GAME, "event": event, "data": {"value": 1}})

    def keepalive(self) -> None:
        if self.active:
            http_json("POST", self.base_url + "/game_heartbeat", {"game": GAME})
            self._fire()

    def stop(self) -> None:
        was, self.active = self.active, False
        if was and self.base_url:
            try:
                http_json("POST", self.base_url + "/stop_game", {"game": GAME})
            except Exception:
                pass
