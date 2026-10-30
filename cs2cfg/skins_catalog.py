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


# Knife skins are not enumerable the way weapon skins are: a weapon's
# finishes come from a fixed collection/case list in items_game.txt, but
# any of a fixed, well-known set of "universal" finishes can go on any
# knife (how a case actually picks one at unbox time), and no such list
# is enumerated anywhere in the file. These codenames were each confirmed
# individually against the account's own data -- resolved by searching the
# localization file for the finish's real, public display name (the
# ordinary flow: "Case Hardened" is sold under that name, so the file has
# to contain it, under a #PaintKit_<codename>_Tag key -- that pattern
# already matches everything built on in this module) and matching the
# codename back from the tag -- not guessed from memory. Ruby/Sapphire/
# Black Pearl Dopplers and knife-specific style variants are not included.
KNIFE_FINISHES = {
    "aq_oiled": "Case Hardened",
    "aa_fade": "Fade",
    "an_tiger_orange": "Tiger Tooth",
    "am_marble_fade": "Marble Fade",
    "hy_webs": "Crimson Web",
    "aq_damascus": "Damascus Steel",
    "am_marked_up": "Freehand",
    "aq_steel_bravo": "Rust Coat",
    "am_zebra": "Slaughter",
    "hy_ocean": "Bright Water",
    "so_purple": "Ultraviolet",
    "aq_forced": "Stained",
    "aq_blued": "Blue Steel",
    "so_night": "Night",
    "hy_forest_boreal": "Boreal Forest",
    "sp_tape_urban": "Urban Masked",
    "sp_mesh_tan": "Safari Mesh",
    "sp_dapple": "Scorched",
    "hy_ak47lam_bw": "Black Laminate",
    "gs_autotronic": "Autotronic",
    "am_doppler_phase1": "Doppler (Phase 1)",
    "am_doppler_phase2": "Doppler (Phase 2)",
    "am_doppler_phase3": "Doppler (Phase 3)",
    "am_doppler_phase4": "Doppler (Phase 4)",
    "am_gamma_doppler_phase1": "Gamma Doppler (Phase 1)",
    "am_gamma_doppler_phase2": "Gamma Doppler (Phase 2)",
    "am_gamma_doppler_phase3": "Gamma Doppler (Phase 3)",
    "am_gamma_doppler_phase4": "Gamma Doppler (Phase 4)",
}

# Every real knife model, read straight from items_game.txt's own weapon
# prefabs the same way cs2cfg.skins_catalog._weapon_prefabs reads guns --
# listed here because a knife's item_class is not referenced from any
# collection's bracket syntax the way a gun's is, so _combos never finds it.
KNIFE_MODELS = {
    "weapon_bayonet": ("Bayonet", "weapons/models/knife/knife_bayonet/weapon_knife_bayonet.vmdl"),
    "weapon_knife_css": ("Classic Knife", "weapons/models/knife/knife_css/weapon_knife_css.vmdl"),
    "weapon_knife_flip": ("Flip Knife", "weapons/models/knife/knife_flip/weapon_knife_flip.vmdl"),
    "weapon_knife_gut": ("Gut Knife", "weapons/models/knife/knife_gut/weapon_knife_gut.vmdl"),
    "weapon_knife_karambit": ("Karambit", "weapons/models/knife/knife_karambit/weapon_knife_karambit.vmdl"),
    "weapon_knife_m9_bayonet": ("M9 Bayonet", "weapons/models/knife/knife_m9/weapon_knife_m9.vmdl"),
    "weapon_knife_tactical": ("Huntsman Knife", "weapons/models/knife/knife_tactical/weapon_knife_tactical.vmdl"),
    "weapon_knife_falchion": ("Falchion Knife", "weapons/models/knife/knife_falchion/weapon_knife_falchion.vmdl"),
    "weapon_knife_survival_bowie": ("Bowie Knife", "weapons/models/knife/knife_bowie/weapon_knife_bowie.vmdl"),
    "weapon_knife_butterfly": ("Butterfly Knife", "weapons/models/knife/knife_butterfly/weapon_knife_butterfly.vmdl"),
    "weapon_knife_push": ("Shadow Daggers", "weapons/models/knife/knife_push/weapon_knife_push.vmdl"),
    "weapon_knife_cord": ("Paracord Knife", "weapons/models/knife/knife_cord/weapon_knife_cord.vmdl"),
    "weapon_knife_canis": ("Survival Knife", "weapons/models/knife/knife_canis/weapon_knife_canis.vmdl"),
    "weapon_knife_ursus": ("Ursus Knife", "weapons/models/knife/knife_ursus/weapon_knife_ursus.vmdl"),
    "weapon_knife_gypsy_jackknife": ("Navaja Knife", "weapons/models/knife/knife_navaja/weapon_knife_navaja.vmdl"),
    "weapon_knife_outdoor": ("Nomad Knife", "weapons/models/knife/knife_outdoor/weapon_knife_outdoor.vmdl"),
    "weapon_knife_stiletto": ("Stiletto Knife", "weapons/models/knife/knife_stiletto/weapon_knife_stiletto.vmdl"),
    "weapon_knife_widowmaker": ("Talon Knife", "weapons/models/knife/knife_talon/weapon_knife_talon.vmdl"),
    "weapon_knife_skeleton": ("Skeleton Knife", "weapons/models/knife/knife_skeleton/weapon_knife_skeleton.vmdl"),
    "weapon_knife_kukri": ("Kukri Knife", "weapons/models/knife/knife_kukri/weapon_knife_kukri.vmdl"),
}


