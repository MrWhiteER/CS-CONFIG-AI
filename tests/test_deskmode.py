"""Giving the desktop back.

The launcher narrows the desktop for a stretched mode and restores it when the
game exits. Reported from a real machine: when the game crashes, or when this
application is closed while it still holds the mode, nobody restores it and
you are left on a 1550x1440 desktop with no obvious way back. That is a worse
state than anything this application exists to fix, so the record of what to
put back lives in a file rather than in memory -- memory being precisely what
does not survive the cases this is for.

The thing these guard hardest is the opposite failure: forcing a resolution
onto somebody who changed it themselves. Every display call here is a mock and
no test touches a real display.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cs2cfg  # noqa: E402
from cs2cfg import deskmode  # noqa: E402
from cs2cfg import window as _window  # noqa: E402,F401  (so the attribute exists to patch)

NATIVE = (2560, 1440, 240)
STRETCHED = (1550, 1440, 240)


class _Fake:
    """Stands in for the window module."""

    def __init__(self, now, registry=None, fails=False):
        self.now = now
        self.registry = registry or NATIVE
        self.fails = fails
        self.set_to = None

    def current_mode(self):
        return self.now

    def registry_mode(self):
        return self.registry

    def set_mode(self, w, h, refresh=0, test_only=False, persist=False):
        if self.fails:
            raise RuntimeError("the driver said no")
        self.set_to = (w, h, refresh)
        self.now = (w, h, refresh)


class _Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "desktop_mode.json"
        patch = mock.patch.object(deskmode, "record_path", return_value=self.path)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def _held(self, before=NATIVE, changed_to=STRETCHED):
        deskmode.remember(before, changed_to)

    def _with(self, fake):
        """Stand the fake in for the real window module.

        Patching the attribute on the package, not the sys.modules entry:
        ``from . import window`` reads the attribute when the real module has
        already been imported, which it has as soon as any other test in the
        suite has touched it. Patching only sys.modules passed when this file
        ran alone and quietly used the real display when it did not.
        """
        import cs2cfg

        return mock.patch.object(cs2cfg, "window", fake)


class TheRecord(_Case):
    def test_it_survives_being_written_and_read(self):
        self._held()
        got = deskmode.outstanding()
        self.assertEqual(got["before"], NATIVE)
        self.assertEqual(got["changed_to"], STRETCHED)

    def test_nothing_recorded_is_not_an_error(self):
        self.assertIsNone(deskmode.outstanding())

    def test_a_damaged_record_is_dropped_rather_than_trusted(self):
        """It decides what resolution somebody's desktop becomes. Half a file
        is not something to act on."""
        for junk in ("{", '{"before": [1, 2]}', '{"before": "x", "changed_to": 3}',
                     '{"changed_to": [1, 2, 3]}'):
            self.path.write_text(junk, encoding="utf-8")
            self.assertIsNone(deskmode.outstanding(), junk)
            self.assertFalse(self.path.exists(), "the bad record should be gone")

    def test_forgetting_a_record_that_is_not_there_is_quiet(self):
        deskmode.forget()      # must not raise


class TheAutomaticPutBack(_Case):
    def test_a_desktop_still_stretched_with_the_game_gone_is_put_back(self):
        """The whole point."""
        self._held()
        fake = _Fake(now=STRETCHED)
        with self._with(fake):
            out = deskmode.tidy(game_running=False)
        self.assertTrue(out["restored"])
        self.assertEqual(fake.set_to[:2], NATIVE[:2])
        self.assertIsNone(deskmode.outstanding(), "the record should be spent")

    def test_it_waits_while_the_game_is_still_running(self):
        """A running game is presumed to want the mode it was launched with."""
        self._held()
        fake = _Fake(now=STRETCHED)
        with self._with(fake):
            out = deskmode.tidy(game_running=True)
        self.assertEqual(out, {})
        self.assertIsNone(fake.set_to)
        self.assertIsNotNone(deskmode.outstanding(), "still ours to give back")

    def test_a_desktop_already_back_just_drops_the_record(self):
        """Windows drops a temporary mode by itself when the process that
        asked for it goes away, so this is the common ending."""
        self._held()
        fake = _Fake(now=NATIVE)
        with self._with(fake):
            out = deskmode.tidy(game_running=False)
        self.assertIsNone(fake.set_to, "nothing to change")
        self.assertEqual(out, {})
        self.assertIsNone(deskmode.outstanding())

    def test_a_resolution_somebody_chose_themselves_is_left_alone(self):
        """The failure that would matter most. The desktop is in neither the
        mode we borrowed nor the one we set, so something else has moved it
        and our idea of "before" is out of date. Forcing it would be taking
        somebody's display decision away from them."""
        self._held()
        fake = _Fake(now=(3840, 2160, 120))
        with self._with(fake):
            out = deskmode.tidy(game_running=False)
        self.assertIsNone(fake.set_to)
        self.assertEqual(out, {})
        self.assertIsNone(deskmode.outstanding(), "a stale record is not kept")

    def test_nothing_recorded_means_nothing_happens(self):
        fake = _Fake(now=STRETCHED)
        with self._with(fake):
            self.assertEqual(deskmode.tidy(game_running=False), {})
        self.assertIsNone(fake.set_to)

    def test_a_failed_put_back_keeps_the_record_for_the_next_try(self):
        self._held()
        fake = _Fake(now=STRETCHED, fails=True)
        with self._with(fake):
            out = deskmode.tidy(game_running=False)
        self.assertFalse(out["restored"])
        self.assertIsNotNone(deskmode.outstanding(),
                             "dropping it here would strand the desktop")

    def test_a_different_refresh_rate_still_counts_as_the_same_desktop(self):
        """Windows reports 165 for a mode asked for as 164.998."""
        deskmode.remember(NATIVE, (1550, 1440, 239))
        fake = _Fake(now=(1550, 1440, 240))
        with self._with(fake):
            out = deskmode.tidy(game_running=False)
        self.assertTrue(out["restored"])


