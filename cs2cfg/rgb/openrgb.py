"""Everything else, through OpenRGB's SDK server (TCP, port 6742).

OpenRGB drives Corsair, Logitech, ASUS, HyperX, Wooting, SteelSeries, Razer
and a few hundred more, once the user runs it with its SDK server on. This
speaks protocol version 0, which every OpenRGB release understands, and only
the five packets it needs.

Devices another backend already owns (Razer while Chroma is live, and so on)
are skipped, or the two would fight over the same LEDs every few seconds.

Before taking a device, its mode and colours are read; ``stop`` writes both
back, so the user's own effect returns.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import keymaps
from .base import Provider
from .palette import RGB, Frame

HOST, PORT = "127.0.0.1", 6742

REQUEST_CONTROLLER_COUNT = 0
REQUEST_CONTROLLER_DATA = 1
SET_CLIENT_NAME = 50
UPDATELEDS = 1050
UPDATEMODE = 1101
SETCUSTOMMODE = 1100

TYPE_KEYBOARD, TYPE_MOUSE = 5, 6


@dataclass
class Controller:
    index: int
    type: int
    name: str
    active_mode: int
    mode_block: bytes                 # the active mode, as sent, for restoring
    leds: List[str] = field(default_factory=list)
    colours: List[RGB] = field(default_factory=list)


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data, self.pos = data, 0

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise ValueError("controller data ended early")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def u16(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def text(self) -> str:
        return self.take(self.u16()).rstrip(b"\0").decode("utf-8", "replace")


def parse_controller(index: int, data: bytes) -> Controller:
    """Protocol 0 RGBController description -> the parts used here."""
    r = _Reader(data)
    r.u32()                                  # data size
    kind = r.i32()
    name = r.text()
    for _ in range(4):                       # description, version, serial, location
        r.text()
    num_modes = r.u16()
    active = r.i32()
    block = b""
    for m in range(num_modes):
        start = r.pos
        r.text()
        r.take(4 * 9)                        # value, flags, speeds, colours, ...
        r.take(4 * r.u16())
        if m == active:
            block = data[start:r.pos]
    for _ in range(r.u16()):                 # zones
        r.text()
        r.take(4 * 4)                        # type, leds min/max/count
        matrix = r.u16()
        r.take(matrix)
    leds = []
    for _ in range(r.u16()):
        leds.append(r.text())
        r.u32()
    colours = []
    for _ in range(r.u16()):
        red, green, blue, _pad = r.take(4)
        colours.append((red, green, blue))
    return Controller(index, kind, name, active, block, leds, colours)


def leds_payload(colours: List[RGB]) -> bytes:
    body = struct.pack("<H", len(colours)) + b"".join(
        bytes((r, g, b, 0)) for r, g, b in colours)
    return struct.pack("<I", 4 + len(body)) + body


def mode_payload(index: int, block: bytes) -> bytes:
    body = struct.pack("<i", index) + block
    return struct.pack("<I", 4 + len(body)) + body


def paint(ctrl: Controller, frame: Frame) -> Optional[List[RGB]]:
    """The colours for one controller, or None if it is not a key or a mouse."""
    if ctrl.type == TYPE_KEYBOARD or any(keymaps.openrgb_usage(n) for n in ctrl.leds):
        out = []
        for name in ctrl.leds:
            usage = keymaps.openrgb_usage(name)
            out.append(frame.key(usage) if usage else frame.base)
        return out
    if ctrl.type == TYPE_MOUSE:
        return [frame.wheel if keymaps.is_wheel(n) else frame.body for n in ctrl.leds]
    return None


class OpenRGBProvider(Provider):
    id = "openrgb"
    name = "OpenRGB"
    vendors = ()

    def __init__(self, host: str = HOST, port: int = PORT) -> None:
        super().__init__()
        self.host, self.port = host, port
        self.sock: Optional[socket.socket] = None
        self.skip_vendors: set = set()
        self.controllers: List[Controller] = []

    # -- wire ---------------------------------------------------------------
    def _send(self, pkt: int, payload: bytes = b"", dev: int = 0) -> None:
        self.sock.sendall(b"ORGB" + struct.pack("<III", dev, pkt, len(payload)) + payload)

    def _recv(self) -> Tuple[int, bytes]:
        head = self._exact(16)
        if head[:4] != b"ORGB":
            raise OSError("not an OpenRGB server")
        _dev, pkt, size = struct.unpack("<III", head[4:])
        return pkt, self._exact(size)

    def _exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise OSError("OpenRGB closed the connection")
            buf += chunk
        return buf

    def _connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=2.0)
        self._send(SET_CLIENT_NAME, b"CS2 Config\0")

    def _close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None

    # -- provider -----------------------------------------------------------
    def probe(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=0.5):
                pass
        except OSError:
            self.why = "OpenRGB is not running with its SDK server on"
            return False
        self.why = ""
        return True

    def start(self) -> None:
        self._connect()
        self._send(REQUEST_CONTROLLER_COUNT)
        _, data = self._recv()
        count = struct.unpack("<I", data[:4])[0]
        found = []
        for i in range(count):
            self._send(REQUEST_CONTROLLER_DATA, dev=i)
            _, blob = self._recv()
            try:
                ctrl = parse_controller(i, blob)
            except ValueError:
                continue
            if any(v in ctrl.name.lower() for v in self.skip_vendors):
                continue
            if paint(ctrl, Frame()) is None:
                continue
            found.append(ctrl)
        self.controllers = found
        self.devices = [c.name for c in found]
        for c in found:
            self._send(SETCUSTOMMODE, dev=c.index)
        self.active = True

    def apply(self, frame: Frame) -> None:
        for c in self.controllers:
            colours = paint(c, frame)
            if colours:
                self._send(UPDATELEDS, leds_payload(colours), dev=c.index)

    def stop(self) -> None:
        was, self.active = self.active, False
        try:
            if was and self.sock:
                for c in self.controllers:
                    if c.mode_block:
                        self._send(UPDATEMODE, mode_payload(c.active_mode, c.mode_block),
                                   dev=c.index)
                    if c.colours:
                        self._send(UPDATELEDS, leds_payload(c.colours), dev=c.index)
        except OSError:
            pass
        finally:
            self._close()
            self.controllers = []
