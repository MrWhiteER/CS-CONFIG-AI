"""The Crosshair X integration: finding it, and what it does to the config."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg import crosshairx, hardware, profile
from cs2cfg.kb import KnowledgeBase


def _library(root: Path, installdir: str = "CrosshairX", with_exe: bool = True) -> Path:
    apps = root / "steamapps"
    apps.mkdir(parents=True, exist_ok=True)
    (apps / f"appmanifest_{crosshairx.APP_ID}.acf").write_text(
        '"AppState"\n{\n'
        f'\t"appid"\t\t"{crosshairx.APP_ID}"\n'
        '\t"name"\t\t"Crosshair X"\n'
        f'\t"installdir"\t\t"{installdir}"\n'
        "}\n", encoding="utf-8")
    home = apps / "common" / installdir
    home.mkdir(parents=True, exist_ok=True)
    if with_exe:
        (home / crosshairx.EXE).write_text("", encoding="utf-8")
    return root


class Finding(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_it_is_found_through_the_library_it_is_in(self):
        lib = _library(self.root / "libB")
        found = crosshairx.find([self.root / "libA", lib])
        self.assertTrue(found["installed"])
        self.assertEqual(found["app_id"], crosshairx.APP_ID)
        self.assertTrue(found["exe"].endswith(crosshairx.EXE))

    def test_it_follows_the_manifest_rather_than_assuming_the_folder(self):
        """installdir is whatever Steam wrote. Hardcoding "CrosshairX" would
        work here and fail on somebody whose install is named otherwise."""
        lib = _library(self.root / "lib", installdir="Crosshair X Beta")
        found = crosshairx.find([lib])
        self.assertIn("Crosshair X Beta", found["folder"])

    def test_no_manifest_anywhere_means_not_installed(self):
        (self.root / "empty" / "steamapps").mkdir(parents=True)
        self.assertIsNone(crosshairx.find([self.root / "empty"]))

    def test_a_manifest_without_the_executable_still_reports_the_folder(self):
        """Steam can have the app registered while the files are gone. Saying
        "installed, but there is nothing to run" beats claiming either."""
        lib = _library(self.root / "lib", with_exe=False)
        found = crosshairx.find([lib])
        self.assertTrue(found["installed"])
        self.assertEqual(found["exe"], "")

    def test_a_corrupt_manifest_does_not_raise(self):
        apps = self.root / "bad" / "steamapps"
        apps.mkdir(parents=True)
        (apps / f"appmanifest_{crosshairx.APP_ID}.acf").write_text(
            "this is not a vdf {{{", encoding="utf-8")
        self.assertIsNone(crosshairx.find([self.root / "bad"]))

    def test_summary_says_not_installed_without_inventing_a_path(self):
        seen = crosshairx.summary([self.root / "nothing"])
        self.assertFalse(seen["installed"])
        self.assertFalse(seen["running"])
        self.assertNotIn("folder", seen)


class WhatItDoesToTheConfig(unittest.TestCase):
    """The only thing this writes is the game's own crosshair convar."""

    @classmethod
    def setUpClass(cls):
        cls.machine = hardware.detect()
        cls.kb = KnowledgeBase()

    def _convars(self, hide):
        p = profile.build_profile(self.machine, self.kb, intent="balanced",
                                  hide_crosshair=hide)
        return dict((k, v) for k, v, _ in p.convars)

    def test_off_by_default(self):
        """Turning somebody's crosshair off uninvited is the one way this
        feature could ruin a session."""
        self.assertNotIn(crosshairx.CONVAR, self._convars(False))

    def test_on_when_asked(self):
        self.assertEqual(self._convars(True)[crosshairx.CONVAR], crosshairx.OFF)

    def test_it_says_why(self):
        p = profile.build_profile(self.machine, self.kb, hide_crosshair=True)
        reason = next(r for k, _, r in p.convars if k == crosshairx.CONVAR)
        self.assertTrue(reason.strip(), "a convar with no reason is a mystery later")

    def test_nothing_else_moves(self):
        before, after = self._convars(False), self._convars(True)
        extra = set(after) - set(before)
        self.assertEqual(extra, {crosshairx.CONVAR})
        for key in before:
            self.assertEqual(before[key], after[key], f"{key} changed as a side effect")


class Starting(unittest.TestCase):
    def test_it_goes_through_steam_rather_than_the_executable(self):
        """Launching a Steam app behind Steam's back is how people end up with
        one that thinks it is unlicensed."""
        with mock.patch.object(crosshairx, "running", return_value=False), \
             mock.patch.object(crosshairx.subprocess, "Popen") as run:
            crosshairx.start()
        args = run.call_args[0][0]
        self.assertTrue(any(f"steam://rungameid/{crosshairx.APP_ID}" in str(a) for a in args),
                        f"expected a steam:// launch, got {args}")

    def test_it_does_not_start_a_second_copy(self):
        with mock.patch.object(crosshairx, "running", return_value=True), \
             mock.patch.object(crosshairx.subprocess, "Popen") as run:
            out = crosshairx.start()
        run.assert_not_called()
        self.assertTrue(out["ok"])
        self.assertTrue(out["already"])


