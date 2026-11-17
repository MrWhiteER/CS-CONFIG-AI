"""Where each key sits for each lighting API, keyed by USB HID usage id.

The configs, the keyboard tab and SteelSeries GameSense all count keys by HID
usage id already. Razer counts them by row and column on a 6 x 22 grid, and
OpenRGB names them ("Key: Left Shift"), so those two get a table each.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# --- Razer Chroma: CHROMA_CUSTOM keyboard grid, 6 rows x 22 columns ----------
# Positions follow Razer's RZKEY enum (high byte row, low byte column).
RAZER_ROWS, RAZER_COLS = 6, 22

_LETTER_USAGE = {c: 4 + i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}


def _letters(row: int, start: int, letters: str) -> Dict[int, Tuple[int, int]]:
    return {_LETTER_USAGE[c]: (row, start + i) for i, c in enumerate(letters)}


RAZER: Dict[int, Tuple[int, int]] = {
    # Row 0: Esc, F1-F12, PrtSc, ScrLk, Pause
    41: (0, 1), 70: (0, 15), 71: (0, 16), 72: (0, 17),
    **{57 + n: (0, 2 + n) for n in range(1, 13)},
    # Row 1: ` 1-0 - = Backspace | Ins Home PgUp | NumLk / * -
    53: (1, 1), **{29 + n: (1, 1 + n) for n in range(1, 10)}, 39: (1, 11),
    45: (1, 12), 46: (1, 13), 42: (1, 14), 73: (1, 15), 74: (1, 16),
    75: (1, 17), 83: (1, 18), 84: (1, 19), 85: (1, 20), 86: (1, 21),
    # Row 2: Tab Q-P [ ] \ | Del End PgDn | 7 8 9 +
    43: (2, 1), **_letters(2, 2, "QWERTYUIOP"), 47: (2, 12), 48: (2, 13),
    49: (2, 14), 76: (2, 15), 77: (2, 16), 78: (2, 17), 95: (2, 18),
    96: (2, 19), 97: (2, 20), 87: (2, 21),
    # Row 3: Caps A-L ; ' (ISO #) Enter | 4 5 6
    57: (3, 1), **_letters(3, 2, "ASDFGHJKL"), 51: (3, 11), 52: (3, 12),
    50: (3, 13), 40: (3, 14), 92: (3, 18), 93: (3, 19), 94: (3, 20),
    # Row 4: LShift (ISO \) Z-M , . / RShift | Up | 1 2 3 Enter
    225: (4, 1), 100: (4, 2), **_letters(4, 3, "ZXCVBNM"), 54: (4, 10),
    55: (4, 11), 56: (4, 12), 229: (4, 14), 82: (4, 16), 89: (4, 18),
    90: (4, 19), 91: (4, 20), 88: (4, 21),
    # Row 5: LCtrl LWin LAlt Space RAlt (Fn) Menu RCtrl | Left Down Right | 0 .
    224: (5, 1), 227: (5, 2), 226: (5, 3), 44: (5, 7), 230: (5, 11),
    101: (5, 13), 228: (5, 14), 80: (5, 15), 81: (5, 16), 79: (5, 17),
    98: (5, 19), 99: (5, 20),
}

# CHROMA_CUSTOM2 mouse grid, 9 rows x 7 columns. The scroll wheel is one cell;
# everything else (logo, side strips, underglow) is "body".
RAZER_MOUSE_ROWS, RAZER_MOUSE_COLS = 9, 7
RAZER_MOUSE_WHEEL = (2, 3)


# --- OpenRGB: LED names ---------------------------------------------------------
# OpenRGB's keyboard layouts name LEDs "Key: <name>". Names below are matched
# case-insensitively after the "Key: " prefix; several drivers spell a few keys
# differently, so some usages accept more than one name.
_OPENRGB_NAMES: Dict[int, Tuple[str, ...]] = {
    41: ("escape", "esc"), 70: ("print screen", "prtsc"), 71: ("scroll lock",),
    72: ("pause/break", "pause"), 53: ("`", "~"), 39: ("0",), 45: ("-",),
    46: ("=",), 42: ("backspace",), 73: ("insert",), 74: ("home",),
    75: ("page up",), 83: ("num lock",), 84: ("number pad /", "numpad /"),
    85: ("number pad *", "numpad *"), 86: ("number pad -", "numpad -"),
    43: ("tab",), 47: ("[",), 48: ("]",), 49: ("\\ (ansi)", "\\"),
    76: ("delete",), 77: ("end",), 78: ("page down",),
    87: ("number pad +", "numpad +"), 57: ("caps lock",), 51: (";",),
    52: ("'",), 50: ("#",), 40: ("enter",), 225: ("left shift",),
    100: ("\\ (iso)",), 54: (",",), 55: (".",), 56: ("/",),
    229: ("right shift",), 82: ("up arrow", "up"),
    88: ("number pad enter", "numpad enter"), 224: ("left control", "left ctrl"),
    227: ("left windows", "left win"), 226: ("left alt",), 44: ("space",),
    230: ("right alt",), 231: ("right windows", "right win"),
    101: ("menu", "context"), 228: ("right control", "right ctrl"),
    80: ("left arrow", "left"), 81: ("down arrow", "down"),
    79: ("right arrow", "right"), 98: ("number pad 0", "numpad 0"),
    99: ("number pad .", "numpad ."),
}
for _c, _u in _LETTER_USAGE.items():
    _OPENRGB_NAMES[_u] = (_c.lower(),)
for _n in range(1, 10):
    _OPENRGB_NAMES[29 + _n] = (str(_n),)
    _OPENRGB_NAMES[88 + _n] = (f"number pad {_n}", f"numpad {_n}")
for _n in range(1, 13):
    _OPENRGB_NAMES[57 + _n] = (f"f{_n}",)

OPENRGB_BY_NAME: Dict[str, int] = {
    name: usage for usage, names in _OPENRGB_NAMES.items() for name in names}


def openrgb_usage(led_name: str) -> Optional[int]:
    """"Key: Left Shift" -> 225; None for an LED that is not a known key."""
    name = (led_name or "").strip()
    if name.lower().startswith("key:"):
        name = name[4:]
    return OPENRGB_BY_NAME.get(name.strip().lower())


def is_wheel(led_name: str) -> bool:
    low = (led_name or "").lower()
    return "wheel" in low or "scroll" in low
