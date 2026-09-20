"""Windows' own per-application graphics settings.

Nothing here touches the real registry: every test either works on the plain
string handling or stubs winreg. The one thing worth guarding hardest is that
another application's settings in the same value survive, because that value
is shared and losing somebody else's entry would be silent.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import wingraphics as wg  # noqa: E402


class Parsing(unittest.TestCase):
    def test_it_reads_what_windows_writes(self):
        got = wg.parse("GpuPreference=2;SwapEffectUpgradeEnable=1;")
        self.assertEqual(got, {"GpuPreference": "2", "SwapEffectUpgradeEnable": "1"})

    def test_a_missing_trailing_semicolon_is_fine(self):
        self.assertEqual(wg.parse("GpuPreference=2"), {"GpuPreference": "2"})

    def test_nothing_at_all_is_not_an_error(self):
        for empty in ("", ";", "   ", "rubbish"):
            self.assertEqual(wg.parse(empty), {})

    def test_it_round_trips(self):
        text = "GpuPreference=2;SwapEffectUpgradeEnable=1;"
        self.assertEqual(wg.render(wg.parse(text)), text)


class NotTakingOverSomebodyElsesValue(unittest.TestCase):
    """Windows files several applications' settings in one key, and other
    tools write their own names into the same string. AppStatus turns up on
    this machine already."""

    def test_an_unrelated_setting_is_carried_through(self):
        got = wg.wanted({"AppStatus": "4"})
        self.assertEqual(got["AppStatus"], "4")
        self.assertEqual(got["GpuPreference"], wg.HIGH_PERFORMANCE)
        self.assertEqual(got["SwapEffectUpgradeEnable"], wg.WINDOWED_ON)

    def test_an_existing_choice_is_replaced_not_appended(self):
        got = wg.wanted({"GpuPreference": "1"})
        self.assertEqual(got["GpuPreference"], wg.HIGH_PERFORMANCE)
        self.assertEqual(wg.render(got).count("GpuPreference"), 1)

    def test_wanted_does_not_mutate_what_it_was_given(self):
        before = {"AppStatus": "4"}
        wg.wanted(before)
        self.assertEqual(before, {"AppStatus": "4"})


class FindingTheExecutable(unittest.TestCase):
    """Windows keys these on the executable, not the Steam shortcut."""

    def test_no_install_means_no_path(self):
        self.assertIsNone(wg.exe_path(None))

    def test_a_missing_executable_is_not_invented(self):
        self.assertIsNone(wg.exe_path(Path("/nonexistent-install")))

    def test_it_points_at_the_game_binary(self):
        self.assertEqual(wg.EXE_REL[-1], "cs2.exe")


class Writing(unittest.TestCase):
    def setUp(self):
        self.install = Path("/fake/install")
        self.exe = Path("/fake/install/game/bin/win64/cs2.exe")

    def test_nothing_is_written_when_it_already_agrees(self):
        """A launch that rewrites a value to the value it already holds is a
        launch that touched the registry for nothing."""
        settled = {"GpuPreference": wg.HIGH_PERFORMANCE,
                   "SwapEffectUpgradeEnable": wg.WINDOWED_ON}
        with mock.patch.object(wg, "exe_path", return_value=self.exe), \
             mock.patch.object(wg, "read", return_value=settled), \
             mock.patch.object(wg.sys, "platform", "win32"), \
             mock.patch.dict(sys.modules, {"winreg": mock.MagicMock()}):
            out = wg.apply(self.install)
            sys.modules["winreg"].SetValueEx.assert_not_called()
        self.assertTrue(out["ok"])
        self.assertFalse(out["changed"])

    def test_describe_never_writes(self):
        fake = mock.MagicMock()
        with mock.patch.object(wg, "exe_path", return_value=self.exe), \
             mock.patch.object(wg, "read", return_value={}), \
             mock.patch.object(wg.sys, "platform", "win32"), \
             mock.patch.dict(sys.modules, {"winreg": fake}):
            wg.describe(self.install)
        fake.SetValueEx.assert_not_called()
        fake.DeleteValue.assert_not_called()

    def test_off_windows_it_refuses_rather_than_raising(self):
        with mock.patch.object(wg.sys, "platform", "linux"):
            self.assertFalse(wg.apply(self.install)["ok"])
            self.assertFalse(wg.describe(self.install)["supported"])

    def test_a_missing_executable_is_refused(self):
        with mock.patch.object(wg, "exe_path", return_value=None), \
             mock.patch.object(wg.sys, "platform", "win32"):
            self.assertFalse(wg.apply(self.install)["ok"])

    def test_clearing_keeps_another_applications_entry(self):
        fake = mock.MagicMock()
        with mock.patch.object(wg, "exe_path", return_value=self.exe), \
             mock.patch.object(wg, "read",
                               return_value={"GpuPreference": "2", "AppStatus": "4"}), \
             mock.patch.object(wg.sys, "platform", "win32"), \
             mock.patch.dict(sys.modules, {"winreg": fake}):
            out = wg.clear(self.install)
        self.assertTrue(out["ok"])
        fake.DeleteValue.assert_not_called()
        written = fake.SetValueEx.call_args[0][-1]
        self.assertIn("AppStatus=4", written)
        self.assertNotIn("GpuPreference", written)

    def test_clearing_removes_the_value_when_it_held_only_ours(self):
        fake = mock.MagicMock()
        with mock.patch.object(wg, "exe_path", return_value=self.exe), \
             mock.patch.object(wg, "read",
                               return_value={"GpuPreference": "2",
                                             "SwapEffectUpgradeEnable": "1"}), \
             mock.patch.object(wg.sys, "platform", "win32"), \
             mock.patch.dict(sys.modules, {"winreg": fake}):
            wg.clear(self.install)
        fake.DeleteValue.assert_called()
        fake.SetValueEx.assert_not_called()


if __name__ == "__main__":
    unittest.main()
