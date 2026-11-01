"""The Keyboard tab's layout-profile endpoints: pinning keys on a match
profile like warmup.vcfg so the profile's own binds can't take them over.

Runs the real web handlers (not cfgscan directly), because the handlers are
what actually resolves a relative path to a file on disk -- the one place a
generated file's location could be wrong without any cfgscan-level test
noticing.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import backup, cfgscan, webui  # noqa: E402
from sandbox import redirect_backups, redirect_layouts  # noqa: E402

FILES = {
    "mrwhiteer/autoexec.vcfg": (
        'exec "mrwhiteer/tools/alias.vcfg"\n'
        'exec "mrwhiteer/mainsettings/key_binds.vcfg"\n'
    ),
    "mrwhiteer/tools/alias.vcfg": (
        'alias "!warmup" "exec mrwhiteer/lan/warmup.vcfg"\n'
    ),
    "mrwhiteer/mainsettings/key_binds.vcfg": (
        'bind "mouse3" "say custom text"\n'
        'bind "mouse4" "player_ping"\n'
    ),
    "mrwhiteer/lan/warmup.vcfg": (
        'bind "mouse3" "noclip"\n'
        'bind "mouse4" "bot_place"\n'
    ),
}


class LayoutsWebCase(unittest.TestCase):
    def setUp(self):
        redirect_backups(self)
        redirect_layouts(self)
        self.sandbox = Path(tempfile.mkdtemp(prefix="cs2cfg-layouts-web-"))
        self.addCleanup(shutil.rmtree, self.sandbox, ignore_errors=True)

        self.cfg_root = self.sandbox / "cfg"
        for relative, text in FILES.items():
            path = self.cfg_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.collection = self.cfg_root / "mrwhiteer"

        self.state = mock.Mock()
        self.state.cfg_scan = cfgscan.scan(self.collection, cfg_root=self.cfg_root)

    def status(self):
        return webui._cfg_layouts_status(self.state, {})

    def pin(self, file, keys):
        return webui._cfg_layouts_pin(self.state, {"file": file, "pinned": keys})

    def profiles(self):
        return webui._cfg_layouts_profiles(self.state, {})

    def create(self, name):
        return webui._cfg_layouts_create(self.state, {"name": name})

    def copy(self, file, name):
        return webui._cfg_layouts_copy(self.state, {"file": file, "name": name})

    def delete(self, file):
        return webui._cfg_layouts_delete(self.state, {"file": file})

    def remove(self, file):
        return webui._cfg_layouts_remove(self.state, {"file": file})

    def switch(self, file):
        return webui._cfg_layouts_apply(self.state, {"file": file})

    def switch_file(self):
        return self.cfg_root / "mrwhiteer/lan/warmup.layout.vcfg"

    def alias_file(self):
        return self.cfg_root / "mrwhiteer/tools/alias.vcfg"


class TestStatus(LayoutsWebCase):
    def test_reports_the_detected_profile_unpinned(self):
        found = self.status()
        self.assertTrue(found["ok"])
        self.assertEqual(len(found["profiles"]), 1)
        profile = found["profiles"][0]
        self.assertEqual(profile["file"], "mrwhiteer/lan/warmup.vcfg")
        self.assertFalse(profile["wired"])
        self.assertFalse(any(o["pinned"] for o in profile["overrides"]))


class TestPinning(LayoutsWebCase):
    def test_pinning_a_key_writes_the_switch_file_on_disk(self):
        result = self.pin("mrwhiteer/lan/warmup.vcfg", ["mouse4"])
        self.assertTrue(result["ok"], result)
        self.assertTrue(self.switch_file().is_file(),
                        "the generated switch file should land next to warmup.vcfg")
        text = self.switch_file().read_text(encoding="utf-8")
        self.assertIn('exec "mrwhiteer/lan/warmup.vcfg"', text)
        self.assertIn('bind "mouse4" "player_ping"', text)

    def test_pinning_retargets_the_warmup_alias_to_the_switch_file(self):
        self.pin("mrwhiteer/lan/warmup.vcfg", ["mouse4"])
        text = self.alias_file().read_text(encoding="utf-8")
        self.assertIn(
            'alias "!warmup" "exec mrwhiteer/lan/warmup.layout.vcfg"', text)

    def test_status_reflects_the_pin_after_saving(self):
        self.pin("mrwhiteer/lan/warmup.vcfg", ["mouse4"])
        profile = self.status()["profiles"][0]
        self.assertTrue(profile["wired"])
        pinned = {o["key"]: o["pinned"] for o in profile["overrides"]}
        self.assertTrue(pinned["mouse4"])
        self.assertFalse(pinned["mouse3"])

    def test_clearing_the_pin_points_the_alias_back_at_warmup_directly(self):
        self.pin("mrwhiteer/lan/warmup.vcfg", ["mouse4"])
        self.pin("mrwhiteer/lan/warmup.vcfg", [])
        text = self.alias_file().read_text(encoding="utf-8")
        self.assertIn('alias "!warmup" "exec mrwhiteer/lan/warmup.vcfg"', text)
        self.assertNotIn("warmup.layout.vcfg", text)

    def test_an_unknown_key_is_silently_dropped(self):
        result = self.pin("mrwhiteer/lan/warmup.vcfg", ["mouse4", "f13"])
        self.assertTrue(result["ok"], result)
        profile = result["profiles"][0]
        pinned = {o["key"] for o in profile["overrides"] if o["pinned"]}
        self.assertEqual(pinned, {"mouse4"})

    def test_an_unknown_profile_file_is_refused(self):
        result = self.pin("mrwhiteer/does/not/exist.vcfg", ["mouse4"])
        self.assertFalse(result["ok"])
        self.assertIn("not a detected layout profile", result["error"])


class TestProfileSelector(LayoutsWebCase):
    """The broader listing behind the Keyboard tab's create/copy/delete UI."""

    def test_lists_the_hand_written_profile_as_not_app_created(self):
        result = self.profiles()
        self.assertTrue(result["ok"], result)
        found = {p["file"]: p for p in result["profiles"]}
        warmup = found["mrwhiteer/lan/warmup.vcfg"]
        self.assertFalse(warmup["app_created"])
        self.assertEqual(warmup["trigger_alias"], "!warmup")
        self.assertEqual(warmup["override_count"], 2)

    def test_not_active_until_the_standard_layout_matches_it(self):
        found = {p["file"]: p for p in self.profiles()["profiles"]}
        self.assertFalse(found["mrwhiteer/lan/warmup.vcfg"]["active"])

    def test_a_blank_profile_with_nothing_to_compare_is_never_active(self):
        self.create("Competitive")
        found = {p["file"]: p for p in self.profiles()["profiles"]}
        self.assertFalse(found["mrwhiteer/lan/competitive.vcfg"]["active"])


