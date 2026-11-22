"""The frame rate goal: never typed, only a real monitor's rate, plus the
frame rate the player's own games really reached."""

import types
import unittest
from pathlib import Path

from cs2cfg import telemetry, webui
from cs2cfg.hardware import Display

HTML = (Path(__file__).resolve().parents[1] / "cs2cfg" / "web" / "index.html").read_text(encoding="utf-8")


def game(avg, low=None, seconds=1800, frames=500_000):
    return {"duration": seconds,
            "overlay": {"avg_fps": avg, "one_percent_low": low, "frame_count": frames}}


class MeasuredFps(unittest.TestCase):
    def test_nothing_measured_yet(self):
        self.assertIsNone(telemetry.measured_fps([]))
        self.assertIsNone(telemetry.measured_fps([{"duration": 900}, {"duration": 900, "overlay": None}]))

    def test_middle_of_recent_games(self):
        result = telemetry.measured_fps([game(280.4, 190), game(310, 200), game(120, 60)])
        self.assertEqual(result, {"games": 3, "average": 280, "low": 190})

    def test_short_launches_and_thin_data_do_not_count(self):
        result = telemetry.measured_fps([game(900, 800, seconds=20), game(900, 800, frames=50), game(250, 170)])
        self.assertEqual(result, {"games": 1, "average": 250, "low": 170})

    def test_only_the_latest_games(self):
        result = telemetry.measured_fps([game(300)] * 3 + [game(100)] * 20, games=3)
        self.assertEqual(result, {"games": 3, "average": 300, "low": None})


class FrameGoal(unittest.TestCase):
    machine = types.SimpleNamespace(displays=[Display(2560, 1440, 165, primary=True),
                                              Display(1920, 1080, 60)])

    def test_real_monitor_rates_are_kept(self):
        self.assertEqual(webui._frame_goal(self.machine, 165), 165)
        self.assertEqual(webui._frame_goal(self.machine, "60"), 60)

    def test_any_other_number_falls_back_to_the_monitor(self):
        for value in (400, 1000, "999", 0, None, "", "auto"):
            self.assertIsNone(webui._frame_goal(self.machine, value), value)


class NoTypedGoal(unittest.TestCase):
    def test_goal_cannot_be_typed(self):
        self.assertIn('<input type="hidden" id="target"', HTML)
        self.assertNotIn('type="number" id="target"', HTML)
        self.assertNotIn("Target frame rate", HTML)


if __name__ == "__main__":
    unittest.main()
