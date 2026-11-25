"""Script Builder: put several actions on one key without writing any code.

The player picks steps from a list of plain-word actions, picks how the key
behaves, and picks a key. This module turns that into config lines -- and,
more importantly, refuses to turn it into config lines that would misbehave.

Three ways a hand-written script goes wrong, and what this does about each:

* **A held action that never lets go.** ``+duck`` in an alias that is not
  itself a ``+`` alias is pressed and never released: the player crouches
  until they die. Here a held action can only be used on a "while held" or
  "on / off" key, and the release half is always written from the press half,
  step for step, so the two can never disagree.
* **A combination CS2 no longer runs.** Since the August 2024 update CS2
  refuses binds that do more than one movement or attack action (jump +
  crouch, jump-throw, snap tap, null binds). Such a script loads without an
  error and then only half works in a match. It is detected -- through the
  player's own scripts too -- and explained instead of written.
* **Text that breaks the line.** A quote ends the alias early, a semicolon
  starts a new command and ``//`` turns the rest into a comment. Chat text is
  cleaned of all three, and the player is told when it was.

Nothing here touches the disk except :func:`write_block`, which returns the
new file text for the caller to save with a backup like every other write.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# The marker on the comment line that carries the builder's own description of
# a script. It lets the builder recognise -- and replace -- its own scripts
# without ever touching one the player wrote by hand.
MARK = "// Made with Script Builder: "

MODES = ("press", "hold", "toggle", "shift")
# How a shift key works: "next" = press it, and only the next press of the
# other key does the new thing; "hold" = while it is held down.
SHIFT_STYLES = ("next", "hold")

# Movement and attack actions, without their sign. CS2 runs at most one of
# these from one key since the August 2024 update. "speed" is the old name of
# "sprint" (walk), and "left"/"right" are the old turning actions.
MOVE_ACTIONS = {
    "forward", "back", "moveleft", "moveright", "left", "right",
    "jump", "duck", "sprint", "speed", "attack", "attack2",
    "reload", "use", "turnleft", "turnright", "turnup", "turndown",
    "moveup", "movedown", "klook", "strafe", "zoom", "yaw", "pitch",
    "forwardback", "rightleft",
}

MAX_STEPS = 12
MAX_NAME = 40
MAX_TEXT = 100
# CS2 cuts very long command lines. Well under the engine's limit, so a
# script never loads half-written.
MAX_LINE = 250

_SLUG = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------------------
# The steps a player can pick
# ---------------------------------------------------------------------------
# Most steps come from the Keyboard tab's own list (knowledge/
# bindable_commands.json), so a step is called the same thing everywhere in
# the app. These are the steps that list does not have: ones that need a bit
# of text or a number, and a few one-press shortcuts worth having by name.

def _use(weapon: str) -> str:
    return "use " + weapon


EXTRA_STEPS: List[Dict[str, Any]] = [
    # Talking
    {"id": "say_team", "group": "comms", "label": "Say to my team",
     "input": "text", "placeholder": "Dropping the bomb", "command": "say_team {text}",
     "says": "Writes “{text}” in team chat"},
    {"id": "say_all", "group": "comms", "label": "Say to everyone",
     "input": "text", "placeholder": "gg", "command": "say {text}",
     "says": "Writes “{text}” in chat to everyone"},
    {"id": "echo", "group": "comms", "label": "Show a note in the console",
     "input": "text", "placeholder": "Script on", "command": "echo {text}",
     "says": "Shows “{text}” in the console"},
    # Weapons, by name rather than by slot
    {"id": "drop_bomb", "group": "weapons", "label": "Drop the bomb",
     "command": _use("weapon_c4") + "; drop",
     "says": "Switches to the bomb and drops it",
     "note": "Only does something while you carry the bomb."},
    {"id": "use_flash", "group": "weapons", "label": "Take out a flashbang",
     "command": _use("weapon_flashbang"), "says": "Takes out a flashbang"},
    {"id": "use_smoke", "group": "weapons", "label": "Take out a smoke",
     "command": _use("weapon_smokegrenade"), "says": "Takes out a smoke"},
    {"id": "use_he", "group": "weapons", "label": "Take out a grenade (HE)",
     "command": _use("weapon_hegrenade"), "says": "Takes out an HE grenade"},
    {"id": "use_molotov", "group": "weapons", "label": "Take out a molotov",
     "command": _use("weapon_molotov") + "; " + _use("weapon_incgrenade"),
     "says": "Takes out a molotov or incendiary"},
    {"id": "use_decoy", "group": "weapons", "label": "Take out a decoy",
     "command": _use("weapon_decoy"), "says": "Takes out a decoy"},
    # Buying
    {"id": "buy_kevlar", "group": "buying", "label": "Buy armor and helmet",
     "command": "buy vesthelm; buy vest", "says": "Buys armor and a helmet"},
    {"id": "buy_kit", "group": "buying", "label": "Buy a defuse kit",
     "command": "buy defuser", "says": "Buys a defuse kit"},
    {"id": "buy_flash", "group": "buying", "label": "Buy a flashbang",
     "command": "buy flashbang", "says": "Buys a flashbang"},
    {"id": "buy_smoke", "group": "buying", "label": "Buy a smoke",
     "command": "buy smokegrenade", "says": "Buys a smoke"},
    {"id": "buy_he", "group": "buying", "label": "Buy a grenade (HE)",
     "command": "buy hegrenade", "says": "Buys an HE grenade"},
    {"id": "buy_molotov", "group": "buying", "label": "Buy a molotov",
     "command": "buy molotov; buy incgrenade", "says": "Buys a molotov or incendiary"},
    # Sound and mouse: a value while the key is held, then back
    {"id": "volume", "group": "sound", "label": "Set game volume",
     "input": "number", "setting": "volume", "min": 0, "max": 1, "step": 0.05,
     "default": 0.5, "back_default": 1,
     "command": "volume {value}", "release": "volume {back}",
     "says": "Sets game volume to {pct}"},
    {"id": "voice_volume", "group": "sound", "label": "Set voice chat volume",
     "input": "number", "setting": "snd_voipvolume", "min": 0, "max": 1, "step": 0.05,
     "default": 0.3, "back_default": 0.5,
     "command": "snd_voipvolume {value}", "release": "snd_voipvolume {back}",
     "says": "Sets voice chat volume to {pct}"},
    {"id": "sensitivity", "group": "mouse", "label": "Set mouse sensitivity",
     "input": "number", "setting": "sensitivity", "min": 0.05, "max": 10, "step": 0.05,
     "default": 1, "back_default": 2,
     "command": "sensitivity {value}", "release": "sensitivity {back}",
     "says": "Sets mouse sensitivity to {value}"},
    {"id": "radar_zoom", "group": "screen", "label": "Zoom the radar out",
     "input": "number", "setting": "cl_radar_scale", "min": 0.25, "max": 1, "step": 0.05,
     "default": 0.3, "back_default": 0.7,
     "command": "cl_radar_scale {value}", "release": "cl_radar_scale {back}",
     "says": "Sets radar zoom to {value}"},
]

GROUP_NAMES = {
    "weapons": "Weapons", "movement": "Moving", "combat": "Shooting",
    "buying": "Buying", "comms": "Talking", "screen": "On screen",
    "interface": "On screen", "sound": "Sound", "mouse": "Mouse",
    "scripts": "Your scripts",
}
GROUP_ORDER = ["weapons", "movement", "combat", "buying", "comms", "screen",
               "sound", "mouse", "scripts"]
# Catalogue groups that make no sense inside a script.
_SKIP_GROUPS = {"session", "practice"}
# Catalogue commands that only open a menu or type box -- which closes or
# ignores whatever the rest of the script does.
_SKIP_COMMANDS = {"messagemode", "messagemode2", "toggleconsole", "clear",
                  "teammenu", "radio", "radio1", "radio2", "radio3", "buymenu"}


def _catalogue_steps() -> List[Dict[str, Any]]:
    from . import commands

    out = []
    for group in commands.catalogue().get("groups", []):
        gid = group.get("id", "")
        if gid in _SKIP_GROUPS:
            continue
        if gid == "interface":
            gid = "screen"
        for entry in group.get("commands", []):
            command = str(entry.get("command", "")).strip()
            if not command or command in _SKIP_COMMANDS:
                continue
            out.append({
                "id": "cmd:" + command,
                "group": gid,
                "label": entry.get("label") or command,
                "command": command,
                "hold": command.startswith("+"),
                "note": entry.get("note", ""),
            })
    return out


def _script_steps(scan) -> List[Dict[str, Any]]:
    from . import commands

    group = commands._script_group(scan) if scan is not None else None
    out = []
    for entry in (group or {}).get("commands", []):
        command = entry["command"]
        out.append({
            "id": "script:" + command,
            "group": "scripts",
            "label": entry.get("label") or command,
            "command": command,
            "hold": command.startswith("+"),
            "note": entry.get("note", ""),
            "script": True,
        })
    return out


def steps(scan=None) -> List[Dict[str, Any]]:
    """Every step the builder offers, in display order."""
    every = _catalogue_steps() + EXTRA_STEPS + _script_steps(scan)
    for step in every:
        step["move"] = bool(_moves_of(step["command"], scan))
        step["group_name"] = GROUP_NAMES.get(step["group"], step["group"].title())
        if step.get("setting") and scan is not None:
            current = scan.effective_setting(step["setting"])
            if current is not None:
                step["back_default"] = _number(current.value.strip('"'),
                                               step.get("back_default"))
    rank = {g: i for i, g in enumerate(GROUP_ORDER)}
    every.sort(key=lambda s: rank.get(s["group"], len(rank)))
    return every


def describe(command: str, scan=None) -> str:
    """A key's current command in plain words, for "X already does ..."."""
    wanted = (command or "").strip().strip('"').lower()
    for step in steps(scan):
        if step["command"].lower() == wanted:
            return step["label"]
    if scan is not None and scan.effective_alias(wanted) is not None:
        made = _own_block(scan, wanted.lstrip("+-"))
        if made is not None and made["spec"].get("name"):
            return f"your script \u201c{made['spec']['name']}\u201d"
        return "one of your scripts"
    return "something else"