class TestSwitchingProfiles(LayoutsWebCase):
    """Switching to a profile right now: writing its overrides onto the
    standard layout in place, the way the new Keyboard-tab switcher bar
    does when a profile tab (that isn't already active) is clicked."""

    def test_switching_writes_the_overrides_onto_the_standard_file(self):
        result = self.switch("mrwhiteer/lan/warmup.vcfg")
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["changed"])
        self.assertEqual(set(result["applied"]), {"Mouse 3", "Mouse 4"})

        text = (self.cfg_root / "mrwhiteer/mainsettings/key_binds.vcfg").read_text(
            encoding="utf-8")
        self.assertIn('bind "mouse3" "noclip"', text)
        self.assertIn('bind "mouse4" "bot_place"', text)

    def test_the_profile_reads_back_as_active_afterwards(self):
        self.switch("mrwhiteer/lan/warmup.vcfg")
        found = {p["file"]: p for p in self.profiles()["profiles"]}
        self.assertTrue(found["mrwhiteer/lan/warmup.vcfg"]["active"])

    def test_a_pinned_key_is_left_on_its_standard_binding(self):
        self.pin("mrwhiteer/lan/warmup.vcfg", ["mouse4"])
        result = self.switch("mrwhiteer/lan/warmup.vcfg")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["applied"], ["Mouse 3"])
        self.assertIn("Mouse 4", result["skipped"])

        text = (self.cfg_root / "mrwhiteer/mainsettings/key_binds.vcfg").read_text(
            encoding="utf-8")
        self.assertIn('bind "mouse4" "player_ping"', text, "pinned, so unchanged")

    def test_switching_to_an_already_active_profile_changes_nothing(self):
        self.switch("mrwhiteer/lan/warmup.vcfg")
        before = (self.cfg_root / "mrwhiteer/mainsettings/key_binds.vcfg").read_bytes()

        result = self.switch("mrwhiteer/lan/warmup.vcfg")
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["changed"])
        after = (self.cfg_root / "mrwhiteer/mainsettings/key_binds.vcfg").read_bytes()
        self.assertEqual(before, after)

    def test_an_unknown_profile_file_is_refused(self):
        result = self.switch("mrwhiteer/does/not/exist.vcfg")
        self.assertFalse(result["ok"])
        self.assertIn("not a detected layout profile", result["error"])

    def test_a_backup_is_taken(self):
        result = self.switch("mrwhiteer/lan/warmup.vcfg")
        self.assertTrue(result["backup"])
        self.assertIsNotNone(backup.find_set(result["backup"]))

    def test_switching_to_a_blank_profile_is_reported_as_empty_not_active(self):
        self.create("Competitive")
        result = self.switch("mrwhiteer/lan/competitive.vcfg")
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["changed"])
        self.assertTrue(result["empty"], "nothing to compare, so not the same as already active")