class TheCardKeepsUp(unittest.TestCase):
    """The card is drawn from two things that are not ready at boot.

    Reported from a real machine: start the computer, open this straight
    away, and the Crosshair X card is wrong until you reload it. Three
    reasons, all of them timing. Crosshair X is still coming up behind Steam,
    so the badge reads NOT RUNNING and never looks again. A Steam library on a
    drive Windows has not finished mounting makes it look uninstalled, which
    hides the card outright. And the two switches are read from preferences
    that may not have arrived when the card is drawn, so they show off while
    the saved answer is on.

    These assert on the page source rather than running it -- there is no
    browser in this suite -- so they are a guard against the fix being
    deleted, not a test of the behaviour. The behaviour was checked in a
    browser against a machine with Crosshair X actually running.
    """

    @classmethod
    def setUpClass(cls):
        from cs2cfg import paths

        cls.page = (paths.bundle_root() / "web" / "index.html").read_text(
            encoding="utf-8", errors="replace")

    def test_it_looks_again_after_the_first_read(self):
        self.assertIn("function startCrosshairWatch()", self.page)
        self.assertIn("startCrosshairWatch();", self.page)

    def test_the_watch_is_only_armed_once(self):
        """loadCrosshairX runs on every visit to the tab; four visits must not
        leave four timers asking the server the same question."""
        self.assertIn("if (xhairTimer) return;", self.page)

    def test_it_stops_asking_when_nobody_is_looking(self):
        """Each check spawns tasklist on the server."""
        self.assertIn('document.hidden || activeTab !== "settings"', self.page)

    def test_the_live_part_is_repainted_rather_than_rebuilt(self):
        """Rewriting the card every five seconds would throw away a checkbox
        under somebody's cursor, which is a worse bug than the one fixed."""
        self.assertIn("function paintCrosshairLive()", self.page)
        self.assertIn("paintCrosshairLive();", self.page)

    def test_a_start_in_progress_keeps_its_own_label(self):
        self.assertIn('btn.dataset.busy === "1"', self.page)

    def test_the_switches_are_redrawn_when_preferences_land(self):
        self.assertIn("if (xhairData) renderCrosshairX();", self.page)


