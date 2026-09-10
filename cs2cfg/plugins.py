"""Find the self-contained little features a config collection defines.

A hand-written CS2 config tends to be organised as blocks -- a banner comment
naming the feature, the aliases that implement it, and an ECHO announcing it at
load time. This collection follows that shape exactly:

    // --------------------------
    // Game Volume
    // --------------------------
    alias "!gamevolume_off" "volume 0; ... alias !gamevoulume !gamevolume_on"
    alias "!gamevolume_on"  "volume 1; ... alias !gamevoulume !gamevolume_off"
    alias "!gamevoulume" "!gamevolume_off"

    ECHO "---Script---Game Volume Script is ... Press (F9)"

so the file already carries the feature's name, its key and its command. This
module reads that structure back out rather than asking anyone to describe it
again, and works out how each one behaves from the aliases themselves.

Read-only: nothing here writes to a config.
"""

from __future__ import annotations

import re

from . import keys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

# A banner line: three or more dashes in a comment, nothing else.
_RULE = re.compile(r"^\s*//\s*-{3,}\s*$")
_COMMENT = re.compile(r"^\s*//\s?(.*?)\s*$")
# The load-time announcement, which carries the human description.
_ANNOUNCE = re.compile(r"---\s*Script\s*---\s*(.*)", re.IGNORECASE)
_KEY = re.compile(r"Press\s*\(([^)]+)\)", re.IGNORECASE)
_COMMAND = re.compile(r"Command\s+([^|\"]+)", re.IGNORECASE)

# Prefixed onto every active line of a block that has been switched off. It has
# to be recognisable on the way back in, and has to be a comment to the engine.
MARK = "//[off]//"


def strip_mark(line: str) -> tuple:
    """Return (line without the marker, whether it had one)."""
    lead = len(line) - len(line.lstrip())
    rest = line[lead:]
    if rest.startswith(MARK):
        return line[:lead] + rest[len(MARK):].lstrip(" "), True
    return line, False


# The scanner phrases its findings as "'name' is ..."; this lifts the name out.
_QUOTED = re.compile(r"'([^']+)'")


def _quoted(message: str) -> str:
    found = _QUOTED.search(message or "")
    return found.group(1) if found else ""


@dataclass
class Plugin:
    name: str
    file: str
    line: int
    description: str = ""
    key: str = ""
    command: str = ""
    kind: str = "action"          # toggle | hold | cycle | action | empty
    aliases: List[str] = field(default_factory=list)
    entry: str = ""               # what you actually run or bind
    states: List[str] = field(default_factory=list)
    touches: List[str] = field(default_factory=list)   # convars it changes
    missing: List[str] = field(default_factory=list)   # names it calls that do not exist
    bound_to: List[str] = field(default_factory=list)
    applies: List[str] = field(default_factory=list)   # set at load, not on a key
    notes: List[dict] = field(default_factory=list)    # what the scanner said here
    end_line: int = 0
    enabled: bool = True
    layout: List[dict] = field(default_factory=list)   # state -> what it runs

    @property
    def broken(self) -> bool:
        """Whether this feature cannot work as written.

        A name it calls that resolves to nothing means the step silently does
        nothing when you press the key.
        """
        return self.enabled and bool(self.missing)

    @property
    def suspect(self) -> bool:
        """Wired oddly enough to be worth a second look, but it still runs."""
        return self.enabled and any(
            n["code"] == "state-redefines-other" for n in self.notes)

    @property
    def group(self) -> str:
        """Features respond to a key and hold state; the rest are shortcuts."""
        return "feature" if self.kind in ("toggle", "cycle", "hold") else "command"


def _blocks(text: str):
    """Split a file into (title, first_line, body_lines) on its banner comments."""
    lines = text.splitlines()
    marks: List[tuple] = []
    for i, line in enumerate(lines):
        if not _RULE.match(line):
            continue
        # A title sits between two rules; a single rule closing a previous
        # block is skipped by requiring a comment directly beneath.
        if i + 2 < len(lines) and _RULE.match(lines[i + 2]):
            found = _COMMENT.match(lines[i + 1])
            if found and found.group(1):
                marks.append((i, found.group(1), i + 3))

    for index, (_start, title, body_at) in enumerate(marks):
        end = marks[index + 1][0] if index + 1 < len(marks) else len(lines)
        yield title, body_at + 1, end, lines[body_at:end]


