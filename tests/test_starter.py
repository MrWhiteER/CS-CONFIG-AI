"""Tests for the config a fresh account does not have yet.

Everything in this app is built on scanning a collection of config files. On a
machine that has never had one written there is nothing to scan, which the
views reported honestly and unhelpfully: four empty tabs, and a Keyboard tab
with nowhere to put a bind. These pin the way out of that -- and, more
importantly, pin that it cannot damage a machine that already has a config.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cfgscan, starter, webui  # noqa: E402
from sandbox import redirect_backups  # noqa: E402


class Bare(unittest.TestCase):
    def setUp(self):
        redirect_backups(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = Path(tmp.name) / "cfg"
        self.cfg.mkdir(parents=True)
        self.folder = "cs2config"

    @property
    def root(self):
        return self.cfg / self.folder

    def make(self):
        return starter.create(self.cfg, self.folder)

    def scan(self):
        return cfgscan.scan(self.root)


class BuildingOne(Bare):
    def test_an_empty_machine_gets_a_collection_that_scans_clean(self):
        self.make()
        result = self.scan()
        errors = [i for i in result.issues if i.severity.name == "ERROR"]
        self.assertEqual(errors, [], "a config this app wrote must not fail its own scan")
        self.assertEqual(len(result.files), 4)

    def test_every_file_is_reachable_from_the_autoexec(self):
        """A file nothing execs never runs, so creating one without an exec
        line is creating nothing."""
        self.make()
        chain = [name for name, _depth in self.scan().exec_chain]
        for piece in starter._pieces():
            self.assertIn(f"{self.folder}/{piece.relative}", chain)

    def test_aliases_load_before_the_binds_that_name_them(self):
        chain = [n for n, _ in (self.make(), self.scan())[1].exec_chain]
        self.assertLess(chain.index(f"{self.folder}/{starter.ALIAS_FILE}"),
                        chain.index(f"{self.folder}/{starter.BINDS_FILE}"))

    def test_it_never_writes_unbindall(self):
        """The binds file starts empty. Clearing CS2's defaults in front of an
        empty binds file leaves a game where nothing moves, shoots, or opens
        the console to fix it."""
        self.make()
        for path in self.root.rglob("*.vcfg"):
            body = "\n".join(line.split("//")[0]
                             for line in path.read_text(encoding="utf-8").splitlines())
            self.assertNotIn("unbindall", body.lower(), f"{path.name} clears every bind")

    def test_running_it_twice_changes_nothing_the_second_time(self):
        self.make()
        before = {p: p.read_bytes() for p in sorted(self.root.rglob("*")) if p.is_file()}
        again = self.make()
        after = {p: p.read_bytes() for p in sorted(self.root.rglob("*")) if p.is_file()}
        self.assertEqual(again["created"], [])
        self.assertTrue(again["already"])
        self.assertEqual(before, after)


class NotTouchingWhatIsThere(Bare):
    def test_an_existing_file_is_left_exactly_as_it_was(self):
        target = self.root / starter.BINDS_FILE
        target.parent.mkdir(parents=True)
        mine = 'bind "scancode4" "+moveleft"   // mine, do not touch\n'
        target.write_text(mine, encoding="utf-8")

        created = self.make()["created"]
        self.assertNotIn(starter.BINDS_FILE, created)
        self.assertEqual(target.read_text(encoding="utf-8"), mine)

    def test_an_existing_autoexec_is_added_to_rather_than_replaced(self):
        autoexec = self.root / starter.AUTOEXEC
        autoexec.parent.mkdir(parents=True)
        autoexec.write_text('// mine\nexec "something/else.vcfg"\n', encoding="utf-8")

        self.make()
        text = autoexec.read_text(encoding="utf-8")
        self.assertIn("// mine", text, "their file survived")
        self.assertIn("something/else.vcfg", text, "their exec survived")
        for piece in starter._pieces():
            self.assertIn(piece.relative, text, "each new file got an exec line")

    def test_a_complete_collection_reports_nothing_to_do(self):
        self.make()
        self.assertTrue(starter.plan(self.cfg, self.folder).complete)


class WhatTheLaunchOptionsExec(Bare):
    def test_the_autoexec_is_the_entry_point_when_there_is_one(self):
        """Not the generated performance file. The autoexec is what execs
        everything else, so naming anything else leaves the binds unloaded."""
        self.make()
        self.assertEqual(
            starter.launch_exec_path(self.cfg, self.folder, "autoperf.vcfg"),
            f"{self.folder}\\{starter.AUTOEXEC}")

    def test_it_falls_back_to_the_generated_file_with_no_autoexec(self):
        self.assertEqual(
            starter.launch_exec_path(self.cfg, "nothing-here", "autoperf.vcfg"),
            "nothing-here\\autoperf.vcfg")


class _State:
    """Only what the bind handlers actually reach for."""

    def __init__(self, scan):
        self.cfg_scan = scan


class BindingIntoIt(Bare):
    """The point of all of it: the Keyboard tab has somewhere to write."""

    def setUp(self):
        super().setUp()
        self.make()
        self.state = _State(self.scan())

    def bind(self, binding, command, **extra):
        body = {"binding": binding, "command": command}
        body.update(extra)
        result = webui._cfg_bind(self.state, body)
        self.state.cfg_scan = self.scan()
        return result

    def test_the_very_first_bind_lands_in_the_binds_file(self):
        result = self.bind("scancode4", "+moveleft")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertTrue(result["file"].endswith(starter.BINDS_FILE))
        self.assertEqual(self.scan().binds["scancode4"][0].body, "+moveleft")

    def test_later_binds_join_the_first(self):
        self.bind("scancode4", "+moveleft")
        self.bind("mouse1", "+attack")
        binds = self.scan().binds
        self.assertEqual(set(binds), {"scancode4", "mouse1"})
        self.assertEqual({b[0].file for b in binds.values()},
                         {f"{self.folder}/{starter.BINDS_FILE}"})

    def test_rebinding_a_key_replaces_it_rather_than_adding_a_second(self):
        self.bind("scancode4", "+moveleft")
        self.bind("scancode4", "+moveright", force=True)
        entries = self.scan().binds["scancode4"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].body, "+moveright")

    def test_the_commented_examples_are_not_mistaken_for_binds(self):
        """The starter's binds file explains itself with commented bind lines.
        Reading one as a real bind would report keys nobody bound."""
        self.assertEqual(self.scan().binds, {})

class ChoosingWhereABindGoes(unittest.TestCase):
    """Which file the first bind lands in, when nothing holds one yet."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name) / "cfg" / "custom"
        self.folder.mkdir(parents=True)

    def write(self, name: str, text: str):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def chosen(self):
        return webui._first_binds_file(cfgscan.scan(self.folder))

    def test_a_generated_file_is_never_chosen(self):
        """`apply` rewrites generated files wholesale, so a bind written into
        one would vanish without explanation. There is deliberately no file
        named like a binds file here, so the choice really is between the
        generated file and the plain one."""
        from cs2cfg import emit

        # The generated file is exec'd last on purpose. The fallback otherwise
        # prefers the last file in the chain, so this is the arrangement where
        # skipping generated files is the only thing keeping it out.
        self.write("autoexec.vcfg", 'exec "custom/stuff.vcfg"\nexec "custom/perf.vcfg"\n')
        self.write("perf.vcfg", f"{emit.GENERATED_MARKER}\nfps_max 0\n")
        self.write("stuff.vcfg", "cl_crosshairsize 2\n")
        picked = self.chosen()
        self.assertIsNotNone(picked)
        self.assertNotIn("perf.vcfg", picked)

    def test_a_file_named_like_a_binds_file_wins(self):
        self.write("autoexec.vcfg", 'exec "custom/stuff.vcfg"\nexec "custom/my_binds.vcfg"\n')
        self.write("stuff.vcfg", "cl_crosshairsize 2\n")
        self.write("my_binds.vcfg", "// binds go here\n")
        self.assertIn("my_binds.vcfg", self.chosen())

    def test_with_nothing_suitable_it_says_so_instead_of_guessing(self):
        self.write("settings.vcfg", "cl_crosshairsize 2\n")
        from cs2cfg import emit
        self.write("gen.vcfg", f"{emit.GENERATED_MARKER}\nfps_max 0\n")
        # Only a generated file and one plain file; the plain one is fine.
        self.assertIn("settings.vcfg", self.chosen())


if __name__ == "__main__":
    unittest.main()
