"""Build cs2cfg/knowledge/nvidia_settings.json from NVIDIA's NvApiDriverSettings.h.

The driver will not tell an app what the choices of a setting are called
(DRS_EnumAvailableSettingValues is refused), so the "Show all settings" list
takes them from NVIDIA's own published header (MIT licensed):
https://github.com/NVIDIA/nvapi/blob/main/NvApiDriverSettings.h

    python tools/gen_nvidia_settings.py path/to/NvApiDriverSettings.h

Run again after a new header is published; the output is committed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "cs2cfg" / "knowledge" / "nvidia_settings.json"

# Plain words for the parts of NVIDIA's value names, so a choice reads
# "Prefer maximum performance" and never "PREFERRED_PSTATE_PREFER_MAX".
WORDS = {
    "ON": "On", "OFF": "Off", "ENABLE": "On", "ENABLED": "On", "DISABLE": "Off",
    "DISABLED": "Off", "FORCEOFF": "Off", "FORCEON": "On", "PASSIVE": "Use the game's setting",
    "MAX": "maximum", "MIN": "minimum", "PREFER": "Prefer", "PERF": "performance",
    "HPERF": "High performance", "HQUAL": "High quality", "QUAL": "Quality",
    "HIGHQUALITY": "High quality", "HIGHPERFORMANCE": "High performance",
    "APP": "game", "CONTROLLED": "controlled", "AUTO": "Automatic",
}

# Hand-written names for the settings people actually change for CS2.
FRIENDLY = {
    0x1057EB71: ("Power management mode", {
        0x0: "Adaptive", 0x1: "Prefer maximum performance", 0x2: "Let the driver decide",
        0x3: "Prefer consistent performance", 0x4: "Prefer lowest power", 0x5: "Normal"}),
    0x00A879CF: ("Vertical sync", {
        0x60925292: "Use the game's setting", 0x08416747: "Off", 0x47814940: "On",
        0x18888888: "Fast", 0x32610244: "Half refresh rate", 0x71271021: "Third of refresh rate",
        0x13245256: "Quarter of refresh rate"}),
    0x007BA09E: ("Low latency mode (frames queued ahead)", {0: "Off (game decides)", 1: "On (1 frame)",
                                                           2: "2 frames", 3: "3 frames", 4: "4 frames"}),
    0x00CE2691: ("Texture filtering - Quality", {
        0xFFFFFFF6: "High quality", 0x0: "Quality", 0xA: "Performance", 0x14: "High performance"}),
    0x00E73211: ("Texture filtering - Anisotropic sample optimization", {0: "Off", 1: "On"}),
    0x002ECAF2: ("Texture filtering - Trilinear optimization", None),
    0x0019BB68: ("Texture filtering - Negative LOD bias", None),
    0x20C1221E: ("Threaded optimization", {0: "Automatic", 1: "On", 2: "Off"}),
    0x10835002: ("Max frame rate", {0: "Off"}),
    0x00198FFF: ("Shader cache", {0: "Off", 1: "On"}),
}

ID_LINE = re.compile(r"^\s*(\w+)_ID\s*=\s*(0x[0-9A-Fa-f]+),")
NAME_LINE = re.compile(r'^#define\s+(\w+)_STRING\s+L"(.*)"')
ENUM_START = re.compile(r"^enum EValues_(\w+)\s*\{")
ENUM_ITEM = re.compile(r"^\s*(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)U?\s*,?")


def words(member: str, prefix: str) -> str:
    rest = member[len(prefix) + 1:] if member.startswith(prefix + "_") else member
    parts = [WORDS.get(p, p.lower()) for p in rest.split("_") if p]
    text = " ".join(parts).strip()
    return text[:1].upper() + text[1:] if text else member


def parse(header: str) -> dict:
    names, ids, enums = {}, {}, {}
    current = None
    for line in header.splitlines():
        if m := NAME_LINE.match(line):
            names[m.group(1)] = m.group(2)
        elif m := ID_LINE.match(line):
            ids[m.group(1)] = int(m.group(2), 16)
        elif m := ENUM_START.match(line):
            current = m.group(1)
            enums[current] = []
        elif current and line.strip().startswith("}"):
            current = None
        elif current and (m := ENUM_ITEM.match(line)):
            enums[current].append((m.group(1), int(m.group(2), 0)))

    out = {}
    for key, setting_id in ids.items():
        name = names.get(key)
        if not name:
            continue
        items = enums.get(key, [])
        default = next((v for n, v in items if n == key + "_DEFAULT"), None)
        rng = {n[len(key) + 1:]: v for n, v in items if n in (key + "_MIN", key + "_MAX")}
        choices = {}
        for member, value in items:
            tail = member[len(key) + 1:]
            if tail in ("NUM_VALUES", "DEFAULT", "MIN", "MAX") or value in choices:
                continue
            choices[value] = words(member, key)
        friendly = FRIENDLY.get(setting_id)
        if friendly:
            name = friendly[0]
            if friendly[1]:
                choices = {**choices, **friendly[1]}
        entry = {"name": name}
        if choices:
            entry["choices"] = {f"{v:#x}": label for v, label in sorted(choices.items())}
        if "MIN" in rng and "MAX" in rng:
            entry["range"] = [rng["MIN"], rng["MAX"]]
        if default is not None:
            entry["default"] = f"{default:#x}"
        out[f"0x{setting_id:08X}"] = entry
    return out


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    table = parse(Path(argv[1]).read_text(encoding="utf-8", errors="replace"))
    OUT.write_text(json.dumps({"source": "NVIDIA nvapi NvApiDriverSettings.h (MIT)",
                               "settings": table}, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"{len(table)} settings -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
