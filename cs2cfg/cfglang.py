"""Source-engine console config syntax: tokenising, parsing, reassembly.

Everything else in the CFG feature sits on this, so it errs towards being
literal about the engine's actual rules rather than convenient:

* ``//`` starts a comment **only outside quotes**. ``say "100// not a comment"``
  is one argument, not a command plus a comment.
* ``;`` separates commands **only outside quotes**. ``say "a; b"`` is one
  command with one argument.
* There are no escape sequences. A backslash is an ordinary character, which is
  why ``play buttons\\button11`` and ``bind "\\"`` mean what they appear to.
* An unterminated quote runs to the end of the line. The engine does not error;
  it just swallows the rest, including anything that looked like a comment.
  That behaviour is reproduced here and reported, because a config in the wild
  really does contain one and guessing at the author's intent would change what
  the file does.

Positions are recorded on every token so edits can be applied surgically
instead of by text substitution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

COMMENT = "//"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Issue:
    """Something worth telling the user about a specific place in a file."""

    code: str
    severity: Severity
    message: str
    line: int
    column: int = 0
    detail: str = ""
    file: str = ""

    def where(self) -> str:
        return f"{self.file}:{self.line}" if self.file else f"line {self.line}"


@dataclass
class Token:
    """One argument. ``text`` is the value; ``raw`` is exactly as written."""

    text: str
    quoted: bool
    start: int
    end: int
    unterminated: bool = False

    @property
    def raw(self) -> str:
        if not self.quoted:
            return self.text
        return f'"{self.text}"' if not self.unterminated else f'"{self.text}'

    def render(self, force_quotes: Optional[bool] = None) -> str:
        """Re-emit the token, optionally normalising whether it is quoted.

        A token is never unquoted if that would change how it parses, so
        anything containing whitespace, a quote, a semicolon or a comment
        marker keeps its quotes regardless of what is asked for.
        """
        must_quote = (
            self.text == ""
            or any(c.isspace() for c in self.text)
            or '"' in self.text
            or ";" in self.text
            or COMMENT in self.text
        )
        if force_quotes is None:
            quoted = self.quoted
        else:
            quoted = force_quotes or must_quote
        quoted = quoted or must_quote
        return f'"{self.text}"' if quoted else self.text


@dataclass
class Command:
    """One executable statement: a name plus arguments."""

    tokens: List[Token]
    line: int
    start: int
    end: int

    @property
    def name(self) -> str:
        return self.tokens[0].text if self.tokens else ""

    @property
    def lname(self) -> str:
        return self.name.lower()

    @property
    def args(self) -> List[Token]:
        return self.tokens[1:]

    def arg(self, index: int) -> Optional[Token]:
        return self.tokens[index + 1] if len(self.tokens) > index + 1 else None

    def arg_text(self, index: int) -> str:
        token = self.arg(index)
        return token.text if token else ""

    def signature(self) -> Tuple[str, ...]:
        """The executable content, ignoring quoting and spacing."""
        return tuple(t.text for t in self.tokens)


@dataclass
class Line:
    """One physical line, with whatever commands and comment it holds."""

    number: int
    raw: str
    commands: List[Command] = field(default_factory=list)
    comment: Optional[str] = None
    comment_column: Optional[int] = None
    issues: List[Issue] = field(default_factory=list)

    @property
    def is_blank(self) -> bool:
        return not self.raw.strip()

    @property
    def is_comment_only(self) -> bool:
        return self.comment is not None and not self.commands

    @property
    def is_banner(self) -> bool:
        """A ``// ====`` or ``// ----`` rule, as opposed to prose."""
        if self.comment is None:
            return False
        body = self.comment.strip()
        return len(body) >= 4 and (set(body) <= set("=") or set(body) <= set("-"))


@dataclass
class Document:
    """A parsed config file."""

    path: str
    lines: List[Line] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
    newline: str = "\n"
    trailing_newline: bool = True
    encoding: str = "utf-8"

    def commands(self) -> Iterable[Command]:
        for line in self.lines:
            yield from line.commands

    def signature(self) -> List[Tuple[str, ...]]:
        """Every executable token, in order. The thing formatting must preserve."""
        return [c.signature() for c in self.commands()]

    def all_issues(self) -> List[Issue]:
        out = list(self.issues)
        for line in self.lines:
            out.extend(line.issues)
        return out


# ---------------------------------------------------------------------------
# Tokenising
# ---------------------------------------------------------------------------