# What CS2 itself puts on the keys that matter most, for when the game's own
# defaults file can't be read. Restoring one of these to "nothing" would take
# away firing, so a key with no bind in the config falls back to these.
STOCK_FALLBACK = {"mouse1": "+attack", "mouse2": "+attack2"}


def normal_bind(scan, binding: str) -> str:
    """What a key runs now, by the bind that loads last."""
    if scan is None or not binding:
        return ""
    entries = scan.binds.get(binding) or []
    if not entries:
        return ""
    winner = max(entries, key=lambda b: b.order)
    return (winner.body or "").strip().strip('"').strip()


def _runs_own(body: str, alias: str) -> bool:
    """Whether a bind runs one of this script's own lines."""
    head = (body or "").strip().strip('"').split(";")[0].strip().lower().lstrip("+-")
    return head == alias or head.startswith(alias + "_")


def _number(text: Any, fallback: Any) -> Any:
    try:
        return float(text)
    except (TypeError, ValueError):
        return fallback


# ---------------------------------------------------------------------------
# What a command does to movement
# ---------------------------------------------------------------------------

def _moves_of(command: str, scan=None, depth: int = 0) -> List[str]:
    """Movement/attack actions a command string runs, through aliases too."""
    found: List[str] = []
    if depth > 8:
        return found
    for piece in (command or "").split(";"):
        words = piece.strip().strip('"').split()
        if not words:
            continue
        head = words[0].lower()
        if head in ("alias", "bind", "echo", "say", "say_team"):
            continue
        bare = head.lstrip("+-")
        if head[:1] in "+-" and bare in MOVE_ACTIONS:
            found.append(bare)
            continue
        if scan is not None:
            alias = scan.effective_alias(head)
            if alias is not None:
                for sub in _moves_of(alias.body, scan, depth + 1):
                    if sub not in found:
                        found.append(sub)
    return found


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

