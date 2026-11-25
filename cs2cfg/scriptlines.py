"""A Script Builder script's config lines: laid out in plain words, and
checked again when the player edits them by hand.

The builder writes the lines itself, so they are right by construction. Once
somebody edits them that guarantee is gone, so every rule the builder follows
is checked here on the text itself:

* every line is an ``alias`` with one pair of quotes (CS2 has no way to put
  quotes inside quotes, and a stray one cuts the line short);
* every name starts with the script's own name, so an edit can never
  overwrite another script or a CS2 command;
* every ``+name`` has its ``-name``, and every held action that is pressed is
  also let go somewhere -- the stuck-crouch bug;
* no single press runs more than one movement or shooting action (the CS2
  August 2024 rule);
* the line the key runs exists, and nothing is too long for CS2 to read.

Anything else that looks odd -- a command CS2 has never heard of, a line that
clears every key -- is a warning rather than a refusal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_ALIAS = re.compile(r'^\s*alias\s+"?([^"\s;]+)"?\s*(.*?)\s*$', re.IGNORECASE)

WEAPONS = {
    "weapon_c4": "the bomb", "weapon_flashbang": "a flashbang",
    "weapon_smokegrenade": "a smoke", "weapon_hegrenade": "an HE grenade",
    "weapon_molotov": "a molotov", "weapon_incgrenade": "an incendiary",
    "weapon_decoy": "a decoy", "weapon_knife": "the knife", "weapon_taser": "the Zeus",
}
SETTINGS = {
    "volume": "game volume", "snd_voipvolume": "voice chat volume",
    "sensitivity": "mouse sensitivity", "cl_radar_scale": "radar zoom",
}
BUYS = {
    "vesthelm": "armor and helmet", "vest": "armor", "defuser": "a defuse kit",
    "flashbang": "a flashbang", "smokegrenade": "a smoke", "hegrenade": "an HE grenade",
    "molotov": "a molotov", "incgrenade": "an incendiary", "decoy": "a decoy",
}
RISKY = {
    "unbindall": "This clears every key you have.",
    "exec": "This loads another config file.",
    "quit": "This closes CS2.",
    "disconnect": "This leaves the match.",
}


@dataclass
class Line:
    number: int
    name: str
    body: str
    role: str = ""
    commands: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class Problem:
    level: str           # block | warn
    text: str
    line: int = 0        # 1-based line in the edited text, 0 for the whole script


def _pieces(body: str) -> List[str]:
    return [p.strip() for p in (body or "").split(";") if p.strip()]


def _labels(scan) -> Dict[str, str]:
    from . import scriptgen

    out = {}
    for step in scriptgen.steps(scan):
        out.setdefault(step["command"].lower(), step["label"])
    return out


def role_of(name: str, base: str, mode: str, key: str, target: str) -> str:
    """What one alias in the script is for, in plain words."""
    key = key or "your key"
    target = target or "the other key"
    if name == "+" + base:
        return f"When you press {key}"
    if name == "-" + base:
        return f"When you let go of {key}"
    if name == base + "_on":
        return f"First press of {key}"
    if name == base + "_off":
        return (f"Second press of {key} (cancels)" if mode == "shift"
                else f"Next press of {key} (turns it off)")
    if name == base + "_do":
        return f"What {target} does once it's changed"
    if name == base + "_arm":
        return f"When you press {key}"
    if name == base + "_next":
        return f"Switches {target} over, or cancels"
    if name == base + "_own":
        return f"What {key} normally does"
    if name == base + "_normal":
        return f"What {target} normally does"
    if name == base:
        return f"When you press {key}" if mode == "press" else "Where it starts"
    return "Part of this script"


def say(piece: str, labels: Dict[str, str], local: Dict[str, str], roles: Dict[str, str]) -> str:
    """One command in plain words."""
    from . import keys

    words = piece.split()
    head = words[0].lower().strip('"')
    rest = piece[len(words[0]):].strip().strip('"')
    if head == "say_team":
        return f"Writes “{rest}” in team chat"
    if head == "say":
        return f"Writes “{rest}” in chat to everyone"
    if head == "echo":
        return f"Shows “{rest}” in the console"
    if head == "use" and len(words) > 1:
        return f"Takes out {WEAPONS.get(words[1].lower(), words[1])}"
    if head == "buy" and len(words) > 1:
        return f"Buys {BUYS.get(words[1].lower(), words[1])}"
    if head in SETTINGS and len(words) > 1:
        return f"Sets {SETTINGS[head]} to {words[1].strip(chr(34))}"
    if head == "bind" and len(words) > 2:
        target = " ".join(words[2:]).strip('"')
        what = roles.get(target.lower()) or labels.get(target.lower()) or target
        return f"Makes {keys.label(words[1].strip(chr(34)))} do “{what}”"
    if head == "unbind" and len(words) > 1:
        return f"Clears {keys.label(words[1].strip(chr(34)))}"
    if head == "alias" and len(words) > 2:
        return f"Next press runs “{roles.get(words[2].lower(), words[2])}”"
    if head == "alias":
        return "Sets up the next press"
    if piece.lower() in labels:
        return labels[piece.lower()]
    if head in labels and len(words) == 1:
        return labels[head]
    if head.startswith("-") and "+" + head[1:] in labels:
        return f"Lets go of: {labels['+' + head[1:]]}"
    if head in local:
        return f"Runs “{roles.get(head, head)}”"
    if head in RISKY:
        return RISKY[head]
    return "A CS2 command"


def parse(text: str) -> List[Line]:
    out = []
    for number, raw in enumerate((text or "").splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("//"):
            continue
        found = _ALIAS.match(stripped)
        if not found:
            out.append(Line(number, "", stripped))
            continue
        out.append(Line(number, found.group(1).lower(), found.group(2)))
    return out


def explain(lines: List[str], scan, base: str, mode: str, key: str, target: str) -> List[Dict]:
    """The script laid out alias by alias, a plain-word note on every command."""
    parsed = parse("\n".join(lines))
    labels = _labels(scan)
    local = {p.name: p.body for p in parsed if p.name}
    roles = {n: role_of(n, base, mode, key, target) for n in local}
    out = []
    for item in parsed:
        body = item.body.strip()
        if body.startswith('"') and body.endswith('"') and len(body) >= 2:
            body = body[1:-1]
        out.append({
            "name": item.name, "role": roles.get(item.name, ""),
            "commands": [{"text": p, "says": say(p, labels, local, roles)} for p in _pieces(body)],
        })
    return out


def _known(head: str, scan, local: Dict[str, str], labels: Dict[str, str]) -> bool:
    from . import cfgscan

    bare = head.lstrip("+-")
    if head in local or head in labels or bare in cfgscan.KNOWN_ENGINE_COMMANDS:
        return True
    if bare in cfgscan.KNOWN_ENGINE_ACTIONS or head in RISKY:
        return True
    if any(bare.startswith(p) for p in cfgscan.KNOWN_ENGINE_PREFIXES):
        return True
    if head in ("use", "buy", "say", "say_team", "echo", "bind", "unbind", "alias"):
        return True
    return scan is not None and scan.effective_alias(head) is not None


def _holdable(head: str, scan, local: Dict[str, str], labels: Dict[str, str]) -> bool:
    """Whether a +command is pressed and needs a matching let-go."""
    from . import cfgscan

    if not head.startswith("+"):
        return False
    bare = head[1:]
    return (bare in cfgscan.KNOWN_ENGINE_ACTIONS or head in labels or head in local
            or (scan is not None and scan.effective_alias(head) is not None))


def lint(text: str, scan, base: str, entry: str, *, mode: str = "press", target: str = "") -> (List[str], List[Problem]):
    """Clean the edited lines and say everything wrong with them."""
    from . import scriptgen

    problems: List[Problem] = []
    lines: List[str] = []
    parsed = parse(text)
    labels = _labels(scan)

    if not parsed:
        return [], [Problem("block", "There are no lines. Write at least one, or undo your edits.")]

    local: Dict[str, str] = {}
    numbers: Dict[str, int] = {}
    for item in parsed:
        if not item.name:
            word = item.body.split()[0].lower() if item.body.split() else ""
            if word == "bind":
                problems.append(Problem("block", "Pick the key in step 4 instead of writing a bind line.", item.number))
            else:
                problems.append(Problem("block", "Every line has to start with alias, then a name, then what it does in quotes.", item.number))
            continue
        body = item.body.strip()
        if body.count('"') not in (0, 2) or (body.count('"') == 2 and not (body.startswith('"') and body.endswith('"'))):
            problems.append(Problem("block", "Quotes are wrong here. Put one pair of quotes around what the line does, and no quotes inside.", item.number))
            continue
        if body.startswith('"'):
            body = body[1:-1]
        elif ";" in body or " " in body.strip():
            problems.append(Problem("block", "Put quotes around what this line does, because it has more than one word.", item.number))
            continue
        if "//" in body:
            problems.append(Problem("block", "// starts a comment in CS2 and would cut this line short.", item.number))
            continue
        name = item.name
        if name.lstrip("+-") != base and not name.startswith(base + "_"):
            problems.append(Problem("block", f"Names in this script have to start with {base}, so they can't overwrite your other scripts.", item.number))
            continue
        if name in local:
            problems.append(Problem("block", f"{name} is written twice. Keep one.", item.number))
            continue
        local[name] = body
        numbers[name] = item.number
        line = f'alias "{name}" "{body}"'
        if len(line) > scriptgen.MAX_LINE:
            problems.append(Problem("block", "This line is too long for CS2. Split it into two names.", item.number))
        lines.append(line)

    if entry and entry not in local and not any(p.level == "block" for p in problems):
        problems.append(Problem("block", f"Your key starts the line named {entry}. Keep a line with that name."))

    for name, body in local.items():
        number = numbers[name]
        # Every +name needs its -name, or CS2 has nothing to run on release.
        if name.startswith("+") and "-" + name[1:] not in local:
            problems.append(Problem("block", f"{name} has no -{name[1:]} line, so letting go of the key would do nothing.", number))
        pressed, released = [], []
        moves = []
        for piece in _pieces(body):
            head = piece.split()[0].lower()
            if head == "alias" and len(piece.split()) > 2 and piece.split()[2].lower() not in local:
                problems.append(Problem("block", f"{piece.split()[2]} isn't one of this script's lines.", number))
            elif not _known(head, scan, local, labels):
                problems.append(Problem("warn", f"CS2 doesn't seem to know “{head}”. Check the spelling.", number))
            if head in RISKY:
                problems.append(Problem("warn", RISKY[head], number))
            if _holdable(head, scan, local, labels):
                pressed.append(head)
            if head.startswith("-"):
                released.append(head)
        for found in scriptgen._moves_of(body, scan):
            if found not in moves:
                moves.append(found)
        # Local aliases called from this line count too.
        for piece in _pieces(body):
            head = piece.split()[0].lower()
            if head in local and head != name:
                for found in scriptgen._moves_of(local[head], scan):
                    if found not in moves:
                        moves.append(found)
        if len(moves) > 1:
            problems.append(Problem(
                "block", "One press here does " + str(len(moves)) + " moving or shooting actions. "
                "CS2 has only allowed one per key since August 2024.", number))
        # A key rebound away from a held action (Mouse 2 off scoping) while it
        # is held would never get its let-go: CS2 lets go of whatever the key
        # is bound to at the moment it is released.
        so_far: List[str] = []
        for piece in _pieces(body):
            words = piece.replace('"', " ").split()
            if len(words) >= 3 and words[0].lower() == "bind":
                was = (scriptgen.normal_bind(scan, words[1].lower())
                       or scriptgen.STOCK_FALLBACK.get(words[1].lower(), ""))
                was = was.strip().strip('"')
                to = " ".join(words[2:]).lower()
                if (re.fullmatch(r"\+[^\s;]+", was) and to != was.lower()
                        and "-" + was[1:].lower() not in so_far):
                    from . import keys

                    problems.append(Problem(
                        "block", f"{keys.label(words[1])} could be held down when this changes it, and "
                        f"then it would stay on. Put -{was[1:]} before the bind.", number))
            so_far.append(piece.lower())
        for head in pressed:
            let_go = "-" + head[1:]
            if name.startswith("+"):
                fine = let_go in _pieces(local.get("-" + name[1:], "").lower())
            else:
                fine = any(let_go in [p.lower() for p in _pieces(other)]
                           for other_name, other in local.items() if other_name != name)
            if not fine:
                what = labels.get(head, head)
                problems.append(Problem(
                    "block", f"“{what}” is pressed here but never let go, so it would stay on. "
                    f"Add {let_go} where it should stop.", number))
    if not any(p.level == "block" for p in problems):
        from . import scriptdebug

        for error in scriptdebug.validation(lines, entry, scan=scan, mode=mode, target=target):
            problems.append(Problem("block", error))
    return lines, problems