def _knife_entries() -> List[Dict[str, Any]]:
    # A knife is always ★ Covert -- that is the knife's own rarity as an
    # item, independent of whichever tier the same finish happens to sit at
    # on a gun (reusing the gun's tier here would have shown "Consumer
    # Grade" knives, which do not exist).
    rarity_name, rarity_color = RARITY["legendary"]
    out: List[Dict[str, Any]] = []
    for weapon_class, (weapon_label, model) in KNIFE_MODELS.items():
        for paintkit_name, skin_label in KNIFE_FINISHES.items():
            out.append({
                "kind": "knife",
                "weapon_class": weapon_class,
                "weapon_name": weapon_label,
                "paintkit": paintkit_name,
                "skin_name": skin_label,
                "display_name": f"{weapon_label} | {skin_label}",
                "rarity": rarity_name,
                "rarity_color": rarity_color,
                "wear_min": 0.0,
                "wear_max": 1.0,
                "model": model,
            })
    return out


# Gloves are yet another shape again: unlike a gun's fixed collection list
# or a knife's "any universal finish on any knife", each glove finish is
# tied to exactly one specific glove model and nothing else -- there is no
# "Driver Gloves | Vice" the way there is no real reason to expect one.
# Nothing in items_game.txt lists these pairs directly (the same gap a
# knife has), so they were found the same deliberate way as everywhere
# else in this module: not guessed, but read back from a real pairing CS2
# itself writes out -- here, the generated preview-icon filenames under
# panorama/images/econ/default_generated/, each named
# "<model>_gloves_<finish>_heavy_png.vtex_c", which is the one place in
# the game's own data that actually states which finish belongs to which
# model. Every finish below was cross-checked against that file list and
# resolved to its real display name through the account's own paint_kits
# and localization data, the same path every other entry in this catalog
# takes. Bloodhound, Hydra, Broken Fang and Hand Wraps gloves do not
# appear in that generated-icon set (each is closer to a single fixed
# item than a model with swappable finishes) and are not included yet.
GLOVE_MODELS = {
    "glove_driver": ("Driver Gloves", "agents/models/shared/arms/glove_slick/glove_slick.vmdl"),
    "glove_specialist": ("Specialist Gloves", "agents/models/shared/arms/glove_specialist/glove_specialist.vmdl"),
    "glove_sport": ("Sport Gloves", "agents/models/shared/arms/glove_sporty/glove_sporty.vmdl"),
    "glove_moto": ("Moto Gloves", "agents/models/shared/arms/glove_motorcycle/glove_motorcycle.vmdl"),
}

