"""The stretch has to survive the whole session, not just the launch.

The desktop mode is set with CDS_FULLSCREEN and no CDS_UPDATEREGISTRY, so it
belongs to the process and Windows drops it whenever it re-evaluates the
display topology. Nothing used to notice. These tests pin the behaviour that
notices, and -- just as important -- pin that it stays still when nothing is
wrong, because re-applying a correct mode would drop the game's swapchain for
no reason.

Every display call is mocked. No test here changes a display mode.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import window  # noqa: E402

WANT = (1550, 1440)
MONITOR = (0, 0, 1550, 1440)


def fake_window(rect=MONITOR):
    found = mock.Mock()
    found.hwnd = 4242
    found.rect = rect
    found.process = "cs2.exe"
    found.size = (rect[2] - rect[0], rect[3] - rect[1])
    found.title = "Counter-Strike 2"
    return found


class TestCheckStretch(unittest.TestCase):
    def test_reports_nothing_running_without_touching_the_display(self):
        with mock.patch.object(window, "find_game_window", return_value=None), \
             mock.patch.object(window, "current_mode") as mode:
            state = window.check_stretch(*WANT)
        self.assertFalse(state["running"])
        mode.assert_not_called()

    def test_a_matching_desktop_and_window_are_both_ok(self):
        with mock.patch.object(window, "find_game_window", return_value=fake_window()), \
             mock.patch.object(window, "current_mode", return_value=(1550, 1440, 240)), \
             mock.patch.object(window, "monitor_bounds", return_value=MONITOR):
            state = window.check_stretch(*WANT)
        self.assertTrue(state["mode_ok"])
        self.assertTrue(state["window_ok"])

    def test_a_desktop_windows_has_taken_back_is_flagged(self):
        """The actual symptom: the game keeps its window, the desktop snaps
        back to native, and the picture stops filling the screen."""
        with mock.patch.object(window, "find_game_window", return_value=fake_window()), \
             mock.patch.object(window, "current_mode", return_value=(2560, 1440, 240)), \
             mock.patch.object(window, "monitor_bounds", return_value=MONITOR):
            state = window.check_stretch(*WANT)
        self.assertFalse(state["mode_ok"])
        self.assertEqual(state["mode"], (2560, 1440))

    def test_a_window_that_has_drifted_off_the_origin_is_flagged(self):
        with mock.patch.object(window, "find_game_window",
                               return_value=fake_window((80, 40, 1630, 1480))), \
             mock.patch.object(window, "current_mode", return_value=(1550, 1440, 240)), \
             mock.patch.object(window, "monitor_bounds", return_value=MONITOR):
            state = window.check_stretch(*WANT)
        self.assertTrue(state["mode_ok"])
        self.assertFalse(state["window_ok"])


class TestRepairStretch(unittest.TestCase):
    def test_a_correct_session_is_left_completely_alone(self):
        """Pressing the button when nothing is wrong must cost nothing --
        re-applying a correct mode would stall the game for no reason."""
        with mock.patch.object(window, "find_game_window", return_value=fake_window()), \
             mock.patch.object(window, "current_mode", return_value=(1550, 1440, 240)), \
             mock.patch.object(window, "monitor_bounds", return_value=MONITOR), \
             mock.patch.object(window, "set_mode") as set_mode, \
             mock.patch.object(window, "make_borderless") as borderless:
            result = window.repair_stretch(*WANT)
        set_mode.assert_not_called()
        borderless.assert_not_called()
        self.assertFalse(result["repaired"])
        self.assertEqual(result["actions"], [])

    def test_a_reverted_desktop_mode_is_put_back(self):
        modes = [(2560, 1440, 240), (2560, 1440, 240), (1550, 1440, 240), (1550, 1440, 240)]
        with mock.patch.object(window, "find_game_window", return_value=fake_window()), \
             mock.patch.object(window, "current_mode", side_effect=modes), \
             mock.patch.object(window, "monitor_bounds", return_value=MONITOR), \
             mock.patch.object(window, "set_mode") as set_mode, \
             mock.patch.object(window, "make_borderless", return_value=(1550, 1440)), \
             mock.patch.object(window, "_load_state", return_value=None), \
             mock.patch.object(window.time, "sleep"):
            result = window.repair_stretch(*WANT)
        self.assertTrue(result["repaired"])
        self.assertIn("desktop 2560x1440 -> 1550x1440", result["actions"][0])
        # Probed with CDS_TEST before committing, then applied.
        self.assertEqual(set_mode.call_count, 2)
        self.assertTrue(set_mode.call_args_list[0].kwargs.get("test_only"))

    def test_only_the_window_is_refitted_when_the_mode_is_fine(self):
        with mock.patch.object(window, "find_game_window",
                               return_value=fake_window((80, 40, 1630, 1480))), \
             mock.patch.object(window, "current_mode", return_value=(1550, 1440, 240)), \
             mock.patch.object(window, "monitor_bounds", return_value=MONITOR), \
             mock.patch.object(window, "set_mode") as set_mode, \
             mock.patch.object(window, "make_borderless",
                               return_value=(1550, 1440)) as borderless:
            result = window.repair_stretch(*WANT)
        set_mode.assert_not_called()
        borderless.assert_called_once()
        self.assertTrue(result["repaired"])

    def test_refitting_does_not_overwrite_the_saved_original_frame(self):
        """The launch recorded the pre-stretch geometry so it can be restored
        on exit; saving again here would record the stretched size as the
        thing to go back to, and the window would never come back."""
        with mock.patch.object(window, "find_game_window",
                               return_value=fake_window((80, 40, 1630, 1480))), \
             mock.patch.object(window, "current_mode", return_value=(1550, 1440, 240)), \
             mock.patch.object(window, "monitor_bounds", return_value=MONITOR), \
             mock.patch.object(window, "make_borderless",
                               return_value=(1550, 1440)) as borderless:
            window.repair_stretch(*WANT)
        self.assertIs(borderless.call_args.kwargs["remember"], False)

    def test_a_game_that_is_not_running_raises_rather_than_changing_the_desktop(self):
        with mock.patch.object(window, "find_game_window", return_value=None), \
             mock.patch.object(window, "set_mode") as set_mode:
            with self.assertRaises(window.WindowError):
                window.repair_stretch(*WANT)
        set_mode.assert_not_called()


if __name__ == "__main__":
    unittest.main()
