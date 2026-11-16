"""The automatic follow-up after a region lock: launch options only, never Steam itself."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import lockfollowup as lf  # noqa: E402


class MaxPing(unittest.TestCase):
    def test_just_above_the_region(self):
        self.assertEqual(lf.max_ping_for(114.4), 129)
        self.assertEqual(lf.max_ping_for(7), 40)
        self.assertEqual(lf.max_ping_for(None), 150)
        self.assertEqual(lf.max_ping_for(900), 350)


class LaunchOptions(unittest.TestCase):
    def test_adds_maxping_and_condebug_keeping_the_rest(self):
        self.assertEqual(lf.launch_options_for("-novid -high", 129),
                         "-novid -high -condebug +mm_dedicated_search_maxping 129")

    def test_replaces_an_old_value_and_does_not_duplicate_condebug(self):
        self.assertEqual(lf.launch_options_for("-condebug +mm_dedicated_search_maxping 40 -novid", 129),
                         "-condebug -novid +mm_dedicated_search_maxping 129")

    def test_unlock_removes_only_the_max_ping(self):
        self.assertEqual(lf.launch_options_for("-novid -condebug +mm_dedicated_search_maxping 129", None),
                         "-novid -condebug")

    def test_empty_options(self):
        self.assertEqual(lf.launch_options_for("", 60), "-condebug +mm_dedicated_search_maxping 60")


if __name__ == "__main__":
    unittest.main()
