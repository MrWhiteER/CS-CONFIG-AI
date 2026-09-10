"""Tests for noticing what changed inside CS2.

All fixtures. The real Steam folder is never read, and nothing anywhere is
written -- the module's whole premise is that it only ever reads the game's
files, so a test that wrote one would be testing the wrong thing.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import gamewatch  # noqa: E402

CONVARS = '''"config"
{
\t"convars"
\t{
\t\t"cl_crosshairsize"\t\t"3"
\t\t"cl_crosshaircolor"\t\t"1"
\t\t"sensitivity"\t\t"1.15"
\t}
}
'''

KEYS = '''"config"
{
\t"bindings"
\t{
\t\t"q"\t\t"+qsw"
\t\t"f"\t\t"+lookatweapon"
\t}
\t"analogbindings"
\t{
\t\t"move"\t\t"1"
\t}
}
'''

VIDEO = '''"video.cfg"
{
\t"setting.defaultres"\t\t"1550"
\t"setting.fullscreen"\t\t"1"
\t"Autoconfig"\t\t"0"
\t"setting.knowndevice"\t\t"1"
}
'''


class FolderCase(unittest.TestCase):
    def folder(self, convars=CONVARS, keys=KEYS, video=VIDEO):
        d = Path(tempfile.mkdtemp(prefix="cs2cfg-gw-"))
        (d / "cs2_user_convars_0_slot0.vcfg").write_text(convars, encoding="utf-8")
        (d / "cs2_user_keys_0_slot0.vcfg").write_text(keys, encoding="utf-8")
        (d / "cs2_video.txt").write_text(video, encoding="utf-8")
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        return d


class TestSnapshot(FolderCase):
    def test_each_source_is_read_into_its_own_map(self):
        snap = gamewatch.take(self.folder())
        self.assertEqual(snap.values["In-game settings"]["cl_crosshairsize"], "3")
        self.assertEqual(snap.values["Key binds"]["q"], "+qsw")
        self.assertEqual(snap.values["Stick binds"]["move"], "1")
        self.assertEqual(snap.values["Picture quality"]["setting.defaultres"], "1550")

    def test_a_missing_file_is_recorded_rather_than_guessed(self):
        snap = gamewatch.take(self.folder())
        self.assertIn("Machine settings", snap.missing)
        self.assertNotIn("Machine settings", snap.values)

    def test_a_snapshot_survives_a_round_trip(self):
        snap = gamewatch.take(self.folder())
        again = gamewatch.Snapshot.from_dict(snap.as_dict())
        self.assertEqual(again.values, snap.values)
        self.assertEqual(again.missing, snap.missing)


class TestCompare(FolderCase):
    def test_no_changes_between_identical_snapshots(self):
        a = gamewatch.take(self.folder())
        b = gamewatch.take(self.folder())
        self.assertEqual(gamewatch.compare(a, b), [])

    def test_an_edited_value_is_reported_both_ways(self):
        before = gamewatch.take(self.folder())
        after = gamewatch.take(self.folder(
            convars=CONVARS.replace('"cl_crosshairsize"\t\t"3"',
                                    '"cl_crosshairsize"\t\t"2"')))
        changes = gamewatch.compare(before, after)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].kind, "changed")
        self.assertEqual((changes[0].was, changes[0].now), ("3", "2"))

    def test_a_new_and_a_removed_setting_are_distinguished(self):
        before = gamewatch.take(self.folder())
        after = gamewatch.take(self.folder(
            convars=CONVARS.replace('\t\t"sensitivity"\t\t"1.15"\n',
                                    '\t\t"cl_radar_scale"\t\t"0.4"\n')))
        kinds = {c.key: c.kind for c in gamewatch.compare(before, after)}
        self.assertEqual(kinds["cl_radar_scale"], "added")
        self.assertEqual(kinds["sensitivity"], "removed")

    def test_the_catalogue_supplies_a_readable_name(self):
        before = gamewatch.take(self.folder())
        after = gamewatch.take(self.folder(
            convars=CONVARS.replace('"cl_crosshairsize"\t\t"3"',
                                    '"cl_crosshairsize"\t\t"2"')))
        change = gamewatch.compare(before, after)[0]
        self.assertTrue(change.label, "cl_crosshairsize should have a label")
        self.assertIn(change.label, change.describe())

    def test_values_the_game_rewrites_itself_are_not_reported(self):
        """Autoconfig and knowndevice move on their own; calling those "you
        changed" would bury the settings that were actually deliberate."""
        before = gamewatch.take(self.folder())
        after = gamewatch.take(self.folder(
            video=VIDEO.replace('"Autoconfig"\t\t"0"', '"Autoconfig"\t\t"1"')
                       .replace('"setting.knowndevice"\t\t"1"',
                                '"setting.knowndevice"\t\t"0"')))
        self.assertEqual(gamewatch.compare(before, after), [])

    def test_machine_settings_are_left_out_unless_asked_for(self):
        machine = '"config"\n{\n\t"convars"\n\t{\n\t\t"r_something"\t\t"%s"\n\t}\n}\n'
        first, second = self.folder(), self.folder()
        (first / "cs2_machine_convars.vcfg").write_text(machine % "1", encoding="utf-8")
        (second / "cs2_machine_convars.vcfg").write_text(machine % "2", encoding="utf-8")
        before, after = gamewatch.take(first), gamewatch.take(second)
        self.assertEqual(gamewatch.compare(before, after), [])
        self.assertEqual(len(gamewatch.compare(before, after, include_machine=True)), 1)

    def test_a_source_missing_on_one_side_reports_nothing_for_it(self):
        """Better silence than announcing that all 92 settings changed because
        one file could not be read."""
        before = gamewatch.take(self.folder())
        bare = self.folder()
        (bare / "cs2_user_convars_0_slot0.vcfg").unlink()
        after = gamewatch.take(bare)
        sources = {c.source for c in gamewatch.compare(before, after)}
        self.assertNotIn("In-game settings", sources)

    def test_the_describe_text_stays_ascii(self):
        """It reaches the console binary, and a cp1252 terminal cannot encode
        an arrow."""
        before = gamewatch.take(self.folder())
        after = gamewatch.take(self.folder(
            convars=CONVARS.replace('"sensitivity"\t\t"1.15"',
                                    '"sensitivity"\t\t"0.9"')))
        for change in gamewatch.compare(before, after):
            change.describe().encode("cp1252")


class TestPayload(FolderCase):
    def test_the_payload_groups_by_source_for_the_page(self):
        before = gamewatch.take(self.folder())
        after = gamewatch.take(self.folder(
            convars=CONVARS.replace('"cl_crosshairsize"\t\t"3"',
                                    '"cl_crosshairsize"\t\t"2"'),
            keys=KEYS.replace('"f"\t\t"+lookatweapon"', '"f"\t\t"+spray_menu"')))
        payload = gamewatch.as_dict(gamewatch.compare(before, after), before, after)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(set(payload["sources"]), {"In-game settings", "Key binds"})
        self.assertIn("text", payload["sources"]["Key binds"][0])


if __name__ == "__main__":
    unittest.main()
