"""Minimal Valve KeyValues (VDF) support.

Two very different jobs, handled two very different ways:

* :func:`parse` / :func:`dumps` do a full round trip. Used for small files
  we own outright, like ``cs2_video.txt``.
* :func:`find_key_line` does a path-aware scan that returns *line numbers*
  only. Callers patch a single line of Steam's ``localconfig.vdf`` and leave
  every other byte of that 300 KB file exactly as Steam wrote it. Reserialising
  a file Steam owns is how you lose someone's friends list.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

_WHITESPACE = " \t\r\n"


class VdfError(ValueError):
    """Raised when a KeyValues document cannot be understood."""


def _tokenize(text: str) -> List[Tuple[str, str, int]]:
    """Return ``(kind, value, lineno)`` triples; kind is 'str', '{' or '}'."""
    tokens: List[Tuple[str, str, int]] = []
    i = 0
    line = 1
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch in _WHITESPACE:
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch in "{}":
            tokens.append((ch, ch, line))
            i += 1
            continue
        if ch == '"':
            start_line = line
            i += 1
            buf: List[str] = []
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    buf.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, "\\" + nxt))
                    i += 2
                    continue
                if c == '"':
                    i += 1
                    break
                if c == "\n":
                    line += 1
                buf.append(c)
                i += 1
            else:
                raise VdfError(f"unterminated string starting on line {start_line}")
            tokens.append(("str", "".join(buf), start_line))
            continue
        # Bare token, e.g. an unquoted key. Runs to the next delimiter.
        start_line = line
        buf = []
        while i < n and text[i] not in _WHITESPACE and text[i] not in '{}"':
            buf.append(text[i])
            i += 1
        tokens.append(("str", "".join(buf), start_line))
    return tokens


def parse(text: str) -> Dict[str, Any]:
    """Parse a KeyValues document into nested dicts.

    Duplicate keys keep the last value, which is what Steam's own reader does.
    """
    tokens = _tokenize(text)
    root: Dict[str, Any] = {}
    stack: List[Dict[str, Any]] = [root]
    pending: Optional[str] = None

    for kind, value, lineno in tokens:
        if kind == "str":
            if pending is None:
                pending = value
            else:
                stack[-1][pending] = value
                pending = None
        elif kind == "{":
            if pending is None:
                raise VdfError(f"line {lineno}: '{{' with no key in front of it")
            child: Dict[str, Any] = {}
            stack[-1][pending] = child
            stack.append(child)
            pending = None
        else:  # '}'
            if len(stack) == 1:
                raise VdfError(f"line {lineno}: '}}' without a matching '{{'")
            stack.pop()

    if len(stack) != 1:
        raise VdfError("unbalanced braces: document ends inside a block")
    return root


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def dumps(data: Dict[str, Any], indent: int = 0) -> str:
    """Serialise nested dicts back to KeyValues, in Valve's tab style."""
    pad = "\t" * indent
    out: List[str] = []
    for key, value in data.items():
        if isinstance(value, dict):
            out.append(f'{pad}"{_escape(key)}"')
            out.append(f"{pad}{{")
            out.append(dumps(value, indent + 1))
            out.append(f"{pad}}}")
        else:
            out.append(f'{pad}"{_escape(key)}"\t\t"{_escape(str(value))}"')
    return "\n".join(out)


def find_key_line(text: str, path: List[str], key: str) -> Dict[str, Optional[int]]:
    """Locate a key inside a nested block without reserialising anything.

    ``path`` is the chain of block names to descend, compared case-insensitively
    because Steam is inconsistent about capitalisation across versions.

    Returns a dict with:

    ``key_line``
        1-based line number of the ``"key"  "value"`` pair, or ``None``.
    ``block_open_line``
        1-based line of the ``{`` that opens the target block, or ``None`` if
        the block itself is missing. Callers insert after this line.
    ``block_indent``
        Tab depth of the keys inside that block, for building a matching line.
    """
    tokens = _tokenize(text)
    want = [p.lower() for p in path]
    stack: List[str] = []
    pending: Optional[str] = None
    block_open_line: Optional[int] = None
    key_line: Optional[int] = None

    for kind, value, lineno in tokens:
        if kind == "str":
            if pending is None:
                pending = value
            else:
                if [s.lower() for s in stack] == want and pending.lower() == key.lower():
                    key_line = lineno
                pending = None
        elif kind == "{":
            if pending is None:
                continue
            stack.append(pending)
            if [s.lower() for s in stack] == want:
                block_open_line = lineno
            pending = None
        else:
            if stack:
                stack.pop()

    return {
        "key_line": key_line,
        "block_open_line": block_open_line,
        "block_indent": len(want) + 1 if block_open_line is not None else None,
    }


def read_value(text: str, path: List[str], key: str) -> Optional[str]:
    """Read one value out of a nested block, or ``None`` if it is not there."""
    node: Any = parse(text)
    for part in path:
        if not isinstance(node, dict):
            return None
        match = next((k for k in node if k.lower() == part.lower()), None)
        if match is None:
            return None
        node = node[match]
    if not isinstance(node, dict):
        return None
    match = next((k for k in node if k.lower() == key.lower()), None)
    return node[match] if match is not None and isinstance(node[match], str) else None
