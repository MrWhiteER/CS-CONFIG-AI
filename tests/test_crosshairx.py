"""The Crosshair X integration: finding it, and what it does to the config."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg import crosshairx, hardware, profile
from cs2cfg.kb import KnowledgeBase


def _library(root: Path, installdir: str = "CrosshairX", with_exe: bool = True) -> Path:
    apps = root / "steamapps"
    apps.mkdir(parents=True, exist_ok=True)
    (apps / f"appmanifest_{crosshairx.APP_ID}.acf").write_text(
        '"AppState"\n{\n'
        f'\t"appid"\t\t"{crosshairx.APP_ID}"\n'
        '\t"name"\t\t"Crosshair X"\n'
        f'\t"installdir"\t\t"{installdir}"\n'
        "}\n", encoding="utf-8")
    home = apps / "common" / installdir
    home.mkdir(parents=True, exist_ok=True)
    if with_exe:
        (home / crosshairx.EXE).write_text("", encoding="utf-8")
    return root


class Finding(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_it_is_found_through_the_library_it_is_in(self):
        lib = _library(self.root / "libB")
        found = crosshairx.find([self.root / "libA", lib])
        self.assertTrue(found["installed"])
        self.assertEqual(found["app_id"], crosshairx.APP_ID)
        self.assertTrue(found["exe"].endswith(crosshairx.EXE))

    def test_it_follows_the_manifest_rather_than_assuming_the_folder(self):
        """installdir is whatever Steam wrote. Hardcoding "CrosshairX" would
        work here and fail on somebody whose install is named otherwise."""
        lib = _library(self.root / "lib", installdir="Crosshair X Beta")
        found = crosshairx.find([lib])
        self.assertIn("Crosshair X Beta", found["folder"])

    def test_no_manifest_anywhere_means_not_installed(self):
        (self.root / "empty" / "steamapps").mkdir(parents=True)
        self.assertIsNone(crosshairx.find([self.root / "empty"]))

    def test_a_manifest_without_the_executable_still_reports_the_folder(self):
        """Steam can have the app registered while the files are gone. Saying
        "installed, but there is nothing to run" beats claiming either."""
        lib = _library(self.root / "lib", with_exe=False)
        found = crosshairx.find([lib])
        self.assertTrue(found["installed"])
        self.assertEqual(found["exe"], "")

    def test_a_corrupt_manifest_does_not_raise(self):
        apps = self.root / "bad" / "steamapps"
        apps.mkdir(parents=True)
        (apps / f"appmanifest_{crosshairx.APP_ID}.acf").write_text(
            "this is not a vdf {{{", encoding="utf-8")
        self.assertIsNone(crosshairx.find([self.root / "bad"]))

    def test_summary_says_not_installed_without_inventing_a_path(self):
        seen = crosshairx.summary([self.root / "nothing"])
        self.assertFalse(seen["installed"])
        self.assertFalse(seen["running"])
        self.assertNotIn("folder", seen)


class WhatItDoesToTheConfig(unittest.TestCase):
    """The only thing this writes is the game's own crosshair convar."""

    @classmethod
    def setUpClass(cls):
        cls.machine = hardware.detect()
        cls.kb = KnowledgeBase()

    def _convars(self, hide):
        p = profile.build_profile(self.machine, self.kb, intent="balanced",
                                  hide_crosshair=hide)
        return dict((k, v) for k, v, _ in p.convars)

    def test_off_by_default(self):
        """Turning somebody's crosshair off uninvited is the one way this
        feature could ruin a session."""
        self.assertNotIn(crosshairx.CONVAR, self._convars(False))

    def test_on_when_asked(self):
        self.assertEqual(self._convars(True)[crosshairx.CONVAR], crosshairx.OFF)

    def test_it_says_why(self):
        p = profile.build_profile(self.machine, self.kb, hide_crosshair=True)
        reason = next(r for k, _, r in p.convars if k == crosshairx.CONVAR)
        self.assertTrue(reason.strip(), "a convar with no reason is a mystery later")

    def test_nothing_else_moves(self):
        before, after = self._convars(False), self._convars(True)
        extra = set(after) - set(before)
        self.assertEqual(extra, {crosshairx.CONVAR})
        for key in before:
            self.assertEqual(before[key], after[key], f"{key} changed as a side effect")


class Starting(unittest.TestCase):
    def test_it_goes_through_steam_rather_than_the_executable(self):
        """Launching a Steam app behind Steam's back is how people end up with
        one that thinks it is unlicensed."""
        with mock.patch.object(crosshairx, "running", return_value=False), \
             mock.patch.object(crosshairx.subprocess, "Popen") as run:
            crosshairx.start()
        args = run.call_args[0][0]
        self.assertTrue(any(f"steam://rungameid/{crosshairx.APP_ID}" in str(a) for a in args),
                        f"expected a steam:// launch, got {args}")

    def test_it_does_not_start_a_second_copy(self):
        with mock.patch.object(crosshairx, "running", return_value=True), \
             mock.patch.object(crosshairx.subprocess, "Popen") as run:
            out = crosshairx.start()
        run.assert_not_called()
        self.assertTrue(out["ok"])
        self.assertTrue(out["already"])


if __name__ == "__main__":
    unittest.main()