class TestCreate(LayoutsWebCase):
    def test_creates_a_blank_profile_and_marks_it_app_created(self):
        result = self.create("Competitive")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["file"], "mrwhiteer/lan/competitive.vcfg")

        path = self.cfg_root / "mrwhiteer/lan/competitive.vcfg"
        self.assertTrue(path.is_file())
        self.assertIn("Competitive", path.read_text(encoding="utf-8"))

        found = {p["file"]: p for p in result["profiles"]}
        self.assertTrue(found["mrwhiteer/lan/competitive.vcfg"]["app_created"])

    def test_a_blank_name_is_refused(self):
        result = self.create("   ")
        self.assertFalse(result["ok"])


class TestCopy(LayoutsWebCase):
    def test_copies_the_sources_content_into_a_new_file(self):
        result = self.copy("mrwhiteer/lan/warmup.vcfg", "Competitive")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["file"], "mrwhiteer/lan/competitive.vcfg")

        # Compared against the source file's own bytes, not the FILES constant:
        # write_text() in setUp already translated "\n" to this platform's line
        # ending, so the source on disk and FILES no longer agree byte for
        # byte -- what the copy must reproduce is the source, verbatim.
        copied = (self.cfg_root / "mrwhiteer/lan/competitive.vcfg").read_bytes()
        source = (self.cfg_root / "mrwhiteer/lan/warmup.vcfg").read_bytes()
        self.assertEqual(copied, source)

        found = {p["file"]: p for p in result["profiles"]}
        self.assertTrue(found["mrwhiteer/lan/competitive.vcfg"]["app_created"])

    def test_copying_a_file_outside_the_scan_is_refused(self):
        result = self.copy("mrwhiteer/does/not/exist.vcfg", "Competitive")
        self.assertFalse(result["ok"])

    def test_a_blank_name_is_refused(self):
        result = self.copy("mrwhiteer/lan/warmup.vcfg", "  ")
        self.assertFalse(result["ok"])


class TestDelete(LayoutsWebCase):
    def test_a_hand_written_profile_cannot_be_deleted(self):
        result = self.delete("mrwhiteer/lan/warmup.vcfg")
        self.assertFalse(result["ok"])
        self.assertIn("created in the app", result["error"])
        self.assertTrue((self.cfg_root / "mrwhiteer/lan/warmup.vcfg").is_file())

    def test_deleting_an_app_created_profile_removes_its_file(self):
        self.create("Competitive")
        result = self.delete("mrwhiteer/lan/competitive.vcfg")
        self.assertTrue(result["ok"], result)
        self.assertFalse((self.cfg_root / "mrwhiteer/lan/competitive.vcfg").exists())
        self.assertNotIn("mrwhiteer/lan/competitive.vcfg",
                         {p["file"] for p in result["profiles"]})

    def test_deleting_unwires_its_switch_key(self):
        self.copy("mrwhiteer/lan/warmup.vcfg", "Competitive")
        alias_path = self.alias_file()
        alias_path.write_text(
            alias_path.read_text(encoding="utf-8") +
            'alias "!comp" "exec mrwhiteer/lan/competitive.vcfg"\n',
            encoding="utf-8")
        self.state.cfg_scan = cfgscan.scan(self.collection, cfg_root=self.cfg_root)

        result = self.delete("mrwhiteer/lan/competitive.vcfg")
        self.assertTrue(result["ok"], result)
        text = alias_path.read_text(encoding="utf-8")
        self.assertIn('// alias "!comp" "exec mrwhiteer/lan/competitive.vcfg"', text)


class TestRemove(LayoutsWebCase):
    def test_removing_a_hand_written_profile_unwires_it_without_touching_the_file(self):
        result = self.remove("mrwhiteer/lan/warmup.vcfg")
        self.assertTrue(result["ok"], result)

        text = (self.cfg_root / "mrwhiteer/lan/warmup.vcfg").read_text(encoding="utf-8")
        self.assertEqual(text, FILES["mrwhiteer/lan/warmup.vcfg"])

        alias_text = self.alias_file().read_text(encoding="utf-8")
        self.assertIn('// alias "!warmup" "exec mrwhiteer/lan/warmup.vcfg"', alias_text)
        self.assertNotIn("mrwhiteer/lan/warmup.vcfg",
                         {p["file"] for p in result["profiles"]})

    def test_removed_profile_stays_off_the_pin_list_too(self):
        self.remove("mrwhiteer/lan/warmup.vcfg")
        status = self.status()
        self.assertNotIn("mrwhiteer/lan/warmup.vcfg",
                         {p["file"] for p in status["profiles"]})
