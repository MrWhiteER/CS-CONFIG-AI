"""Whatever runs alongside the game, started and confirmed before it.

Starting Crosshair X in the same breath as CS2 used to mean both raced for a
window at the same time. This is the fix: every companion asked to come up
with the game is started first, and launcher.play() does not hand off to
Steam until each one answers or this gives up waiting on it -- never fatal,
never indefinite.
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import launcher  # noqa: E402


class _Said(list):
    """Collects (text, tag) pairs the way LaunchSession._say does."""

    def __call__(self, text, tag=""):
        self.append((text, tag))

    def find(self, needle):
        return [t for t, _ in self if needle in t]


class StartingCrosshairX(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(launcher, "COMPANION_WAIT", 0.2)
        patch.start()
        self.addCleanup(patch.stop)

    def test_already_running_is_not_started_again(self):
        said = _Said()
        with mock.patch("cs2cfg.crosshairx.running", return_value=True), \
             mock.patch("cs2cfg.crosshairx.start") as start:
            launcher._bring_up_companions(None, True, said)
        start.assert_not_called()
        self.assertTrue(said.find("already running"))

    def test_a_fresh_start_is_waited_for_until_it_answers(self):
        said = _Said()
        states = iter([False, False, True])
        with mock.patch("cs2cfg.crosshairx.running", side_effect=lambda: next(states, True)), \
             mock.patch("cs2cfg.crosshairx.start", return_value={"ok": True}), \
             mock.patch.object(launcher.time, "sleep"):
            launcher._bring_up_companions(None, True, said)
        self.assertTrue(said.find("starting Crosshair X"))
        self.assertTrue(said.find("Crosshair X is up"))

    def test_a_failed_start_is_reported_and_not_waited_for(self):
        said = _Said()
        with mock.patch("cs2cfg.crosshairx.running", return_value=False), \
             mock.patch("cs2cfg.crosshairx.start",
                       return_value={"ok": False, "error": "no install found"}):
            t0 = time.monotonic()
            launcher._bring_up_companions(None, True, said)
        # Nothing to wait on, so this returns immediately rather than sitting
        # out the whole timeout for a companion that never started.
        self.assertLess(time.monotonic() - t0, 0.1)
        self.assertTrue(said.find("could not start Crosshair X"))

    def test_one_that_never_answers_lets_the_game_start_anyway(self):
        said = _Said()
        with mock.patch("cs2cfg.crosshairx.running", return_value=False), \
             mock.patch("cs2cfg.crosshairx.start", return_value={"ok": True}), \
             mock.patch.object(launcher.time, "sleep"):
            launcher._bring_up_companions(None, True, said)
        self.assertTrue(said.find("did not answer in time"))
        self.assertTrue(said.find("starting CS2 anyway"))


class StartingOtherCompanions(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(launcher, "COMPANION_WAIT", 0.2)
        patch.start()
        self.addCleanup(patch.stop)
        self.entry = {"id": "medal", "name": "Medal", "exe": r"C:\Medal\Medal.exe",
                     "args": "", "with_game": True}

    def test_already_running_is_skipped(self):
        said = _Said()
        with mock.patch("cs2cfg.companions.running", return_value=True), \
             mock.patch("cs2cfg.companions.start") as start:
            launcher._bring_up_companions([self.entry], False, said)
        start.assert_not_called()
        self.assertTrue(said.find("Medal is already running"))

    def test_a_fresh_start_is_waited_for(self):
        said = _Said()
        states = iter([False, True])
        with mock.patch("cs2cfg.companions.running",
                       side_effect=lambda n: next(states, True)), \
             mock.patch("cs2cfg.companions.start",
                       return_value={"ok": True, "already": False}), \
             mock.patch.object(launcher.time, "sleep"):
            launcher._bring_up_companions([self.entry], False, said)
        self.assertTrue(said.find("starting Medal"))
        self.assertTrue(said.find("Medal is up"))

    def test_several_companions_do_not_block_each_other(self):
        """One slow companion does not stop the fast one from being reported
        the moment it is actually up."""
        said = _Said()
        other = {"id": "obs", "name": "OBS", "exe": r"C:\OBS\obs64.exe",
                 "args": "", "with_game": True}
        up = {"Medal.exe": False, "obs64.exe": False}

        def fake_running(name):
            return up.get(name, False)

        def fake_start(entry):
            return {"ok": True, "already": False}

        calls = {"n": 0}

        def fake_sleep(_seconds):
            calls["n"] += 1
            if calls["n"] == 1:
                up["Medal.exe"] = True   # Medal answers after one tick
            if calls["n"] == 2:
                up["obs64.exe"] = True   # OBS a tick later

        with mock.patch("cs2cfg.companions.running", side_effect=fake_running), \
             mock.patch("cs2cfg.companions.start", side_effect=fake_start), \
             mock.patch.object(launcher.time, "sleep", side_effect=fake_sleep):
            launcher._bring_up_companions([self.entry, other], False, said)
        self.assertTrue(said.find("Medal is up"))
        self.assertTrue(said.find("OBS is up"))

    def test_should_stop_ends_the_wait_early(self):
        said = _Said()
        with mock.patch("cs2cfg.companions.running", return_value=False), \
             mock.patch("cs2cfg.companions.start",
                       return_value={"ok": True, "already": False}), \
             mock.patch.object(launcher.time, "sleep") as sleeper:
            launcher._bring_up_companions([self.entry], False, said,
                                          should_stop=lambda: True)
        # Stopped before ever sleeping -- the first check of should_stop
        # happens before the loop body does anything else.
        sleeper.assert_not_called()

    def test_nothing_asked_for_does_nothing(self):
        said = _Said()
        with mock.patch("cs2cfg.companions.running") as running, \
             mock.patch("cs2cfg.crosshairx.running") as cx_running:
            launcher._bring_up_companions(None, False, said)
        running.assert_not_called()
        cx_running.assert_not_called()
        self.assertEqual(len(said), 0)


if __name__ == "__main__":
    unittest.main()