def tokenize_line(text: str, line_number: int = 1) -> Line:
    """Split one line into commands plus an optional trailing comment."""
    line = Line(number=line_number, raw=text)

    tokens: List[Token] = []
    command_start: Optional[int] = None
    index = 0
    length = len(text)

    def flush(end: int) -> None:
        nonlocal tokens, command_start
        if tokens:
            line.commands.append(Command(
                tokens=tokens, line=line_number,
                start=command_start if command_start is not None else 0,
                end=end,
            ))
        tokens = []
        command_start = None

    while index < length:
        char = text[index]

        if char.isspace():
            index += 1
            continue

        # Comment, but only out here in the open.
        if text.startswith(COMMENT, index):
            line.comment = text[index + len(COMMENT):]
            line.comment_column = index
            break

        if char == ";":
            flush(index)
            index += 1
            continue

        if command_start is None:
            command_start = index

        if char == '"':
            start = index
            index += 1
            buffer: List[str] = []
            terminated = False
            while index < length:
                if text[index] == '"':
                    terminated = True
                    index += 1
                    break
                buffer.append(text[index])
                index += 1
            token = Token("".join(buffer), True, start, index, unterminated=not terminated)
            tokens.append(token)
            if not terminated:
                line.issues.append(Issue(
                    code="unterminated-quote",
                    severity=Severity.ERROR,
                    message="quote is never closed, so the rest of the line is swallowed as text",
                    line=line_number,
                    column=start,
                    detail=(
                        "The engine reads to the end of the line and keeps going. Anything after "
                        "this point on the line -- including what looks like a comment -- becomes "
                        "part of the argument. Left exactly as written; repairing it would change "
                        "what the file does."
                    ),
                ))
            continue

        # Bare token: runs until whitespace, a separator, or a comment.
        start = index
        while index < length:
            if text[index].isspace() or text[index] in ';"':
                break
            if text.startswith(COMMENT, index):
                break
            index += 1
        tokens.append(Token(text[start:index], False, start, index))

    flush(index)
    return line


def parse(text: str, path: str = "") -> Document:
    """Parse a whole config file."""
    newline = "\r\n" if "\r\n" in text else "\n"
    trailing = text.endswith(("\n", "\r"))
    body = text.splitlines()

    document = Document(path=path, newline=newline, trailing_newline=trailing)
    for number, raw in enumerate(body, start=1):
        line = tokenize_line(raw, number)
        for issue in line.issues:
            issue.file = path
        document.lines.append(line)
    return document


def parse_command_string(text: str, line_number: int = 0) -> List[Command]:
    """Parse the inside of an alias or bind body.

    Used for the deferred content of ``alias x "a; b"``: it is a command list
    in its own right, and the semicolons inside it separate commands that run
    later rather than now.
    """
    return tokenize_line(text, line_number).commands


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def write_config_text(path, text: str, encoding: str = "utf-8") -> None:
    """Write config text verbatim, with no newline translation.

    ``Path.write_text`` opens in text mode with ``newline=None``, which rewrites
    every ``\\n`` to ``os.linesep``. On Windows that is ``\\r\\n`` -- so text
    that already contains ``\\r\\n`` comes out as ``\\r\\r\\n``, doubling every
    line ending in the file.

    That matters here because the parser reads bytes and decodes them, which
    preserves ``\\r\\n``, and the writers reassemble text using the newline the
    document actually had. Round-tripping a CRLF file -- which is every file a
    Windows editor produces -- would corrupt it. Opening with ``newline=""``
    disables translation and writes exactly what it is given.
    """
    with open(path, "w", encoding=encoding, newline="") as handle:
        handle.write(text)


def restore_newlines(text: str, newline: str = "\n",
                     trailing: bool = True) -> str:
    """Give edited text back the line ending the file it came from used.

    A browser textarea returns "\\n" whatever the file contained, so writing it
    straight back would convert a CRLF file to LF -- every line changed, in a
    file the user only meant to edit one line of. Normalising first means text
    that arrives already mixed comes out consistent rather than half converted.
    """
    body = text.replace("\r\n", "\n").replace("\r", "\n")
    if newline != "\n":
        body = body.replace("\n", newline)
    if trailing and body and not body.endswith(newline):
        body += newline
    return body


def render_command(command: Command, force_quotes: Optional[bool] = None) -> str:
    return " ".join(t.render(force_quotes) for t in command.tokens)


def render_commands(commands: Sequence[Command], force_quotes: Optional[bool] = None) -> str:
    return "; ".join(render_command(c, force_quotes) for c in commands)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

