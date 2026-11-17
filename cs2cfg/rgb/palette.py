"""What colour each key should be, worked out the way the keyboard tab does it.

The keyboard tab colours a key by what is bound to it (cs2cfg/web/index.html,
``kbCap`` and the ``.kb-key.*`` styles). The lights on the desk are meant to
look like that board, so this module copies its rule rather than inventing a
second one: a script the collection runs is pink, a key changed on purpose is
gold, a key still doing what CS2 ships is blue, and a free key stays out of
the way.

The input is the ``bound`` mapping ``/api/cfg/keys`` returns. The output is a
``Frame``: one colour per USB HID usage id, plus the two lit areas a mouse
usually has. No device is touched here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

RGB = Tuple[int, int, int]

# The glow colour of each .kb-key state in index.html. These are the bright
# accents the board uses for its halo, not the darker cap gradients: an LED
# shows the colour of light, and the dark caps would read as nearly off.
COLOURS: Dict[str, RGB] = {
    "script": (255, 45, 149),      # .kb-key.script  -> rgba(255, 45, 149)
    "custom": (255, 183, 43),      # .kb-key.custom  -> rgba(255, 183, 43)
    "bound": (61, 139, 253),       # .kb-key.bound   -> rgba(61, 139, 253)
    "script_off": (60, 40, 52),    # .kb-key.script.off: greyed and dimmed
    "free": (14, 14, 20),          # .kb-key (free): barely there
}
OFF: RGB = (0, 0, 0)

# Which mouse state wins when a mouse's single body light has to stand for
# every button: the loudest one on the board, in the board's own order.
_LOUDNESS = ("script", "custom", "bound", "script_off", "free")

MOUSE_BUTTONS = ("mouse1", "mouse2", "mouse3", "mouse4", "mouse5",
                 "mwheelup", "mwheeldown")


def kind(entry: Optional[Mapping[str, Any]]) -> str:
    """The keyboard tab's class for one bound entry (mirrors ``kbCap``)."""
    if not entry:
        return "free"
    if entry.get("script"):
        return "script" if entry.get("enabled", True) else "script_off"
    if entry.get("is_default") is False:
        return "custom"
    return "bound"


def usage_of(binding: str) -> Optional[int]:
    """``scancode44`` / ``space`` / ``e`` -> 44 / 44 / 8; None for mouse names."""
    from ..defaults import normalise

    name = normalise(binding)
    if name.startswith("scancode") and name[8:].isdigit():
        return int(name[8:])
    return None


def _scale(colour: RGB, brightness: int) -> RGB:
    b = max(0, min(100, int(brightness)))
    return tuple(int(round(c * b / 100)) for c in colour)  # type: ignore[return-value]


@dataclass(frozen=True)
class Frame:
    """One full picture for the lights.

    ``keys`` holds every HID usage that has a binding; anything not listed is
    ``base``. ``wheel`` and ``body`` are the two lit areas found on most mice:
    the scroll wheel, and everything else (logo, strips, underglow).
    """

    keys: Dict[int, RGB] = field(default_factory=dict)
    base: RGB = OFF
    wheel: RGB = OFF
    body: RGB = OFF

    def key(self, usage: int) -> RGB:
        return self.keys.get(usage, self.base)


def frame(bound: Mapping[str, Mapping[str, Any]], *, free: str = "dim",
          brightness: int = 100) -> Frame:
    """Build the lighting for the board described by ``bound``."""
    base = OFF if free == "off" else COLOURS["free"]

    states: Dict[int, str] = {}
    mouse: Dict[str, str] = {}
    for name, entry in bound.items():
        state = kind(entry)
        low = (name or "").strip().strip('"').lower()
        if low in MOUSE_BUTTONS:
            mouse[low] = state
            continue
        usage = usage_of(low)
        if usage is None:
            continue
        # One key bound under two spellings: show the louder of the two, so a
        # script never hides behind a plain bind on the same key.
        prev = states.get(usage)
        if prev is None or _LOUDNESS.index(state) < _LOUDNESS.index(prev):
            states[usage] = state

    def colour_of(state: Optional[str]) -> RGB:
        if not state or state == "free":
            return base
        return COLOURS[state]

    # The wheel is what mouse3 and the two wheel directions are bound to.
    wheel_states = [mouse[b] for b in ("mouse3", "mwheelup", "mwheeldown") if b in mouse]
    wheel = min(wheel_states, key=_LOUDNESS.index) if wheel_states else None
    body_states = list(mouse.values())
    body = min(body_states, key=_LOUDNESS.index) if body_states else None

    return Frame(
        keys={u: _scale(colour_of(s), brightness) for u, s in states.items()},
        base=_scale(base, brightness),
        wheel=_scale(colour_of(wheel), brightness),
        body=_scale(colour_of(body), brightness),
    )
