"""Tests for spotting a toggle that can lose track of itself.

A toggle keeps its state in an alias it rewrites each press. That is only ever
as good as its starting assumption. A state that sets an absolute value makes
itself true whatever came before; a state that flips whatever is there assumes
it already knows, and nothing ever corrects it.

The case that matters most: re-exec'ing a config mid-session puts the alias
back to its first state while leaving the game's setting where it was. From
then on the key says one thing and does the other, and pressing it again flips
both together, so it never recovers.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cfgscan, plugins  # noqa: E402


def block(title: str, body: str) -> str:
    return (f"// --------------------------\n// {title}\n"
            f"// --------------------------\n{body}\n")


# Flips a setting and never states one: the alias is the only record.
FLIPPER = block("Voice Toggle", '''\
alias "!vc_off" "toggle_voice; echo muted; alias !vc !vc_on"
alias "!vc_on"  "toggle_voice; echo unmuted; alias !vc !vc_off"
alias "!vc" "!vc_off"
bind "scancode230" "!vc"
''')

# Sets a value each time, so it is true whatever came before.
ANCHORED = block("Game Volume", '''\
alias "!gv_off" "volume 0; echo off; alias !gv !gv_on"
alias "!gv_on"  "volume 1; echo on; alias !gv !gv_off"
alias "!gv" "!gv_off"
bind "scancode62" "!gv"
''')

# Flips, but also sets something absolute, which re-establishes the assumption.
BOTH = block("Mixed", '''\
alias "!mx_off" "toggle_voice; voice_scale 0; alias !mx !mx_on"
alias "!mx_on"  "toggle_voice; voice_scale 1; alias !mx !mx_off"
alias "!mx" "!mx_off"
''')

# Says things only. Nothing to drift away from.
TALKER = block("Troll Text", '''\
alias "t1" "say one; alias t t2"
alias "t2" "say two; alias t t1"
alias "t" "t1"
''')


class SpottingDrift(unittest.TestCase):
    def _find(self, text: str, name: str):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        (folder / "scripts.vcfg").write_text(text, encoding="utf-8")
        scan = cfgscan.scan(folder)
        found = next((p for p in plugins.find(scan) if p.name == name), None)
        self.assertIsNotNone(found, f"{name} was not found at all")
        return found

    def test_a_toggle_that_only_flips_is_flagged(self):
        found = self._find(FLIPPER, "Voice Toggle")
        self.assertTrue(found.drifts)
        self.assertIn("toggle_voice", found.flips)
        self.assertEqual(found.anchors, [])

    def test_a_toggle_that_sets_a_value_is_not(self):
        found = self._find(ANCHORED, "Game Volume")
        self.assertFalse(found.drifts)
        self.assertEqual(found.flips, [])
        self.assertIn("volume", found.anchors)

    def test_flipping_and_setting_together_is_not_drift(self):
        """The absolute part re-establishes what the flip assumed."""
        found = self._find(BOTH, "Mixed")
        self.assertTrue(found.flips, "it does flip")
        self.assertTrue(found.anchors, "but it also sets")
        self.assertFalse(found.drifts)

    def test_a_script_that_only_talks_is_not_flagged(self):
        """Nothing it does can fall out of step, because it changes nothing."""
        found = self._find(TALKER, "Troll Text")
        self.assertFalse(found.drifts)

    def test_the_flipped_command_is_named_in_full(self):
        """"toggle" alone says nothing; the reader needs what it toggles."""
        text = block("Loopback", '''\
alias "!lb_off" "toggle voice_loopback; alias !lb !lb_on"
alias "!lb_on"  "toggle voice_loopback; alias !lb !lb_off"
alias "!lb" "!lb_off"
''')
        found = self._find(text, "Loopback")
        self.assertTrue(found.drifts)
        self.assertIn("toggle voice_loopback", found.flips)

    def test_incrementvar_counts_as_flipping(self):
        """It steps from wherever the value happens to be."""
        text = block("Step", '''\
alias "s1" "incrementvar volume 0 1 0.1; alias s s2"
alias "s2" "incrementvar volume 0 1 0.1; alias s s1"
alias "s" "s1"
''')
        self.assertTrue(self._find(text, "Step").drifts)

    def test_an_ordinary_command_is_not_a_toggle(self):
        """A one-shot has no state to lose track of."""
        text = block("Drop", 'alias "!d" "drop"\nbind "scancode7" "!d"\n')
        found = self._find(text, "Drop")
        self.assertFalse(found.drifts)


if __name__ == "__main__":
    unittest.main()