def _classify(names: Set[str], bodies: Dict[str, str]) -> tuple:
    """Work out how a block behaves from the aliases it defines."""
    holds = sorted(n[1:] for n in names if n.startswith("+") and "-" + n[1:] in names)
    if holds:
        return "hold", "+" + holds[0], []

    # A dispatcher is an alias that other aliases in the block reassign.
    reassigned = {}
    for owner, body in bodies.items():
        for match in re.finditer(r"\balias\s+\"?([^\s\";]+)\"?\s+\"?([^\s\";]+)",
                                 body, re.IGNORECASE):
            reassigned.setdefault(match.group(1).lower(), set()).add(match.group(2).lower())

    for target, options in reassigned.items():
        if target in names:
            states = sorted(n for n in names if n != target)
            # Two states flipping between each other is a toggle; more than two
            # is a cycle you step through one press at a time.
            kind = "toggle" if len(states) == 2 else "cycle" if len(states) > 2 else "action"
            return kind, target, states

    return ("empty" if not names else "action"), (sorted(names)[0] if names else ""), []


# Chatter, not behaviour: what a script prints or plays while it works.
_TALK = {"echo", "say", "say_team", "play", "playvol"}
# Bookkeeping that exists only to make a toggle or cycle advance.
_PLUMBING = {"alias", "bind"}


def steps_of(body: str) -> dict:
    """Split one alias body into what it does, says, and rewires.

    The three read very differently on a card: the commands are the feature,
    the messages are flavour, and the alias reassignment is the mechanism that
    makes the next press do something else.
    """
    does, says, rewires = [], [], []
    for piece in re.split(r";", body or ""):
        piece = piece.strip()
        if not piece:
            continue
        head = piece.split()[0].lower().strip('"')
        if head in _TALK:
            rest = piece[len(head):].strip()
            if rest:
                says.append(rest)
        elif head in _PLUMBING:
            rewires.append(piece)
        else:
            does.append(piece)
    return {"does": does, "says": says, "rewires": rewires}


def _convars(body: str) -> List[str]:
    """Settings a body changes, ignoring the chatter around them."""
    out = []
    for piece in re.split(r";", body):
        piece = piece.strip()
        found = re.match(r"^(toggle\s+)?([a-z_][a-z0-9_]*)\s+[-\d.]", piece, re.IGNORECASE)
        if found:
            out.append(found.group(2).lower())
        elif re.match(r"^toggle\s+([a-z_][a-z0-9_]*)\s*$", piece, re.IGNORECASE):
            out.append(piece.split()[1].lower())
    return sorted(set(out))


