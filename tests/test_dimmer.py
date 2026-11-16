"""The screen dim behind the match-found alert: harmless where it cannot run."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import dimmer  # noqa: E402


class OffWindows(unittest.TestCase):
    def test_show_and_hide_do_nothing_off_windows(self):
        with mock.patch.object(dimmer.sys, "platform", "linux"):
            self.assertFalse(dimmer.show())
            dimmer.hide()                 # never raises
            self.assertEqual(dimmer.monitors(), [])

    def test_hide_without_show_is_fine(self):
        dimmer.hide()
        dimmer.hide()


class OneDimPerScreen(unittest.TestCase):
    def test_show_twice_starts_one_thread(self):
        started = []

        def fake_run(stop, ready):
            started.append(1)
            ready.set()
            stop.wait(2)

        with mock.patch.object(dimmer.sys, "platform", "win32"), \
             mock.patch.object(dimmer, "_run", side_effect=fake_run):
            self.assertTrue(dimmer.show())
            self.assertTrue(dimmer.show())
            dimmer.hide()
        self.assertEqual(len(started), 1)


if __name__ == "__main__":
    unittest.main()