# weapon_class (made up here -- gloves have no item_class of their own the
# way a weapon does) -> (paintkit codename, display name), read back from
# the generated-icon pairing described above.
GLOVE_FINISHES = {
    "glove_moto": [
        ("motorcycle_basic_black", "Eclipse"),
        ("motorcycle_basic_green_orange", "Turtle"),
        ("motorcycle_carbonfiber_red", "Blood Pressure"),
        ("motorcycle_checker_flag_blue_green", "Finish Line"),
        ("motorcycle_choco_boom", "POW!"),
        ("motorcycle_commando_ksk", "3rd Commando Company"),
        ("motorcycle_mint_triangle", "Spearmint"),
        ("motorcycle_mono_boom", "Boom!"),
        ("motorcycle_smoke", "Smoke Out"),
        ("motorcycle_triangle_blue", "Cool Mint"),
        ("motorcycle_trigrid_blue", "Polygon"),
        ("motorcycle_yellow_camo", "Transport"),
    ],
    "glove_driver": [
        ("glove_driver_brocade_crane_red", "Brocade Crane"),
        ("glove_driver_brocade_flower_red", "Brocade Flowers"),
        ("glove_driver_dragon_scale_red", "Dragon Fists"),
        ("glove_driver_embroidered_flowers_teal", "Garden"),
        ("glove_driver_knit_argyle_green", "Hand Sweaters"),
        ("glove_driver_ostrich_purple", "Plum Quill"),
        ("glove_driver_scallop_metallic_blue", "Seigaiha"),
        ("glove_driver_silk_dragon_white", "Wave Chaser"),
        ("slick_black", "Lunar Weave"),
        ("slick_jaguar_white", "Snow Leopard"),
        ("slick_jaguar_yellow", "Queen Jaguar"),
        ("slick_military", "Convoy"),
        ("slick_plaid_purple", "Imperial Plaid"),
        ("slick_red", "Crimson Weave"),
        ("slick_rezan", "Rezan the Red"),
        ("slick_snakeskin_white", "King Snake"),
        ("slick_snakeskin_yellow", "Diamondback"),
        ("slick_stitched_black_orange", "Overtake"),
        ("slick_stitched_black_white", "Black Tie"),
        ("slick_stitched_green_grey", "Racing Green"),
    ],
    "glove_specialist": [
        ("glove_specialist_abstract_green", "Lime Polycam"),
        ("glove_specialist_dragon_blue", "Cloud Chaser"),
        ("glove_specialist_graffiti_black", "Blackbook"),
        ("glove_specialist_quilted_black", "Chocolate Chesterfield"),
        ("glove_specialist_quilted_white", "Pillow Punchers"),
        ("glove_specialist_sunburst_red", "Sunburst"),
        ("glove_specialist_wave_blue", "Big Swell"),
        ("specialist_ddpat_green_camo", "Forest DDPAT"),
        ("specialist_emerald_web", "Emerald Web"),
        ("specialist_fade", "Fade"),
        ("specialist_fbi", "Field Agent"),
        ("specialist_forest_brown", "Buckshot"),
        ("specialist_kimono_diamonds_red", "Crimson Kimono"),
        ("specialist_marble_fade", "Marble Fade"),
        ("specialist_orange_white", "Foundation"),
        ("specialist_ricksaw_camo", "Lt. Commander"),
        ("specialist_tiger_orange", "Tiger Strike"),
        ("specialist_webs_red", "Crimson Web"),
        ("specialist_winterhex", "Mogul"),
    ],
    "glove_sport": [
        ("glove_sport_beadwork_diamonds_purple", "Violet Beadwork"),
        ("glove_sport_camo_winter", "Frosty"),
        ("glove_sport_flames_orange", "Blaze"),
        ("glove_sport_pinstripe_black", "Creme Pinstripe"),
        ("glove_sport_racer_red", "Red Racer"),
        ("glove_sport_tech_gradient_bright", "Ultra Violent"),
        ("glove_sport_velvet_red", "Occult"),
        ("sporty_black_webbing_yellow", "Omega"),
        ("sporty_blue_pink", "Vice"),
        ("sporty_green", "Hedge Maze"),
        ("sporty_houndstooth_red", "Scarlet Shamagh"),
        ("sporty_hunter", "Big Game"),
        ("sporty_jaguar", "Nocts"),
        ("sporty_light_blue", "Superconductor"),
        ("sporty_military", "Arid"),
        ("sporty_poison_frog_blue_white", "Amphibious"),
        ("sporty_poison_frog_red_green", "Bronze Morph"),
        ("sporty_purple", "Pandora's Box"),
        ("sporty_slingshot", "Slingshot"),
    ],
}


def _glove_entries() -> List[Dict[str, Any]]:
    # A glove is always ★ Covert too, the same reasoning as a knife.
    rarity_name, rarity_color = RARITY["legendary"]
    out: List[Dict[str, Any]] = []
    for weapon_class, (weapon_label, model) in GLOVE_MODELS.items():
        for paintkit_name, skin_label in GLOVE_FINISHES.get(weapon_class, []):
            out.append({
                "kind": "glove",
                "weapon_class": weapon_class,
                "weapon_name": weapon_label,
                "paintkit": paintkit_name,
                "skin_name": skin_label,
                "display_name": f"{weapon_label} | {skin_label}",
                "rarity": rarity_name,
                "rarity_color": rarity_color,
                "wear_min": 0.0,
                "wear_max": 1.0,
                "model": model,
            })
    return out


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
            "kind": "gun",
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
    out += sorted(_knife_entries(), key=lambda it: (it["weapon_name"], it["skin_name"]))
    out += sorted(_glove_entries(), key=lambda it: (it["weapon_name"], it["skin_name"]))
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