class TheManualPutBack(_Case):
    def test_it_uses_the_recorded_mode_when_there_is_one(self):
        self._held()
        fake = _Fake(now=STRETCHED)
        with self._with(fake):
            out = deskmode.restore()
        self.assertTrue(out["ok"])
        self.assertEqual(fake.set_to[:2], NATIVE[:2])

    def test_with_no_record_it_falls_back_to_what_windows_has_saved(self):
        """The emergency case: this application was restarted, so the record
        is gone, and the desktop is still wrong. A stretched mode set
        temporarily never reaches the registry, so the registry still holds
        the real one."""
        fake = _Fake(now=STRETCHED, registry=NATIVE)
        with self._with(fake):
            out = deskmode.restore()
        self.assertTrue(out["ok"])
        self.assertEqual(fake.set_to[:2], NATIVE[:2])

    def test_pressing_it_when_nothing_is_wrong_changes_nothing(self):
        """It has to be safe to press on a hunch."""
        fake = _Fake(now=NATIVE, registry=NATIVE)
        with self._with(fake):
            out = deskmode.restore()
        self.assertTrue(out["ok"])
        self.assertFalse(out["changed"])
        self.assertIsNone(fake.set_to)

    def test_it_acts_on_a_mode_it_does_not_recognise(self):
        """Unlike the automatic one. Somebody pressing this is saying the
        desktop is wrong, and second-guessing them is not useful."""
        self._held()
        fake = _Fake(now=(1024, 768, 60))
        with self._with(fake):
            out = deskmode.restore()
        self.assertTrue(out["ok"])
        self.assertEqual(fake.set_to[:2], NATIVE[:2])

    def test_a_refusal_is_reported_rather_than_raised(self):
        fake = _Fake(now=STRETCHED, fails=True)
        with self._with(fake):
            out = deskmode.restore()
        self.assertFalse(out["ok"])
        self.assertIn("error", out)

    def test_it_is_offered_during_a_game_too(self):
        """If the desktop is wrong with the game up, the presumption that a
        running game wants its launch mode is already false."""
        from cs2cfg import quickfix

        entry = next(f for f in quickfix.catalogue() if f["id"] == "display.restore")
        self.assertTrue(entry["allowed_in_game"])
        self.assertFalse(entry["needs_admin"])


if __name__ == "__main__":
    unittest.main()