def find(result) -> List[Plugin]:
    """Every feature block in the scanned collection, in load order."""
    from .cfglang import tokenize_line

    defined = {name.lower() for name in result.aliases}
    binds: Dict[str, List[str]] = {}
    for key, entries in result.binds.items():
        for bind in entries:
            for word in re.split(r"[;\s]+", bind.body or ""):
                if word:
                    binds.setdefault(word.lower(), []).append(key)

    found: List[Plugin] = []
    empty_sections: List[tuple] = []
    for config in result.files.values():
        if not config.is_commands:
            continue
        text = config.path.read_bytes().decode(config.document.encoding, errors="replace")

        for title, line_no, end_line, body in _blocks(text):
            names: Set[str] = set()
            bodies: Dict[str, str] = {}
            applied: List[str] = []
            description = ""

            disabled_lines = 0
            for offset, raw in enumerate(body):
                raw, was_off = strip_mark(raw)
                if was_off:
                    disabled_lines += 1
                parsed = tokenize_line(raw)
                for command in parsed.commands:
                    if command.name.lower() == "alias" and len(command.tokens) >= 3:
                        alias_name = command.arg_text(0)
                        names.add(alias_name.lower())
                        bodies[alias_name.lower()] = command.arg_text(1)
                    elif command.name.lower() == "echo" and command.tokens[1:]:
                        note = _ANNOUNCE.search(command.arg_text(0) or "")
                        if note:
                            description = note.group(1).strip()
                    elif command.name.lower() not in ("echo", "alias", "bind"):
                        # Applied when the file loads, not when a key is
                        # pressed -- a setting sitting loose inside a feature
                        # block behaves differently from the feature around it.
                        applied.append(" ".join(
                            [command.name] + [command.arg_text(i) or ""
                                              for i in range(len(command.tokens) - 1)]
                        ).strip())

            # No aliases at all means this is a heading over a group of
            # settings, not a feature. Only a block inside a file that also
            # defines features is worth mentioning as an empty section.
            if not names:
                empty_sections.append((config.relative, title, line_no))
                continue

            kind, entry, states = _classify(names, bodies)

            touches: Set[str] = set()
            for body_text in bodies.values():
                touches.update(_convars(body_text))

            # What the scanner already worked out about these lines. It resolves
            # references against the whole collection and its command knowledge,
            # which is a far better judge than a name-shape guess.
            notes = [
                {"code": i.code, "severity": i.severity.name.lower(),
                 "message": i.message, "line": i.line}
                for i in result.issues
                if i.file == config.relative and line_no <= i.line <= end_line
            ]
            missing = sorted({
                _quoted(i["message"]) for i in notes
                if i["code"] in ("unresolved-custom-reference", "unverified-command")
                and _quoted(i["message"])
            })

            # A toggle reads better on-then-off than alphabetically, and the
            # dispatcher itself only points at whichever state is next, which
            # says nothing about what the feature does.
            def rank(name: str) -> tuple:
                low = name.lower()
                if low.startswith("+"):
                    return (0, low)
                if low.startswith("-"):
                    return (1, low)
                return (0 if any(k in low for k in ("_on", "1", "open")) else 1, low)

            layout = []
            for name in sorted(bodies, key=rank):
                # Only a toggle or cycle has a dispatcher worth hiding. For a
                # hold, the + alias is the behaviour itself.
                if kind in ("toggle", "cycle") and name == entry and len(bodies) > 1:
                    continue
                step = steps_of(bodies[name])
                # A body that only calls another state in this same block is
                # plumbing too; showing it twice helps nobody.
                if len(step["does"]) == 1 and step["does"][0].lower() in bodies:
                    continue
                if step["does"] or step["says"]:
                    layout.append({"state": name, **step})

            plugin = Plugin(
                name=title, file=config.relative, line=line_no,
                description=description, kind=kind,
                aliases=sorted(names), entry=entry, states=states,
                touches=sorted(touches), missing=missing,
                bound_to=sorted(set(binds.get(entry.lower(), []))),
                applies=sorted(set(applied)),
                notes=notes,
                end_line=end_line,
                enabled=disabled_lines == 0,
                layout=layout,
            )
            if description:
                key = _KEY.search(description)
                if key:
                    plugin.key = key.group(1).strip()
                command = _COMMAND.search(description)
                if command:
                    plugin.command = command.group(1).strip()
            found.append(plugin)

    # Only sections in files that carry real features are worth reporting as
    # empty; a settings file is nothing but headings over values.
    feature_files = {p.file for p in found if p.group == "feature"}
    find.empty_sections = [e for e in empty_sections if e[0] in feature_files]
    return found


def as_dict(plugins: List[Plugin]) -> dict:
    return {
        "count": len(plugins),
        "features": sum(1 for p in plugins if p.group == "feature"),
        "broken": sum(1 for p in plugins if p.broken),
        "suspect": sum(1 for p in plugins if p.suspect),
        "disabled": sum(1 for p in plugins if not p.enabled),
        "plugins": [
            {
                "name": p.name, "file": p.file, "line": p.line,
                "description": p.description, "key": p.key, "command": p.command,
                "kind": p.kind, "entry": p.entry, "aliases": p.aliases,
                "states": p.states, "touches": p.touches, "missing": p.missing,
                "bound_to": p.bound_to, "broken": p.broken,
                # scancode44 means nothing on a card; Space does.
                "bound_labels": [keys.label(b) for b in p.bound_to],
                "applies": p.applies, "group": p.group,
                "notes": p.notes, "suspect": p.suspect,
                "end_line": p.end_line, "enabled": p.enabled,
                "layout": p.layout,
                "id": p.file + ":" + str(p.line),
            }
            for p in plugins
        ],
    }


def set_enabled(text: str, first_line: int, last_line: int, enable: bool) -> str:
    """Comment a block's active lines out, or put them back.

    Blank lines and lines that were already comments are left alone, so
    switching a block off and on again returns the file to exactly what it was.
    Line numbers are 1-based and inclusive, matching what ``find`` reports.
    """
    lines = text.split("\n")
    for index in range(first_line - 1, min(last_line, len(lines))):
        raw = lines[index]
        bare = raw.rstrip("\r")
        carriage = raw[len(bare):]
        stripped, marked = strip_mark(bare)

        if enable:
            if marked:
                lines[index] = stripped + carriage
            continue

        if marked or not bare.strip():
            continue                      # already off, or nothing to switch off
        if bare.lstrip().startswith("//"):
            continue                      # a comment the author wrote; leave it
        lead = len(bare) - len(bare.lstrip())
        lines[index] = bare[:lead] + MARK + " " + bare[lead:] + carriage
    return "\n".join(lines)
