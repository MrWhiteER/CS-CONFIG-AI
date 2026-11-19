"""Plain-word names for the user's own scripts.

A hand-written config names its blocks for the person who wrote it --
"RIFLES", "CUSTOM MATCH CONTROL", "ALIASES / CUSTOM ACTIONS" -- and its aliases
for typing -- ``!ak``, ``matchpause``, ``+invsmoke``. Neither says what pressing
the key will do. This module works that out from what each alias actually runs,
so the key picker can say "Buy AK-47" or "Pause / unpause the match" and keep
the raw command as small print underneath.

Order of preference for one alias:

1. what its body does, when every step is something recognised here
   (``buy ak47; give weapon_ak47`` -> "Buy AK-47");
2. the note written beside it in the file (``// Max health``), when it reads
   as a description rather than a reminder about keys;
3. the block's own title, made readable, when that title names a feature
   ("Game Volume") rather than a filing category ("GENERAL COMMAND ALIASES");
4. the alias name itself, made readable.

Read-only, and nothing here guesses at what an unknown command does: anything
not recognised falls through to the author's own words.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from . import maps

# --------------------------------------------------------------------------
# Item names, as the buy menu spells them. Keys are what ``buy`` and ``give``
# take, with any weapon_/item_ prefix removed.
# --------------------------------------------------------------------------
ITEMS = {
    "ak47": "AK-47", "m4a1": "M4A4", "m4a4": "M4A4", "m4a1_silencer": "M4A1-S",
    "m4a1_silencer_off": "M4A1-S", "aug": "AUG", "sg556": "SG 553",
    "galilar": "Galil AR", "famas": "FAMAS",
    "awp": "AWP", "ssg08": "SSG 08 (Scout)", "scar20": "SCAR-20", "g3sg1": "G3SG1",
    "mp9": "MP9", "mp7": "MP7", "mp5sd": "MP5-SD", "mac10": "MAC-10",
    "ump45": "UMP-45", "bizon": "PP-Bizon", "p90": "P90",
    "nova": "Nova", "xm1014": "XM1014", "mag7": "MAG-7", "sawedoff": "Sawed-Off",
    "m249": "M249", "negev": "Negev",
    "glock": "Glock-18", "usp_silencer": "USP-S", "usp_silencer_off": "USP-S",
    "hkp2000": "P2000", "p250": "P250", "deagle": "Desert Eagle",
    "revolver": "R8 Revolver", "cz75a": "CZ75-Auto", "fiveseven": "Five-SeveN",
    "tec9": "Tec-9", "elite": "Dual Berettas",
    "flashbang": "Flashbang", "smokegrenade": "Smoke grenade",
    "hegrenade": "HE grenade", "decoy": "Decoy grenade", "molotov": "Molotov",
    "incgrenade": "Incendiary grenade",
    "vest": "Kevlar vest", "kevlar": "Kevlar vest",
    "vesthelm": "Kevlar + helmet", "assaultsuit": "Kevlar + helmet",
    "defuser": "Defuse kit", "taser": "Zeus x27", "c4": "C4 bomb",
    "knife": "Knife", "snowball": "Snowball", "healthshot": "Healthshot",
}

# A step that names an engine command with a fixed meaning.
_PLAIN = {
    "disconnect": "Leave the server",
    "status": "Show server status",
    "clear": "Clear the console",
    "mp_pause_match": "Pause the match",
    "mp_unpause_match": "Unpause the match",
    "mp_restartgame": "Restart the match",
    "mp_warmup_end": "End warmup",
    "mp_warmup_start": "Start warmup",
    "mp_swapteams": "Swap teams",
    "givecurrentammo": "Refill ammo",
    "noclip": "Fly through walls",
    "god": "God mode",
    "buddha": "Can't die",
    "bot_add": "Add a bot",
    "bot_kick": "Kick all bots",
    "sv_rethrow_last_grenade": "Rethrow last grenade",
    "jpeg": "Take screenshot",
    "stopsound": "Stop all sounds",
    "buymenu": "Buy menu",
    "autobuy": "Auto-buy",
    "rebuy": "Buy same as last round",
    "drop": "Drop weapon",
    "lastinv": "Switch to last weapon",
    "toggleconsole": "Open console",
    "noclip_fixup": "Fly through walls",
    "kill": "Respawn (kill yourself)",
    "explode": "Respawn (kill yourself)",
    "record": "Start recording a demo",
    "stop": "Stop recording",
    "retry": "Reconnect to the server",
    "quit": "Quit the game",
}

# Settings a toggle commonly flips, phrased as the thing being turned on/off.
_SETTING = {
    "volume": "Game sound",
    "voice_modenable": "Voice chat",
    "voice_enable": "Voice chat",
    "voice_loopback": "Hear your own mic",
    "voice_scale": "Voice chat volume",
    "cl_mute_enemy_team": "Mute enemy team",
    "cl_showfps": "Show FPS",
    "r_drawworld": "See through walls",
    "host_timescale": "Game speed",
    "sv_cheats": "Cheats",
    "sv_infinite_ammo": "Infinite ammo",
    "sv_grenade_trajectory_prac_pipreview": "Grenade path preview",
    "sv_showimpacts": "Show bullet impacts",
    "cl_draw_only_deathnotices": "Hide the HUD",
    "cl_drawhud": "Show the HUD",
    "r_drawviewmodel": "Show your weapon",
    "cl_righthand": "Gun hand",
}

# Held commands, by what holding them does.
_HELD = {
    "+attack": "Shoot", "+attack2": "Right click", "+jump": "Jump",
    "+duck": "Crouch", "+sprint": "Walk", "+use": "Use",
    "+reload": "Reload", "+lookatweapon": "Inspect weapon",
    "+showscores": "Scoreboard", "+voicerecord": "Open mic",
    "+cl_show_team_equipment": "Show teammates' gear",
    "+forward": "Move forward", "+back": "Move backward",
    "+left": "Move left", "+right": "Move right",
}

# Words a banner uses to file things, not to name them. A title made only of
# these and connectors says nothing about what a single alias does.
_FILING = {
    "alias", "aliases", "custom", "general", "command", "commands", "action",
    "actions", "control", "controls", "settings", "setting", "misc", "other",
    "shortcuts", "shortcut", "scripts", "script", "binds", "bind", "tools",
    "utility", "utilities", "stuff", "extra", "extras", "match", "complete",
}
_CONNECTORS = {"/", "|", "&", "and", "-", "—", "+", "(", ")", "the", "of"}

# Notes about keys rather than about behaviour: "{BUTTON - NUM-DEL}".
_KEY_NOTE = re.compile(r"\{[^}]*\}|\bbutton\b|\bpress\b", re.IGNORECASE)

_STEP_SPLIT = re.compile(r";")


def _steps(body: str) -> List[str]:
    # A body missing its closing quote swallows the line's // note; drop it.
    body = re.split(r"\s//", body or "", maxsplit=1)[0]
    return [p.strip() for p in _STEP_SPLIT.split(body) if p.strip()]


def _map_name(raw: str) -> str:
    """'de_mirage' -> 'Mirage'. An old map is not renamed to its remake."""
    low = raw.lower().strip('"')
    if maps.canonical(low) == low or low in getattr(maps, "ALIASES", {}):
        return maps.display(low)
    return readable_alias(re.sub(r"^[a-z]{2}_", "", low))


_labels: Optional[Dict[str, str]] = None


def _catalogue_labels() -> Dict[str, str]:
    """The key picker's own names for engine commands, reused here."""
    global _labels
    if _labels is None:
        from . import commands
        _labels = {}
        for group in commands.catalogue().get("groups", []):
            for entry in group.get("commands", []):
                _labels[str(entry.get("command", "")).lower()] = entry.get("label", "")
    return _labels


