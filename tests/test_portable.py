"""Carrying a setup to another machine, and refusing to be used as a way in."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from cs2cfg import portable


class Writing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = self.root / "cfg"
        (self.cfg / "mainsettings").mkdir(parents=True)
        (self.cfg / "autoexec.vcfg").write_text("exec tools/alias\n", encoding="utf-8")
        (self.cfg / "mainsettings" / "key_binds.vcfg").write_text(
            'bind "f" "+lookatweapon"\n', encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_it_carries_the_folder_and_the_choices(self):
        out = portable.write(self.root / "mine", {"intent": "competitive",
                                                  "target_fps": "300"}, self.cfg)
        self.assertEqual(out["files"], 2)
        back = portable.read(Path(out["path"]))
        self.assertEqual(back["prefs"]["intent"], "competitive")
        self.assertIn("mainsettings/key_binds.vcfg", back["files"])

    def test_it_gets_the_suffix_whether_or_not_you_typed_it(self):
        out = portable.write(self.root / "named", {}, self.cfg)
        self.assertTrue(out["path"].endswith(portable.SUFFIX))

    def test_nothing_identifying_the_machine_goes_in(self):
        """A setup is meant to be handed to somebody else. An account id or a
        path off this disk in it would be a surprise to whoever sent it."""
        ui = {"intent": "balanced", "account": "244173392",
              "pinned_account": "244173392", "cfg_folder": r"C:\Users\me\cfg",
              "rail_width": 188}
        out = portable.write(self.root / "clean", ui, self.cfg)
        text = Path(out["path"]).read_bytes().decode("utf-8", "replace")
        for leak in portable.WITHHELD:
            self.assertNotIn(leak, portable.read(Path(out["path"]))["prefs"])
        self.assertNotIn("244173392", text)
        self.assertNotIn("Users", text)

    def test_a_folder_that_is_not_there_still_writes_the_choices(self):
        out = portable.write(self.root / "bare", {"intent": "quality"},
                             self.root / "nope")
        self.assertEqual(out["files"], 0)
        self.assertEqual(portable.read(Path(out["path"]))["prefs"]["intent"],
                         "quality")


class Reading(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_something_that_is_not_a_setup_says_so(self):
        plain = self.root / "notes.txt"
        plain.write_text("hello", encoding="utf-8")
        with self.assertRaises(portable.SetupError):
            portable.read(plain)

    def test_a_zip_without_our_manifest_says_so(self):
        z = self.root / "other.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("readme.txt", "not ours")
        with self.assertRaises(portable.SetupError) as caught:
            portable.read(z)
        self.assertIn("not a saved setup", str(caught.exception))

    def test_a_setup_from_the_future_is_refused_rather_than_half_read(self):
        z = self.root / ("newer" + portable.SUFFIX)
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr(portable.MANIFEST, json.dumps(
                {"format": portable.FORMAT + 5, "written_by": "9.9.9", "prefs": {}}))
        with self.assertRaises(portable.SetupError) as caught:
            portable.read(z)
        self.assertIn("update first", str(caught.exception))


class NotAWayIn(unittest.TestCase):
    """A setup file arrives from somewhere else. It is data, not a licence to
    write wherever its entry names point."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _hostile(self, *names):
        z = self.root / ("bad" + portable.SUFFIX)
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr(portable.MANIFEST, json.dumps({"format": 1, "prefs": {}}))
            for n in names:
                zf.writestr(n, "pwned")
        return z

    def test_it_will_not_climb_out_of_the_folder(self):
        z = self._hostile(portable.CFG_PREFIX + "../../escaped.vcfg",
                          portable.CFG_PREFIX + "../sibling.vcfg")
        into = self.root / "dest"
        out = portable.unpack(z, into)
        self.assertEqual(out["written"], [])
        self.assertFalse((self.root / "escaped.vcfg").exists())
        self.assertFalse((self.root / "sibling.vcfg").exists())

    def test_an_absolute_path_inside_is_ignored(self):
        z = self._hostile(portable.CFG_PREFIX + "/etc/passwd",
                          portable.CFG_PREFIX + "C:/Windows/system.ini")
        out = portable.unpack(z, self.root / "dest")
        self.assertEqual(out["written"], [])

    def test_ordinary_names_still_come_through(self):
        z = self._hostile(portable.CFG_PREFIX + "tools/alias.vcfg",
                          portable.CFG_PREFIX + "autoexec.vcfg")
        into = self.root / "dest"
        out = portable.unpack(z, into)
        self.assertEqual(sorted(out["written"]), ["autoexec.vcfg", "tools/alias.vcfg"])
        self.assertTrue((into / "tools" / "alias.vcfg").is_file())

    def test_reading_one_lists_only_the_names_it_would_unpack(self):
        z = self._hostile(portable.CFG_PREFIX + "../escape.vcfg",
                          portable.CFG_PREFIX + "fine.vcfg")
        self.assertEqual(portable.read(z)["files"], ["fine.vcfg"])


if __name__ == "__main__":
    unittest.main()
