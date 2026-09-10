"""Editing aliases: renaming identifiers, and changing what they do.

Two operations, deliberately kept apart because they carry different risk:

**Rename** changes an identifier and every reference to it. Behaviour is
unchanged by construction -- the commands an alias runs are not touched.

**Edit behaviour** changes the commands, values, order or toggle states. That
does change what happens, so it is reviewed separately and never bundled into a
rename.

Both work on the parsed token stream, never on raw text. A find-and-replace for
``!afk`` would also hit ``!afk_on``, ``!afk_off``, the word inside a chat
message, and a comment -- four different things, only some of which the user
meant. Renaming here rewrites exact token matches at known positions and offers
comment and message wording as separate, individually selectable changes.

Naming is treated as naming. An identifier is a label the author chose; it is
not evidence about what the commands do, and this module neither blocks nor
alters an alias on the basis of the words in its name. What a script actually
does is visible in its commands, which the UI shows in full. Whether any
particular script is permitted somewhere is a question for that event's rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .cfglang import (
    Command, Document, Issue, Severity, Token, alias_definition, bind_definition,
    family_of, parse, parse_command_string, press_release_parts, render_command,
    state_suffix,
)
from .cfgscan import ScanResult


class EditError(RuntimeError):
    """An edit could not be prepared safely."""


@dataclass
class TextEdit:
    """One replacement in one file, expressed as a line rewrite."""

    file: str
    line: int
    before: str
    after: str
    kind: str            # "definition" | "call" | "bind" | "nested" | "wording"
    description: str
    selected: bool = True


@dataclass
class RenamePlan:
    old_name: str
    new_name: str
    edits: List[TextEdit] = field(default_factory=list)
    wording_edits: List[TextEdit] = field(default_factory=list)
    family: List[Tuple[str, str]] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)

    @property
    def code_edits(self) -> List[TextEdit]:
        return self.edits

    def files_touched(self) -> List[str]:
        return sorted({e.file for e in self.edits + self.wording_edits})

    def summary(self) -> str:
        parts = [f"{len(self.edits)} code reference(s)"]
        if self.family:
            parts.append(f"{len(self.family)} related alias name(s)")
        if self.wording_edits:
            parts.append(f"{len(self.wording_edits)} optional wording update(s)")
        return ", ".join(parts)


@dataclass
class BehaviourChange:
    """A proposed change to what an alias does."""

    alias: str
    file: str
    line: int
    before_body: str
    after_body: str
    before_commands: List[str] = field(default_factory=list)
    after_commands: List[str] = field(default_factory=list)
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(i.severity == Severity.ERROR for i in self.issues)

    def explain(self) -> List[str]:
        """Plain description of the concrete difference."""
        out: List[str] = []
        if self.added:
            out.append("Will now run: " + "; ".join(self.added))
        if self.removed:
            out.append("Will no longer run: " + "; ".join(self.removed))
        if not self.added and not self.removed and self.before_commands != self.after_commands:
            out.append("Same commands, different order.")
        if not out:
            out.append("No change to the commands.")
        return out


# ---------------------------------------------------------------------------
# Renaming
# ---------------------------------------------------------------------------

def rewrite_identifiers(text: str, old: str, new: str, line_number: int = 0) -> Optional[str]:
    """Replace identifier tokens inside a command string, changing nothing else.

    Splices at the exact character offsets the tokeniser reported, so spacing,
    quoting and every other token survive untouched. Re-rendering the parsed
    command would be simpler but would also reformat the body, mixing a
    cosmetic change into what is supposed to be a pure rename.
    """
    commands = parse_command_string(text, line_number)
    spans: List[Tuple[int, int]] = []

    def collect(cmds: Sequence[Command], base: int) -> None:
        for command in cmds:
            definition = alias_definition(command)
            bound = bind_definition(command)

            if definition is not None:
                name_token = command.tokens[1]
                if name_token.text == old:
                    spans.append((base + name_token.start, base + name_token.end))
                if len(command.tokens) > 2:
                    body_token = command.tokens[2]
                    inner_base = base + body_token.start + (1 if body_token.quoted else 0)
                    collect(parse_command_string(body_token.text, line_number), inner_base)
            elif bound is not None:
                body_token = command.tokens[2]
                inner_base = base + body_token.start + (1 if body_token.quoted else 0)
                collect(parse_command_string(body_token.text, line_number), inner_base)
            elif command.tokens and command.tokens[0].text == old:
                token = command.tokens[0]
                spans.append((base + token.start, base + token.end))

    collect(commands, 0)
    if not spans:
        return None

    result = text
    for start, end in sorted(spans, reverse=True):
        fragment = result[start:end]
        # A quoted identifier keeps its quotes; only the name inside changes.
        if fragment.startswith('"') and fragment.endswith('"') and len(fragment) >= 2:
            result = result[:start] + f'"{new}"' + result[end:]
        else:
            result = result[:start] + new + result[end:]
    return result


def _rewrite_tokens(command: Command, old: str, new: str) -> Optional[Command]:
    """Return a copy with exact-match name tokens swapped, or None if untouched.

    Only tokens in command-name position, and the arguments of alias/bind that
    name an identifier, are eligible. Message text is never touched here.
    """
    changed = False
    tokens = [Token(t.text, t.quoted, t.start, t.end, t.unterminated) for t in command.tokens]

    definition = alias_definition(command)
    bound = bind_definition(command)

    if definition is not None:
        if tokens[1].text == old:
            tokens[1] = Token(new, tokens[1].quoted, tokens[1].start, tokens[1].end)
            changed = True
        if len(tokens) > 2:
            inner = parse_command_string(tokens[2].text, command.line)
            rewritten = [_rewrite_tokens(c, old, new) or c for c in inner]
            if any(_rewrite_tokens(c, old, new) is not None for c in inner):
                body = "; ".join(render_command(c) for c in rewritten)
                tokens[2] = Token(body, True, tokens[2].start, tokens[2].end)
                changed = True
    elif bound is not None:
        inner = parse_command_string(tokens[2].text, command.line)
        if any(_rewrite_tokens(c, old, new) is not None for c in inner):
            rewritten = [_rewrite_tokens(c, old, new) or c for c in inner]
            body = "; ".join(render_command(c) for c in rewritten)
            tokens[2] = Token(body, True, tokens[2].start, tokens[2].end)
            changed = True
    else:
        if tokens and tokens[0].text == old:
            tokens[0] = Token(new, tokens[0].quoted, tokens[0].start, tokens[0].end)
            changed = True

    if not changed:
        return None
    return Command(tokens=tokens, line=command.line, start=command.start, end=command.end)


def _renamed_family(old: str, new: str, known: Sequence[str]) -> List[Tuple[str, str]]:
    """Related names that should move with the base one.

    ``!afk`` -> ``!idle`` should carry ``!afk_on`` and ``!afk_off`` with it, and
    ``+qsw`` -> ``+swap`` should carry ``-qsw``. Anything that merely starts
    with the same letters is left alone.
    """
    pairs: List[Tuple[str, str]] = []
    old_sign = press_release_parts(old)
    new_sign = press_release_parts(new)

    for name in known:
        if name == old:
            continue

        # +x / -x partners.
        parts = press_release_parts(name)
        if old_sign and parts and parts[1] == old_sign[1] and new_sign:
            pairs.append((name, parts[0] + new_sign[1]))
            continue

        # x_on / x_off states.
        suffixed = state_suffix(name)
        if suffixed and suffixed[0] == old:
            pairs.append((name, f"{new}_{suffixed[1]}"))
    return sorted(set(pairs))


def plan_rename(
    result: ScanResult,
    old_name: str,
    new_name: str,
    include_family: bool = True,
) -> RenamePlan:
    """Work out every edit a rename needs, without applying any of them."""
    old_name = old_name.strip()
    new_name = new_name.strip()
    if not old_name or not new_name:
        raise EditError("both the current and the new name are required")
    if old_name == new_name:
        raise EditError("the new name is the same as the current one")
    if any(c.isspace() or c in '";' for c in new_name):
        raise EditError(
            "an alias name cannot contain spaces, quotes or semicolons -- the engine would "
            "read it as more than one token"
        )

    plan = RenamePlan(old_name=old_name, new_name=new_name)
    known = [d[0].name for defs in result.aliases.values() for d in [defs] if defs]
    known = sorted({d.name for defs in result.aliases.values() for d in defs})

    if old_name.lower() not in result.aliases:
        plan.issues.append(Issue(
            code="rename-unknown-source",
            severity=Severity.WARNING,
            message=f"'{old_name}' is not defined in the scanned collection",
            line=0,
            detail="References to it will still be renamed, but there is no definition to update.",
        ))

    if new_name.lower() in result.aliases:
        plan.issues.append(Issue(
            code="rename-collision",
            severity=Severity.ERROR,
            message=f"'{new_name}' already exists",
            line=0,
            detail=(
                "Renaming onto an existing alias would make one of them unreachable. "
                "Choose a different name, or rename the existing one first."
            ),
        ))

    renames = [(old_name, new_name)]
    if include_family:
        plan.family = _renamed_family(old_name, new_name, known)
        for source, target in plan.family:
            if target.lower() in result.aliases:
                plan.issues.append(Issue(
                    code="rename-collision",
                    severity=Severity.ERROR,
                    message=f"related rename '{source}' -> '{target}' collides with an existing alias",
                    line=0,
                ))
        renames.extend(plan.family)

    for config in result.files.values():
        if not config.is_commands:
            continue
        for line in config.document.lines:
            if not line.commands:
                continue

            # Only the code part of the line is eligible; the comment is a
            # separate, opt-in wording change.
            code_end = line.comment_column if line.comment_column is not None else len(line.raw)
            code = line.raw[:code_end]
            tail = line.raw[code_end:]

            rewritten_code = code
            touched = False
            kinds: Set[str] = set()

            for source, target in renames:
                candidate = rewrite_identifiers(rewritten_code, source, target, line.number)
                if candidate is None:
                    continue
                rewritten_code = candidate
                touched = True
                for command in line.commands:
                    definition = alias_definition(command)
                    if definition and definition[0] == source:
                        kinds.add("definition")
                    elif bind_definition(command) and source in command.arg_text(1):
                        kinds.add("bind")
                    elif definition and source in (command.arg_text(1) or ""):
                        kinds.add("nested")
                    elif command.tokens and command.tokens[0].text == source:
                        kinds.add("call")

            if not touched:
                continue

            # Hold the comment at its original column by adjusting only the
            # whitespace run in front of it. The comment text itself is
            # untouched here.
            after = rewritten_code + tail
            if tail and len(rewritten_code) != len(code):
                stripped = rewritten_code.rstrip()
                shift = code_end - len(stripped)
                after = stripped + (" " * max(1, shift)) + tail

            plan.edits.append(TextEdit(
                file=config.relative,
                line=line.number,
                before=line.raw,
                after=after,
                kind=", ".join(sorted(kinds)) or "call",
                description=f"{', '.join(sorted(kinds))} of {old_name}",
            ))

    plan.wording_edits = _wording_edits(result, renames)
    return plan


_WORD = re.compile(r"(?<![\w!+\-])({})(?![\w])")


def _wording_edits(result: ScanResult, renames: Sequence[Tuple[str, str]]) -> List[TextEdit]:
    """Comments and console/chat text that mention the old name.

    Offered as separate opt-in edits. Renaming code should not silently rewrite
    a player's chat messages or help text; that is a wording decision, not a
    mechanical consequence.
    """
    edits: List[TextEdit] = []
    for config in result.files.values():
        if not config.is_commands:
            continue
        for line in config.document.lines:
            replaced = line.raw
            hit = False

            for source, target in renames:
                pattern = re.compile(r"(?<![\w])" + re.escape(source) + r"(?![\w])")

                if line.comment and pattern.search(line.comment):
                    replaced = pattern.sub(target, replaced)
                    hit = True

                for command in line.commands:
                    if command.lname not in ("echo", "say", "say_team"):
                        continue
                    for token in command.args:
                        if pattern.search(token.text):
                            replaced = pattern.sub(target, replaced)
                            hit = True

            if hit and replaced != line.raw:
                edits.append(TextEdit(
                    file=config.relative,
                    line=line.number,
                    before=line.raw,
                    after=replaced,
                    kind="wording",
                    description="mentions the old name in a comment or message",
                    selected=False,
                ))
    return edits


# ---------------------------------------------------------------------------
# Behaviour editing
# ---------------------------------------------------------------------------

def plan_behaviour_change(
    result: ScanResult,
    alias_name: str,
    new_body: str,
) -> BehaviourChange:
    """Validate a proposed new body for an alias and describe the difference.

    Nothing is executed. Validation is structural: quoting, references, and
    whether a press/release or on/off partner still lines up.
    """
    definition = result.effective_alias(alias_name)
    if definition is None:
        raise EditError(f"'{alias_name}' is not defined in the scanned collection")

    before = parse_command_string(definition.body, definition.line)
    after_line = parse(new_body, definition.file).lines[0] if new_body.strip() else None
    after = parse_command_string(new_body, definition.line)

    change = BehaviourChange(
        alias=definition.name,
        file=definition.file,
        line=definition.line,
        before_body=definition.body,
        after_body=new_body,
        before_commands=[render_command(c) for c in before],
        after_commands=[render_command(c) for c in after],
    )

    before_set = list(change.before_commands)
    after_set = list(change.after_commands)
    change.added = [c for c in after_set if c not in before_set]
    change.removed = [c for c in before_set if c not in after_set]

    # Quoting.
    probe = parse(f'alias "{definition.name}" "{new_body}"', definition.file)
    for issue in probe.all_issues():
        if issue.code == "unterminated-quote":
            change.issues.append(Issue(
                code="unbalanced-quotes",
                severity=Severity.ERROR,
                message="the new body has an unbalanced quote",
                line=definition.line,
                detail="Every opening quote needs a closing one, or the rest of the line is swallowed.",
            ))
            break

    if new_body.count('"') % 2:
        change.issues.append(Issue(
            code="odd-quote-count",
            severity=Severity.ERROR,
            message="odd number of quote characters in the new body",
            line=definition.line,
        ))

    # References.
    for command in after:
        name = command.lname
        if not name or alias_definition(command):
            continue
        if name in result.aliases:
            continue
        from .cfgscan import KNOWN_ENGINE_COMMANDS, KNOWN_ENGINE_PREFIXES
        if name in KNOWN_ENGINE_COMMANDS or any(name.startswith(p) for p in KNOWN_ENGINE_PREFIXES):
            continue
        change.issues.append(Issue(
            code="unknown-reference",
            severity=Severity.WARNING,
            message=f"'{command.name}' is not a known alias or command",
            line=definition.line,
            detail=(
                "It may still be valid -- this tool does not have the full engine command list. "
                "Flagged so you can check rather than repaired by guessing."
            ),
        ))

    # State machines: if the old body redefined itself, the new one probably
    # should too, or the toggle stops toggling.
    # A state alias almost never redefines *itself*; it redefines the base name
    # of its family. '!wallhack_on' points '!wallhack' at '!wallhack_off'.
    # Checking only for self-redefinition misses every real toggle.
    suffixed = state_suffix(definition.name)
    own_names = {definition.name.lower()}
    if suffixed:
        own_names.add(suffixed[0].lower())

    def redefines_family(commands: Sequence[Command]) -> Optional[str]:
        for command in commands:
            inner = alias_definition(command)
            if inner and inner[0].lower() in own_names:
                return inner[0]
        return None

    was_toggle = redefines_family(before)
    if was_toggle and not redefines_family(after):
        change.issues.append(Issue(
            code="toggle-broken",
            severity=Severity.WARNING,
            message=f"the original redefined '{was_toggle}' but the replacement does not",
            line=definition.line,
            detail=(
                f"'{definition.name}' was one state of a toggle: running it pointed "
                f"'{was_toggle}' at the next state. Without that redefinition the toggle stops "
                "advancing and will do the same thing every time."
            ),
        ))

    # Press/release partners.
    parts = press_release_parts(definition.name)
    if parts:
        partner = ("-" if parts[0] == "+" else "+") + parts[1]
        if partner.lower() not in result.aliases:
            change.issues.append(Issue(
                code="missing-partner",
                severity=Severity.WARNING,
                message=f"'{partner}' is not defined",
                line=definition.line,
                detail=(
                    f"'{definition.name}' runs while a key is held; '{partner}' should run when it "
                    "is released. Without it, whatever this starts is never stopped."
                ),
            ))

    return change


def render_alias_line(name: str, body: str, comment: Optional[str] = None) -> str:
    """Emit an alias definition in house style."""
    body_text = f'alias "{name}" "{body}"'
    if not comment:
        return body_text
    padding = max(1, 44 - len(body_text))
    return f"{body_text}{' ' * padding}//{comment.rstrip()}"


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------

def apply_edits(
    result: ScanResult,
    edits: Sequence[TextEdit],
    dry_run: bool = True,
) -> Dict[str, str]:
    """Produce the new text for each affected file.

    Returns ``{relative_path: new_text}``. Writing is the caller's job, so a
    preview and an apply share exactly the same code path.
    """
    selected = [e for e in edits if e.selected]
    by_file: Dict[str, List[TextEdit]] = {}
    for edit in selected:
        by_file.setdefault(edit.file, []).append(edit)

    out: Dict[str, str] = {}
    for relative, file_edits in by_file.items():
        config = None
        for candidate in result.files.values():
            if candidate.relative == relative:
                config = candidate
                break
        if config is None:
            raise EditError(f"{relative} is not part of the scan")

        lines = config.path.read_bytes().decode(
            config.document.encoding, errors="replace"
        ).splitlines()
        for edit in sorted(file_edits, key=lambda e: e.line, reverse=True):
            index = edit.line - 1
            if not (0 <= index < len(lines)):
                raise EditError(f"{relative}:{edit.line} is out of range")
            if lines[index] != edit.before:
                raise EditError(
                    f"{relative}:{edit.line} has changed since the scan; re-scan before applying"
                )
            lines[index] = edit.after

        newline = config.document.newline
        text = newline.join(lines)
        if config.document.trailing_newline:
            text += newline
        out[relative] = text
    return out