def _head(step: str) -> str:
    return step.split()[0].strip('"').lower() if step.split() else ""


def _rest(step: str) -> str:
    parts = step.split(None, 1)
    return parts[1].strip().strip('"') if len(parts) > 1 else ""


def _item(token: str) -> Optional[str]:
    bare = token.lower().strip('"')
    for prefix in ("weapon_", "item_"):
        if bare.startswith(prefix):
            bare = bare[len(prefix):]
    return ITEMS.get(bare)


def _quote(text: str, limit: int = 32) -> str:
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return "“" + text + "”"


def _value_phrase(name: str, value: str) -> Optional[str]:
    label = _SETTING.get(name)
    if not label:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    if name == "host_timescale":
        if number > 1:
            return f"Speed up the game ×{value}"
        return "Normal game speed" if number == 1 else f"Slow the game to ×{value}"
    if name in ("voice_scale", "volume") and 0 < number < 1:
        return f"{label} {round(number * 100)}%"
    if name == "r_drawworld":
        return "See through walls" if number == 0 else "Normal view"
    return f"{label} {'on' if number else 'off'}"


def describe_step(step: str, bodies: Dict[str, str], depth: int = 0) -> Optional[str]:
    """One step of an alias, in words; None when it is chatter or unknown."""
    head = _head(step)
    rest = _rest(step)
    if not head or head in ("echo", "play", "playvol", "alias", "developer"):
        return ""          # chatter or plumbing: says nothing about behaviour
    if head in ("buy", "give"):
        name = _item(rest.split()[0]) if rest else None
        # "buy" spends money; "give" (practice servers) just hands it over.
        return f"{'Buy' if head == 'buy' else 'Get'} {name}" if name else None
    if head == "map" and rest:
        return f"Load map {_map_name(rest.split()[0])}"
    if head in ("say", "say_team") and rest:
        where = "team chat" if head == "say_team" else "chat"
        return f"Say in {where}: {_quote(rest)}"
    if head == "exec" and rest:
        file = rest.split()[0].strip('"').replace("\\", "/").rsplit("/", 1)[-1]
        file = re.sub(r"\.(v?cfg)$", "", file, flags=re.IGNORECASE)
        return f"Load the {file.replace('_', ' ')} config"
    if head == "toggle" and rest:
        name = rest.split()[0].lower()
        label = _SETTING.get(name)
        return f"{label} on/off" if label else None
    if head in _PLAIN:
        return _PLAIN[head]
    if head in _HELD:
        return _HELD[head]
    if head in _catalogue_labels():
        return _catalogue_labels()[head]
    if head.startswith("-"):
        return ""          # the release half of something already described
    if head == "ent_fire" and "kill" in rest.lower() and \
            ("projectile" in rest.lower() or "inferno" in rest.lower()):
        return "Remove thrown grenades"
    if head == "ent_fire" and "sethealth" in rest.lower():
        return "Set health to max"
    if head == "bind" and rest:
        return None
    if head in _SETTING and rest:
        return _value_phrase(head, rest.split()[0])
    # Another alias from the collection: describe what that one does, once.
    if head in bodies and depth < 2:
        return describe_body(bodies[head], bodies, depth + 1)
    return None


