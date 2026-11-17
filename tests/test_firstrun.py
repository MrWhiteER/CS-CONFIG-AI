"""The first-run setup wizard: what it finds, and what its answers change."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import firstrun, profiles  # noqa: E402


class Needed(unittest.TestCase):
    def test_a_fresh_install_needs_it_and_a_finished_one_does_not(self):
        self.assertTrue(firstrun.needed({}))
        self.assertFalse(firstrun.needed({"ui": {"firstrun_done": True}}))

    def test_its_flags_belong_to_this_pc(self):
        """Permission to write into a cfg folder is given per machine. Kept per
        account, a second Steam account would inherit it unasked -- and kept
        per account, the wizard would show again for every account."""
        for key in firstrun.MACHINE_KEYS:
            self.assertTrue(profiles.is_machine(key), key)


class CfgAccess(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="cs2cfg-firstrun-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_no_game(self):
        self.assertFalse(firstrun.cfg_access(None)["writable"])

    def test_folder_missing(self):
        out = firstrun.cfg_access(self.root / "nope")
        self.assertFalse(out["exists"])

    def test_writable_and_leaves_nothing_behind(self):
        out = firstrun.cfg_access(self.root)
        self.assertTrue(out["writable"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_refused_write_is_reported(self):
        with mock.patch("tempfile.mkstemp", side_effect=PermissionError("denied")):
            out = firstrun.cfg_access(self.root)
        self.assertTrue(out["exists"])
        self.assertFalse(out["writable"])
        self.assertIn("denied", out["reason"])


class Presets(unittest.TestCase):
    def test_three_presets_with_the_visual_label(self):
        out = firstrun.presets(None, None)
        self.assertEqual([p["id"] for p in out], ["competitive", "balanced", "quality"])
        self.assertEqual(out[2]["label"], "Visual")

    def test_each_carries_its_own_estimate(self):
        fps = {"competitive": 410, "balanced": 330, "quality": 250}

        def fake(machine, kb, intent):
            return mock.Mock(estimated_fps=fps[intent], bottleneck="GPU", tier="high")

        with mock.patch("cs2cfg.profile.build_profile", side_effect=fake):
            out = firstrun.presets(object(), object())
        self.assertEqual([p["fps"] for p in out], [410, 330, 250])

    def test_an_estimate_that_fails_leaves_the_preset_choosable(self):
        with mock.patch("cs2cfg.profile.build_profile", side_effect=RuntimeError):
            out = firstrun.presets(object(), object())
        self.assertEqual([p["fps"] for p in out], [None, None, None])


class Apps(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="cs2cfg-apps-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_discord_is_found_through_its_updater(self):
        (self.root / "Discord").mkdir()
        (self.root / "Discord" / "Update.exe").write_bytes(b"")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.root)}):
            found = firstrun._discord()
        self.assertEqual(found["args"], "--processStart Discord.exe")

    def test_ticking_adds_and_unticking_keeps_but_switches_off(self):
        exe = self.root / "Update.exe"
        exe.write_bytes(b"")
        available = [{"id": "discord", "name": "Discord", "exe": str(exe),
                      "args": "--processStart Discord.exe"},
                     {"id": "crosshairx", "name": "Crosshair X", "exe": str(exe),
                      "args": "", "integration": "crosshairx"}]
        ui = {"companions": [{"id": "crosshairx", "name": "Crosshair X",
                              "exe": str(exe), "with_game": True}]}
        out = firstrun.companions_change(ui, available, ["discord"])
        by_id = {c["id"]: c for c in out}
        self.assertTrue(by_id["discord"]["with_game"])
        self.assertEqual(by_id["discord"]["args"], "--processStart Discord.exe")
        self.assertFalse(by_id["crosshairx"]["with_game"])


class Finishing(unittest.TestCase):
    def test_answers_become_preferences(self):
        changes = firstrun.answers_to_changes(
            {"cfg_write": True, "sound": {"output": "{out}", "input": "{mic}"},
             "preset": "quality", "theme": "frost", "sync": True, "apps": []},
            {}, [])
        self.assertTrue(changes["cfg_write_ok"])
        self.assertTrue(changes["write_cfg"])
        self.assertEqual(changes["audio_output"], "{out}")
        self.assertEqual(changes["audio_input"], "{mic}")
        self.assertEqual(changes["intent"], "quality")
        self.assertEqual(changes["theme"], "frost")
        self.assertTrue(changes["sync_auto"])
        self.assertTrue(changes["firstrun_done"])

    def test_skipped_steps_change_nothing_but_still_finish(self):
        changes = firstrun.answers_to_changes({}, {"intent": "balanced"}, [])
        self.assertEqual(changes, {"firstrun_done": True})

    def test_unknown_values_are_ignored(self):
        changes = firstrun.answers_to_changes(
            {"preset": "ultra", "theme": "rainbow"}, {}, [])
        self.assertNotIn("intent", changes)
        self.assertNotIn("theme", changes)

    def test_every_theme_the_wizard_offers_exists_on_the_page(self):
        from cs2cfg import paths

        page = (paths.bundle_root() / "web" / "index.html").read_text(
            encoding="utf-8", errors="replace")
        for theme in firstrun.THEMES:
            self.assertIn(f'["{theme}",', page.replace(" ", ""), theme)


if __name__ == "__main__":
    unittest.main()
