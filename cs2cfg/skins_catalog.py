"""Every weapon-and-finish combination CS2 has ever released, read fresh
from the account's own ``items_game.txt`` and its English localization file
-- both plain text, both inside the VPK the game already installed.

This builds *names and metadata only*: which paint kit goes on which weapon,
what it's called, how rare it is. Nothing here reads a model, a texture, or
anything else that would need rendering -- that is :mod:`cs2cfg.skin_render`,
and it only ever runs against a tool the user installed themselves. This
module answers one question -- "what skins exist" -- the same way a wiki
page would, from the same public KeyValues format :mod:`cs2cfg.vdf` already
reads elsewhere in this project.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List

from . import vpk

ITEMS_GAME_PATH = "scripts/items/items_game.txt"
LOCALIZATION_PATH = "resource/csgo_english.txt"

# items_game.txt's own rarity keys, mapped to the display name and colour
# Steam's own inventory shows for the same tier -- not a guess at the
# ordering the words suggest: checked against skins whose real tier is
# public knowledge (AWP | Dragon Lore and AK-47 | Redline among them) and
# confirmed from the account's own data, because the plain-English order
# the key names imply ("legendary" above "ancient") does not match Valve's
# actual tier order here.
RARITY = {
    "common": ("Consumer Grade", "#b0c3d9"),
    "uncommon": ("Industrial Grade", "#5e98d9"),
    "rare": ("Mil-Spec", "#4b69ff"),
    "ancient": ("Restricted", "#8847ff"),
    "mythical": ("Classified", "#d32ce6"),
    "legendary": ("Covert", "#eb4b4b"),
    "immortal": ("Contraband", "#e4ae39"),
}

CACHE_TTL = 3600.0  # this is game data, not live state -- an hour is plenty
_CACHE: Dict[str, Any] = {}


class CatalogError(RuntimeError):
    """The install could not be found, or its files could not be read."""


def _all_block_bodies(text: str, key: str) -> List[str]:
    """The ``{ ... }`` body of *every* top-level ``"key"`` sibling in the
    file, found by counting braces.

    items_game.txt does not keep one logical block in one place: Valve has
    repeatedly appended a brand new ``"paint_kits"`` (and
    ``"paint_kits_rarity"``) sibling further down the file rather than
    editing the existing one -- confirmed by finding real released skins
    sitting entirely outside the first occurrence. Reading only the first
    match silently drops everything appended later, so every occurrence is
    returned here and the caller merges them.
    """
    bodies: List[str] = []
    for header in re.finditer(r'"' + re.escape(key) + r'"\s*\r?\n\s*\{', text):
        start = header.end() - 1
        depth = 0
        i = start
        n = len(text)
        while i < n:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    bodies.append(text[start + 1:i])
                    break
            i += 1
    return bodies


def _unescape(value: str) -> str:
    return value.replace('\\"', '"').replace("\\n", " ").replace("\\\\", "\\")


def _lang_tokens(text: str) -> Dict[str, str]:
    tokens: Dict[str, str] = {}
    for m in re.finditer(r'"(#?[A-Za-z0-9_]+)"\s*"((?:[^"\\]|\\.)*)"', text):
        tokens[m.group(1).lstrip("#").lower()] = _unescape(m.group(2))
    return tokens


def _weapon_prefabs(text: str) -> Dict[str, Dict[str, str]]:
    """The economy's own weapon identifier -> display-name token and
    in-VPK model path, read straight off each weapon's prefab block.

    A handful of weapons share one ``item_class`` for two real guns that
    occupy the same loadout slot (M4A4/M4A1-S, P2000/USP-S, Desert
    Eagle/R8 Revolver) -- the collection lists that say which skins exist
    tell the two apart by ``anim_class`` instead, so that is the key here
    whenever a block has one, falling back to ``item_class`` for the
    ordinary one-gun-per-class case.
    """
    out: Dict[str, Dict[str, str]] = {}
    for m in re.finditer(r'"item_class"\s*"(weapon_[A-Za-z0-9_]+)"', text):
        window = text[m.end():m.end() + 800]
        name_m = re.search(r'"item_name"\s*"#?([A-Za-z0-9_]+)"', window)
        model_m = re.search(r'"model_player"\s*"([^"]+)"', window)
        if not (name_m and model_m):
            continue
        # anim_class, when a block has one, sits between item_class and
        # item_name -- never searched past item_name, or a short block
        # (no anim_class of its own) picks up the *next* weapon's instead.
        anim_m = re.search(r'"anim_class"\s*"(weapon_[A-Za-z0-9_]+)"', window[:name_m.start()])
        key = anim_m.group(1) if anim_m else m.group(1)
        out[key] = {
            "name_token": name_m.group(1).lower(),
            "model": model_m.group(1),
        }
    return out


def _paint_kits(text: str) -> Dict[str, Dict[str, Any]]:
    """Paint kit codename -> its display-name token and wear range,
    merged across every ``paint_kits`` sibling block in the file (see
    :func:`_all_block_bodies`)."""
    out: Dict[str, Dict[str, Any]] = {}
    for body in _all_block_bodies(text, "paint_kits"):
        for m in re.finditer(r'"\d+"\s*\r?\n\s*\{', body):
            depth2 = 1
            j = m.end()
            bn = len(body)
            while j < bn and depth2 > 0:
                if body[j] == "{":
                    depth2 += 1
                elif body[j] == "}":
                    depth2 -= 1
                j += 1
            chunk = body[m.end():j]
            name_m = re.search(r'"name"\s*"([A-Za-z0-9_]+)"', chunk)
            tag_m = re.search(r'"description_tag"\s*"#?([A-Za-z0-9_]+)"', chunk)
            if not name_m:
                continue
            min_m = re.search(r'"wear_remap_min"\s*"([0-9.]+)"', chunk)
            max_m = re.search(r'"wear_remap_max"\s*"([0-9.]+)"', chunk)
            out[name_m.group(1)] = {
                "name_token": tag_m.group(1).lower() if tag_m else "",
                "wear_min": float(min_m.group(1)) if min_m else 0.0,
                "wear_max": float(max_m.group(1)) if max_m else 1.0,
            }
    return out


def _rarities(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for body in _all_block_bodies(text, "paint_kits_rarity"):
        out.update(re.findall(r'"([A-Za-z0-9_]+)"\s*"([A-Za-z]+)"', body))
    return out


def _combos(text: str) -> List[tuple]:
    """Every ``[paintkit]weapon_class`` pair that has actually shipped as a
    real item -- read from the collection/crate contents lists, the one
    place items_game.txt enumerates combinations that exist rather than
    ones that are merely possible."""
    return re.findall(r'"\[([A-Za-z0-9_]+)\](weapon_[A-Za-z0-9_]+)"\s*"1"', text)


_LEAKED_TOKEN = re.compile(r'^paintkit_[a-z0-9_]+$', re.IGNORECASE)


def _looks_like_a_leaked_token(value: str) -> bool:
    """Whether a resolved display string is actually real text, or just
    another internal token name that leaked through.

    A handful of paint kits (a few of the cartel-camo, mastery and
    hyper_beast families) have their own ``description_tag`` miscopied in
    items_game.txt, pointing at a sibling skin's tag instead of their own
    -- confirmed by checking several by hand, all the same shape, clearly a
    copy-paste slip in Valve's own data rather than anything this gets to
    fix at the source. Real display text always has it below; this just
    keeps a leaked token (``PaintKit_whatever``, no spaces, the exact
    internal naming convention) from being shown as if it were a name.
    """
    return bool(_LEAKED_TOKEN.match(value))


def _load_text(dir_vpk: Path, internal_path: str) -> str:
    index = vpk.read_index(dir_vpk)
    entry = vpk.find(index, internal_path)
    if entry is None:
        raise CatalogError(f"{internal_path} was not found in {dir_vpk}")
    raw = vpk.read_file(dir_vpk, entry)
    return raw.decode("utf-8", "replace").lstrip("﻿")


def build(dir_vpk: Path, force: bool = False) -> List[Dict[str, Any]]:
    """Every weapon/finish combo CS2 has released, with a display name and
    rarity resolved. Cached in memory -- this is static game data, re-read
    only when the game itself updates or a refresh is explicitly asked for."""
    key = str(dir_vpk)
    cached = _CACHE.get(key)
    if cached and not force and time.time() - cached["at"] < CACHE_TTL:
        return cached["data"]

    items_text = _load_text(dir_vpk, ITEMS_GAME_PATH)
    lang_text = _load_text(dir_vpk, LOCALIZATION_PATH)

    tokens = _lang_tokens(lang_text)
    weapons = _weapon_prefabs(items_text)
    paint_kits = _paint_kits(items_text)
    rarity_keys = _rarities(items_text)

    # The same combo is often listed in more than one collection or case, so
    # this is keyed to collapse repeats rather than counting them twice.
    by_combo: Dict[tuple, Dict[str, Any]] = {}
    for paintkit_name, weapon_class in _combos(items_text):
        weapon = weapons.get(weapon_class)
        kit = paint_kits.get(paintkit_name)
        if not weapon or not kit:
            continue
        weapon_label = tokens.get(weapon["name_token"], weapon_class)
        skin_label = tokens.get(kit["name_token"], paintkit_name)
        if _looks_like_a_leaked_token(skin_label):
            skin_label = paintkit_name
        rarity_key = rarity_keys.get(paintkit_name, "")
        rarity_name, rarity_color = RARITY.get(rarity_key, ("", "#4b4b4b"))
        by_combo[(weapon_class, paintkit_name)] = {
            "weapon_class": weapon_class,
            "weapon_name": weapon_label,
            "paintkit": paintkit_name,
            "skin_name": skin_label,
            "display_name": f"{weapon_label} | {skin_label}",
            "rarity": rarity_name,
            "rarity_color": rarity_color,
            "wear_min": kit["wear_min"],
            "wear_max": kit["wear_max"],
            "model": weapon["model"],
        }

    out = sorted(by_combo.values(), key=lambda it: (it["weapon_name"], it["skin_name"]))
    _CACHE[key] = {"at": time.time(), "data": out}
    return out


def forget_all() -> None:
    _CACHE.clear()


GROUPS = ["Rifle", "Pistol", "SMG", "Shotgun", "Sniper Rifle", "Machine Gun"]

_WEAPON_GROUP = {
    "weapon_ak47": "Rifle", "weapon_aug": "Rifle", "weapon_famas": "Rifle",
    "weapon_galilar": "Rifle", "weapon_m4a1": "Rifle", "weapon_m4a1_silencer": "Rifle",
    "weapon_sg556": "Rifle", "weapon_sg553": "Rifle",
    "weapon_deagle": "Pistol", "weapon_elite": "Pistol", "weapon_fiveseven": "Pistol",
    "weapon_glock": "Pistol", "weapon_hkp2000": "Pistol", "weapon_p250": "Pistol",
    "weapon_tec9": "Pistol", "weapon_cz75a": "Pistol", "weapon_usp_silencer": "Pistol",
    "weapon_revolver": "Pistol", "weapon_taser": "Pistol",
    "weapon_bizon": "SMG", "weapon_mac10": "SMG", "weapon_mp7": "SMG",
    "weapon_mp9": "SMG", "weapon_p90": "SMG", "weapon_ump45": "SMG", "weapon_mp5sd": "SMG",
    "weapon_mag7": "Shotgun", "weapon_nova": "Shotgun", "weapon_sawedoff": "Shotgun",
    "weapon_xm1014": "Shotgun",
    "weapon_awp": "Sniper Rifle", "weapon_g3sg1": "Sniper Rifle",
    "weapon_scar20": "Sniper Rifle", "weapon_ssg08": "Sniper Rifle",
    "weapon_m249": "Machine Gun", "weapon_negev": "Machine Gun",
}


def group_of(weapon_class: str) -> str:
    return _WEAPON_GROUP.get(weapon_class, "Other")