def describe_body(body: str, bodies: Dict[str, str], depth: int = 0) -> Optional[str]:
    """What a whole alias does, or None if any step is not understood."""
    phrases: List[str] = []
    buys: List[str] = []
    buying = False
    says_only = True
    for step in _steps(body):
        phrase = describe_step(step, bodies, depth)
        if phrase is None:
            return None
        if not phrase:
            continue
        if phrase.startswith(("Buy ", "Get ")):
            verb, item = phrase.split(" ", 1)
            buying = buying or verb == "Buy"
            if item not in buys:
                buys.append(item)
            continue
        if not phrase.startswith("Say in"):
            says_only = False
        if phrase not in phrases:
            phrases.append(phrase)
    if buys:
        verb = "Buy" if buying else "Get"
        if len(buys) > 3:
            phrases.insert(0, f"{verb} {len(buys)} items ({', '.join(buys[:3])}…)")
        else:
            phrases.insert(0, verb + " " + " + ".join(buys))
    if not phrases:
        return None
    # A script that does something and then announces it is named for the
    # doing, not the announcement.
    if not says_only:
        phrases = [p for p in phrases if not p.startswith("Say in")]
    # Silencing leftovers is housekeeping next to the real action.
    if len(phrases) > 1 and "Stop all sounds" in phrases:
        phrases.remove("Stop all sounds")
    if len(phrases) > 3:
        return None        # too much going on to name honestly in a line
    low = [p[:1].lower() + p[1:] for p in phrases[1:]]
    if not low:
        return phrases[0]
    return ", ".join([phrases[0]] + low[:-1]) + " and " + low[-1]


def readable_title(title: str) -> str:
    """'CUSTOM MATCH CONTROL' -> 'Custom match control'; mixed case kept."""
    text = re.sub(r"\s+", " ", (title or "").replace("_", " ")).strip(" -—/|")
    text = re.sub(r"\bScript\b", "", text, flags=re.IGNORECASE).strip()
    words = []
    for i, word in enumerate(text.split(" ")):
        parts = []
        for part in word.split("-"):
            letters = [c for c in part if c.isalpha()]
            # Short all-caps words are acronyms (AFK, HE, FPS); keep them.
            keep = 1 < len(letters) <= 3 and all(c.isupper() for c in letters)
            parts.append(part if keep else part.lower())
        word = "-".join(parts)
        if i == 0:
            word = word[:1].upper() + word[1:]
        words.append(word)
    return " ".join(words)


def is_filing_title(title: str) -> bool:
    words = re.findall(r"[A-Za-z]+|[/|&\-—+()]", (title or "").lower())
    meaningful = [w for w in words if w not in _CONNECTORS]
    return not meaningful or all(w in _FILING for w in meaningful) or \
        sum(w not in _FILING for w in meaningful) <= 0


def readable_alias(name: str) -> str:
    bare = name.lstrip("+-!").replace("_", " ").replace(".", " ")
    bare = re.sub(r"(?<=[a-z])(?=[0-9])", " ", bare).strip()
    return (bare[:1].upper() + bare[1:]) if bare else name


