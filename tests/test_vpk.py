"""Reading a VPK v2 directory -- built from a small synthetic package here,
not the real multi-gigabyte one any installed copy of CS2 has.
"""

from __future__ import annotations

import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import vpk  # noqa: E402


def _entry_struct(crc: int, preload_bytes: int, archive_index: int,
                  entry_offset: int, entry_length: int) -> bytes:
    return struct.pack("<IHHIIH", crc, preload_bytes, archive_index,
                       entry_offset, entry_length, 0xFFFF)


def _build_vpk(entries: dict, extra_after_tree: bytes = b"") -> bytes:
    """entries: {"folder/name.ext": preload_bytes} -- every test entry here
    is small enough to live entirely in the preload, the same as a real
    VPK does for tiny files."""
    by_ext: dict = {}
    for full_path, data in entries.items():
        folder, _, filename_ext = full_path.rpartition("/")
        filename, _, ext = filename_ext.rpartition(".")
        by_ext.setdefault(ext, {}).setdefault(folder, {})[filename] = data

    tree = bytearray()
    for ext, folders in by_ext.items():
        tree += ext.encode() + b"\x00"
        for folder, files in folders.items():
            tree += (folder or " ").encode() + b"\x00"
            for filename, data in files.items():
                tree += filename.encode() + b"\x00"
                tree += _entry_struct(0, len(data), 0x7FFF, 0, 0)
                tree += data
            tree += b"\x00"  # end of filenames in this folder
        tree += b"\x00"  # end of folders for this extension
    tree += b"\x00"  # end of extensions

    header = struct.pack("<IIIIIII", vpk.SIGNATURE, 2, len(tree), 0, 0, 0, 0)
    return header + bytes(tree) + extra_after_tree


class ReadingTheIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "pak01_dir.vpk"
        vpk.forget_index()
        self.addCleanup(vpk.forget_index)

    def _write(self, data: bytes) -> None:
        self.path.write_bytes(data)

    def test_a_preloaded_entry_is_found_by_its_full_path(self):
        self._write(_build_vpk({"scripts/items/items_game.txt": b"hello"}))
        index = vpk.read_index(self.path)
        self.assertIn("scripts/items/items_game.txt", index)
        self.assertEqual(index["scripts/items/items_game.txt"].preload, b"hello")

    def test_a_root_level_file_has_no_leading_slash(self):
        self._write(_build_vpk({"readme.txt": b"hi"}))
        index = vpk.read_index(self.path)
        self.assertIn("readme.txt", index)

    def test_several_entries_under_different_extensions_are_all_found(self):
        self._write(_build_vpk({
            "a/one.txt": b"1",
            "b/two.vmat_c": b"22",
            "a/three.txt": b"333",
        }))
        index = vpk.read_index(self.path)
        self.assertEqual(set(index), {"a/one.txt", "b/two.vmat_c", "a/three.txt"})

    def test_too_small_a_file_is_a_vpk_error(self):
        self._write(b"\x00\x00")
        with self.assertRaises(vpk.VpkError):
            vpk.read_index(self.path)

    def test_a_bad_signature_is_a_vpk_error(self):
        self._write(struct.pack("<III", 0x12345678, 2, 0))
        with self.assertRaises(vpk.VpkError):
            vpk.read_index(self.path)

    def test_an_unknown_version_is_a_vpk_error(self):
        self._write(struct.pack("<III", vpk.SIGNATURE, 99, 0))
        with self.assertRaises(vpk.VpkError):
            vpk.read_index(self.path)

    def test_find_matches_by_suffix(self):
        self._write(_build_vpk({"materials/models/weapons/x/so_red.vmat_c": b"x"}))
        index = vpk.read_index(self.path)
        entry = vpk.find(index, "so_red.vmat_c")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.path, "materials/models/weapons/x/so_red.vmat_c")

    def test_find_with_no_match_is_none(self):
        self._write(_build_vpk({"a/one.txt": b"1"}))
        index = vpk.read_index(self.path)
        self.assertIsNone(vpk.find(index, "does_not_exist.txt"))


class ReadingFileBytes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "pak01_dir.vpk"
        vpk.forget_index()
        self.addCleanup(vpk.forget_index)

    def test_a_fully_preloaded_entry_reads_back_exactly(self):
        self.path.write_bytes(_build_vpk({"a/one.txt": b"the-full-contents"}))
        index = vpk.read_index(self.path)
        data = vpk.read_file(self.path, index["a/one.txt"])
        self.assertEqual(data, b"the-full-contents")

    def test_data_stored_in_the_dir_vpk_itself_past_the_tree_is_read(self):
        """archive_index 0x7fff with entry_length > 0 means "the rest is
        right after the tree, in this same _dir.vpk file" -- the preload is
        only part of the entry in that case."""
        preload = b"abc"
        rest = b"def-the-rest"
        folder_entries = {}
        # Build manually so entry_length can be set and extra bytes appended
        # at the known tree-end offset, something _build_vpk's helper
        # (every-entry-fully-preloaded) does not support.
        tree = bytearray()
        tree += b"txt\x00"
        tree += b"a\x00"
        tree += b"one\x00"
        tree += _entry_struct(0, len(preload), 0x7FFF, 0, len(rest))
        tree += preload
        tree += b"\x00\x00\x00"  # end filenames, end folders, end extensions
        header = struct.pack("<IIIIIII", vpk.SIGNATURE, 2, len(tree), 0, 0, 0, 0)
        self.path.write_bytes(header + bytes(tree) + rest)

        index = vpk.read_index(self.path)
        data = vpk.read_file(self.path, index["a/one.txt"])
        self.assertEqual(data, preload + rest)


class CachingTheIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "pak01_dir.vpk"
        vpk.forget_index()
        self.addCleanup(vpk.forget_index)

    def test_a_second_read_does_not_reparse_the_file(self):
        self.path.write_bytes(_build_vpk({"a/one.txt": b"1"}))
        first = vpk.read_index(self.path)
        # Prove it is the *same* dict object, not an equal one re-parsed.
        second = vpk.read_index(self.path)
        self.assertIs(first, second)

    def test_a_changed_file_is_not_served_stale(self):
        self.path.write_bytes(_build_vpk({"a/one.txt": b"1"}))
        first = vpk.read_index(self.path)
        self.assertIn("a/one.txt", first)

        time.sleep(0.01)
        self.path.write_bytes(_build_vpk({"b/two.txt": b"2"}))
        second = vpk.read_index(self.path)
        self.assertNotIn("a/one.txt", second)
        self.assertIn("b/two.txt", second)

    def test_forget_index_clears_one_path_without_touching_others(self):
        other = Path(self.tmp.name) / "other_dir.vpk"
        self.path.write_bytes(_build_vpk({"a/one.txt": b"1"}))
        other.write_bytes(_build_vpk({"a/one.txt": b"1"}))
        vpk.read_index(self.path)
        vpk.read_index(other)
        self.assertEqual(len(vpk._INDEX_CACHE), 2)
        vpk.forget_index(self.path)
        self.assertEqual(len(vpk._INDEX_CACHE), 1)
        self.assertIn(str(other), vpk._INDEX_CACHE)


if __name__ == "__main__":
    unittest.main()