# Commands that take a nested command list as an argument. The engine defers
# that content: it is parsed now and run later, which is the distinction the
# whole dependency analysis turns on.
DEFERRING = {"alias", "bind", "bindtoggle"}

EXEC_COMMANDS = {"exec", "execifexists"}

# Not settings: these do something when the line runs.
EXECUTABLE = {
    "echo", "say", "say_team", "clear", "exec", "execifexists", "alias", "bind",
    "unbind", "unbindall", "toggle", "incrementvar", "play", "map", "disconnect",
    "quit", "restart", "mp_restartgame", "mp_warmup_end", "host_writeconfig",
    "status", "connect", "retry", "give", "buy", "ent_fire", "bot_place",
    "sellbackall", "autobuy", "rebuy", "cancelselect",
}


def is_deferring(command: Command) -> bool:
    return command.lname in DEFERRING


def alias_definition(command: Command) -> Optional[Tuple[str, str]]:
    """``(name, body)`` if this defines an alias, else None.

    ``alias foo`` with no body clears it, which is a definition of a sort and
    is reported as one with an empty body.
    """
    if command.lname != "alias" or len(command.tokens) < 2:
        return None
    name = command.arg_text(0)
    body = command.arg_text(1) if len(command.tokens) > 2 else ""
    return name, body


def bind_definition(command: Command) -> Optional[Tuple[str, str]]:
    """``(key, body)`` if this binds a key, else None."""
    if command.lname not in ("bind", "bindtoggle") or len(command.tokens) < 3:
        return None
    return command.arg_text(0), command.arg_text(1)


def exec_target(command: Command) -> Optional[str]:
    if command.lname in EXEC_COMMANDS and len(command.tokens) > 1:
        return command.arg_text(0)
    return None


_PRESS_RELEASE = re.compile(r"^([+-])(.+)$")


def press_release_parts(name: str) -> Optional[Tuple[str, str]]:
    """``('+', 'jump')`` for ``+jump``; None for anything else."""
    match = _PRESS_RELEASE.match(name)
    return (match.group(1), match.group(2)) if match else None


def state_suffix(name: str) -> Optional[Tuple[str, str]]:
    """``('!afk', 'on')`` for ``!afk_on``; None for anything else."""
    for suffix in ("_on", "_off", "_enable", "_disable", "_1", "_2"):
        if name.lower().endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)], suffix.lstrip("_")
    return None


def family_of(name: str) -> str:
    """The base identifier a name belongs to, for grouping related aliases."""
    parts = press_release_parts(name)
    if parts:
        return parts[1]
    suffixed = state_suffix(name)
    if suffixed:
        return suffixed[0]
    return name


def normalise_exec_path(target: str) -> str:
    """Normalise an exec target for comparison.

    Paths in ``exec`` are resolved from the cfg root, never relative to the
    file doing the exec'ing, which is why ``mrwhiteer/tools/alias.vcfg`` works
    identically from ``autoexec.vcfg`` and from a file inside ``tools/``. The
    explicit extension is preserved: the engine treats ``a.vcfg`` and ``a.cfg``
    as different files.
    """
    path = target.replace("\\", "/").strip()
    # removeprefix, not lstrip: lstrip("./") strips *characters*, so a path
    # beginning with a dot would lose it.
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/").lower()


def looks_like_commands(text: str) -> bool:
    """Whether a file's content is console commands rather than KeyValues.

    ``.vcfg`` is used for both in the wild: Valve writes KeyValues into some,
    and players write plain console commands into others. Checking the content
    is the only reliable way to tell.

    Braces are counted from *tokenised* content only. Counting them in the raw
    text misreads any config whose comments describe keys -- ``// JUMP {BUTTON
    - SPACE}`` is a comment, not structure, and a file full of those was being
    classified as KeyValues and skipped entirely.
    """
    code_lines: List[str] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = tokenize_line(raw, number)
        if not line.commands:
            continue
        code_lines.append(" ".join(
            t.text if not t.quoted else "\x00" for c in line.commands for t in c.tokens
        ))

    if not code_lines:
        return True

    first = code_lines[0].strip()
    # KeyValues opens with a lone quoted root key, then a brace on its own.
    if first == "\x00" and len(code_lines) > 1 and code_lines[1].strip().startswith("{"):
        return False
    if first.startswith("{"):
        return False

    body = "\n".join(code_lines)
    braces = body.count("{") + body.count("}")
    return braces <= 2