def _usable_comment(comment: str) -> Optional[str]:
    text = (comment or "").strip().lstrip("/").strip()
    if not text or _KEY_NOTE.search(text) or len(text) > 60:
        return None
    if text.lower().startswith(("alias to ", "initial ")):
        return None
    return text[:1].upper() + text[1:]


def _toggle_name(states: List[str], bodies: Dict[str, str]) -> Optional[str]:
    """'Pause the match' + 'Unpause the match' -> 'Pause / unpause the match'."""
    if len(states) != 2:
        return None
    # One state does something, the other only releases it: "X on/off".
    quiet = [_releases_only(bodies.get(s.lower(), "")) for s in states]
    if quiet.count(True) == 1:
        busy = states[quiet.index(False)]
        said = describe_body(bodies.get(busy.lower(), ""), bodies)
        return said + " on/off" if said and _single(said) else None
    said = [describe_body(bodies.get(s.lower(), ""), bodies) for s in states]
    if not all(said) or not all(_single(x) for x in said):
        return None
    a, b = said
    if a == b:
        return a
    # Shared tail ("the match"), different verb.
    ta, tb = a.split(" ", 1), b.split(" ", 1)
    if len(ta) == 2 and len(tb) == 2 and ta[1] == tb[1]:
        return f"{ta[0]} / {tb[0].lower()} {ta[1]}"
    # "Game sound on" / "Game sound off".
    for on, off in ((" on", " off"), (" off", " on")):
        if a.endswith(on) and b.endswith(off) and a[:-len(on)] == b[:-len(off)]:
            return a[:-len(on)] + " on/off"
    return None


def _releases_only(body: str) -> bool:
    """A toggle state that only lets go of what the other one holds."""
    steps = [_head(s) for s in _steps(body)]
    steps = [s for s in steps
             if s not in ("echo", "play", "playvol", "alias", "say", "say_team")]
    return bool(steps) and all(s.startswith("-") for s in steps)


def _single(phrase: str) -> bool:
    """One clear thing, short enough to put "on/off" after."""
    return "," not in phrase and " and " not in phrase


def feature_name(plugin, everything: Optional[Dict[str, str]] = None) -> str:
    """A name for a toggle, cycle or hold feature, as one entry.

    ``everything`` is every alias in the collection, so a step that calls an
    alias defined in another file can still be described.
    """
    bodies = dict(everything or {})
    bodies.update(getattr(plugin, "bodies", {}) or {})
    title = readable_title(plugin.name)
    filing = is_filing_title(plugin.name)
    entry = (plugin.entry or "").lower()

    if plugin.kind == "toggle":
        derived = _toggle_name(plugin.states, bodies)
        if derived:
            return derived
        name = title if not filing else (derived or readable_alias(plugin.entry))
        if not re.search(r"on/off|toggle", name, re.IGNORECASE):
            name += " on/off"
        return name

    if plugin.kind == "hold":
        if not filing:
            return title
        comment = _usable_comment(plugin.comments.get(entry, "")) if hasattr(plugin, "comments") else None
        return describe_body(bodies.get(entry, ""), bodies) or comment \
            or readable_alias(plugin.entry)

    if plugin.kind == "cycle":
        said = [describe_body(bodies.get(s.lower(), ""), bodies) or ""
                for s in plugin.states]
        if said and all(x.startswith("Say in") for x in said):
            return f"Say the next of {len(said)} chat lines"
        name = title if not filing else readable_alias(plugin.entry)
        return "Cycle: " + name[:1].lower() + name[1:]

    return title if not filing else readable_alias(plugin.entry)


def alias_name(alias: str, body: str, comment: str, block_title: str,
               bodies: Dict[str, str]) -> str:
    """A name for one plain alias in a block of shortcuts."""
    derived = describe_body(body, bodies)
    if derived:
        return derived
    note = _usable_comment(comment)
    if note:
        return note
    if not is_filing_title(block_title):
        return f"{readable_title(block_title)}: {readable_alias(alias)}"
    return readable_alias(alias)


def hold_name(name: str, bodies: Dict[str, str], everything: Dict[str, str]) -> str:
    """One held alias among several in a block: press, plus what release adds."""
    press = describe_body(bodies.get(name, ""), everything)
    if not press:
        return readable_alias(name)
    release = describe_body(bodies.get("-" + name[1:], ""), everything)
    if release:
        return f"{press}, then {release[:1].lower() + release[1:]} on release"
    return press


def is_shortcut(body: str, everything: Dict[str, str]) -> bool:
    """Worth offering on its own even when a bigger script also calls it.

    What another script calls is usually one of its moving parts: a key
    rebinder, or one of the lines a "say a random joke" cycle steps through.
    Anything that does a real thing on its own (buy, leave, load a map) stays.
    """
    said = describe_body(body, everything)
    return bool(said) and not said.startswith("Say in")
