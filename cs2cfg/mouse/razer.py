"""Razer mice, straight over USB. No Synapse, no Razer DLLs, nothing launched.

Same 90-byte feature reports as the lighting (cs2cfg.rgb.razer_usb), with the
public command numbers openrazer and OpenRGB use:

    mouse speed   class 0x04: set 0x05, read 0x85
                  args: storage, x high, x low, y high, y low, 0, 0
    polling rate  class 0x00: set 0x05, read 0x85, one byte
                  (1 = 1000 Hz, 2 = 500 Hz, 8 = 125 Hz)
    newer mice    class 0x00: set 0x40, read 0xC0, (0, rate byte)
                  (1 = 8000 ... 8 = 1000, 0x10 = 500, 0x40 = 125 Hz)

Speed is written with "store" set, so the mouse keeps it in its own memory
(what Razer's own app does). The mouse's answer is read back each time, so
the app only ever shows what the mouse really uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..rgb import razer_usb
from ..rgb.razer_usb import REPORT_LEN, VENDOR, exchange, report
from .base import Brand, Reading

STORE = 0x01
OK, FAILED, TIMEOUT, UNSUPPORTED = 0x02, 0x03, 0x04, 0x05

POLL_OLD = {0x01: 1000, 0x02: 500, 0x08: 125}
POLL_NEW = {0x01: 8000, 0x02: 4000, 0x04: 2000, 0x08: 1000, 0x10: 500, 0x40: 125}


@dataclass(frozen=True)
class MouseModel:
    name: str
    connection: str          # "wireless" (USB receiver) or "cable"
    max_dpi: int
    max_poll: int = 1000     # highest rate offered without extra hardware


MICE: Dict[int, MouseModel] = {
    0x00DB: MouseModel("Cobra HyperSpeed", "wireless", 26000),
    0x00DA: MouseModel("Cobra HyperSpeed", "cable", 26000),
}

ASLEEP = "The mouse didn't answer. Move it to wake it up, then try again."


def dpi_report(dpi: int) -> bytes:
    hi, lo = (dpi >> 8) & 0xFF, dpi & 0xFF
    return report(0x04, 0x05, bytes((STORE, hi, lo, hi, lo, 0, 0)))


def dpi_read_report() -> bytes:
    return report(0x04, 0x85, bytes((STORE,)), size=0x07)


def poll_report(hz: int, new: bool, target: int = 0) -> bytes:
    if new:
        code = {v: k for k, v in POLL_NEW.items()}[hz]
        return report(0x00, 0x40, bytes((target, code)))
    code = {v: k for k, v in POLL_OLD.items()}[hz]
    return report(0x00, 0x05, bytes((code,)))


def poll_read_report(new: bool) -> bytes:
    return report(0x00, 0xC0, size=0x01) if new else report(0x00, 0x85, size=0x01)


def _args(answer: bytes) -> bytes:
    return answer[8:8 + 80] if len(answer) >= REPORT_LEN else b""


class _Mouse:
    def __init__(self, hid, info, pid: int) -> None:
        self.hid, self.info, self.pid = hid, info, pid
        model = MICE.get(pid)
        self.tested = model is not None
        self.model = model or MouseModel(f"mouse {pid:04X}", "", 20000)
        self.new_poll: Optional[bool] = None    # which polling command it takes

    @property
    def id(self) -> str:
        return f"razer-{self.pid:04x}"

    def _talk(self, data: bytes) -> Tuple[int, bytes]:
        handle = self.hid.Handle(self.info.path)
        try:
            answer = exchange(handle, data)
        finally:
            handle.close()
        if len(answer) < REPORT_LEN:
            return 0, b""
        return answer[0], _args(answer)

    def read_dpi(self) -> Optional[int]:
        status, args = self._talk(dpi_read_report())
        if status != OK:
            return None
        dpi = (args[1] << 8) | args[2]
        return dpi or None

    def read_poll(self) -> Optional[int]:
        tries = (True, False) if self.new_poll is None else (self.new_poll,)
        for new in tries:
            status, args = self._talk(poll_read_report(new))
            if status != OK:
                continue
            table = POLL_NEW if new else POLL_OLD
            code = (args[1] or args[0]) if new else args[0]
            if code in table:
                self.new_poll = new
                return table[code]
        return None

    def rates(self) -> Tuple[int, ...]:
        if self.new_poll is None:
            return ()
        table = POLL_NEW if self.new_poll else POLL_OLD
        return tuple(sorted(hz for hz in table.values() if hz <= self.model.max_poll))

    def reading(self, problem: str = "") -> Reading:
        dpi = poll = None
        try:
            dpi = self.read_dpi()
            poll = self.read_poll()
        except OSError:
            problem = problem or "The mouse could not be opened."
        if dpi is None and not problem:
            problem = ASLEEP
        return Reading(
            id=self.id, name="Razer " + self.model.name,
            connection=self.model.connection, dpi=dpi, poll=poll,
            max_dpi=self.model.max_dpi, rates=self.rates(),
            tested=self.tested, problem=problem)


class Razer(Brand):
    name = "Razer"

    def __init__(self, hid=None) -> None:
        if hid is None:
            from ..rgb import winhid as hid
        self.hid = hid

    def _mice(self) -> List[_Mouse]:
        by_pid: Dict[int, list] = {}
        for info in self.hid.devices(VENDOR):
            if info.feature_len == REPORT_LEN + 1:
                by_pid.setdefault(info.product_id, []).append(info)
        mice: List[_Mouse] = []
        for pid, infos in by_pid.items():
            if pid in razer_usb.MODELS and razer_usb.MODELS[pid].kind != "mouse":
                continue
            if pid not in MICE:
                usage = next((i.usage for i in infos if i.usage_page == 1), 0)
                if usage != 2:      # HID usage 2 = mouse; skip keyboards etc.
                    continue
            mice.append(_Mouse(self.hid, infos[0], pid))
        # A mouse on its cable with its receiver still plugged in shows up
        # twice. Both reach the same mouse; the cable answers faster.
        mice.sort(key=lambda m: m.model.connection != "cable")
        seen, out = set(), []
        for m in mice:
            if m.model.name not in seen:
                seen.add(m.model.name)
                out.append(m)
        return out

    def find(self) -> List[Reading]:
        return [m.reading() for m in self._mice()]

    def set(self, mouse_id: str, dpi: Optional[int] = None,
            poll: Optional[int] = None) -> Reading:
        mouse = next((m for m in self._mice() if m.id == mouse_id), None)
        if mouse is None:
            raise LookupError("That mouse isn't plugged in any more.")
        problem = ""
        if dpi is not None:
            dpi = max(100, min(int(dpi), mouse.model.max_dpi))
            status, _ = mouse._talk(dpi_report(dpi))
            if status != OK:
                problem = ASLEEP if status in (0, TIMEOUT, FAILED) else \
                    "This mouse doesn't let its speed be set from the app."
        if poll is not None and not problem:
            mouse.read_poll()
            if poll not in mouse.rates():
                problem = f"This mouse can't use {poll} Hz."
            else:
                targets = (0x00, 0x01) if mouse.new_poll else (0x00,)
                for target in targets:
                    mouse._talk(poll_report(poll, bool(mouse.new_poll), target))
                    if mouse.read_poll() == poll:
                        break
        return mouse.reading(problem)
