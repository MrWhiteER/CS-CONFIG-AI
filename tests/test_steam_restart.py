"""Restarting Steam, and never launching something twice.

Both came out of the same session. "No Steam logon" mid-match turned out not
to be this application's doing -- it happens launching straight from Steam,
and a restart of the client clears it -- so the answer is a repair, not a
change to how the game is launched. The second is the rule that nothing may be
started while it is already running.

Nothing here restarts anything: every process call is a mock, and what is
asserted is which calls were made and in what order. The waits are shortened
to milliseconds, because the logic is what is under test and not the length of
the pause.
"""

from __future__ import annotations

import sys
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import quickfix  # noqa: E402

STEAM = Path("/fake/steam.exe")


def _quick(stack, **extra):
    """The common stubbing: Windows, a findable Steam, and no real waiting."""
    patches = {
        "STEAM_SHUTDOWN_WAIT": 0.05,
        "STEAM_READY_WAIT": 0.05,
    }
    stack.enter_context(mock.patch.object(quickfix.sys, "platform", "win32"))
    stack.enter_context(mock.patch("cs2cfg.launcher.steam_exe", return_value=STEAM))
    stack.enter_context(mock.patch.object(quickfix.time, "sleep"))
    for name, value in patches.items():
        stack.enter_context(mock.patch.object(quickfix, name, value))
    for name, value in extra.items():
        stack.enter_context(mock.patch.object(quickfix, name, **value))


class ClosingItProperly(unittest.TestCase):
    def _run(self, up, closes=True, signed_in=True, body=None):
        """``closes`` says whether the graceful shutdown works.

        When it does not, Steam stays up until taskkill is what ends it, which
        is what makes the forced path observable.
        """
        live = {"up": up}

        def popened(argv, **kw):
            if len(argv) > 1 and argv[1] == "-shutdown" and closes:
                live["up"] = False
            return mock.MagicMock()

        def killed(argv, **kw):
            live["up"] = False
            return mock.MagicMock()

        with ExitStack() as stack:
            _quick(stack,
                   _steam_running={"side_effect": lambda: live["up"]},
                   _signed_in_since={"return_value": signed_in})
            popen = stack.enter_context(
                mock.patch.object(quickfix.subprocess, "Popen", side_effect=popened))
            ran = stack.enter_context(
                mock.patch.object(quickfix.subprocess, "run", side_effect=killed))
            out = quickfix._fix_restart_steam(body or {})
        return out, popen, ran

    def test_it_asks_steam_to_close_rather_than_killing_it(self):
        """Steam writes localconfig.vdf on the way out -- the file the launch
        options live in. A kill loses whatever it had not written yet."""
        out, popen, ran = self._run(up=True)
        self.assertEqual(popen.call_args_list[0][0][0][1:], ["-shutdown"])
        ran.assert_not_called()
        self.assertFalse(out["forced"])

    def test_it_starts_steam_again_afterwards(self):
        out, popen, _ = self._run(up=True)
        self.assertEqual(popen.call_args_list[-1][0][0], [str(STEAM)])
        self.assertTrue(out["ok"])

    def test_a_steam_that_will_not_close_is_ended_only_after_its_full_chance(self):
        out, _, ran = self._run(up=True, closes=False)
        self.assertTrue(out["forced"])
        self.assertIn("taskkill", ran.call_args[0][0][0])

    def test_the_graceful_attempt_always_comes_first(self):
        """Never a kill as the opening move."""
        _, popen, ran = self._run(up=True, closes=False)
        self.assertEqual(popen.call_args_list[0][0][0][1:], ["-shutdown"])
        self.assertTrue(popen.call_count >= 2, "it must still be started again")

    def test_a_steam_that_was_not_running_is_simply_started(self):
        out, popen, ran = self._run(up=False)
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(popen.call_args_list[0][0][0], [str(STEAM)])
        ran.assert_not_called()


class KnowingWhenItIsBack(unittest.TestCase):
    def _run(self, signed_in, body):
        with ExitStack() as stack:
            _quick(stack,
                   _steam_running={"return_value": False},
                   _signed_in_since={"return_value": signed_in})
            stack.enter_context(mock.patch.object(quickfix.subprocess, "Popen"))
            return quickfix._fix_restart_steam(body)

    def test_it_waits_for_a_sign_in_not_just_a_process(self):
        """The process exists a second after starting it and can do nothing
        with a game for another twenty."""
        out = self._run(signed_in=False, body={"then_play": True})
        # Not an error: Steam may be waiting on a password or a phone prompt,
        # and calling that a failure would be a lie.
        self.assertTrue(out["ok"])
        self.assertFalse(out["signed_in"])
        self.assertFalse(out["then_play"],
                         "must not launch into a Steam that is not ready")

    def test_the_launch_is_only_offered_once_it_is_signed_in(self):
        self.assertTrue(self._run(signed_in=True, body={"then_play": True})["then_play"])

    def test_not_asked_to_play_means_not_playing(self):
        self.assertFalse(self._run(signed_in=True, body={})["then_play"])

    def test_a_stale_sign_in_does_not_count_as_a_fresh_one(self):
        """The whole reason the log is read by date: Steam rotates the file on
        restart, so yesterday's entry must not read as today's."""
        log = f"[2020-01-01 10:00:00] [Logged On, 4, 7] [U:1:1] {quickfix._LOGON_MARK}"
        root = mock.MagicMock()
        (root / "logs" / "connection_log.txt").read_text.return_value = log
        with mock.patch("cs2cfg.steam.find_steam_root", return_value=root):
            self.assertFalse(quickfix._signed_in_since(time.time()))
            self.assertTrue(quickfix._signed_in_since(0))

    def test_an_unreadable_log_is_not_mistaken_for_a_sign_in(self):
        with mock.patch("cs2cfg.steam.find_steam_root", side_effect=OSError("no")):
            self.assertFalse(quickfix._signed_in_since(0))


class RefusingToStartItTwice(unittest.TestCase):
    """Rule one: never offer to start something that is already started."""

    def test_the_repair_is_held_back_during_a_match(self):
        entry = next(f for f in quickfix.catalogue() if f["id"] == "steam.restart")
        self.assertTrue(entry["disruptive"])
        self.assertFalse(entry["allowed_in_game"])

    def test_running_it_while_cs2_is_up_is_refused(self):
        with mock.patch.object(quickfix, "_game_running", return_value=True):
            out = quickfix.run("steam.restart", {})
        self.assertFalse(out["ok"])
        self.assertTrue(out["blocked"])

    def test_the_launcher_asks_the_process_not_the_window(self):
        """A window turns up half a minute after the process does, and
        pressing Play in that gap used to start a second game."""
        from cs2cfg import launcher

        with mock.patch("cs2cfg.steam.cs2_running", return_value=True), \
             mock.patch.object(launcher.window, "find_game_window", return_value=None), \
             self.assertRaises(launcher.LaunchError) as caught:
            launcher.play(mock.MagicMock(), 1920, 1080)
        self.assertIn("already running", str(caught.exception))

    def test_the_window_check_still_catches_what_the_process_check_cannot(self):
        """Kept behind the process check rather than replaced by it, for a
        machine where tasklist cannot be run at all."""
        from cs2cfg import launcher

        with mock.patch("cs2cfg.steam.cs2_running", return_value=False), \
             mock.patch.object(launcher.window, "find_game_window",
                               return_value=object()), \
             self.assertRaises(launcher.LaunchError) as caught:
            launcher.play(mock.MagicMock(), 1920, 1080)
        self.assertIn("already running", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
