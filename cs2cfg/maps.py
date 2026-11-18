"""Plain names for CS2 maps and game modes.

The game, Steam and FACEIT all speak in ids: ``de_dust2``, ``cs_office``,
``scrimcomp2v2``. Nothing the user reads should look like that, so every
place that shows a map or a mode goes through here (the Stats tab has a
matching table in ``web/assets/faceit/dashboard.js``).

Unknown ids still read as words: ``de_new_map`` becomes "New Map".
"""

from __future__ import annotations

import re
from typing import Dict

# Map id -> the name CS2 itself shows.
MAPS: Dict[str, str] = {
    "de_dust2": "Dust II",
    "de_mirage": "Mirage",
    "de_inferno": "Inferno",
    "de_nuke": "Nuke",
    "de_ancient": "Ancient",
    "de_ancient_night": "Ancient Night",
    "de_anubis": "Anubis",
    "de_vertigo": "Vertigo",
    "de_overpass": "Overpass",
    "de_train": "Train",
    "de_cache": "Cache",
    "de_cbble": "Cobblestone",
    "de_tuscan": "Tuscan",
    "de_basalt": "Basalt",
    "de_edin": "Edin",
    "de_palais": "Palais",
    "de_whistle": "Whistle",
    "de_thera": "Thera",
    "de_mills": "Mills",
    "de_memento": "Memento",
    "de_assembly": "Assembly",
    "de_jura": "Jura",
    "de_grail": "Grail",
    "de_brewery": "Brewery",
    "de_dogtown": "Dogtown",
    "de_golden": "Golden",
    "de_rooftop": "Rooftop",
    "de_palacio": "Palacio",
    "de_shortdust": "Shortdust",
    "de_lake": "Lake",
    "de_bank": "Bank",
    "de_safehouse": "Safehouse",
    "de_sanctum": "Sanctum",
    "de_poseidon": "Poseidon",
    "de_stronghold": "Stronghold",
    "de_vineyard": "Vineyard",
    "de_overpass_night": "Overpass Night",
    "cs_italy": "Italy",
    "cs_office": "Office",
    "cs_agency": "Agency",
    "cs_militia": "Militia",
    "cs_assault": "Assault",
    "ar_baggage": "Baggage",
    "ar_shoots": "Shoots",
    "ar_shoots_night": "Shoots Night",
    "ar_pool_day": "Pool Day",
    "ar_lunacy": "Lunacy",
    "ar_monastery": "Monastery",
}

# Other ways the same maps get written (Steam's page, old saves).
ALIASES: Dict[str, str] = {
    "de_dustii": "de_dust2",
    "de_dust_ii": "de_dust2",
    "de_dust": "de_dust2",
    "de_cobblestone": "de_cbble",
    "de_italy": "cs_italy",
    "de_office": "cs_office",
    "de_agency": "cs_agency",
    "de_militia": "cs_militia",
    "de_baggage": "ar_baggage",
    "de_shoots": "ar_shoots",
    "de_pool_day": "ar_pool_day",
    "de_poolday": "ar_pool_day",
}

_BY_NAME = {re.sub(r"[^a-z0-9]", "", name.lower()): key for key, name in MAPS.items()}

# GSI / Steam / FACEIT mode values -> what CS2's menu calls them.
MODES: Dict[str, str] = {
    "premier": "Premier",
    "competitive": "Competitive",
    "scrimcomp2v2": "Wingman",
    "wingman": "Wingman",
    "casual": "Casual",
    "deathmatch": "Deathmatch",
    "gungameprogressive": "Arms Race",
    "armsrace": "Arms Race",
    "gungametrbomb": "Demolition",
    "survival": "Danger Zone",
    "cooperative": "Co-op",
    "coopmission": "Co-op Strike",
    "training": "Training",
    "custom": "Custom",
    "retakes": "Retakes",
    "skirmish": "War Games",
    "faceit": "FACEIT",
    "5v5": "5v5",
}

_PREFIX = re.compile(r"^(de|cs|ar|dz|gd|aim|fy|awp|mg|wp|coop|lobby)_", re.I)


def _key(text: str) -> str:
    text = str(text or "").strip().lower().replace("\\", "/")
    text = text.rsplit("/", 1)[-1]          # workshop/123456/de_x -> de_x
    return re.sub(r"\s+", "_", text)


def _known_suffix(flat: str) -> str:
    """'premierdustii' -> 'de_dust2': a known map name at the end of the text.

    Steam writes the mode first in the player's own language ("Премьер-режим
    Mirage"), so the map is whatever known name the line ends with."""
    best = ""
    for name in _BY_NAME:
        if len(name) >= 4 and flat.endswith(name) and len(name) > len(best):
            best = name
    return _BY_NAME.get(best, "")


def canonical(map_id: str) -> str:
    """Any spelling of a map -> one id (``de_dustii`` -> ``de_dust2``)."""
    key = _key(map_id)
    if not key:
        return ""
    if key in MAPS:
        return key
    if key in ALIASES:
        return ALIASES[key]
    flat = re.sub(r"[^a-z0-9]", "", _PREFIX.sub("", key))
    if flat in _BY_NAME:
        return _BY_NAME[flat]
    if "de_" + flat in ALIASES:
        return ALIASES["de_" + flat]
    found = _known_suffix(flat)
    if found:
        return found
    if not re.fullmatch(r"[a-z0-9_]+", key):
        # Letters from a translated label stuck to the name: keep the last
        # plain-Latin word, e.g. "de_премьер-режимbrandnew" -> "de_brandnew".
        tail = re.findall(r"[a-z0-9_]+", _PREFIX.sub("", key))
        key = "de_" + tail[-1].strip("_") if tail and tail[-1].strip("_") else ""
        return key
    return key if _PREFIX.match(key) or "_" in key else "de_" + key


def from_name(name: str) -> str:
    """A name as Steam writes it ('Dust II', 'Mirage') -> the map's id."""
    flat = re.sub(r"[^a-z0-9]", "", str(name or "").lower())
    if not flat:
        return ""
    if flat in _BY_NAME:
        return _BY_NAME[flat]
    found = _known_suffix(flat)
    if found:
        return found
    # An unknown map: its last plain-Latin words, after any translated label.
    words = re.findall(r"[a-z0-9]+", str(name).lower().split(" ", 1)[-1] if re.search(r"[^\x00-\x7f]", str(name)) else str(name).lower())
    if not words:
        return ""
    key = canonical("_".join(words))
    return key if _PREFIX.match(key) else "de_" + key


def display(map_id: str) -> str:
    """The name to show: 'Dust II', or the id made readable when unknown."""
    key = canonical(map_id)
    if not key:
        return "Unknown map"
    if key in MAPS:
        return MAPS[key]
    words = _PREFIX.sub("", key).replace("-", "_").split("_")
    return " ".join(w[:1].upper() + w[1:] for w in words if w) or "Unknown map"


def mode(raw: str) -> str:
    """'scrimcomp2v2' -> 'Wingman'. Unknown modes become plain words."""
    text = str(raw or "").strip()
    if not text:
        return ""
    known = MODES.get(re.sub(r"[\s_-]", "", text.lower()))
    if known:
        return known
    words = re.split(r"[\s_-]+", text)
    return " ".join(w[:1].upper() + w[1:].lower() for w in words if w)
