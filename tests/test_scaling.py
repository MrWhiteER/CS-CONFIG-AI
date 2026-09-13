"""Tests for the setting that decides whether a stretch fills the screen.

A stretched resolution is a narrow desktop mode scaled back out by the GPU. The
scale is the driver's job, and on "aspect ratio" it keeps the shape instead of
filling, which puts a black bar down each side. The mode switch cannot tell:
Windows reports the desktop as 1550 wide either way, so nothing downstream
notices that half the panel is unlit.

Changing it means writing to the driver's display configuration, so what these
pin is mostly restraint -- that the write is validated first, that a rejected
or un-committed change leaves the configuration exactly as the driver handed it
over, and that a display which is already right is not written to at all.

No test here calls NVAPI. The driver layer is stubbed throughout.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import scaling  # noqa: E402


def screen(scale=scaling.FULL_SCREEN, primary=True, display_id=0x80061082):
    return scaling.Screen(display_id=display_id, scaling=scale,
                          width=2560, height=1440, primary=primary, refresh=240)


class FakeConfig:
    """Stands in for a live driver session.

    ``values`` is the mutable store a real ``_Config`` keeps in driver-filled
    memory, so a test can check what was left behind after a failed write.
    """

    def __init__(self, screens, reject=False, reject_commit=False):
        self._screens = screens
        self.values = {s.display_id: s.scaling for s in screens}
        self.reject = reject
        # Validation passes and the commit fails. A separate case because the
        # two failures leave through different branches, and a fake that fails
        # both only ever exercises the first.
        self.reject_commit = reject_commit
        self.applied = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def screens(self):
        return [scaling.Screen(s.display_id, self.values[s.display_id], s.width,
                               s.height, s.primary, s.refresh) for s in self._screens]

    def _explain(self, code):
        return f"driver said {code}"

    def apply(self, flags):
        self.applied.append(flags)
        if self.reject:
            return -1
        if self.reject_commit and flags != scaling.VALIDATE_ONLY:
            return -1
        return 0

    # The real method, bound to this stand-in, so the logic under test is the
    # shipped one rather than a copy.
    def _field(self, display_id):
        store = self.values

        class Words:
            def __getitem__(self, _index):
                return store[display_id]

            def __setitem__(self, _index, value):
                store[display_id] = value

        return Words() if display_id in store else None

    set_scaling = scaling._Config.set_scaling


class ReadingIt(unittest.TestCase):
    def test_full_screen_fills_and_aspect_does_not(self):
        self.assertTrue(screen(scaling.FULL_SCREEN).fills)
        self.assertFalse(screen(scaling.ASPECT).fills)
        self.assertTrue(screen(scaling.ASPECT).bars)

    def test_the_names_match_what_the_control_panel_calls_them(self):
        self.assertEqual(screen(scaling.ASPECT).name, "aspect ratio")
        self.assertEqual(screen(scaling.FULL_SCREEN).name, "full-screen")

    def test_an_untouched_display_is_not_accused_of_anything(self):
        """"Driver default" says the display has no override, not that it is
        wrong. Reporting it as letterboxed would be claiming to know something
        this cannot read."""
        found = screen(scaling.DEFAULT)
        self.assertFalse(found.fills)
        self.assertFalse(found.bars)

    def test_all_fill_needs_every_screen_not_just_the_primary(self):
        report = scaling.Report(True, screens=[
            screen(scaling.FULL_SCREEN, primary=True),
            screen(scaling.ASPECT, primary=False, display_id=0x80061080),
        ])
        self.assertFalse(report.all_fill)
        self.assertEqual(report.primary.display_id, 0x80061082)

    def test_no_driver_is_reported_rather_than_raised(self):
        with mock.patch.object(scaling, "_Config",
                               side_effect=scaling.ScalingError("no NVIDIA driver")):
            report = scaling.read()
        self.assertFalse(report.available)
        self.assertIn("no NVIDIA driver", report.reason)
        self.assertEqual(report.screens, [])


class ChangingIt(unittest.TestCase):
    def _with(self, screens, reject=False, reject_commit=False):
        fake = FakeConfig(screens, reject, reject_commit)
        patch = mock.patch.object(scaling, "_Config", return_value=fake)
        patch.start()
        self.addCleanup(patch.stop)
        return fake

    def test_a_display_that_already_fills_is_never_written_to(self):
        fake = self._with([screen(scaling.FULL_SCREEN)])
        result = scaling.ensure_fill(apply=True)
        self.assertTrue(result["ok"])
        self.assertFalse(result["changed"])
        self.assertTrue(result["already"])
        self.assertEqual(fake.applied, [], "nothing should have been applied")

    def test_a_letterboxed_display_is_validated_then_applied(self):
        fake = self._with([screen(scaling.ASPECT)])
        result = scaling.ensure_fill(apply=True)
        self.assertTrue(result["changed"])
        self.assertEqual(result["previous"], scaling.ASPECT)
        self.assertEqual(fake.values[0x80061082], scaling.FULL_SCREEN)
        # Validated before committing, exactly like set_mode's CDS_TEST probe.
        self.assertEqual(fake.applied, [scaling.VALIDATE_ONLY, 0])

    def test_the_previous_value_comes_back_so_it_can_be_put_back(self):
        self._with([screen(scaling.ASPECT)])
        result = scaling.ensure_fill(apply=True)
        self.assertEqual(result["previous"], scaling.ASPECT)
        self.assertEqual(result["was"], "aspect ratio")

    def test_without_apply_nothing_is_committed(self):
        fake = self._with([screen(scaling.ASPECT)])
        result = scaling.ensure_fill(apply=False)
        self.assertTrue(result["ok"])
        self.assertFalse(result["changed"])
        self.assertTrue(result["validated"])
        self.assertEqual(fake.applied, [scaling.VALIDATE_ONLY])
        self.assertEqual(fake.values[0x80061082], scaling.ASPECT,
                         "a validate-only call must leave the field alone")

    def test_a_change_the_driver_will_not_validate_is_rolled_back(self):
        """The field is edited in the driver's own buffer, so a write that does
        not go through has to put it back or the next read reports a setting
        that was never applied."""
        fake = self._with([screen(scaling.ASPECT)], reject=True)
        result = scaling.ensure_fill(apply=True)
        self.assertFalse(result["ok"])
        self.assertFalse(result["changed"])
        self.assertEqual(fake.values[0x80061082], scaling.ASPECT)
        self.assertEqual(fake.applied, [scaling.VALIDATE_ONLY],
                         "a failed validation must not go on to commit")

    def test_a_change_that_validates_but_fails_to_commit_is_rolled_back(self):
        """The harder half: the driver accepted the value and then refused to
        apply it, so the buffer is holding a change that never took effect."""
        fake = self._with([screen(scaling.ASPECT)], reject_commit=True)
        result = scaling.ensure_fill(apply=True)
        self.assertFalse(result["ok"])
        self.assertFalse(result["changed"])
        self.assertEqual(fake.applied, [scaling.VALIDATE_ONLY, 0],
                         "it should have got as far as committing")
        self.assertEqual(fake.values[0x80061082], scaling.ASPECT)

    def test_persisting_is_asked_for_explicitly(self):
        fake = self._with([screen(scaling.ASPECT)])
        scaling.ensure_fill(apply=True, persist=True)
        self.assertEqual(fake.applied,
                         [scaling.VALIDATE_ONLY, scaling.SAVE_TO_PERSISTENCE])

    def test_the_primary_is_the_default_target(self):
        """It is the display window.set_mode switches, so it is the one CS2
        ends up on."""
        fake = self._with([
            screen(scaling.FULL_SCREEN, primary=False, display_id=0x1),
            screen(scaling.ASPECT, primary=True, display_id=0x2),
        ])
        result = scaling.ensure_fill(apply=True)
        self.assertEqual(result["display_id"], 0x2)
        self.assertEqual(fake.values[0x1], scaling.FULL_SCREEN, "left alone")

    def test_setting_the_value_it_already_has_is_a_no_op(self):
        fake = self._with([screen(scaling.ASPECT)])
        result = scaling.set_scaling(0x80061082, scaling.ASPECT, apply=True)
        self.assertTrue(result["ok"])
        self.assertFalse(result["changed"])
        self.assertEqual(fake.applied, [])

    def test_an_unknown_display_is_an_error_not_a_silent_pass(self):
        self._with([screen(scaling.ASPECT)])
        result = scaling.set_scaling(0xDEAD, scaling.FULL_SCREEN, apply=True)
        self.assertFalse(result["ok"])
        self.assertIn("0x0000DEAD", result["error"])


class InTheLaunch(unittest.TestCase):
    """What the launcher does with it, which is where it actually matters."""

    def setUp(self):
        from cs2cfg import launcher
        self.launcher = launcher
        self.said = []

    def _report(self, message, tag=""):
        self.said.append((message, tag))

    def test_a_correct_machine_is_left_alone_and_nothing_to_restore(self):
        with mock.patch.object(scaling, "ensure_fill",
                               return_value={"ok": True, "changed": False,
                                             "already": True}):
            self.assertIsNone(self.launcher._make_it_fill(self._report))

    def test_a_letterboxed_machine_is_fixed_and_remembered(self):
        with mock.patch.object(scaling, "ensure_fill",
                               return_value={"ok": True, "changed": True,
                                             "display_id": 7, "previous": scaling.ASPECT,
                                             "was": "aspect ratio"}):
            remembered = self.launcher._make_it_fill(self._report)
        self.assertEqual(remembered, (7, scaling.ASPECT))
        self.assertTrue(any("full-screen" in m for m, _ in self.said))

    def test_a_machine_with_no_nvidia_driver_still_launches(self):
        """An AMD card is not a reason to refuse to start the game."""
        with mock.patch.object(scaling, "ensure_fill",
                               return_value={"ok": False, "changed": False,
                                             "error": "no NVIDIA driver on this machine"}):
            self.assertIsNone(self.launcher._make_it_fill(self._report))
        self.assertTrue(any("black bars" in m for m, _ in self.said),
                        "it should still say how to fix it by hand")

    def test_a_driver_that_throws_does_not_stop_the_launch(self):
        with mock.patch.object(scaling, "ensure_fill",
                               side_effect=OSError("driver fell over")):
            self.assertIsNone(self.launcher._make_it_fill(self._report))


if __name__ == "__main__":
    unittest.main()
