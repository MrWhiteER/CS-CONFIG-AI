"""Tests for giving a key back its stock bind when a script is switched off.

The defaults come from the game's own user_keys_default.vcfg, so the fixture
below is a trimmed copy of that file's shape rather than a table of guesses.
No real installation is read and nothing is written outside a temporary
directory.

The property that matters most is the round trip: switching a block off and
back on has to leave the file byte-identical. A restored bind that outlives
the script it replaced would be a bind the user never wrote.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import defaults, plugins  # noqa: E402

DEFAULTS_VCFG = '''"config"
{
\t"bindings"
\t{
\t\t"ESCAPE"\t\t"cancelselect"
\t\t"TAB"\t\t"+showscores"
\t\t"SPACE"\t\t"+jump"
\t\t"f"\t\t"+lookatweapon"
\t\t"q"\t\t"lastinv"
\t\t"r"\t\t"+reload"
\t\t"CTRL"\t\t"+duck"
\t\t"SHIFT"\t\t"+sprint"
\t\t"MOUSE1"\t\t"+attack"
\t\t"MWHEELUP"\t\t"invprev"
\t\t"F10"\t\t"cs_quit_prompt"
\t}
}
'''


class Naming(unittest.TestCase):
    """The game names keys one way; configs bind them another."""

    def test_letters_become_hid_usages(self):
        self.assertEqual(defaults.normalise("f"), "scancode9")
        self.assertEqual(defaults.normalise("a"), "scancode4")
        self.assertEqual(defaults.normalise("q"), "scancode20")

    def test_digits(self):
        self.assertEqual(defaults.normalise("1"), "scancode30")
        self.assertEqual(defaults.normalise("0"), "scancode39")

    def test_named_keys_are_case_insensitive(self):
        self.assertEqual(defaults.normalise("SPACE"), "scancode44")
        self.assertEqual(defaults.normalise("space"), "scancode44")
        self.assertEqual(defaults.normalise("CTRL"), "scancode224")
        self.assertEqual(defaults.normalise("SHIFT"), "scancode225")

    def test_function_keys(self):
        self.assertEqual(defaults.normalise("F10"), "scancode67")
        self.assertEqual(defaults.normalise("F1"), "scancode58")

    def test_mouse_passes_through(self):
        self.assertEqual(defaults.normalise("MOUSE1"), "mouse1")
        self.assertEqual(defaults.normalise("MWHEELUP"), "mwheelup")

    def test_a_scancode_is_already_in_the_right_form(self):
        self.assertEqual(defaults.normalise("scancode9"), "scancode9")


class Loading(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.install = Path(self.tmp.name)
        cfg = self.install / "game" / "csgo" / "cfg"
        cfg.mkdir(parents=True)
        (cfg / defaults.DEFAULTS_FILE).write_text(DEFAULTS_VCFG, encoding="utf-8")

    def test_reads_the_games_own_binds(self):
        table = defaults.load(self.install)
        self.assertEqual(defaults.for_key(table, "f"), "+lookatweapon")
        self.assertEqual(defaults.for_key(table, "scancode9"), "+lookatweapon")
        self.assertEqual(defaults.for_key(table, "SHIFT"), "+sprint")
        self.assertEqual(defaults.for_key(table, "mouse1"), "+attack")

    def test_a_key_the_game_does_not_bind_has_no_default(self):
        """Home is not in CS2's defaults; it must not be given an invented one."""
        table = defaults.load(self.install)
        self.assertEqual(defaults.for_key(table, "scancode74"), "")

    def test_no_install_is_not_an_error(self):
        self.assertEqual(defaults.load(None), {})
        self.assertEqual(defaults.load(Path(self.tmp.name) / "nope"), {})

    def test_a_damaged_file_is_not_an_error(self):
        path = self.install / "game" / "csgo" / "cfg" / defaults.DEFAULTS_FILE
        path.write_text('"config" { "bindings" {{{ ', encoding="utf-8")
        self.assertEqual(defaults.load(self.install), {})


BLOCK = """// ---------------------------------------------------------------
// Inspect On Fire
// ---------------------------------------------------------------
alias +inspectfire "+attack; +lookatweapon"
alias -inspectfire "-attack; -lookatweapon"
bind "scancode9" "+inspectfire"
"""


class RestoringAndRemoving(unittest.TestCase):
    def setUp(self):
        self.table = {"scancode9": "+lookatweapon", "scancode20": "lastinv"}

    def test_the_stock_bind_is_written_after_the_block(self):
        text, restored = plugins.restore_stock(BLOCK, 6, ["scancode9"], self.table)
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["command"], "+lookatweapon")
        self.assertEqual(restored[0]["label"], "F")
        lines = text.split("\n")
        self.assertIn("+lookatweapon", lines[6])
        self.assertIn(plugins.STD, lines[6])
        # The block itself is untouched by this step.
        self.assertEqual(lines[:6], BLOCK.split("\n")[:6])

    def test_a_key_with_no_default_gets_nothing(self):
        text, restored = plugins.restore_stock(BLOCK, 6, ["scancode74"], self.table)
        self.assertEqual(restored, [])
        self.assertEqual(text, BLOCK, "the file must not be touched at all")

    def test_removing_takes_back_only_the_matching_key(self):
        text, _ = plugins.restore_stock(BLOCK, 6, ["scancode9"], self.table)
        text, _ = plugins.restore_stock(text, 6, ["scancode20"], self.table)
        text, removed = plugins.drop_stock(text, ["scancode9"])
        self.assertEqual(len(removed), 1)
        self.assertIn("+lookatweapon", removed[0])
        self.assertIn("lastinv", text, "the other key's default must survive")

    def test_a_bind_the_user_wrote_is_never_removed(self):
        """Only lines this tool marked are ever taken away."""
        mine = BLOCK + 'bind "scancode9" "+lookatweapon"\n'
        text, removed = plugins.drop_stock(mine, ["scancode9"])
        self.assertEqual(removed, [])
        self.assertEqual(text, mine)

    def test_off_then_on_is_byte_identical(self):
        """The property that matters: nothing is left behind."""
        off = plugins.set_enabled(BLOCK, 1, 6, False)
        off, _ = plugins.restore_stock(off, 6, ["scancode9"], self.table)
        self.assertIn(plugins.STD, off)

        back, _ = plugins.drop_stock(off, ["scancode9"])
        back = plugins.set_enabled(back, 1, 6, True)
        self.assertEqual(back, BLOCK)

    def test_the_restored_line_is_a_real_bind_the_game_would_run(self):
        text, _ = plugins.restore_stock(BLOCK, 6, ["scancode9"], self.table)
        line = [l for l in text.split("\n") if plugins.STD in l][0]
        command = line.split(plugins.STD)[0].strip()
        self.assertTrue(command.startswith('bind "scancode9" "+lookatweapon"'),
                        f"the marker must be a trailing comment, got: {line!r}")


if __name__ == "__main__":
    unittest.main()
