"""Razer Chroma, through the Chroma SDK's local REST server.

Synapse runs this server itself (http://localhost:54235), so nothing needs to
be installed and nothing needs administrator. Registering returns a session
URI; effects are PUT to it, a heartbeat keeps it alive (the SDK drops a
session after 15 seconds of silence), and DELETE ends it, at which point
Synapse puts back whatever lighting the user had before.

Colours are BGR integers (0x00BBGGRR), as the SDK expects.
"""

from __future__ import annotations

import time
from typing import Optional

from . import keymaps
from .base import Provider, http_json
from .palette import RGB, Frame

ROOT = "http://localhost:54235/razer/chromasdk"

APP_INFO = {
    "title": "CS2 Config",
    "description": "Lights each key with the colour of its CS2 binding",
    "author": {"name": "CS2 Config", "contact": "https://github.com/MrWhiteER/CS-CONFIG-AI"},
    "device_supported": ["keyboard", "mouse"],
    "category": "application",
}


def bgr(colour: RGB) -> int:
    r, g, b = colour
    return (b << 16) | (g << 8) | r


def keyboard_grid(frame: Frame) -> list:
    grid = [[bgr(frame.base)] * keymaps.RAZER_COLS for _ in range(keymaps.RAZER_ROWS)]
    for usage, (row, col) in keymaps.RAZER.items():
        grid[row][col] = bgr(frame.key(usage))
    return grid


def mouse_grid(frame: Frame) -> list:
    grid = [[bgr(frame.body)] * keymaps.RAZER_MOUSE_COLS
            for _ in range(keymaps.RAZER_MOUSE_ROWS)]
    row, col = keymaps.RAZER_MOUSE_WHEEL
    grid[row][col] = bgr(frame.wheel)
    return grid


class ChromaProvider(Provider):
    id = "razer"
    name = "Razer Chroma"
    vendors = ("razer",)

    def __init__(self, root: str = ROOT, settle: float = 1.0) -> None:
        super().__init__()
        self.root = root
        self.settle = settle
        self.uri: Optional[str] = None

    def probe(self) -> bool:
        try:
            info = http_json("GET", self.root, timeout=1.5)
        except OSError:
            self.why = "Razer Synapse's Chroma SDK is not running"
            return False
        if not isinstance(info, dict) or "version" not in info:
            self.why = "Chroma SDK answered, but not as expected"
            return False
        self.why = ""
        self.devices = [f"Chroma SDK {info.get('version')}"]
        return True

    def start(self) -> None:
        reply = http_json("POST", self.root, APP_INFO, timeout=3.0)
        uri = isinstance(reply, dict) and reply.get("uri")
        if not uri:
            raise OSError(f"Chroma SDK refused the session: {reply!r}")
        self.uri = uri.rstrip("/")
        # The session's own server takes a moment to come up after init.
        if self.settle:
            time.sleep(self.settle)
        self.active = True

    def apply(self, frame: Frame) -> None:
        if not self.uri:
            return
        http_json("PUT", self.uri + "/keyboard",
                  {"effect": "CHROMA_CUSTOM", "param": keyboard_grid(frame)})
        http_json("PUT", self.uri + "/mouse",
                  {"effect": "CHROMA_CUSTOM2", "param": mouse_grid(frame)})

    def keepalive(self) -> None:
        if self.uri:
            http_json("PUT", self.uri + "/heartbeat")

    def stop(self) -> None:
        uri, self.uri = self.uri, None
        self.active = False
        if uri:
            try:
                http_json("DELETE", uri)
            except OSError:
                pass   # Synapse drops a silent session on its own after 15 s
