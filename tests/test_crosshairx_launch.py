"""What a launch does about the crosshair.

The switch is read on every Play, so the rules that matter are the ones about
which way it moves and when it is ignored.
"""

import tempfile
import unittest
from pathlib import Path

from cs2cfg import crosshairx, emit


class Deciding(unittest.TestCase):
    """crosshairx.decide is the whole policy, so it is tested on its own."""

    def test_switch_on_turns_the_games_crosshair_off(self):
        out = crosshairx.decide(hide=True, installed=True, up=True, starting=False)
        self.assertEqual(out["value"], crosshairx.OFF)
        self.assertTrue(out["hidden"])
        self.assertFalse(out["warning"])

    def test_switch_off_turns_it_back_on(self):
        """The half that is easy to forget. Without it, somebody who stops
        using the overlay has no crosshair and no idea why."""
        out = crosshairx.decide(hide=False, installed=True, up=True, starting=False)
        self.assertEqual(out["value"], crosshairx.ON)
        self.assertFalse(out["hidden"])

    def test_it_counts_an_overlay_we_are_about_to_start(self):
        """Not running yet, but this launch will start it, so the game should
        still stand down."""
        out = crosshairx.decide(hide=True, installed=True, up=False, starting=True)
        self.assertEqual(out["value"], crosshairx.OFF)

    def test_it_refuses_when_nothing_would_draw_a_crosshair(self):
        """Switch on, overlay not running and not being started: honouring it
        would put somebody in a match with no crosshair at all."""
        out = crosshairx.decide(hide=True, installed=True, up=False, starting=False)
        self.assertEqual(out["value"], crosshairx.ON)
        self.assertFalse(out["hidden"])
        self.assertIn("not running", out["warning"])

    def test_it_refuses_when_crosshair_x_is_not_installed(self):
        out = crosshairx.decide(hide=True, installed=False, up=False, starting=True)
        self.assertEqual(out["value"], crosshairx.ON)
        self.assertIn("not installed", out["warning"])

    def test_every_outcome_explains_itself(self):
        for hide in (True, False):
            for installed in (True, False):
                for up in (True, False):
                    for starting in (True, False):
                        out = crosshairx.decide(hide, installed, up, starting)
                        self.assertIn(out["value"], (crosshairx.ON, crosshairx.OFF))
                        self.assertTrue(out["why"].strip(),
                                        f"no reason for {(hide, installed, up, starting)}")


class TheFileItWrites(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_it_sets_only_the_crosshair(self):
        body = crosshairx.render_cfg(crosshairx.OFF, crosshairx.REASON)
        commands = [ln.split("//")[0].strip() for ln in body.splitlines()]
        commands = [c for c in commands if c]
        self.assertEqual(commands, ['crosshair "0"'])

    def test_it_carries_the_marker_so_nobody_hand_edits_it(self):
        self.assertIn(emit.GENERATED_MARKER,
                      crosshairx.render_cfg(crosshairx.ON, "because"))

    def test_it_is_not_the_generated_performance_config(self):
        """A launch must not rewrite autoperf.vcfg: that file is a whole
        performance profile, and nobody pressed Apply for it."""
        self.assertNotEqual(crosshairx.CFG_NAME, "autoperf.vcfg")

    def test_the_exec_line_says_what_it_is(self):
        autoexec = self.root / "autoexec.vcfg"
        autoexec.write_text("// mine\n", encoding="utf-8")
        emit.ensure_exec_line(autoexec, f"mrwhiteer/{crosshairx.CFG_NAME}",
                              title="Crosshair, from the Crosshair X switch (cs2-autoconfig)",
                              shout="CROSSHAIR Setting")
        text = autoexec.read_text(encoding="utf-8")
        self.assertIn(crosshairx.CFG_NAME, text)
        self.assertIn("Crosshair X switch", text)
        self.assertNotIn("AUTO-TUNED PERFORMANCE", text)

    def test_the_exec_line_is_added_once(self):
        autoexec = self.root / "autoexec.vcfg"
        autoexec.write_text("// mine\n", encoding="utf-8")
        target = f"mrwhiteer/{crosshairx.CFG_NAME}"
        emit.ensure_exec_line(autoexec, target, title="Crosshair (cs2-autoconfig)")
        emit.ensure_exec_line(autoexec, target, title="Crosshair (cs2-autoconfig)")
        self.assertEqual(autoexec.read_text(encoding="utf-8").count(target), 1)

    def test_the_performance_block_still_reads_as_it_always_did(self):
        """The heading became a parameter; its default must not have moved."""
        autoexec = self.root / "autoexec.vcfg"
        autoexec.write_text("// mine\n", encoding="utf-8")
        emit.ensure_exec_line(autoexec, "mrwhiteer/autoperf.vcfg")
        text = autoexec.read_text(encoding="utf-8")
        self.assertIn("// Auto-tuned performance settings (cs2-autoconfig)", text)
        self.assertIn('ECHO "Loading AUTO-TUNED PERFORMANCE Settings"', text)
        self.assertIn('ECHO "AUTO-TUNED PERFORMANCE Settings Loaded Successfully"', text)

    def test_revert_clears_both_blocks(self):
        """Revert predates the crosshair block, so it has to learn about it."""
        autoexec = self.root / "autoexec.vcfg"
        autoexec.write_text("// mine\n", encoding="utf-8")
        emit.ensure_exec_line(autoexec, "mrwhiteer/autoperf.vcfg")
        emit.ensure_exec_line(autoexec, f"mrwhiteer/{crosshairx.CFG_NAME}",
                              title="Crosshair, from the Crosshair X switch (cs2-autoconfig)",
                              shout="CROSSHAIR Setting")
        while emit.strip_generated_block(autoexec):
            pass
        left = autoexec.read_text(encoding="utf-8")
        self.assertNotIn("autoperf.vcfg", left)
        self.assertNotIn(crosshairx.CFG_NAME, left)
        self.assertIn("// mine", left, "revert ate the user's own file")


if __name__ == "__main__":
    unittest.main()
