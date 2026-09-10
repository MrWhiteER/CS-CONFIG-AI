"""Polishing: reformat a config without changing what it does.

The rule the whole module is built around: **the executable token sequence must
come out identical**. Formatting may change whitespace, comment alignment and
blank lines. It may not reorder commands, merge or split them, add or remove
them, alphabetise anything, rename anything, or move anything between files.

:func:`polish` verifies that itself by re-parsing its own output and comparing
token signatures. If they differ it returns the original untouched and reports
why, because a formatter that silently alters behaviour is worse than one that
declines to run.

The house style is taken from ``mainsettings/gamesettings.vcfg``: a banner of
``=`` for the file, ``-`` rules around section headings, one command per line,
and inline ``//`` comments aligned within their own block rather than across
the whole file.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .cfglang import (
    COMMENT, Command, Document, Issue, Line, Severity, parse, render_command,
)

BANNER = "// " + "=" * 45
RULE = "// " + "-" * 26

# Where inline comments sit. Wide enough for the long bind lines in the
# reference collection without pushing short setting lines absurdly far out.
COMMENT_COLUMN = 44
MAX_COMMENT_COLUMN = 92


@dataclass
class FormatChange:
    line: int
    before: str
    after: str
    reason: str


@dataclass
class FormatResult:
    path: str
    original: str
    formatted: str
    changed: bool
    safe: bool
    issues: List[Issue] = field(default_factory=list)
    changes: List[FormatChange] = field(default_factory=list)
    skipped_reason: str = ""

    @property
    def diff(self) -> str:
        return "\n".join(difflib.unified_diff(
            self.original.splitlines(),
            self.formatted.splitlines(),
            fromfile=f"{self.path} (before)",
            tofile=f"{self.path} (after)",
            lineterm="",
            n=2,
        ))

    def stats(self) -> dict:
        before = self.original.splitlines()
        after = self.formatted.splitlines()
        changed = sum(1 for a, b in zip(before, after) if a != b)
        return {
            "lines_before": len(before),
            "lines_after": len(after),
            "lines_touched": changed + abs(len(after) - len(before)),
        }


def _strip_trailing(text: str) -> str:
    """Remove trailing whitespace, but never from inside a quoted string.

    The reference collection has chat messages with meaningful trailing spaces
    inside quotes, so this only trims what is outside them.
    """
    in_quote = False
    last_significant = -1
    for index, char in enumerate(text):
        if char == '"':
            in_quote = not in_quote
        if in_quote or not char.isspace():
            last_significant = index
    return text[: last_significant + 1]


def _align(body: str, comment: Optional[str], column: int) -> str:
    if comment is None:
        return _strip_trailing(body)
    body = _strip_trailing(body)
    if not body:
        return f"{COMMENT}{comment}".rstrip()
    padding = max(1, column - len(body))
    if len(body) + padding > MAX_COMMENT_COLUMN:
        padding = 1
    return f"{body}{' ' * padding}{COMMENT}{comment.rstrip()}"


def _is_section_heading(line: Line, previous: Optional[Line], following: Optional[Line]) -> bool:
    """A comment sandwiched between two rules is a section heading."""
    return (
        line.is_comment_only and not line.is_banner
        and previous is not None and previous.is_banner
        and following is not None and following.is_banner
    )


def _block_comment_column(lines: Sequence[Line], start: int, end: int) -> int:
    """Alignment column for one run of commands, not the whole file.

    Local alignment is what the reference files do and what stays readable: one
    very long bind should not push every short setting in the file out to
    column 90.
    """
    widest = 0
    for line in lines[start:end]:
        if line.comment is None or not line.commands:
            continue
        body = render_command(line.commands[0])
        if len(line.commands) > 1:
            body = "; ".join(render_command(c) for c in line.commands)
        widest = max(widest, len(body))
    if widest == 0:
        return COMMENT_COLUMN
    return min(max(COMMENT_COLUMN, widest + 2), MAX_COMMENT_COLUMN)


def format_document(document: Document, source: str) -> Tuple[str, List[FormatChange]]:
    """Render a parsed document in house style."""
    lines = document.lines
    changes: List[FormatChange] = []
    out: List[str] = []

    # Group consecutive command-bearing lines so comment alignment is local.
    blocks: List[Tuple[int, int]] = []
    start: Optional[int] = None
    for index, line in enumerate(lines):
        if line.commands:
            if start is None:
                start = index
        else:
            if start is not None:
                blocks.append((start, index))
                start = None
    if start is not None:
        blocks.append((start, len(lines)))

    column_for: dict = {}
    for begin, finish in blocks:
        column = _block_comment_column(lines, begin, finish)
        for index in range(begin, finish):
            column_for[index] = column

    blank_run = 0
    for index, line in enumerate(lines):
        previous = lines[index - 1] if index else None
        following = lines[index + 1] if index + 1 < len(lines) else None

        if line.is_blank:
            blank_run += 1
            # Collapse runs of three or more blank lines to two.
            if blank_run <= 2:
                out.append("")
            continue
        blank_run = 0

        if line.is_comment_only:
            body = line.comment or ""
            if line.is_banner:
                text = BANNER if set(body.strip()) <= set("=") else RULE
            elif _is_section_heading(line, previous, following):
                text = f"{COMMENT} {body.strip()}"
            else:
                # Preserve the author's own prose exactly, only trimming the
                # trailing whitespace and normalising the leading space.
                stripped = body.rstrip()
                text = f"{COMMENT}{stripped}" if stripped.startswith(" ") else f"{COMMENT} {stripped}"
                if not stripped:
                    text = COMMENT
            if text != line.raw:
                changes.append(FormatChange(line.number, line.raw, text, "comment formatting"))
            out.append(text)
            continue

        if not line.commands:
            out.append(_strip_trailing(line.raw))
            continue

        # One top-level command per line, except when the author put several on
        # one line deliberately; splitting those would change the diff more than
        # it helps, so they are kept together and only respaced.
        body = "; ".join(render_command(c) for c in line.commands)
        text = _align(body, line.comment, column_for.get(index, COMMENT_COLUMN))
        if text != line.raw:
            changes.append(FormatChange(line.number, line.raw, text, "spacing and alignment"))
        out.append(text)

    # Trim leading and trailing blank lines to at most one.
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()

    newline = document.newline
    rendered = newline.join(out)
    if document.trailing_newline:
        rendered += newline
    return rendered, changes


def _signatures_match(before: Document, after: Document) -> Tuple[bool, str]:
    left = before.signature()
    right = after.signature()
    if left == right:
        return True, ""

    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return False, (
                f"command {index + 1} changed: {a!r} became {b!r}"
            )
    return False, f"command count changed: {len(left)} became {len(right)}"


def polish(text: str, path: str = "") -> FormatResult:
    """Format a config, refusing to return output that would run differently."""
    document = parse(text, path)
    issues = list(document.all_issues())

    unterminated = [i for i in issues if i.code == "unterminated-quote"]
    if unterminated:
        # The parse is a faithful reproduction of what the engine does with a
        # broken quote, but it is not what the author meant, and reformatting
        # around it would bake in a guess. Report and leave alone.
        return FormatResult(
            path=path, original=text, formatted=text, changed=False, safe=False,
            issues=issues,
            skipped_reason=(
                f"line {unterminated[0].line} has an unterminated quote. The affected content is "
                "preserved exactly; formatting it would require guessing where the quote was "
                "meant to close, which could change what the file does."
            ),
        )

    formatted, changes = format_document(document, text)
    reparsed = parse(formatted, path)

    ok, why = _signatures_match(document, reparsed)
    if not ok:
        return FormatResult(
            path=path, original=text, formatted=text, changed=False, safe=False,
            issues=issues,
            skipped_reason=f"formatting would have altered the commands ({why}); left unchanged",
        )

    return FormatResult(
        path=path,
        original=text,
        formatted=formatted,
        changed=formatted != text,
        safe=True,
        issues=issues,
        changes=changes,
    )


def is_idempotent(text: str, path: str = "") -> bool:
    """Whether formatting twice gives the same result as formatting once."""
    once = polish(text, path)
    if not once.safe:
        return True
    twice = polish(once.formatted, path)
    return twice.formatted == once.formatted
