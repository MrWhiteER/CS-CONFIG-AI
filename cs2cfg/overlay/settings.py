"""Machine-wide overlay preferences; reading defaults starts no resources."""

from __future__ import annotations

FIELDS = ("fps", "one_percent_low", "frame_time_ms", "cpu_percent", "gpu_percent", "gpu_temp_c")
CORNERS = ("top_left", "top_right", "bottom_left", "bottom_right")
DEFAULTS = {
    "overlay_enabled": False,
    "overlay_corner": "top_left",
    "overlay_fields": list(FIELDS),
    "overlay_hotkey": "Ctrl+Alt+O",
    "overlay_sign_out_hint_dismissed": False,
}


def hotkey(value: str) -> tuple[int, int]:
    """Parse a modifier chord accepted by RegisterHotKey, with no repeat."""
    parts = str(value).split("+")
    modifiers = {"ctrl": 2, "alt": 1, "shift": 4}
    if len(parts) < 2 or len(parts) > 4:
        raise ValueError("Use Ctrl, Alt or Shift plus a letter, digit or F1-F24.")
    keys = [part.strip().casefold() for part in parts]
    if len(set(keys[:-1])) != len(keys[:-1]) or any(k not in modifiers for k in keys[:-1]):
        raise ValueError("Use Ctrl, Alt or Shift once each.")
    key = keys[-1].upper()
    if len(key) == 1 and key.isascii() and key.isalnum():
        code = ord(key)
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        code = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError("Use a letter, digit or F1-F24.")
    return 0x4000 | sum(modifiers[k] for k in keys[:-1]), code


def read(ui: dict | None = None, *, strict: bool = False) -> dict:
    ui = ui or {}
    out = {**DEFAULTS, "overlay_fields": list(FIELDS)}
    for key in DEFAULTS:
        if key not in ui:
            continue
        value = ui[key]
        valid = True
        if key in ("overlay_enabled", "overlay_sign_out_hint_dismissed"):
            valid = isinstance(value, bool)
        elif key == "overlay_corner":
            valid = value in CORNERS
        elif key == "overlay_fields":
            valid = (isinstance(value, list) and bool(value)
                     and all(isinstance(v, str) and v in FIELDS for v in value))
            if valid:
                value = list(dict.fromkeys(value))
        else:
            try:
                hotkey(value)
                valid = isinstance(value, str)
            except ValueError:
                valid = False
        if not valid:
            if strict:
                raise ValueError(f"Invalid {key}.")
            continue
        out[key] = value
    return out
