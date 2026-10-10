"""What is in the account's Steam inventory, read from Steam's own page.

Not the official Web API -- that needs a key tied to a Steam account, and
this application has no server of its own to keep one on. The page every
browser already loads when somebody opens their own inventory answers in
JSON if asked for it directly, needs nothing but a SteamID64, and works for
any inventory set to public (which an account's own always is, to itself).

Everything here is a read. Nothing in a Steam inventory is written by this
application, the same rule :mod:`cs2cfg.companions` holds about another
program's settings -- it is not this application's to touch.

What this deliberately does not do
-----------------------------------

It does not reach into the game's own files to pull out what an item sounds
or looks like. Steam's inventory page already gives an icon URL for every
item, server-side, and for anything that supports it -- weapon skins,
agents, knives -- an "Inspect in Game" link Steam itself built, parameters
and all. Both are used as Steam hands them over. What is not here is a
module that decompiles the game's own sound or model files to play or render
an item outside the game: that is a different kind of thing to build than
reading a public JSON page, and this project does not build it.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

TIMEOUT = 12.0
APP_ID = 730
CONTEXT_ID = 2

# Answers are kept warm briefly: the page that shows an inventory is checked
# on every tab open, and an inventory does not change from one look to the
# next unless a trade just happened.
CACHE_TTL = 90.0
_SEEN: Dict[str, Dict[str, Any]] = {}


def _user_agent() -> str:
    """Something that is not "Python-urllib". See cs2cfg.cloud for why this
    is not optional -- the third time this project has needed it."""
    from . import __version__

    return f"cs2-autoconfig/{__version__} (+https://github.com/MrWhiteER/CS-CONFIG-AI)"


def forget(steam_id64: int) -> None:
    _SEEN.pop(str(steam_id64), None)


def forget_all() -> None:
    _SEEN.clear()


def _tag_map(description: Dict[str, Any]) -> Dict[str, str]:
    """Steam's own tags, flattened from a list of category/name pairs into
    one dict -- 'Type' -> 'Music Kit', 'Exterior' -> 'Field-Tested', and so
    on. Whatever the item is, this is how its kind is told apart."""
    out: Dict[str, str] = {}
    for tag in description.get("tags") or []:
        category = tag.get("category")
        name = tag.get("localized_tag_name") or tag.get("internal_name")
        if category and name:
            out[category] = name
    return out


def _inspect_link(description: Dict[str, Any]) -> str:
    for action in (description.get("actions") or []) + (description.get("market_actions") or []):
        if "inspect" in str(action.get("link", "")).lower() or \
           "inspect" in str(action.get("name", "")).lower():
            return str(action.get("link") or "")
    return ""


def _icon_url(description: Dict[str, Any]) -> str:
    icon = description.get("icon_url_large") or description.get("icon_url")
    if not icon:
        return ""
    return f"https://community.cloudflare.steamstatic.com/economy/image/{icon}"


def _combine(assets: List[Dict[str, Any]],
            descriptions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Assets are *how many* and *which copy*; descriptions are *what it
    is*, shared by every copy of the same item. Steam links them by a pair
    of ids rather than repeating the description per copy."""
    by_key = {(d.get("classid"), d.get("instanceid", "0")): d for d in descriptions}
    out: List[Dict[str, Any]] = []
    for asset in assets:
        key = (asset.get("classid"), asset.get("instanceid", "0"))
        description = by_key.get(key)
        if description is None:
            continue
        tags = _tag_map(description)
        out.append({
            "asset_id": str(asset.get("assetid") or ""),
            "name": description.get("market_hash_name") or description.get("name") or "",
            "type": tags.get("Type", ""),
            "rarity": tags.get("Rarity", ""),
            "exterior": tags.get("Exterior", ""),
            "weapon": tags.get("Weapon", ""),
            "category": tags.get("ItemSet", ""),
            "stattrak": "StatTrak" in (description.get("name") or ""),
            "tradable": bool(description.get("tradable")),
            "marketable": bool(description.get("marketable")),
            "icon": _icon_url(description),
            "inspect": _inspect_link(description),
        })
    return out


def fetch(steam_id64: int, force: bool = False) -> Dict[str, Any]:
    """Everything in one account's CS2 inventory. Never raises."""
    key = str(steam_id64)
    cached = _SEEN.get(key)
    if cached and not force and time.time() - cached["at"] < CACHE_TTL:
        return cached["data"]

    # 5000 is the figure the community usually quotes as the ceiling, and it
    # is not: it gets a bare 400 from this endpoint when nothing else about
    # the request is wrong, measured against a real account rather than
    # assumed. 2000 is what is actually used, well past any inventory an
    # ordinary player holds; a very large one falls back to what "more" below
    # already reports rather than silently losing anything past the first page.
    url = (f"https://steamcommunity.com/inventory/{steam_id64}/{APP_ID}/"
          f"{CONTEXT_ID}?count=2000&l=english")
    request = urllib.request.Request(url, method="GET")
    request.add_header("accept", "application/json")
    request.add_header("user-agent", _user_agent())

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            raw = answer.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 401):
            result = {"ok": False, "private": True,
                     "error": "this inventory is private", "items": []}
        else:
            result = {"ok": False, "error": f"Steam said {exc.code}", "items": []}
        return result
    except urllib.error.URLError as exc:
        return {"ok": False, "error": f"could not reach Steam: {exc.reason}", "items": []}
    except OSError as exc:
        return {"ok": False, "error": f"could not reach Steam: {exc}", "items": []}

    try:
        data = json.loads(raw)
    except ValueError:
        return {"ok": False, "error": "Steam sent something that was not JSON", "items": []}

    if not isinstance(data, dict) or not data.get("success"):
        return {"ok": False, "error": "could not read that inventory", "items": []}

    items = _combine(data.get("assets") or [], data.get("descriptions") or [])
    result = {"ok": True, "items": items, "count": len(items),
              "more": bool(data.get("more_items"))}
    _SEEN[key] = {"at": time.time(), "data": result}
    return result


# Rough groupings for the page to sort into sections. An item whose Type tag
# matches none of these still shows up -- under "Other" -- rather than
# vanishing, because a tag Valve adds later should not make an owned item
# disappear from somebody's own inventory.
GROUPS: List[tuple] = [
    ("Weapon skins", lambda it: bool(it["weapon"]) and it["type"] not in ("Music Kit",)),
    ("Knives & gloves", lambda it: "Knife" in it["type"] or "Gloves" in it["type"]),
    ("Music kits", lambda it: it["type"] == "Music Kit"),
    ("Agents", lambda it: it["type"] == "Agent"),
    ("Stickers", lambda it: it["type"] == "Sticker"),
    ("Cases & keys", lambda it: it["type"] in ("Container", "Key")),
    ("Graffiti", lambda it: it["type"] == "Graffiti"),
    ("Patches & pins", lambda it: it["type"] in ("Patch", "Collectible")),
]


def grouped(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The same items, sorted into named sections for the page to render."""
    out = []
    claimed: set = set()
    for name, test in GROUPS:
        bucket = [it for it in items if id(it) not in claimed and test(it)]
        for it in bucket:
            claimed.add(id(it))
        if bucket:
            out.append({"name": name, "items": bucket})
    leftover = [it for it in items if id(it) not in claimed]
    if leftover:
        out.append({"name": "Other", "items": leftover})
    return out
