"""Map pictures cut out of CS2's own files (cs2cfg.mapart)."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg import mapart

PNG = b"\x89PNG\r\n\x1a\n" + b"pixels" + b"IEND\xaeB`\x82"


class Pictures(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.vpk = self.tmp / "pak01_dir.vpk"
        self.vpk.write_bytes(b"x")
        self.index = {mapart.FOLDER + "360p/de_dust2_png.vtex_c": "dust2",
                      mapart.FOLDER + "720p/de_mirage_png.vtex_c": "mirage"}

    def _picture(self, map_id):
        with mock.patch.object(mapart.vpk, "read_index", return_value=self.index), \
             mock.patch.object(mapart.vpk, "read_file", return_value=b"RED2" + b"\0" * 2096 + PNG):
            return mapart.picture(self.vpk, self.tmp / "data", map_id)

    def test_cut_from_the_compiled_texture(self):
        self.assertEqual(mapart.cut_png(b"RED2header" + PNG + b"tail"), PNG)
        self.assertIsNone(mapart.cut_png(b"RED2 no picture"))

    def test_picture_by_any_spelling(self):
        out = self._picture("de_dustii")
        self.assertEqual(out.name, "de_dust2.png")
        self.assertEqual(out.read_bytes(), PNG)
        self.assertEqual(self._picture("de_mirage").name, "de_mirage.png")

    def test_unknown_or_unsafe_ids(self):
        self.assertIsNone(self._picture("de_nothere"))
        self.assertIsNone(self._picture("../../secret"))

    def test_no_cs2_on_this_pc(self):
        self.assertIsNone(mapart.picture(None, self.tmp / "data", "de_dust2"))


class ModeIcons(unittest.TestCase):
    def test_game_icon_for_a_plain_mode_name(self):
        tmp = Path(tempfile.mkdtemp())
        vpk_path = tmp / "pak01_dir.vpk"
        vpk_path.write_bytes(b"x")
        index = {mapart.ICON_FOLDER + "scrimcomp2v2.vsvg_c": "w"}
        svg = b'<svg viewBox="0 0 32 32"><path d="M0 0h1"/></svg>'
        with mock.patch.object(mapart.vpk, "read_index", return_value=index), \
             mock.patch.object(mapart.vpk, "read_file", return_value=b"RED2..." + svg + b"\0tail"):
            out = mapart.mode_icon(vpk_path, tmp / "data", "scrimcomp2v2")
            self.assertEqual(out.read_bytes(), svg.replace(b"<svg", b'<svg xmlns="http://www.w3.org/2000/svg"'))
            self.assertIsNone(mapart.mode_icon(vpk_path, tmp / "data", "something else"))
        self.assertIsNone(mapart.mode_icon(None, tmp / "other", "Premier"))


if __name__ == "__main__":
    unittest.main()
