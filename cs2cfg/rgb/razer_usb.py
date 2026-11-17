"""Razer keyboards and mice, straight over USB. No Synapse, no Razer DLLs.

Razer devices take lighting as 90-byte HID feature reports. The format is
public (it is what OpenRGB and openrazer use), so the app writes the reports
itself and nothing from Razer has to be installed or running.

Report layout (90 bytes, sent behind report id 0):
    0 status, 1 transaction id, 2-3 remaining packets, 4 protocol type,
    5 data size, 6 command class, 7 command id, 8-87 arguments,
    88 CRC (XOR of bytes 2-87), 89 reserved.

Keyboards get one "custom frame" row per report, then the custom-frame effect
switches the board over to it. Mice get one static colour for every LED,
which works without knowing how many LEDs a model has.

Nothing is stored on the device ("no store" everywhere), so unplugging or
rebooting brings back whatever the device kept itself. ``stop`` puts the
factory spectrum effect back straight away.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from . import keymaps
from .base import Provider
from .palette import RGB, Frame

VENDOR = 0x1532
REPORT_LEN = 90

NOSTORE = 0x00
ZERO_LED = 0x00
EFFECT_STATIC, EFFECT_SPECTRUM, EFFECT_CUSTOM = 0x01, 0x03, 0x08
STATUS_BUSY, STATUS_OK = 0x01, 0x02


@dataclass(frozen=True)
class Model:
    name: str
    kind: str              # "keyboard" or "mouse"
    rows: int = 6
    cols: int = 22
    tid: int = 0x1F        # transaction id the device answers to


# Known models. A Razer keyboard or mouse not listed is tried with the
# defaults for its kind and marked unverified in the status.
MODELS: Dict[int, Model] = {
    0x02A6: Model("Huntsman V3 Pro", "keyboard"),
    0x00DB: Model("Cobra HyperSpeed", "mouse"),
    0x00DA: Model("Cobra HyperSpeed", "mouse"),
}


def report(command_class: int, command_id: int, args: bytes = b"",
           tid: int = 0x1F, size: Optional[int] = None) -> bytes:
    """One 90-byte Razer report, CRC filled in."""
    if len(args) > 80:
        raise ValueError("Razer reports carry at most 80 bytes of arguments")
    buf = bytearray(REPORT_LEN)
    buf[1] = tid
    buf[5] = len(args) if size is None else size
    buf[6] = command_class
    buf[7] = command_id
    buf[8:8 + len(args)] = args
    crc = 0
    for b in buf[2:88]:
        crc ^= b
    buf[88] = crc
    return bytes(buf)


def frame_row(row: int, colours: List[RGB], tid: int = 0x1F) -> bytes:
    """Custom-frame data for one keyboard row (class 0x0F, id 0x03)."""
    stop = len(colours) - 1
    rgb = b"".join(bytes(c) for c in colours)
    return report(0x0F, 0x03, bytes((0, 0, row, 0, stop)) + rgb, tid)


def effect(effect_id: int, extra: bytes = b"", tid: int = 0x1F,
           size: Optional[int] = None) -> bytes:
    """Switch the whole device to an effect (class 0x0F, id 0x02)."""
    return report(0x0F, 0x02, bytes((NOSTORE, ZERO_LED, effect_id)) + extra, tid, size)


def custom_frame_on(tid: int = 0x1F) -> bytes:
    return effect(EFFECT_CUSTOM, tid=tid, size=0x0C)


def static(colour: RGB, tid: int = 0x1F) -> bytes:
    return effect(EFFECT_STATIC, bytes((0, 0, 1)) + bytes(colour), tid)


def spectrum(tid: int = 0x1F) -> bytes:
    return effect(EFFECT_SPECTRUM, tid=tid, size=0x06)


def keyboard_rows(frame: Frame, rows: int, cols: int) -> List[List[RGB]]:
    grid = [[frame.base] * cols for _ in range(rows)]
    for usage, (row, col) in keymaps.RAZER.items():
        if row < rows and col < cols:
            grid[row][col] = frame.key(usage)
    return grid


class _Device:
    def __init__(self, handle, model: Model, pid: int, known: bool) -> None:
        self.handle, self.model, self.pid, self.known = handle, model, pid, known

    def send(self, data: bytes) -> None:
        """Send one report and wait until the device has taken it.

        The firmware answers "busy" (0x01) while it works; a wireless mouse
        stays busy for several milliseconds, a wired keyboard for about one.
        Sending the next report before then drops it, so the answer is read
        back until it is anything but busy, for at most ~50 ms.
        """
        self.handle.set_feature(b"\0" + data)
        for _ in range(25):
            time.sleep(0.002)
            try:
                status = self.handle.get_feature(REPORT_LEN + 1)[1]
            except (OSError, IndexError):
                return
            if status != STATUS_BUSY:
                return

    @property
    def label(self) -> str:
        return f"Razer {self.model.name}" + ("" if self.known else " (untested model)")


def _model_for(pid: int, usage: int) -> tuple:
    if pid in MODELS:
        return MODELS[pid], True
    # HID usage 6 = keyboard, 2 = mouse, on the device's main collection.
    kind = "keyboard" if usage == 6 else "mouse"
    return Model(f"device {pid:04X}", kind), False


class RazerUsbProvider(Provider):
    id = "razer-usb"
    name = "Razer (direct USB)"
    vendors = ("razer",)

    def __init__(self, hid=None) -> None:
        super().__init__()
        if hid is None:
            from . import winhid as hid
        self.hid = hid
        self.found: List[_Device] = []

    def _candidates(self) -> Dict[int, list]:
        """PID -> HID collections that carry Razer's 90-byte feature report."""
        by_pid: Dict[int, list] = {}
        for info in self.hid.devices(VENDOR):
            if info.feature_len == REPORT_LEN + 1:
                by_pid.setdefault(info.product_id, []).append(info)
        return by_pid

    def probe(self) -> bool:
        try:
            pids = self._candidates()
        except OSError as exc:
            self.why = f"USB devices could not be listed: {exc}"
            return False
        if not pids:
            self.why = "No Razer keyboard or mouse found over USB"
            return False
        self.why = ""
        return True

    def start(self) -> None:
        devices: List[_Device] = []
        for pid, infos in self._candidates().items():
            usage = next((i.usage for i in infos if i.usage_page == 1), 0)
            model, known = _model_for(pid, usage)
            for info in infos:
                try:
                    handle = self.hid.Handle(info.path)
                except OSError:
                    continue
                devices.append(_Device(handle, model, pid, known))
                break
        if not devices:
            raise OSError("Razer devices are present but none could be opened")
        self.found = devices
        self.devices = [d.label for d in devices]
        self.active = True

    def apply(self, frame: Frame) -> None:
        for d in self.found:
            m = d.model
            if m.kind == "keyboard":
                for row, colours in enumerate(keyboard_rows(frame, m.rows, m.cols)):
                    d.send(frame_row(row, colours, m.tid))
                d.send(custom_frame_on(m.tid))
            else:
                d.send(static(frame.body, m.tid))

    def stop(self) -> None:
        found, self.found = self.found, []
        self.active = False
        for d in found:
            try:
                d.send(spectrum(d.model.tid))
            except OSError:
                pass
            finally:
                d.handle.close()
