"""Reading Valve's VPK v2 package format -- directory listing and raw bytes.

This is Valve's own documented modding format (not reverse-engineered, not a
trade secret): a signature, a tree of null-terminated extension/folder/file
name strings each followed by a small metadata struct, then either embedded
"preload" bytes or an offset into a numbered archive part
(``pak01_000.vpk``, ``pak01_001.vpk``, ...). Reading it is just binary
parsing of a documented container -- the same kind of thing :mod:`cs2cfg.vdf`
does for KeyValues text.

What this does not do: nothing here decodes what is *inside* a compiled
Source 2 resource (``.vmdl_c``, ``.vmat_c``, ...). That format is not
published by Valve, and this module stops at handing back the raw bytes of
whatever entry was asked for.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Dict, Iterator, NamedTuple, Optional

SIGNATURE = 0x55AA1234


class VpkError(ValueError):
    """The file does not look like a VPK v2 directory, or is truncated."""


class Entry(NamedTuple):
    path: str               # full internal path, e.g. "scripts/items/items_game.txt"
    crc: int
    archive_index: int      # 0x7fff means "stored in this _dir.vpk itself"
    entry_offset: int
    entry_length: int
    preload: bytes          # bytes embedded directly in the directory tree


def _read_cstr(data: bytes, pos: int) -> tuple:
    end = data.index(b"\x00", pos)
    return data[pos:end].decode("utf-8", "replace"), end + 1


_INDEX_CACHE: Dict[str, tuple] = {}


def read_index(dir_vpk: Path) -> Dict[str, Entry]:
    """Every entry in the package, keyed by its full internal path.

    Cached in memory by path and the file's own modification time: parsing
    a VPK with well over a hundred thousand entries from scratch on every
    call added real, avoidable latency to anything that calls this more
    than once in a process's lifetime (cs2cfg.skin_render resolves a
    texture with two or three of these in a row). A changed mtime -- the
    game updating -- invalidates it automatically rather than needing to be
    told to.
    """
    key = str(dir_vpk)
    try:
        mtime = dir_vpk.stat().st_mtime_ns
    except OSError:
        mtime = None
    cached = _INDEX_CACHE.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    index = _parse_index(dir_vpk)
    _INDEX_CACHE[key] = (mtime, index)
    return index


def forget_index(dir_vpk: Optional[Path] = None) -> None:
    if dir_vpk is None:
        _INDEX_CACHE.clear()
    else:
        _INDEX_CACHE.pop(str(dir_vpk), None)


def _parse_index(dir_vpk: Path) -> Dict[str, Entry]:
    data = dir_vpk.read_bytes()
    if len(data) < 12:
        raise VpkError(f"{dir_vpk} is too small to be a VPK")

    signature, version, tree_size = struct.unpack_from("<III", data, 0)
    if signature != SIGNATURE:
        raise VpkError(f"{dir_vpk} does not start with the VPK signature")

    if version == 1:
        header_size = 12
    elif version == 2:
        header_size = 28  # + file_data/archive_md5/other_md5/signature section sizes
    else:
        raise VpkError(f"{dir_vpk} is VPK version {version}, which this does not know")

    pos = header_size
    tree_end = header_size + tree_size
    out: Dict[str, Entry] = {}

    while pos < tree_end:
        extension, pos = _read_cstr(data, pos)
        if extension == "":
            break
        while pos < tree_end:
            folder, pos = _read_cstr(data, pos)
            if folder == "":
                break
            folder = "" if folder == " " else folder
            while pos < tree_end:
                filename, pos = _read_cstr(data, pos)
                if filename == "":
                    break
                crc, preload_bytes, archive_index, entry_offset, entry_length, terminator = \
                    struct.unpack_from("<IHHIIH", data, pos)
                pos += 18
                preload = data[pos:pos + preload_bytes]
                pos += preload_bytes

                full_path = f"{folder}/{filename}.{extension}" if folder else f"{filename}.{extension}"
                out[full_path] = Entry(full_path, crc, archive_index, entry_offset,
                                       entry_length, preload)

    return out


def read_file(dir_vpk: Path, entry: Entry) -> bytes:
    """The full bytes of one entry: its preload, plus whatever is in an
    archive part when there is more than what was preloaded."""
    if entry.entry_length == 0:
        return entry.preload
    if entry.archive_index == 0x7FFF:
        # The remainder lives in the _dir.vpk itself, right after the tree.
        with dir_vpk.open("rb") as handle:
            handle.seek(0)
            header = handle.read(28)
            tree_size = struct.unpack_from("<I", header, 8)[0]
            version = struct.unpack_from("<I", header, 4)[0]
            header_size = 12 if version == 1 else 28
            handle.seek(header_size + tree_size + entry.entry_offset)
            rest = handle.read(entry.entry_length)
        return entry.preload + rest

    archive_path = dir_vpk.parent / dir_vpk.name.replace("_dir.vpk", f"_{entry.archive_index:03d}.vpk")
    with archive_path.open("rb") as handle:
        handle.seek(entry.entry_offset)
        rest = handle.read(entry.entry_length)
    return entry.preload + rest


def find(index: Dict[str, Entry], suffix: str) -> Optional[Entry]:
    """The first entry whose path ends with ``suffix``, if any."""
    for path, entry in index.items():
        if path.endswith(suffix):
            return entry
    return None
