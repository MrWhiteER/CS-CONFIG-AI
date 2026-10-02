"""Putting back what was armed for a launch, once the launch is over.

Reported: a demo chosen with Watch played again on the next launch, and the
one after that. Clearing it was tied to launching *through this application*,
so a game started from Steam, a session this application was not running for,
or a crash all left it armed indefinitely.

The rule is now simply: the game is not running, therefore nothing should
still be armed for it. The whole difficulty is one timing trap, which is what
most of this file is about -- the game is also not running in the half-minute
between pressing Watch and the game appearing.
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import webui  # noqa: E402


def _state():
    return types.SimpleNamespace(cs2_install=None, users=[], cfg_folder="mrwhiteer",
                                 refresh=lambda *a, **k: None)


class TheTimingTrap(unittest.TestCase):
    """The reason this is not simply "clear it when the game is not up"."""

    def test_arming_then_waiting_for_the_game_does_not_disarm_it(self):
        """Press Watch, and for the next half-minute the game is still not
        running. Clearing then would disarm the very launch it was for."""
        state = _state()
        state._watched_once = True            # not a fresh start
        with mock.patch.object(webui, "_settle_demo") as cleared:
            for _ in range(8):                # half a minute of polling
                webui._stand_down(state, game_running=False)
        cleared.assert_not_called()

    def test_it_stands_down_once_the_game_has_been_and_gone(self):
        state = _state()
        state._watched_once = True
        with mock.patch.object(webui, "_settle_demo", return_value=True) as cleared:
            webui._stand_down(state, game_running=False)   # still starting
            webui._stand_down(state, game_running=True)    # playing
            webui._stand_down(state, game_running=True)
            out = webui._stand_down(state, game_running=False)  # quit
        cleared.assert_called_once()
        self.assertTrue(out["demo_cleared"])

    def test_it_only_stands_down_once(self):
        """Polling continues forever after the game exits."""
        state = _state()
        state._watched_once = True
        with mock.patch.object(webui, "_settle_demo", return_value=True) as cleared:
            webui._stand_down(state, game_running=True)
            for _ in range(5):
                webui._stand_down(state, game_running=False)
        self.assertEqual(cleared.call_count, 1)

    def test_a_second_launch_arms_and_stands_down_again(self):
        state = _state()
        state._watched_once = True
        with mock.patch.object(webui, "_settle_demo", return_value=True) as cleared:
            webui._stand_down(state, game_running=True)
            webui._stand_down(state, game_running=False)
            webui._stand_down(state, game_running=True)
            webui._stand_down(state, game_running=False)
        self.assertEqual(cleared.call_count, 2)


class TheCasesThatUsedToStickForever(unittest.TestCase):
    def test_a_fresh_start_with_the_game_closed_stands_down(self):
        """The crash case, and the "quit the software" case. If this
        application has only just started and the game is not running, any arm
        it finds belongs to a session that is over however it ended."""
        state = _state()                      # no _watched_once: first poll
        with mock.patch.object(webui, "_settle_demo", return_value=True) as cleared:
            webui._stand_down(state, game_running=False)
        cleared.assert_called_once()

    def test_a_fresh_start_with_the_game_running_waits(self):
        """Started this application while already playing. The game is up, so
        whatever is armed is in use -- or at least cannot be judged yet."""
        state = _state()
        with mock.patch.object(webui, "_settle_demo") as cleared:
            webui._stand_down(state, game_running=True)
        cleared.assert_not_called()

    def test_it_does_not_depend_on_having_launched_the_game_itself(self):
        """The actual bug: clearing was tied to launching through here, so a
        game started from Steam never cleared anything. Nothing in this path
        knows or cares how the game was started."""
        state = _state()
        state._watched_once = True
        with mock.patch.object(webui, "_settle_demo", return_value=True) as cleared:
            webui._stand_down(state, game_running=True)     # started elsewhere
            webui._stand_down(state, game_running=False)
        cleared.assert_called_once()


class ItIsNeverFatal(unittest.TestCase):
    def test_a_failure_to_tidy_does_not_take_the_poll_with_it(self):
        """This runs inside the status poll the whole interface depends on."""
        state = _state()
        state._watched_once = True
        with mock.patch.object(webui, "_settle_demo", side_effect=OSError("no")):
            webui._stand_down(state, game_running=True)
            self.assertEqual(webui._stand_down(state, game_running=False), {})

    def test_nothing_to_clear_says_nothing(self):
        state = _state()
        state._watched_once = True
        with mock.patch.object(webui, "_settle_demo", return_value=False):
            webui._stand_down(state, game_running=True)
            self.assertEqual(webui._stand_down(state, game_running=False), {})


if __name__ == "__main__":
    unittest.main()
