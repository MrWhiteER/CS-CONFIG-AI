"""Tests for the display and NVIDIA modules.

These run on any machine: a box with no NVIDIA driver, or no Windows display
API at all, must degrade to a clear message rather than raising. Nothing here
changes a display mode or writes to the driver database.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import displays, nvidia  # noqa: E402


class TestDisplayModel(unittest.TestCase):
    """The parts that reason about modes, driven by made-up data."""

    def make(self, current, rates, primary=True):
        return displays.Display(
            device=r"\\.\DISPLAY9", name="Test panel", primary=primary,
            current=current, rates=rates)

    def test_reports_the_rates_for_the_resolution_in_use(self):
        screen = self.make(displays.Mode(2560, 1440, 120),
                           {(2560, 1440): [240, 120, 60], (1920, 1080): [360]})
        self.assertEqual(screen.available_here, [240, 120, 60])
        self.assertEqual(screen.best_here, 240)

    def test_a_screen_below_its_maximum_is_flagged(self):
        screen = self.make(displays.Mode(2560, 1440, 120), {(2560, 1440): [240, 120]})
        self.assertFalse(screen.at_best)

    def test_a_screen_at_its_maximum_is_not_flagged(self):
        screen = self.make(displays.Mode(2560, 1440, 240), {(2560, 1440): [240, 120]})
        self.assertTrue(screen.at_best)

    def test_a_rate_above_the_listed_maximum_still_counts_as_best(self):
        """Panels round: a 239.964 Hz mode is reported as 239 by some APIs and
        240 by others. Being at or above the highest listed rate is enough."""
        screen = self.make(displays.Mode(2560, 1440, 240), {(2560, 1440): [239]})
        self.assertTrue(screen.at_best)

    def test_a_screen_with_no_current_mode_claims_nothing(self):
        screen = self.make(None, {(2560, 1440): [240]})
        self.assertEqual(screen.available_here, [])
        self.assertIsNone(screen.best_here)
        self.assertFalse(screen.at_best)


class TestRefreshGuards(unittest.TestCase):
    """set_refresh should refuse rather than surprise anyone."""

    def test_unknown_display_is_refused(self):
        # Pinned off, or this passes or fails depending on whether the machine
        # running the tests happens to have CS2 open.
        with mock.patch.object(displays, "_game_running", return_value=False):
            result = displays.set_refresh(r"\\.\NOSUCH", 120, apply=True)
        self.assertFalse(result["ok"])
        self.assertIn("no display", result["error"])

    def test_a_rate_the_panel_does_not_offer_is_refused(self):
        screen = displays.Display(
            device=r"\\.\DISPLAY9", name="Test", primary=True,
            current=displays.Mode(2560, 1440, 120), rates={(2560, 1440): [240, 120]})
        with mock.patch.object(displays, "find", return_value=screen), \
             mock.patch.object(displays, "_game_running", return_value=False):
            result = displays.set_refresh(r"\\.\DISPLAY9", 360, apply=True)
        self.assertFalse(result["ok"])
        self.assertIn("does not offer 360", result["error"])

    def test_the_mode_is_not_changed_while_the_game_is_running(self):
        """Changing the mode under a running game drops its swapchain, which is
        the black screen this application exists to avoid."""
        screen = displays.Display(
            device=r"\\.\DISPLAY9", name="Test", primary=True,
            current=displays.Mode(2560, 1440, 120), rates={(2560, 1440): [240, 120]})
        with mock.patch.object(displays, "find", return_value=screen), \
             mock.patch.object(displays, "_game_running", return_value=True):
            result = displays.set_refresh(r"\\.\DISPLAY9", 240, apply=True)
        self.assertFalse(result["ok"])
        self.assertTrue(result["game_running"])
        self.assertIn("CS2 is running", result["error"])

    def test_testing_a_mode_is_allowed_while_the_game_runs(self):
        """Only applying is blocked; asking whether a rate would work is safe."""
        screen = displays.Display(
            device=r"\\.\DISPLAY9", name="Test", primary=True,
            current=displays.Mode(2560, 1440, 120), rates={(2560, 1440): [240, 120]})
        with mock.patch.object(displays, "find", return_value=screen), \
             mock.patch.object(displays, "_game_running", return_value=True):
            result = displays.set_refresh(r"\\.\DISPLAY9", 240, apply=False)
        self.assertNotIn("game_running", result)

    def test_summary_has_the_shape_the_page_expects(self):
        payload = displays.summary()
        self.assertTrue(payload["ok"])
        self.assertIn("displays", payload)
        for screen in payload["displays"]:
            self.assertEqual(
                set(screen) >= {"device", "name", "primary", "current",
                                "rates", "best", "at_best"}, True)


class TestNvidiaIsReadOnly(unittest.TestCase):
    def test_no_write_call_is_reachable(self):
        """The safety property this module rests on: without SaveSettings in
        the function table, nothing here can modify the driver database."""
        for forbidden in ("DRS_SaveSettings", "DRS_SetSetting",
                          "DRS_CreateProfile", "DRS_CreateApplication",
                          "DRS_DeleteProfile", "DRS_RestoreDefaults"):
            self.assertNotIn(forbidden, nvidia._FN)

    def test_the_source_never_mentions_saving(self):
        source = Path(nvidia.__file__).read_text(encoding="utf-8")
        code = "\n".join(line for line in source.splitlines()
                         if not line.strip().startswith("#"))
        self.assertNotIn("SaveSettings", code.split('"""')[-1])

    def test_a_machine_with_no_driver_reports_rather_than_raises(self):
        with mock.patch.object(nvidia.ctypes, "WinDLL",
                               side_effect=OSError("not found")):
            result = nvidia.probe()
        self.assertFalse(result.available)
        self.assertIn("no NVIDIA driver", result.reason)

    def test_the_payload_survives_an_unavailable_driver(self):
        with mock.patch.object(nvidia.ctypes, "WinDLL",
                               side_effect=OSError("not found")):
            payload = nvidia.as_dict(nvidia.probe())
        self.assertFalse(payload["available"])
        self.assertIsNone(payload["global"])
        self.assertEqual(payload["apps"], {})

    def test_a_setting_without_a_driver_name_is_marked_unknown(self):
        named = nvidia.Setting(id=0x1057EB71, name="Power management mode",
                               value="0x00000001", predefined=False)
        internal = nvidia.Setting(id=0x00313537, name="", value="0x00000004",
                                  predefined=True)
        self.assertTrue(named.known)
        self.assertFalse(internal.known)


if __name__ == "__main__":
    unittest.main()