@dataclass
class Check:
    level: str      # ok | warn | block
    text: str
    fix: str = ""   # an id the page can offer as a one-click fix


@dataclass
class Built:
    ok: bool
    alias: str = ""
    entry: str = ""
    lines: List[str] = field(default_factory=list)
    says: List[str] = field(default_factory=list)
    release_says: List[str] = field(default_factory=list)
    checks: List[Check] = field(default_factory=list)
    replaces: Optional[Dict[str, Any]] = None
    spec: Dict[str, Any] = field(default_factory=dict)
    target: Dict[str, Any] = field(default_factory=dict)
    explained: List[Dict[str, Any]] = field(default_factory=list)
    generated: List[str] = field(default_factory=list)
    edited: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok, "alias": self.alias, "entry": self.entry,
            "lines": self.lines, "says": self.says,
            "release_says": self.release_says,
            "checks": [c.__dict__ for c in self.checks],
            "replaces": self.replaces, "spec": self.spec,
            "target": self.target, "explained": self.explained,
            "generated": self.generated, "edited": self.edited,
        }


def clean_text(text: str) -> str:
    """Chat text that can sit inside an alias without breaking it."""
    out = (text or "").replace('"', "'").replace(";", ",")
    out = re.sub(r"[\r\n\t]+", " ", out)
    while "//" in out:
        out = out.replace("//", "/")
    return re.sub(r" {2,}", " ", out).strip()[:MAX_TEXT]


