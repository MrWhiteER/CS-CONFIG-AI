"""Tests for pulling the window back when a change is left unanswered.

Taking focus is a blunt thing to do, so most of what matters here is when it
is *not* done: never while CS2 holds the foreground, never across processes,
and never as a failure when Windows declines. The prompt the player answers
lives in the page and appears either way -- the only thing in question is
whether the window is grabbed along with it.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import webui  # noqa: E402


class Window:
    def __init__(self, hwnd=4242):
        self.hwnd = hwnd


class RaisingTheWindow(unittest.TestCase):
    def _focus(self, game=None, foreground=0, raised=True, boom=None):
        from cs2cfg import desktop, window

        patches = [
            mock.patch.object(window, "find_game_window", return_value=game),
            mock.patch.object(window, "foreground_hwnd", return_value=foreground),
        ]
        if boom is not None:
            patches.append(mock.patch.object(desktop, "focus_existing_window",
                                             side_effect=boom))
        else:
            patches.append(mock.patch.object(desktop, "focus_existing_window",
                                             return_value=raised))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.raiser = patches[-1]
        return webui._focus(None, {})

    def test_it_raises_when_nothing_is_in_the_way(self):
        result = self._focus()
        self.assertTrue(result["ok"])
        self.assertTrue(result["raised"])

    def test_it_never_takes_focus_from_cs2_in_the_foreground(self):
        """Pulling focus out of a live round loses the round. A setting left
        unconfirmed for a few minutes costs nothing by comparison."""
        game = Window(hwnd=99)
        result = self._focus(game=game, foreground=99)
        self.assertTrue(result["ok"])
        self.assertFalse(result["raised"])
        self.assertEqual(result["reason"], "cs2_foreground")

    def test_cs2_running_but_not_in_front_is_not_in_the_way(self):
        """Alt-tabbed out of the game is exactly when someone is in the app."""
        result = self._focus(game=Window(hwnd=99), foreground=1234)
        self.assertTrue(result["raised"])

    def test_windows_declining_is_reported_not_raised_as_an_error(self):
        """SetForegroundWindow is refused from a background process; the
        taskbar is flashed instead, and the prompt is already up regardless."""
        result = self._focus(raised=False)
        self.assertTrue(result["ok"])
        self.assertFalse(result["raised"])
        self.assertEqual(result["reason"], "flashed_instead")

    def test_a_driver_level_failure_does_not_take_the_page_down(self):
        result = self._focus(boom=OSError("no user32 here"))
        self.assertFalse(result["ok"])
        self.assertIn("no user32", result["error"])

    def test_a_broken_game_check_still_lets_the_raise_happen(self):
        """The guard is a courtesy. If it cannot answer, the request the user
        actually made still goes through."""
        from cs2cfg import desktop, window

        with mock.patch.object(window, "find_game_window",
                               side_effect=OSError("cannot enumerate")), \
             mock.patch.object(desktop, "focus_existing_window", return_value=True):
            result = webui._focus(None, {})
        self.assertTrue(result["raised"])


class ScopingTheSearch(unittest.TestCase):
    """A window belonging to another copy of the app is not ours to raise."""

    def test_the_self_raise_is_limited_to_this_process(self):
        from cs2cfg import desktop

        with mock.patch.object(desktop, "focus_existing_window") as raiser:
            raiser.return_value = True
            with mock.patch.object(webui, "_focus", webui._focus):
                from cs2cfg import window
                with mock.patch.object(window, "find_game_window", return_value=None):
                    webui._focus(None, {})
        self.assertTrue(raiser.call_args.kwargs.get("same_process"),
                        "a title match can find another instance's window")


if __name__ == "__main__":
    unittest.main()
