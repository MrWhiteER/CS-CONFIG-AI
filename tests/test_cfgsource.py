"""Tests for choosing a config, and for converting a .cfg to .vcfg.

The mistake worth guarding against is rewriting a file CS2 owns. The game and
the user both write ``.vcfg`` and they are not the same format -- the game's
are KeyValues, the user's are lines of console commands -- so the extension
proves nothing and a file has to be classified by reading it.

Everything here works in a temporary directory.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cfgsource  # noqa: E402

CONSOLE = """// my settings
unbindall
bind "scancode26" "+forward"
alias +inspectfire "+attack; +lookatweapon"
"""

# The shape CS2 writes for itself, as in cfg/user_keys_default.vcfg.
KEYVALUES = '''"config"
{
\t"bindings"
\t{
\t\t"SPACE"\t\t"+jump"
\t}
}
'''


class TellingTheFormatsApart(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_console_script_is_recognised(self):
        self.assertEqual(cfgsource.looks_like(self._write("a.cfg", CONSOLE)),
                         cfgsource.SCRIPT)

    def test_the_games_own_format_is_recognised(self):
        self.assertEqual(cfgsource.looks_like(self._write("b.vcfg", KEYVALUES)),
                         cfgsource.KEYVALUES)

    def test_the_extension_is_not_the_evidence(self):
        """A .vcfg holding a console script is still a console script.

        This is the normal case for the configs people write: the user's own
        .vcfg files are lines of commands, not KeyValues.
        """
        self.assertEqual(cfgsource.looks_like(self._write("c.vcfg", CONSOLE)),
                         cfgsource.SCRIPT)

    def test_an_empty_file_is_neither(self):
        self.assertEqual(cfgsource.looks_like(self._write("d.cfg", "   \n")),
                         cfgsource.EMPTY)

    def test_comments_alone_do_not_make_it_keyvalues(self):
        self.assertEqual(
            cfgsource.looks_like(self._write("e.cfg", '// "config" {\nbind x y\n')),
            cfgsource.SCRIPT)

    def test_a_missing_file_is_not_an_error(self):
        self.assertEqual(cfgsource.looks_like(self.dir / "nope.cfg"),
                         cfgsource.UNKNOWN)


class Converting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_it_copies_and_keeps_the_original(self):
        source = self._write("autoexec.cfg", CONSOLE)
        made = cfgsource.convert(source)
        self.assertEqual(made.name, "autoexec.vcfg")
        self.assertTrue(source.exists(), "the original must stay")
        self.assertEqual(made.read_text(encoding="utf-8"), CONSOLE)

    def test_it_refuses_a_file_the_game_owns(self):
        """The damage this exists to prevent."""
        source = self._write("user_keys_default.cfg", KEYVALUES)
        with self.assertRaisesRegex(ValueError, "not ours to rewrite"):
            cfgsource.convert(source)
        self.assertTrue(source.exists())

    def test_it_refuses_to_clobber_an_existing_vcfg(self):
        self._write("autoexec.cfg", CONSOLE)
        self._write("autoexec.vcfg", "something already here\n")
        with self.assertRaises(FileExistsError):
            cfgsource.convert(self.dir / "autoexec.cfg")
        self.assertEqual((self.dir / "autoexec.vcfg").read_text(encoding="utf-8"),
                         "something already here\n")

    def test_overwriting_is_possible_but_has_to_be_asked_for(self):
        self._write("autoexec.cfg", CONSOLE)
        self._write("autoexec.vcfg", "old\n")
        cfgsource.convert(self.dir / "autoexec.cfg", overwrite=True)
        self.assertEqual((self.dir / "autoexec.vcfg").read_text(encoding="utf-8"),
                         CONSOLE)

    def test_converting_a_vcfg_is_refused(self):
        source = self._write("already.vcfg", CONSOLE)
        with self.assertRaisesRegex(ValueError, "not a .cfg"):
            cfgsource.convert(source)

    def test_convertible_says_which_ones_are_worth_offering(self):
        self._write("good.cfg", CONSOLE)
        self._write("theirs.cfg", KEYVALUES)
        self._write("done.vcfg", CONSOLE)
        self.assertTrue(cfgsource.convertible(self.dir / "good.cfg"))
        self.assertFalse(cfgsource.convertible(self.dir / "theirs.cfg"))
        self.assertFalse(cfgsource.convertible(self.dir / "done.vcfg"))


class PointingAtAConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        (self.dir / "autoexec.vcfg").write_text(CONSOLE, encoding="utf-8")
        (self.dir / "scripts.vcfg").write_text(CONSOLE, encoding="utf-8")

    def test_a_file_names_its_folder_and_is_kept_as_the_entry(self):
        found = cfgsource.resolve(str(self.dir / "autoexec.vcfg"))
        self.assertEqual(Path(found["folder"]), self.dir)
        self.assertEqual(found["entry"], "autoexec.vcfg")
        self.assertEqual(found["error"], "")

    def test_a_folder_has_its_entry_guessed(self):
        found = cfgsource.resolve(str(self.dir))
        self.assertEqual(Path(found["folder"]), self.dir)
        self.assertEqual(found["entry"], "autoexec.vcfg")

    def test_a_folder_with_no_autoexec_gets_no_invented_entry(self):
        (self.dir / "autoexec.vcfg").unlink()
        found = cfgsource.resolve(str(self.dir))
        self.assertIsNone(found["entry"],
                          "picking one anyway would be a guess dressed up")

    def test_a_file_that_is_not_a_config_still_gives_the_folder(self):
        (self.dir / "notes.txt").write_text("hello", encoding="utf-8")
        found = cfgsource.resolve(str(self.dir / "notes.txt"))
        self.assertEqual(Path(found["folder"]), self.dir)
        self.assertIn("not a .cfg or .vcfg", found["error"])
        self.assertEqual(found["entry"], "autoexec.vcfg")

    def test_a_path_that_is_not_there_says_so(self):
        found = cfgsource.resolve(str(self.dir / "gone" / "x.vcfg"))
        self.assertFalse(found["exists"])
        self.assertIn("nothing at", found["error"])

    def test_nothing_given_is_not_a_crash(self):
        self.assertIn("nothing given", cfgsource.resolve("")["error"])

    def test_quotes_round_a_pasted_path_are_ignored(self):
        found = cfgsource.resolve(f'"{self.dir}"')
        self.assertEqual(Path(found["folder"]), self.dir)


AUTOEXEC = '''// ---------------------------------------------
// Exec Settings and VCFG
// ---------------------------------------------

unbindall

exec "mrwhiteer/tools/alias.vcfg"

exec "mrwhiteer/tools/scripts.vcfg"

host_writeconfig
'''


class MakingSureItRuns(unittest.TestCase):
    """A file nothing execs never runs, so creating one without this is
    creating nothing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)          # stands in for cfg/
        self.mine = self.root / "mrwhiteer"
        (self.mine / "tools").mkdir(parents=True)
        self.autoexec = self.mine / "autoexec.vcfg"
        self.autoexec.write_text(AUTOEXEC, encoding="utf-8")

    def _lines(self):
        return self.autoexec.read_text(encoding="utf-8").split("\n")

    def test_a_new_file_gets_an_exec_line(self):
        made = self.mine / "tools" / "extra.vcfg"
        made.write_text("bind x y\n", encoding="utf-8")
        out = cfgsource.ensure_exec(self.autoexec, self.root, made)
        self.assertTrue(out["changed"])
        self.assertEqual(out["action"], "added")
        self.assertIn('exec "mrwhiteer/tools/extra.vcfg"',
                      self.autoexec.read_text(encoding="utf-8"))

    def test_the_path_is_written_the_way_real_configs_write_it(self):
        made = self.mine / "tools" / "extra.vcfg"
        made.write_text("x\n", encoding="utf-8")
        out = cfgsource.ensure_exec(self.autoexec, self.root, made)
        self.assertEqual(out["target"], "mrwhiteer/tools/extra.vcfg",
                         "relative to cfg/, forward slashes, extension kept")

    def test_it_sits_with_the_other_execs(self):
        made = self.mine / "tools" / "extra.vcfg"
        made.write_text("x\n", encoding="utf-8")
        cfgsource.ensure_exec(self.autoexec, self.root, made)
        lines = self._lines()
        added = next(i for i, l in enumerate(lines) if "extra.vcfg" in l)
        last_other = max(i for i, l in enumerate(lines) if "scripts.vcfg" in l)
        self.assertEqual(added, last_other + 1)

    def test_a_conversion_rewrites_the_old_line_instead_of_adding_one(self):
        """Otherwise the same commands run twice: once from the .cfg and
        once from the .vcfg beside it."""
        self.autoexec.write_text(
            AUTOEXEC.replace("tools/scripts.vcfg", "tools/scripts.cfg"),
            encoding="utf-8")
        old = self.mine / "tools" / "scripts.cfg"
        new = self.mine / "tools" / "scripts.vcfg"
        for f in (old, new):
            f.write_text("x\n", encoding="utf-8")

        out = cfgsource.ensure_exec(self.autoexec, self.root, new, replaced=old)
        text = self.autoexec.read_text(encoding="utf-8")
        self.assertEqual(out["action"], "pointed at the new file")
        self.assertIn('exec "mrwhiteer/tools/scripts.vcfg"', text)
        self.assertNotIn("scripts.cfg", text, "it must not run both")
        self.assertEqual(text.count("scripts.vcfg"), 1)

    def test_it_does_not_add_a_line_that_is_already_there(self):
        made = self.mine / "tools" / "scripts.vcfg"
        made.write_text("x\n", encoding="utf-8")
        out = cfgsource.ensure_exec(self.autoexec, self.root, made)
        self.assertFalse(out["changed"])
        self.assertEqual(out["action"], "already there")
        self.assertEqual(
            self.autoexec.read_text(encoding="utf-8").count("scripts.vcfg"), 1)

    def test_a_commented_out_exec_does_not_count_as_present(self):
        self.autoexec.write_text(
            AUTOEXEC + '// exec "mrwhiteer/tools/extra.vcfg"\n', encoding="utf-8")
        made = self.mine / "tools" / "extra.vcfg"
        made.write_text("x\n", encoding="utf-8")
        out = cfgsource.ensure_exec(self.autoexec, self.root, made)
        self.assertTrue(out["changed"], "a switched-off line does not run it")

    def test_line_endings_survive(self):
        """Configs here keep whatever endings they had."""
        self.autoexec.write_bytes(AUTOEXEC.replace("\n", "\r\n").encode("utf-8"))
        made = self.mine / "tools" / "extra.vcfg"
        made.write_text("x\n", encoding="utf-8")
        cfgsource.ensure_exec(self.autoexec, self.root, made)
        raw = self.autoexec.read_bytes()
        self.assertNotIn(b"\r\r", raw)
        self.assertGreater(raw.count(b"\r\n"), 5)

    def test_no_autoexec_is_reported_rather_than_guessed_at(self):
        self.autoexec.unlink()
        made = self.mine / "x.vcfg"
        made.write_text("x\n", encoding="utf-8")
        out = cfgsource.ensure_exec(self.autoexec, self.root, made)
        self.assertFalse(out["changed"])
        self.assertIn("no autoexec", out["action"])


class SurveyingAFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        (self.dir / "autoexec.cfg").write_text(CONSOLE, encoding="utf-8")
        (self.dir / "binds.vcfg").write_text(CONSOLE, encoding="utf-8")
        (self.dir / "theirs.vcfg").write_text(KEYVALUES, encoding="utf-8")
        (self.dir / "notes.txt").write_text("ignore me", encoding="utf-8")

    def test_it_lists_configs_and_ignores_everything_else(self):
        names = [f["name"] for f in cfgsource.survey(self.dir)]
        self.assertIn("autoexec.cfg", names)
        self.assertIn("binds.vcfg", names)
        self.assertNotIn("notes.txt", names)

    def test_the_ones_needing_a_decision_come_first(self):
        found = cfgsource.survey(self.dir)
        self.assertTrue(found[0]["convertible"])
        self.assertEqual(found[0]["name"], "autoexec.cfg")

    def test_a_games_own_file_is_listed_but_not_offered(self):
        found = {f["name"]: f for f in cfgsource.survey(self.dir)}
        self.assertEqual(found["theirs.vcfg"]["kind"], cfgsource.KEYVALUES)
        self.assertFalse(found["theirs.vcfg"]["convertible"])

    def test_it_says_when_a_conversion_already_exists(self):
        (self.dir / "autoexec.vcfg").write_text(CONSOLE, encoding="utf-8")
        found = {f["name"]: f for f in cfgsource.survey(self.dir)}
        self.assertEqual(found["autoexec.cfg"]["already"], "autoexec.vcfg")

    def test_a_missing_folder_is_not_an_error(self):
        self.assertEqual(cfgsource.survey(self.dir / "nope"), [])


if __name__ == "__main__":
    unittest.main()