def slug(name: str) -> str:
    out = _SLUG.sub("_", (name or "").lower()).strip("_")
    # Cut at a word break, not mid-word, so the name still reads.
    while len(out) > 32 and "_" in out:
        out = out.rsplit("_", 1)[0]
    out = out[:32]
    if not out or out[0].isdigit():
        out = "my_" + out
    return out


def _fmt(value: float) -> str:
    text = ("%.2f" % float(value)).rstrip("0").rstrip(".")
    return text or "0"


def _taken_names() -> set:
    from . import cfgscan

    names = set(cfgscan.KNOWN_ENGINE_COMMANDS)
    names.update(cfgscan.KNOWN_ENGINE_ACTIONS)
    return names


def _own_block(scan, alias: str) -> Optional[Dict[str, Any]]:
    """Where this builder already wrote a script with this alias, if it did."""
    if scan is None:
        return None
    for config in scan.files.values():
        try:
            text = config.path.read_bytes().decode(
                config.document.encoding, errors="replace")
        except OSError:
            continue
        if MARK not in text:
            continue
        for found in own_blocks(text):
            if found["spec"].get("alias") == alias:
                return {"file": config.relative, **found}
    return None


def own_blocks(text: str) -> List[Dict[str, Any]]:
    """The builder's scripts in one file: spec plus the lines they span."""
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith(MARK):
            continue
        try:
            spec = json.loads(stripped[len(MARK):])
        except ValueError:
            continue
        # The block is the banner above the marker down to its ECHO line.
        start = i
        while start > 0 and lines[start - 1].strip().startswith("//"):
            start -= 1
            if start <= i - 3:
                break
        end = i
        while end + 1 < len(lines):
            end += 1
            if lines[end].strip().upper().startswith("ECHO"):
                break
        out.append({"spec": spec, "first": start + 1, "last": end + 1})
    return out


