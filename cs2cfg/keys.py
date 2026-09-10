"""Key names, and the scancodes this collection writes them as.

The configs bind by USB HID usage id -- ``scancode44`` for space, ``scancode9``
for F -- which is unreadable on a card and impossible to type from memory. The
browser reports a pressed key as a ``KeyboardEvent.code``, and those map onto
the same HID ids, so the two ends meet here.

Mouse buttons are not HID keyboard usages; the engine names them directly and
the configs already use those names, so they pass through unchanged.
"""

from __future__ import annotations

from typing import Dict, Optional

# KeyboardEvent.code -> USB HID keyboard usage id, which is what "scancodeNNN"
# counts in. Letters and digits are filled in below rather than spelled out.
_CODES: Dict[str, int] = {
    "Enter": 40, "Escape": 41, "Backspace": 42, "Tab": 43, "Space": 44,
    "Minus": 45, "Equal": 46, "BracketLeft": 47, "BracketRight": 48,
    "Backslash": 49, "Semicolon": 51, "Quote": 52, "Backquote": 53,
    "Comma": 54, "Period": 55, "Slash": 56, "CapsLock": 57,
    "PrintScreen": 70, "ScrollLock": 71, "Pause": 72,
    "Insert": 73, "Home": 74, "PageUp": 75, "Delete": 76, "End": 77,
    "PageDown": 78, "ArrowRight": 79, "ArrowLeft": 80, "ArrowDown": 81,
    "ArrowUp": 82, "NumLock": 83,
    "NumpadDivide": 84, "NumpadMultiply": 85, "NumpadSubtract": 86,
    "NumpadAdd": 87, "NumpadEnter": 88, "NumpadDecimal": 99,
    "ControlLeft": 224, "ShiftLeft": 225, "AltLeft": 226, "MetaLeft": 227,
    "ControlRight": 228, "ShiftRight": 229, "AltRight": 230, "MetaRight": 231,
}
for _i, _letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _CODES[f"Key{_letter}"] = 4 + _i
for _i in range(1, 10):
    _CODES[f"Digit{_i}"] = 29 + _i
_CODES["Digit0"] = 39
for _i in range(1, 13):
    _CODES[f"F{_i}"] = 57 + _i
for _i in range(1, 10):
    _CODES[f"Numpad{_i}"] = 88 + _i
_CODES["Numpad0"] = 98

# How each one reads on a card.
_LABELS: Dict[int, str] = {
    40: "Enter", 41: "Esc", 42: "Backspace", 43: "Tab", 44: "Space",
    45: "-", 46: "=", 47: "[", 48: "]", 49: "\\", 51: ";", 52: "'",
    53: "`", 54: ",", 55: ".", 56: "/", 57: "Caps",
    70: "PrtSc", 71: "ScrLk", 72: "Pause", 73: "Insert", 74: "Home",
    75: "PgUp", 76: "Delete", 77: "End", 78: "PgDn",
    79: "Right", 80: "Left", 81: "Down", 82: "Up", 83: "NumLk",
    84: "Num /", 85: "Num *", 86: "Num -", 87: "Num +", 88: "Num Enter",
    99: "Num .", 98: "Num 0",
    224: "L-Ctrl", 225: "L-Shift", 226: "L-Alt", 227: "L-Win",
    228: "R-Ctrl", 229: "R-Shift", 230: "R-Alt", 231: "R-Win",
}
for _i, _letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _LABELS[4 + _i] = _letter
for _i in range(1, 10):
    _LABELS[29 + _i] = str(_i)
_LABELS[39] = "0"
for _i in range(1, 13):
    _LABELS[57 + _i] = f"F{_i}"
for _i in range(1, 10):
    _LABELS[88 + _i] = f"Num {_i}"

# Names the engine uses directly, which the configs already write as-is.
DIRECT = {"mouse1", "mouse2", "mouse3", "mouse4", "mouse5",
          "mwheelup", "mwheeldown"}


def from_code(code: str) -> Optional[str]:
    """A browser KeyboardEvent.code as this collection would write the bind."""
    usage = _CODES.get(code)
    return f"scancode{usage}" if usage else None


def label(binding: str) -> str:
    """How a bind target reads on screen: 'scancode44' -> 'Space'."""
    binding = (binding or "").strip().strip('"')
    low = binding.lower()
    if low in DIRECT:
        return {"mouse1": "Mouse 1", "mouse2": "Mouse 2", "mouse3": "Mouse 3",
                "mouse4": "Mouse 4", "mouse5": "Mouse 5",
                "mwheelup": "Wheel Up", "mwheeldown": "Wheel Down"}[low]
    if low.startswith("scancode") and low[8:].isdigit():
        return _LABELS.get(int(low[8:]), binding)
    return binding.upper() if len(binding) == 1 else binding