class WakingTheOverlay(unittest.TestCase):
    """Automating the fix the user found by hand: Win+G, wait, then a focus
    change on the game's own window -- timed off what is on screen, so the
    Crosshair X widget is never left frozen on its loading spinner."""

    def setUp(self):
        from cs2cfg import window

        self.window = window
        self.game = window.WindowInfo(hwnd=99, title="Counter-Strike 2",
                                      process="cs2.exe", rect=(0, 0, 100, 100))
        # A fake Game Bar: Win+G toggles its panel, and the panel shows up
        # ``delay`` polls after the keystroke that opened it.
        self.panel = {"open": False, "pending": None, "delay": 0}
        self.presses = 0
        patches = [
            mock.patch.object(crosshairx.sys, "platform", "win32"),
            mock.patch.object(crosshairx.time, "sleep"),
            mock.patch.object(crosshairx, "_press_win_g", side_effect=self._press),
            mock.patch.object(crosshairx, "_gamebar_in_front", side_effect=self._in_front),
            mock.patch.object(crosshairx, "_gamebar_running", return_value=False),
            mock.patch.object(window, "find_game_window", return_value=self.game),
        ]
        self.mocks = [p.start() for p in patches]
        self.addCleanup(mock.patch.stopall)
        self.gamebar_running = self.mocks[4]
        self.nudge = mock.patch.object(window, "nudge_focus").start()

    def _press(self):
        self.presses += 1
        if self.panel["open"]:
            self.panel["open"] = False
        else:
            self.panel["pending"] = self.panel["delay"]
        return 0

    def _in_front(self):
        if self.panel["pending"] is not None:
            if self.panel["pending"] <= 0:
                self.panel["open"], self.panel["pending"] = True, None
            else:
                self.panel["pending"] -= 1
        return self.panel["open"]

    def _wake(self, **kw):
        kw.setdefault("panel_timeout", 5)
        kw.setdefault("settle", 1)
        kw.setdefault("close_timeout", 1)
        kw.setdefault("interval", 0.01)
        return crosshairx.wake_overlay(**kw)

    def test_windows_only(self):
        with mock.patch.object(crosshairx.sys, "platform", "linux"):
            out = crosshairx.wake_overlay()
        self.assertFalse(out["ok"])

    def test_a_rejected_keystroke_is_reported_not_raised(self):
        with mock.patch.object(crosshairx, "_press_win_g", return_value=5):
            out = self._wake()
        self.assertFalse(out["ok"])
        self.assertIn("error", out)
        self.nudge.assert_not_called()

    def test_it_opens_lets_widgets_load_closes_then_refocuses(self):
        out = self._wake()
        self.assertTrue(out["ok"], out)
        self.assertEqual(self.presses, 2)
        self.assertFalse(self.panel["open"], "Game Bar's panel was left over the game")
        self.nudge.assert_called_once_with(99)

    def test_a_slow_game_bar_is_waited_for_not_raced(self):
        """The bug behind the stuck spinner: on a cold boot the panel took
        longer to appear than the fixed warm-up, so the close keystroke
        landed before it was up. The close must follow the panel, not the
        clock."""
        self.panel["delay"] = 50   # far longer than ``settle`` alone
        clock = {"t": 0.0}

        def tick(seconds):
            clock["t"] += seconds

        with mock.patch.object(crosshairx.time, "sleep", side_effect=tick), \
             mock.patch.object(crosshairx.time, "monotonic", side_effect=lambda: clock["t"]):
            out = self._wake(panel_timeout=5, settle=0.1, interval=0.01)
        self.assertTrue(out["ok"], out)
        self.assertEqual(self.presses, 2)
        self.assertFalse(self.panel["open"])

    def test_the_panel_stays_up_long_enough_for_widgets_to_load(self):
        clock = {"t": 0.0}
        closed_at = {}

        def tick(seconds):
            clock["t"] += seconds

        def press():
            if self.panel["open"]:
                closed_at["t"] = clock["t"]
            return self._press()

        with mock.patch.object(crosshairx.time, "sleep", side_effect=tick), \
             mock.patch.object(crosshairx.time, "monotonic", side_effect=lambda: clock["t"]), \
             mock.patch.object(crosshairx, "_press_win_g", side_effect=press):
            self._wake(settle=3, interval=0.25)
        self.assertGreaterEqual(closed_at["t"], 3)

    def test_a_panel_that_never_appears_is_not_toggled_again(self):
        """Pressing Win+G a second time with no panel in front would be the
        press that opens it -- late, over the game."""
        self.panel["delay"] = 10_000
        clock = {"t": 0.0}
        with mock.patch.object(crosshairx.time, "sleep",
                               side_effect=lambda s: clock.__setitem__("t", clock["t"] + s)), \
             mock.patch.object(crosshairx.time, "monotonic", side_effect=lambda: clock["t"]):
            out = self._wake(panel_timeout=1, interval=0.25)
        self.assertEqual(self.presses, 1)
        self.assertTrue(out["ok"])
        self.assertIn("never came to the front", out["detail"])
        self.nudge.assert_called_once_with(99)

    def test_a_panel_closed_by_the_player_is_not_reopened(self):
        def in_front():
            # Up when first checked, gone (closed by hand) by the time the
            # settle is over.
            in_front.calls += 1
            return in_front.calls == 1
        in_front.calls = 0
        with mock.patch.object(crosshairx, "_gamebar_in_front", side_effect=in_front):
            out = self._wake()
        self.assertTrue(out["ok"])
        self.assertEqual(self.presses, 1)

    def test_an_awake_game_bar_gets_no_keystroke_at_all(self):
        """Game Bar already running means the broker is already attached;
        opening its panel again would only risk the same stuck widget."""
        self.gamebar_running.return_value = True
        out = self._wake()
        self.assertTrue(out["ok"])
        self.assertEqual(self.presses, 0)
        self.nudge.assert_called_once_with(99)

    def test_cancelling_while_waiting_for_the_panel_skips_the_refocus(self):
        self.panel["delay"] = 10_000
        calls = {"n": 0}

        def stop():
            calls["n"] += 1
            return calls["n"] > 3

        out = self._wake(should_stop=stop)
        self.assertEqual(out.get("error"), "cancelled")
        self.nudge.assert_not_called()

    def test_cancelling_mid_settle_leaves_no_refocus(self):
        calls = {"n": 0}

        def stop():
            calls["n"] += 1
            return calls["n"] > 2

        out = self._wake(should_stop=stop, settle=10)
        self.assertEqual(out.get("error"), "cancelled")
        self.nudge.assert_not_called()

    def test_the_game_window_disappearing_is_reported_not_raised(self):
        with mock.patch.object(self.window, "find_game_window", return_value=None):
            out = self._wake()
        self.assertFalse(out["ok"])


class GameBarProbes(unittest.TestCase):
    def test_not_running_off_windows(self):
        with mock.patch.object(crosshairx.sys, "platform", "linux"):
            self.assertFalse(crosshairx._gamebar_running())

    def test_running_reads_tasklist(self):
        done = mock.Mock(stdout="GameBar.exe   1234 Console  1  50,000 K\n")
        with mock.patch.object(crosshairx.sys, "platform", "win32"), \
             mock.patch.object(crosshairx.subprocess, "run", return_value=done):
            self.assertTrue(crosshairx._gamebar_running())

    def test_in_front_compares_the_focused_process(self):
        from cs2cfg import window

        with mock.patch.object(window, "foreground_process", return_value="gamebar.exe"):
            self.assertTrue(crosshairx._gamebar_in_front())
        with mock.patch.object(window, "foreground_process", return_value="cs2.exe"):
            self.assertFalse(crosshairx._gamebar_in_front())
        with mock.patch.object(window, "foreground_process", side_effect=OSError):
            self.assertFalse(crosshairx._gamebar_in_front())


if __name__ == "__main__":
    unittest.main()