def build(spec: Dict[str, Any], scan=None, key_label: str = "") -> Built:
    """Turn the player's choices into config lines, or say why not."""
    from . import keys

    offered = {s["id"]: s for s in steps(scan)}
    checks: List[Check] = []
    block = False

    name = re.sub(r"\s+", " ", str(spec.get("name") or "")).strip()
    name = name.replace('"', "'")[:MAX_NAME]
    mode = spec.get("mode") if spec.get("mode") in MODES else "press"
    picked = list(spec.get("steps") or [])[:MAX_STEPS + 1]
    binding = str(spec.get("binding") or "").strip()
    label = key_label or (keys.label(binding) if binding else "")

    if not name:
        checks.append(Check("block", "Give your script a name."))
        block = True
    if not picked:
        checks.append(Check("block", "Add at least one step."))
        block = True
    if len(picked) > MAX_STEPS:
        checks.append(Check("block", f"Up to {MAX_STEPS} steps fit on one key."))
        picked = picked[:MAX_STEPS]
        block = True

    press: List[str] = []
    release: List[str] = []
    says: List[str] = []
    release_says: List[str] = []
    moves: List[str] = []
    move_steps: List[str] = []
    holds: List[str] = []
    cleaned = False
    clean_steps: List[Dict[str, Any]] = []

    for raw in picked:
        step = offered.get(str(raw.get("id") or ""))
        if step is None:
            checks.append(Check("block", "One step is no longer available. Remove it and add it again."))
            block = True
            continue
        kept: Dict[str, Any] = {"id": step["id"]}
        fill: Dict[str, str] = {}

        if step.get("input") == "text":
            given = str(raw.get("text") or "")
            text = clean_text(given)
            if text != given.strip():
                cleaned = True
            if not text:
                checks.append(Check("block", f"“{step['label']}” needs some text."))
                block = True
                text = step.get("placeholder", "")
            fill["text"] = text
            kept["text"] = text
        if step.get("input") == "number":
            low, high = step["min"], step["max"]
            value = _number(raw.get("value"), None)
            if value is None or not low <= value <= high:
                checks.append(Check("block", f"“{step['label']}” needs a number from {_fmt(low)} to {_fmt(high)}."))
                block = True
                value = step["default"]
            fill["value"] = _fmt(value)
            fill["pct"] = f"{round(value * 100)}%"
            kept["value"] = value
            if mode in ("hold", "toggle"):
                back = _number(raw.get("back"), None)
                if back is None or not low <= back <= high:
                    checks.append(Check("block", f"“{step['label']}” needs a number to go back to, from {_fmt(low)} to {_fmt(high)}."))
                    block = True
                    back = step.get("back_default", step["default"])
                fill["back"] = _fmt(back)
                kept["back"] = back

        command = step["command"].format(**fill)
        said = (step.get("says") or step["label"]).format(**fill)

        found = _moves_of(command, scan)
        if found:
            moves.extend(m for m in found if m not in moves)
            move_steps.append(step["label"])

        if step.get("hold"):
            holds.append(step["label"])
            press.append(command)
            # The release half is derived, never typed: -x for every +x.
            release.append("-" + command[1:])
            says.append(said)
        elif step.get("release"):
            press.append(command)
            if mode in ("hold", "toggle"):
                release.append(step["release"].format(**fill))
                release_says.append(f"puts {step['label'].lower().replace('set ', '')} back to {fill['back']}")
            says.append(said)
        else:
            press.append(command)
            says.append(said)
        clean_steps.append(kept)

    # "While held" can also do its own things when the key is let go, after
    # undoing what the press did -- fire on press, knife on release.
    clean_release: List[Dict[str, Any]] = []
    let_go: List[str] = []
    for raw in (list(spec.get("release_steps") or [])[:MAX_STEPS] if mode == "hold" else []):
        step = offered.get(str(raw.get("id") or ""))
        if step is None:
            checks.append(Check("block", "One let-go step is no longer available. Remove it and add it again."))
            block = True
            continue
        if step.get("hold"):
            checks.append(Check(
                "block", f"\u201c{step['label']}\u201d can't be a let-go step: nothing would ever "
                "let go of it, so it would stay on. Put it in the press steps instead."))
            block = True
            continue
        kept = {"id": step["id"]}
        fill = {}
        if step.get("input") == "text":
            given = str(raw.get("text") or "")
            text = clean_text(given)
            if text != given.strip():
                cleaned = True
            if not text:
                checks.append(Check("block", f"\u201c{step['label']}\u201d needs some text."))
                block = True
                text = step.get("placeholder", "")
            fill["text"] = kept["text"] = text
        if step.get("input") == "number":
            value = _number(raw.get("value"), None)
            if value is None or not step["min"] <= value <= step["max"]:
                checks.append(Check("block", f"\u201c{step['label']}\u201d needs a number from {_fmt(step['min'])} to {_fmt(step['max'])}."))
                block = True
                value = step["default"]
            fill["value"] = _fmt(value)
            fill["pct"] = f"{round(value * 100)}%"
            kept["value"] = value
        command = step["command"].format(**fill)
        if _moves_of(command, scan):
            checks.append(Check("block", f"\u201c{step['label']}\u201d moves or shoots, which a let-go step can't do safely."))
            block = True
        let_go.append(command)
        release_says.append((step.get("says") or step["label"]).format(**fill))
        clean_release.append(kept)
    release = release + let_go

    # A hold action on a press-once key is the stuck-crouch bug: it is
    # pressed and nothing ever releases it.
    if holds and mode == "shift":
        checks.append(Check(
            "block",
            f"\u201c{holds[0]}\u201d only works while a key is held down, so it can't be the "
            "shift key's other action. Pick steps that finish on their own."))
        block = True
    if holds and mode == "press":
        checks.append(Check(
            "block",
            f"“{holds[0]}” only works while a key is held down. On a press-once key it "
            "would stay on forever. Choose “While held”.", fix="mode:hold"))
        block = True

    if len(moves) > 1:
        checks.append(Check(
            "block",
            "CS2 blocks this script. Since the August 2024 update, one key can only do one "
            "moving or shooting action (jump, crouch, walk, move, fire). "
            f"This one has {len(move_steps)}: {', '.join(move_steps)}. CS2 would only run part "
            "of it, so the app won't write it. Put them on separate keys instead.",
            fix="valve"))
        block = True

    if cleaned:
        checks.append(Check("warn", "Removed quotes, semicolons or // from your text. They would break the script."))

    # Names
    step_end = len(checks)
    alias = slug(name) if name else ""
    replaces = None
    earlier: Dict[str, Any] = {}
    if alias:
        own = _own_block(scan, alias)
        earlier = dict((own or {}).get("spec") or {})
        clash = alias in _taken_names() or alias.lstrip("+-") in _taken_names()
        users = []
        if scan is not None:
            for candidate in (alias, "+" + alias, "-" + alias, alias + "_on", alias + "_off",
                              alias + "_do", alias + "_arm", alias + "_normal",
                              alias + "_next", alias + "_own"):
                if scan.effective_alias(candidate) is not None:
                    users.append(candidate)
        if own is not None:
            replaces = {"file": own["file"], "first": own["first"], "last": own["last"],
                        "binding": str(earlier.get("binding") or ""),
                        "key_before": str(earlier.get("key_before") or "")}
            checks.append(Check("ok", "Saving replaces your earlier script with this name."))
        elif clash:
            checks.append(Check("block", "That name is already a CS2 command. Pick another name."))
            block = True
        elif users:
            checks.append(Check("block", "You already have a script with that name. Pick another name."))
            block = True
        else:
            checks.append(Check("ok", "Name is free. Nothing else uses it."))

    if not binding:
        checks.append(Check("block", "Pick a key."))
        block = True

    # What the key did before this script took it, remembered so switching
    # the script off (or keeping the shift key's own job) can give it back.
    # The page's caller passes what the key does now on the keyboard in use
    # (a profile has keys of its own); otherwise the files decide.
    key_before = (str(spec["key_now"]).strip().strip('"') if "key_now" in spec
                  else normal_bind(scan, binding))
    if key_before and alias and _runs_own(key_before, alias):
        key_before = (str(earlier.get("key_before") or "")
                      if earlier.get("binding") == binding else "")

    # The shift key's second key, and how to give that key its own job back.
    target = str(spec.get("target") or "").strip() if mode == "shift" else ""
    style = spec.get("style") if spec.get("style") in SHIFT_STYLES else "next"
    restore = ""
    let_go = ""
    normal_lines: List[str] = []
    target_label = keys.label(target) if target else ""
    normal_said = ""
    if mode == "shift":
        if not target:
            checks.append(Check("block", "Pick the key the shift key changes."))
            block = True
        elif target == binding:
            checks.append(Check("block", "The shift key and the key it changes must be two different keys."))
            block = True
        else:
            normal = ((str(spec["target_now"]).strip().strip('"') if "target_now" in spec
                       else normal_bind(scan, target)) or str(spec.get("target_stock") or "").strip()
                      or STOCK_FALLBACK.get(target, ""))
            normal_said = describe(normal, scan) if normal else "nothing"
            if not normal:
                restore = f"unbind {target}"
            elif re.fullmatch(r"[^\s\";]+", normal):
                restore = f"bind {target} {normal}"
                if normal.startswith("+") and len(normal) > 1:
                    # CS2 runs the let-go half of whatever the key is bound to
                    # when it is let go. Rebinding a key that is held down
                    # (scoping with Mouse 2) would leave the press running for
                    # good, so it is let go first.
                    let_go = "-" + normal[1:]
            elif '"' not in normal and not re.search(r"(^|;)\s*[+-]", normal):
                # Several commands: kept in an alias of its own, because a
                # bind inside an alias cannot hold a second pair of quotes.
                normal_lines = [f'alias "{alias}_normal" "{normal}"']
                restore = f"bind {target} {alias}_normal"
            else:
                checks.append(Check(
                    "block",
                    f"{target_label} runs several things at once, including a held action, so the "
                    "app can't give it back safely. Put a single action on that key first."))
                block = True
            if let_go:
                checks.append(Check(
                    "ok", f"If you are holding {target_label} when it changes, it is let go "
                    "first, so it can't get stuck."))
            if restore:
                checks.append(Check(
                    "ok", f"{target_label} always goes back to \u201c{normal_said}\u201d. "
                    f"If you change what {target_label} does later, save this script again."))

    # The shift key's own job, kept unless the player turns that off: Mouse 5
    # can stay voice chat and still be the shift key.
    own_press, own_release, own_lines, own_said = "", "", [], ""
    # Another shift script already on this key is always kept: several
    # scripts can share one shift key, whatever "keep its own job" says.
    shared = bool(key_before) and _own_block(
        scan, key_before.strip('"').lstrip("+-").split(";")[0].strip().lower()) is not None
    if mode == "shift" and binding and (spec.get("keep_own", True) is not False or shared):
        own = (key_before or str(spec.get("key_stock") or "").strip()
               or STOCK_FALLBACK.get(binding, ""))
        if own and alias and own.lower().lstrip("+") != alias:
            own_said = describe(own, scan)
            if re.fullmatch(r"\+[^\s\";]+", own):
                own_press, own_release = own, "-" + own[1:]
            elif re.fullmatch(r"[^\s\";+-][^\s\";]*", own):
                own_press = own
            elif '"' not in own and not re.search(r"(^|;)\s*[+-]", own):
                own_lines = [f'alias "{alias}_own" "{own}"']
                own_press = f"{alias}_own"
            else:
                checks.append(Check(
                    "block", f"{label} runs several things at once, including a held action, so it "
                    "can't keep its own job as a shift key. Turn off \u201cKeep its own job\u201d."))
                block = True
                own_said = ""
            if own_press:
                checks.append(Check("ok", f"{label} still does \u201c{own_said}\u201d too."))

    # Lines
    head_checks = checks[step_end:]
    name_checks = [c for c in checks[:step_end] if c.text == "Give your script a name."]
    lines: List[str] = []
    entry = alias
    away = (f"{let_go}; " if let_go else "") + f"bind {target} {alias}_do"
    if alias and press and mode == "shift":
        if restore and style == "hold":
            entry = "+" + alias
            on = (([own_press] if own_press else []) + ([let_go] if let_go else [])
                  + [f"bind {target} {alias}_do"])
            off = ([own_release] if own_release else []) + [restore]
            lines = normal_lines + own_lines + [
                f'alias "{alias}_do" "{"; ".join(press)}"',
                f'alias "+{alias}" "{"; ".join(on)}"',
                f'alias "-{alias}" "{"; ".join(off)}"']
        elif restore and own_press:
            # A held own job (voice chat) needs the key bound to a +name, so
            # the press/let-go pair wraps the arm-and-cancel switch.
            entry = "+" + alias
            nxt = alias + "_next"
            lines = normal_lines + own_lines + [
                f'alias "{alias}_do" "{"; ".join(press + [restore, f"alias {nxt} {alias}_arm"])}"',
                f'alias "{alias}_arm" "{away}; alias {nxt} {alias}_off"',
                f'alias "{alias}_off" "{restore}; alias {nxt} {alias}_arm"',
                f'alias "{nxt}" "{alias}_arm"',
                f'alias "+{alias}" "{own_press}; {nxt}"',
                f'alias "-{alias}" "{own_release}"']
        elif restore:
            lines = normal_lines + [
                f'alias "{alias}_do" "{"; ".join(press + [restore, f"alias {alias} {alias}_arm"])}"',
                f'alias "{alias}_arm" "{away}; alias {alias} {alias}_off"',
                f'alias "{alias}_off" "{restore}; alias {alias} {alias}_arm"',
                f'alias "{alias}" "{alias}_arm"']
        if any(len(line) > MAX_LINE for line in lines):
            checks.append(Check("block", "Too much for one key. Remove a step or shorten the text."))
            block = True
    elif alias and press:
        if mode == "hold":
            entry = "+" + alias
            lines = [f'alias "+{alias}" "{"; ".join(press)}"',
                     f'alias "-{alias}" "{"; ".join(release)}"']
        elif mode == "toggle":
            on = press + [f"alias {alias} {alias}_off"]
            off = release + [f"alias {alias} {alias}_on"]
            lines = [f'alias "{alias}_on" "{"; ".join(on)}"',
                     f'alias "{alias}_off" "{"; ".join(off)}"',
                     f'alias "{alias}" "{alias}_on"']
        else:
            lines = [f'alias "{alias}" "{"; ".join(press)}"']
        if any(len(line) > MAX_LINE for line in lines):
            checks.append(Check("block", "Too much for one key. Remove a step or shorten the text."))
            block = True

    if not block:
        checks.insert(0, Check("ok", "Config syntax and the documented CS2 multi-input rule checked. Server and anti-cheat policies are not certified."))
        if mode == "press":
            checks.insert(1, Check("ok", "Nothing can get stuck. Every step finishes on its own."))
        elif mode == "hold":
            checks.insert(1, Check("ok", "Letting go undoes everything that was held or changed."))
        elif mode == "toggle":
            checks.insert(1, Check("ok", "The second press undoes everything the first one turned on."))
        elif style == "hold":
            checks.insert(1, Check("ok", f"Letting go of the shift key gives {target_label} its own job back."))
        else:
            checks.insert(1, Check("ok", f"{target_label} does the new thing once, then goes back by itself. "
                                         "Pressing the shift key again before that cancels it."))

    if mode == "hold" and not release:
        checks.append(Check("warn", "Nothing here needs undoing, so “Press once” does the same job.",
                            fix="mode:press"))

    if alias and (mode == "hold" or (mode == "shift" and (style == "hold" or own_press))):
        entry = "+" + alias

    # Lines the player edited by hand replace the generated ones, and are
    # checked on their own: the steps no longer say what the key does.
    edited = spec.get("lines_text")
    generated = list(lines)
    if isinstance(edited, str) and alias:
        from . import scriptlines

        lines, problems = scriptlines.lint(edited, scan, alias, entry, mode=mode, target=target)
        checks = name_checks + head_checks
        checks += [Check(p.level, (f"Line {p.line}: " if p.line else "") + p.text) for p in problems]
        block = any(c.level == "block" for c in checks)
        if not block:
            checks.insert(0, Check("ok", "Edited lines passed syntax, alias flow, reachable release and documented input checks. This is not an anti-cheat certification."))

    explained = []
    if alias and lines:
        from . import scriptlines

        explained = scriptlines.explain(lines, scan, alias, mode, label, target_label)

    stored = {"v": 1, "name": name, "mode": mode, "steps": clean_steps,
              "binding": binding, "alias": alias}
    if mode == "shift":
        stored.update(target=target, style=style,
                      keep_own=spec.get("keep_own", True) is not False)
    if clean_release:
        stored["release_steps"] = clean_release
    if key_before:
        stored["key_before"] = key_before
    if isinstance(edited, str) and alias:
        stored["lines"] = lines
    return Built(ok=not block, alias=alias, entry=entry, lines=lines,
                 says=says, release_says=release_says, checks=checks,
                 replaces=replaces, spec=stored,
                 target={"binding": target, "label": target_label,
                         "normal": normal_said, "own": own_said if own_press else ""}
                 if mode == "shift" else {},
                 explained=explained, generated=generated,
                 edited=isinstance(edited, str))


def block_lines(built: Built, key_label: str) -> List[str]:
    """The script as a banner block the Scripts tab already knows how to read."""
    spec = built.spec
    # Short on purpose: a long ECHO is cut by the engine, and the Scripts tab
    # reads the key from the "Press (X)" at its end.
    echo = f"---Script---{clean_text(spec['name'])}. Press ({clean_text(key_label)})"
    return [
        "// --------------------------",
        f"// {spec['name']}",
        "// --------------------------",
        MARK + json.dumps(spec, separators=(",", ":")),
        *built.lines,
        f'ECHO "{echo}"',
    ]


def write_block(text: str, newline: str, trailing: bool, built: Built,
                key_label: str) -> str:
    """The file text with this script added, or swapped in for its old copy."""
    block = block_lines(built, key_label)
    lines = text.splitlines()
    if built.replaces:
        first, last = built.replaces["first"], built.replaces["last"]
        lines[first - 1:last] = block
        body = newline.join(lines)
    else:
        body = text.rstrip("\r\n") + newline + newline.join([""] + block)
    if trailing and not body.endswith(newline):
        body += newline
    return body
