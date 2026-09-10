"""Finding the features a config defines, and switching them off and on.

The switch edits a real config file, so the property that matters most is that
off-then-on returns the file to exactly what it was, byte for byte. Everything
here runs on fixtures in a temp directory.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import backup, cfgscan, plugins, webui  # noqa: E402

CRLF = "\r\n"

SCRIPTS = CRLF.join([
    '// --------------------------',
    '// Game Volume',
    '// --------------------------',
    'alias "!vol_off" "volume 0; alias !vol !vol_on"',
    'alias "!vol_on" "volume 1; alias !vol !vol_off"',
    'alias "!vol" "!vol_off"',
    '',
    'ECHO "---Script---Game Volume Script is Ready. Press (F9) / Command !vol"',
    '',
    '// --------------------------',
    '// Better Jump',
    '// --------------------------',
    'alias "+jumpduck" "+jump; +duck"',
    'alias "-jumpduck" "-jump; -duck"',
    '',
    'ECHO "---Script---Better Jump Script is Ready. Press (Space)"',
    '',
    '// --------------------------',
    '// Shooting Styles',
    '// --------------------------',
    'alias "st_1" "nosuchcommand; alias st st_2"',
    'alias "st_2" "alsomissing; alias st st_3"',
    'alias "st_3" "thirdmissing; alias st st_1"',
    'alias "st" "st_1"',
    '',
    'ECHO "---Script---Shooting Styles Script is Ready. Press (F10)"',
    '',
]) + CRLF


class PluginCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cs2cfg-plug-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        patcher = mock.patch.object(backup, "backups_root", lambda: self.tmp / "backups")
        patcher.start()
        self.addCleanup(patcher.stop)

        self.cfg_root = self.tmp / "cfg"
        self.collection = self.cfg_root / "mine"
        (self.collection / "tools").mkdir(parents=True)
        (self.collection / "autoexec.vcfg").write_bytes(
            ('exec mine/tools/scripts.vcfg' + CRLF).encode("utf-8"))
        self.scripts = self.collection / "tools" / "scripts.vcfg"
        self.scripts.write_bytes(SCRIPTS.encode("utf-8"))

        self.state = mock.Mock()
        self.rescan()

    def rescan(self):
        self.state.cfg_scan = cfgscan.scan(self.collection, cfg_root=self.cfg_root)
        return self.state.cfg_scan

    def found(self):
        return {p.name: p for p in plugins.find(self.state.cfg_scan)}


class TestFinding(PluginCase):
    def test_each_banner_block_becomes_a_feature(self):
        names = set(self.found())
        self.assertEqual({"Game Volume", "Better Jump", "Shooting Styles"}, names)

    def test_the_key_and_command_come_from_the_files_own_announcement(self):
        vol = self.found()["Game Volume"]
        self.assertEqual(vol.key, "F9")
        self.assertEqual(vol.command, "!vol")

    def test_two_states_read_as_a_toggle_and_more_as_a_cycle(self):
        found = self.found()
        self.assertEqual(found["Game Volume"].kind, "toggle")
        self.assertEqual(found["Shooting Styles"].kind, "cycle")

    def test_a_press_release_pair_reads_as_a_hold(self):
        self.assertEqual(self.found()["Better Jump"].kind, "hold")

    def test_the_convars_a_feature_changes_are_listed(self):
        self.assertIn("volume", self.found()["Game Volume"].touches)

    def test_a_feature_calling_names_that_do_not_exist_is_broken(self):
        styles = self.found()["Shooting Styles"]
        self.assertTrue(styles.broken)
        self.assertTrue(set(styles.missing) & {"nosuchcommand", "alsomissing"})

    def test_a_healthy_feature_is_not_flagged(self):
        self.assertFalse(self.found()["Game Volume"].broken)


class TestSwitching(PluginCase):
    def toggle(self, name, enable):
        target = self.found()[name]
        return webui._cfg_plugin_toggle(
            self.state, {"id": f"{target.file}:{target.line}", "enable": enable})

    def test_switching_off_comments_the_block_out(self):
        r = self.toggle("Game Volume", False)
        self.assertTrue(r["changed"])
        body = self.scripts.read_bytes().decode("utf-8")
        self.assertIn("//[off]// alias \"!vol_off\"", body)
        self.assertNotIn("\n alias \"!vol_off\"", body)

    def test_a_switched_off_feature_still_appears_and_says_so(self):
        self.toggle("Game Volume", False)
        self.rescan()
        vol = self.found()["Game Volume"]
        self.assertFalse(vol.enabled)
        self.assertEqual(vol.kind, "toggle", "it should still be understood")

    def test_off_then_on_restores_the_file_exactly(self):
        """The whole reason for commenting out rather than deleting."""
        before = self.scripts.read_bytes()
        self.toggle("Game Volume", False)
        self.rescan()
        self.toggle("Game Volume", True)
        self.assertEqual(self.scripts.read_bytes(), before)

    def test_switching_one_feature_leaves_its_neighbours_alone(self):
        self.toggle("Better Jump", False)
        self.rescan()
        found = self.found()
        self.assertFalse(found["Better Jump"].enabled)
        self.assertTrue(found["Game Volume"].enabled)
        self.assertTrue(found["Shooting Styles"].enabled)

    def test_comments_the_author_wrote_are_left_as_they_are(self):
        self.toggle("Game Volume", False)
        body = self.scripts.read_bytes().decode("utf-8")
        self.assertIn("// Game Volume" + CRLF, body)
        self.assertNotIn("//[off]// // Game Volume", body)

    def test_crlf_survives_the_edit(self):
        self.toggle("Game Volume", False)
        data = self.scripts.read_bytes()
        self.assertNotIn(b"\r\r\n", data)
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))

    def test_a_backup_is_taken(self):
        r = self.toggle("Game Volume", False)
        self.assertTrue(r["backup"])
        self.assertIsNotNone(backup.find_set(r["backup"]))

    def test_switching_to_the_state_it_is_already_in_writes_nothing(self):
        before = self.scripts.read_bytes()
        r = self.toggle("Game Volume", True)
        self.assertFalse(r["changed"])
        self.assertEqual(self.scripts.read_bytes(), before)

    def test_an_unknown_script_is_refused(self):
        r = webui._cfg_plugin_toggle(self.state, {"id": "nope/none.vcfg:1", "enable": False})
        self.assertFalse(r["ok"])
        self.assertIn("no longer where it was", r["error"])

    def test_a_switched_off_feature_is_not_reported_broken(self):
        """It cannot misbehave while it is commented out, and listing it among
        the problems would bury the ones that are actually running."""
        self.toggle("Shooting Styles", False)
        self.rescan()
        styles = self.found()["Shooting Styles"]
        self.assertFalse(styles.enabled)
        self.assertFalse(styles.broken)


if __name__ == "__main__":
    unittest.main()
