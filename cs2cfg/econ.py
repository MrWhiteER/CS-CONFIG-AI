"""Everything in All Skins that is not a gun, knife or glove finish --
agents, stickers, graffiti, patches, charms and music kits -- plus the real
item pictures and music kit songs, all read from the player's own CS2
install at runtime.

Names, rarity and picture paths come from ``items_game.txt`` and the
English localization file, the same two files :mod:`cs2cfg.skins_catalog`
already reads. Pictures come from ``panorama/images/econ/...`` and songs
from ``sounds/music/<kit>/`` inside ``pak01_dir.vpk``. The app ships none of
these: a PC without CS2 gets the plain cards and no songs.
"""

from __future__ import annotations

import html
import re
import struct
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from . import vpk, vtex

Pairs = List[Tuple[str, Union[str, "Pairs"]]]

# --- a small KeyValues reader that keeps repeated keys --------------------

_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|(\{)|(\})|(//[^\n]*)')


def parse_kv(text: str) -> Pairs:
    """KeyValues text -> nested list of (key, value) pairs. Repeated keys
    are kept (items_game.txt repeats whole top-level blocks)."""
    stack: List[Pairs] = [[]]
    key: Optional[str] = None
    for m in _TOKEN.finditer(text):
        word, opened, closed, comment = m.groups()
        if comment is not None:
            continue
        if opened:
            child: Pairs = []
            stack[-1].append((key or "", child))
            stack.append(child)
            key = None
        elif closed:
            if len(stack) > 1:
                stack.pop()
            key = None
        elif key is None:
            key = word
        else:
            stack[-1].append((key, word))
            key = None
    return stack[0]


def get(pairs: Pairs, name: str, default: str = "") -> str:
    for k, v in pairs:
        if k.lower() == name and isinstance(v, str):
            return v
    return default


def child(pairs: Pairs, name: str) -> Pairs:
    for k, v in pairs:
        if k.lower() == name and isinstance(v, list):
            return v
    return []


def blocks(root: Pairs, name: str) -> Iterable[Pairs]:
    """Every top-level block called *name* under the file's root."""
    for _k, top in root:
        if isinstance(top, list):
            for k, v in top:
                if k.lower() == name and isinstance(v, list):
                    yield v


# --- rarity names per item type --------------------------------------------

_LEVEL = {"default": 0, "common": 1, "uncommon": 2, "rare": 3, "mythical": 4,
          "legendary": 5, "ancient": 6, "immortal": 7}
_COLOR = ["#6a6156", "#b0c3d9", "#5e98d9", "#4b69ff", "#8847ff", "#d32ce6", "#eb4b4b", "#e4ae39"]
_NAMES = {
    "agent": ["Stock", "Base Grade", "Industrial Grade", "Distinguished", "Exceptional",
              "Superior", "Master", "Contraband"],
    "other": ["Stock", "Base Grade", "Industrial Grade", "High Grade", "Remarkable",
              "Exotic", "Extraordinary", "Contraband"],
}


def rarity(kind: str, key: str) -> Tuple[str, str]:
    level = _LEVEL.get((key or "").lower())
    if level is None:
        return "", "#4b4b4b"
    return _NAMES["agent" if kind == "agent" else "other"][level], _COLOR[level]


# --- the extra item types ------------------------------------------------

_STYLE = re.compile(r"\((Holo|Foil|Gold|Glitter|Lenticular|Embroidered|Champion)\)", re.I)


def _style(name: str) -> str:
    m = _STYLE.search(name)
    return m.group(1).title() if m else "Paper"


def _say(tokens: Dict[str, str], token: str) -> str:
    # Some names carry HTML escapes ("ALLEYCVT &amp; LEVEL UP"); show the
    # plain character.
    return html.unescape(tokens.get(token.lstrip("#").lower(), ""))


def _safe(text: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_")[:120]


def _entry(kind: str, group_id: str, group_name: str, key: str, label: str,
           display: str, rarity_key: str, pictures: List[str]) -> Dict[str, Any]:
    name, color = rarity(kind, rarity_key)
    return {
        "kind": kind,
        "weapon_class": group_id,
        "weapon_name": group_name,
        "paintkit": key,
        "skin_name": label,
        "display_name": display,
        "rarity": name,
        "rarity_color": color,
        "wear_min": 0.0,
        "wear_max": 1.0,
        "model": "",
        "art": f"{kind}__{_safe(key)}",
        "_pictures": pictures,
    }


def agents(root: Pairs, tokens: Dict[str, str]) -> List[Dict[str, Any]]:
    out = []
    for body in blocks(root, "items"):
        for _id, item in body:
            if not isinstance(item, list) or get(item, "prefab") != "customplayertradable":
                continue
            name = _say(tokens, get(item, "item_name"))
            code = get(item, "name")
            if not name or not code:
                continue
            classes = child(item, "used_by_classes")
            side = ("t", "Terrorist") if get(classes, "terrorists") else ("ct", "Counter-Terrorist")
            picture = get(item, "image_inventory") or f"econ/characters/{code}"
            out.append(_entry("agent", side[0], side[1], code, name, name,
                              get(item, "item_rarity"), [f"panorama/images/{picture}_png.vtex_c"]))
    return out


def sticker_kits(root: Pairs, tokens: Dict[str, str]) -> List[Dict[str, Any]]:
    """Stickers, graffiti and patches: all three live in ``sticker_kits``."""
    out = []
    for body in blocks(root, "sticker_kits"):
        for _id, kit in body:
            if not isinstance(kit, list):
                continue
            code = get(kit, "name")
            token = get(kit, "item_name")
            label = _say(tokens, token)
            if not code or not label or code == "default":
                continue
            low = token.lower()
            patch = get(kit, "patch_material")
            material = get(kit, "sticker_material")
            if patch or low.startswith("#patchkit"):
                path = patch or material
                pictures = [f"panorama/images/econ/patches/{path}_png.vtex_c",
                            f"panorama/images/econ/patches/{path}_large_png.vtex_c"]
                out.append(_entry("patch", "patch", "Patch", code, label,
                                  f"Patch | {label}", get(kit, "item_rarity"), pictures))
                continue
            if not material:
                continue
            pictures = [f"panorama/images/econ/stickers/{material}_png.vtex_c",
                        f"panorama/images/econ/stickers/{material}_large_png.vtex_c"]
            if low.startswith("#spraykit") or code.startswith("spray_"):
                out.append(_entry("graffiti", "graffiti", "Graffiti", code, label,
                                  f"Graffiti | {label}", get(kit, "item_rarity"), pictures))
            else:
                style = _style(label)
                out.append(_entry("sticker", style.lower(), style, code, label,
                                  f"Sticker | {label}", get(kit, "item_rarity"), pictures))
    return out


def charms(root: Pairs, tokens: Dict[str, str]) -> List[Dict[str, Any]]:
    out = []
    for body in blocks(root, "keychain_definitions"):
        for _id, kc in body:
            if not isinstance(kc, list):
                continue
            code = get(kc, "name")
            label = _say(tokens, get(kc, "loc_name"))
            picture = get(kc, "image_inventory")
            if not code or not label:
                continue
            pictures = [f"panorama/images/{picture}_png.vtex_c"] if picture else []
            pictures.append(f"panorama/images/econ/keychains/{code}_png.vtex_c")
            # Tournament highlight charms have no picture of their own: they
            # show the event's charm ("base"), e.g. keychains/cologne2026/kc_cologne2026.
            base = get(kc, "base")
            if base:
                event = base[3:] if base.startswith("kc_") else base
                pictures.append(f"panorama/images/econ/keychains/{event}/{base}_png.vtex_c")
                pictures.append(f"panorama/images/econ/keychains/{base}_png.vtex_c")
            group = ("highlight", "Tournament highlight") if get(kc, "highlight_reel") else ("charm", "Charm")
            out.append(_entry("charm", group[0], group[1], code, label,
                              f"Charm | {label}", get(kc, "item_rarity"), pictures))
    return out


def music_kits(root: Pairs, tokens: Dict[str, str]) -> List[Dict[str, Any]]:
    out = []
    seen = set()
    for body in blocks(root, "music_definitions"):
        for _id, kit in body:
            if not isinstance(kit, list):
                continue
            code = get(kit, "name")
            title = _say(tokens, get(kit, "loc_name"))
            if not code or not title or code in seen:
                continue
            seen.add(code)
            artist = _say(tokens, get(kit, "loc_description"))
            # Some descriptions are a whole sentence about the song; only a
            # short line reads as an artist name.
            if len(artist) > 60 or "\n" in artist:
                artist = ""
            # The game names most kits "Artist, Song" in one line.
            if not artist and ", " in title:
                artist, title = title.split(", ", 1)
            picture = get(kit, "image_inventory") or f"econ/music_kits/{code}"
            entry = _entry("music", "music", "Music Kit", code, title,
                           f"Music Kit | {artist + ', ' if artist else ''}{title}", "rare",
                           [f"panorama/images/{picture}_png.vtex_c"])
            entry["artist"] = artist
            out.append(entry)
    out.sort(key=lambda e: e["skin_name"].lower())
    return out


def extra_items(items_text: str, tokens: Dict[str, str]) -> List[Dict[str, Any]]:
    root = parse_kv(items_text)
    out: List[Dict[str, Any]] = []
    for reader in (agents, sticker_kits, charms, music_kits):
        part = reader(root, tokens)
        if reader is not music_kits:
            part.sort(key=lambda e: (e["weapon_name"], e["skin_name"].lower()))
        out += part
    return out


# --- pictures --------------------------------------------------------------

GLOVE_PREFIX = {
    "glove_driver": "slick_gloves",
    "glove_specialist": "specialist_gloves",
    "glove_sport": "sporty_gloves",
    "glove_moto": "motorcycle_gloves",
}
GENERATED = "panorama/images/econ/default_generated/"


def finish_pictures(kind: str, weapon_class: str, paintkit: str) -> List[str]:
    """Where CS2 keeps the inventory picture of one gun/knife/glove finish."""
    base = GLOVE_PREFIX.get(weapon_class, weapon_class)
    return [f"{GENERATED}{base}_{paintkit}_{size}_png.vtex_c"
            for size in ("light", "medium", "heavy")]


_SAFE_ID = re.compile(r"^[a-z0-9_]{1,40}__[a-z0-9_]{1,200}$")
_lock = threading.Lock()
_NAMES_CACHE: Dict[str, Tuple[int, Dict[str, str]]] = {}


def _by_name(dir_vpk: Path, index: Dict[str, Any]) -> Dict[str, str]:
    """File name -> full path for every picture under panorama/images/econ,
    so a picture that moved to another folder is still found."""
    try:
        stamp = dir_vpk.stat().st_mtime_ns
    except OSError:
        stamp = 0
    cached = _NAMES_CACHE.get(str(dir_vpk))
    if cached and cached[0] == stamp:
        return cached[1]
    names: Dict[str, str] = {}
    for path in index:
        if path.startswith("panorama/images/econ/") and path.endswith(".vtex_c"):
            names.setdefault(path.rsplit("/", 1)[-1], path)
    _NAMES_CACHE[str(dir_vpk)] = (stamp, names)
    return names


def picture(dir_vpk: Optional[Path], cache_dir: Path, art_id: str,
            candidates: List[str]) -> Optional[Path]:
    """A PNG file with the item's real picture, or None."""
    if not _SAFE_ID.match(art_id or "") or not candidates:
        return None
    folder = Path(cache_dir) / "item-art"
    out = folder / f"{art_id}.png"
    missing = folder / f"{art_id}.none"
    try:
        stamp = dir_vpk.stat().st_mtime if dir_vpk is not None else 0
    except OSError:
        stamp = 0
    for done in (out, missing):
        try:
            if done.is_file() and (not stamp or done.stat().st_mtime >= stamp):
                return out if done is out else None
        except OSError:
            pass
    if not stamp:
        return None
    try:
        index = vpk.read_index(dir_vpk)
        entry = None
        for path in candidates:
            entry = index.get(path)
            if entry is not None:
                break
        if entry is None:
            names = _by_name(dir_vpk, index)
            for path in candidates:
                found = names.get(path.rsplit("/", 1)[-1])
                if found:
                    entry = index[found]
                    break
        png = vtex.picture(vpk.read_file(dir_vpk, entry)) if entry is not None else None
        with _lock:
            folder.mkdir(parents=True, exist_ok=True)
            if png is None:
                missing.write_bytes(b"")
                return None
            tmp = folder / f"{art_id}.{threading.get_ident()}.tmp"
            tmp.write_bytes(png)
            tmp.replace(out)
            missing.unlink(missing_ok=True)
        return out
    except (OSError, vpk.VpkError, KeyError):
        return None


# --- music kit songs -------------------------------------------------------

MUSIC_FOLDER = "sounds/music/"

# Song file name (without number) -> what the player hears it as, in the
# order a buyer cares about. The MVP song comes first: it is the part
# everyone else in the match hears.
PARTS = [
    ("roundmvpanthem", "MVP song"),
    ("mvpanthem", "MVP song"),
    ("mainmenu", "Main menu"),
    ("startround", "Round start"),
    ("startaction", "Action starts"),
    ("bombplanted", "Bomb planted"),
    ("bombtenseccount", "Bomb: last 10 seconds"),
    ("roundtenseccount", "Round: last 10 seconds"),
    ("wonround", "Round won"),
    ("lostround", "Round lost"),
    ("deathcam", "Death camera"),
    ("chooseteam", "Choosing a team"),
]
_PART_ORDER = {stem: i for i, (stem, _label) in enumerate(PARTS)}
_PART_LABEL = dict(PARTS)
_SONG_CACHE: Dict[str, Tuple[int, Dict[str, Dict[str, str]]]] = {}


def _songs_by_kit(dir_vpk: Path) -> Dict[str, Dict[str, str]]:
    """Kit folder (lower case) -> {song file name: full path in the VPK}."""
    try:
        stamp = dir_vpk.stat().st_mtime_ns
    except OSError:
        stamp = 0
    cached = _SONG_CACHE.get(str(dir_vpk))
    if cached and cached[0] == stamp:
        return cached[1]
    found: Dict[str, Dict[str, str]] = {}
    for path in vpk.read_index(dir_vpk):
        if path.startswith(MUSIC_FOLDER) and path.endswith(".vsnd_c"):
            rest = path[len(MUSIC_FOLDER):].split("/")
            if len(rest) == 2:
                found.setdefault(rest[0].lower(), {})[rest[1][:-len(".vsnd_c")]] = path
    _SONG_CACHE[str(dir_vpk)] = (stamp, found)
    return found


def _stem(name: str) -> str:
    return re.sub(r"(_?\d+)$", "", name.lower())


def song_parts(dir_vpk: Optional[Path], kit: str) -> List[Dict[str, str]]:
    """The song parts this kit has in the player's game files, MVP first."""
    if dir_vpk is None:
        return []
    try:
        files = list(_songs_by_kit(dir_vpk).get(kit.lower(), {}))
    except (OSError, vpk.VpkError):
        return []
    known = [f for f in files if _stem(f) in _PART_ORDER]
    known.sort(key=lambda f: (_PART_ORDER[_stem(f)], f))
    parts, counts = [], {}
    for f in known:
        label = _PART_LABEL[_stem(f)]
        counts[label] = counts.get(label, 0) + 1
        parts.append({"part": f, "label": label if counts[label] == 1 else f"{label} {counts[label]}"})
    return parts


_MP3_RATES = {
    3: (44100, 48000, 32000),   # MPEG 1
    2: (22050, 24000, 16000),   # MPEG 2
    0: (11025, 12000, 8000),    # MPEG 2.5
}
_MP3_KBPS_V1 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
_MP3_KBPS_V2 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)


def _mp3_frame(data: bytes, at: int) -> int:
    """Length of the MPEG layer III frame starting at *at*, or 0."""
    if at + 4 > len(data) or data[at] != 0xFF or (data[at + 1] & 0xE0) != 0xE0:
        return 0
    version = (data[at + 1] >> 3) & 3
    layer = (data[at + 1] >> 1) & 3
    rate_i = (data[at + 2] >> 2) & 3
    kbps_i = data[at + 2] >> 4
    if version == 1 or layer != 1 or rate_i == 3 or kbps_i in (0, 15):
        return 0
    rate = _MP3_RATES[version][rate_i]
    pad = (data[at + 2] >> 1) & 1
    if version == 3:
        return 144000 * _MP3_KBPS_V1[kbps_i] // rate + pad
    return 72000 * _MP3_KBPS_V2[kbps_i] // rate + pad


def _cut_mp3(data: bytes) -> Optional[bytes]:
    at = data.find(b"\xff")
    while 0 <= at < len(data) - 4:
        n, pos = 0, at
        while True:
            size = _mp3_frame(data, pos)
            if not size or pos + size > len(data):
                break
            pos += size
            n += 1
        if n >= 4:
            return data[at:pos]
        at = data.find(b"\xff", at + 1)
    return None


def _cut_wav(data: bytes) -> Optional[bytes]:
    at = data.find(b"RIFF")
    if at < 0 or data[at + 8:at + 12] != b"WAVE":
        return None
    size = struct.unpack_from("<I", data, at + 4)[0]
    return data[at:at + 8 + size]


def cut_song(data: bytes) -> Optional[Tuple[bytes, str]]:
    """The playable audio inside one compiled sound file, and its type."""
    wav = _cut_wav(data)
    if wav:
        return wav, "audio/wav"
    mp3 = _cut_mp3(data)
    if mp3:
        return mp3, "audio/mpeg"
    return None


def song(dir_vpk: Optional[Path], kit: str, part: str) -> Optional[Tuple[bytes, str]]:
    """One song part's audio, only for a part :func:`song_parts` lists."""
    if dir_vpk is None or part not in {p["part"] for p in song_parts(dir_vpk, kit)}:
        return None
    try:
        path = _songs_by_kit(dir_vpk).get(kit.lower(), {}).get(part)
        entry = vpk.read_index(dir_vpk).get(path) if path else None
        if entry is None:
            return None
        return cut_song(vpk.read_file(dir_vpk, entry))
    except (OSError, vpk.VpkError, struct.error):
        return None
