"""Tests for what a key can be assigned, and what is offered.

The property worth protecting is that nothing in the catalogue is invented. A
command the engine does not have binds without complaint and then does nothing
when the key is pressed, which is indistinguishable from a broken config -- so
every entry is checked against the engine lists this collection already
validates configs against.

Nothing here reads the real game or writes anything.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cfgscan, commands  # noqa: E402


class TheCatalogue(unittest.TestCase):
    def setUp(self):
        commands._cache = None
        self.cat = commands.catalogue()

    def tearDown(self):
        commands._cache = None

    def _all(self):
        for group in self.cat["groups"]:
            for entry in group["commands"]:
                yield group, entry

    def test_every_command_is_one_the_engine_has(self):
        """The whole point: a command that does not exist fails silently."""
        known = {c.lower() for c in cfgscan.KNOWN_ENGINE_COMMANDS}
        actions = {a.lower() for a in cfgscan.KNOWN_ENGINE_ACTIONS}
        unknown = []
        for _group, entry in self._all():
            bare = entry["command"].lstrip("+-").lower()
            if bare not in known and bare not in actions:
                unknown.append(entry["command"])
        self.assertEqual(unknown, [], "not found in cfgscan's engine lists")

    def test_every_command_has_a_readable_label(self):
        for _group, entry in self._all():
            self.assertTrue(entry.get("label", "").strip(),
                            f"{entry['command']} has no label")

    def test_commands_are_not_listed_twice(self):
        seen = [e["command"].lower() for _g, e in self._all()]
        self.assertEqual(len(seen), len(set(seen)), "a command appears twice")

    def test_held_commands_are_marked_as_held(self):
        """A + command behaves differently, and the picker says so."""
        for _group, entry in self._all():
            if entry["command"].startswith("+"):
                self.assertTrue(entry.get("hold"),
                                f"{entry['command']} should be marked hold")

    def test_nothing_is_marked_held_that_is_not(self):
        for _group, entry in self._all():
            if entry.get("hold"):
                self.assertTrue(entry["command"].startswith("+"),
                                f"{entry['command']} is not a held command")

    def test_groups_have_ids_and_names(self):
        for group in self.cat["groups"]:
            self.assertTrue(group.get("id"))
            self.assertTrue(group.get("name"))

    def test_the_commands_that_act_immediately_are_flagged(self):
        """Leaving a server the moment a key is pressed deserves a warning."""
        leaving = next(g for g in self.cat["groups"] if g["id"] == "session")
        self.assertTrue(leaving.get("care"))

    def test_every_command_names_a_symbol(self):
        for _group, entry in self._all():
            self.assertTrue(entry.get("icon"),
                            f"{entry['command']} has no symbol")

    def test_every_symbol_named_has_a_drawing_in_the_page(self):
        """A symbol with no drawing silently falls back to a plain dot.

        The catalogue says which symbol a command wears and the page holds the
        drawings, so the two can drift apart without anything failing -- the
        list just quietly stops being readable.
        """
        page = (Path(__file__).resolve().parents[1] /
                "cs2cfg" / "web" / "index.html").read_text(encoding="utf-8")
        art = page[page.index("const KB_ICONS = {"):]
        art = art[:art.index("\n};")]
        undrawn = sorted({e["icon"] for _g, e in self._all()
                          if f"\n  {e['icon']}:" not in art
                          and f"\n  {e['icon']}: " not in art})
        self.assertEqual(undrawn, [], "named in the catalogue, not drawn in the page")

    def test_a_missing_catalogue_does_not_break_the_picker(self):
        commands._cache = None
        with mock.patch.object(Path, "read_text", side_effect=OSError("gone")):
            self.assertEqual(commands.catalogue()["groups"], [])


class WhatIsOffered(unittest.TestCase):
    def tearDown(self):
        commands._cache = None

    def test_a_known_command_is_recognised(self):
        self.assertTrue(commands.is_offered("+jump"))
        self.assertTrue(commands.is_offered("buymenu"))

    def test_quoting_and_case_do_not_matter(self):
        self.assertTrue(commands.is_offered('"+JUMP"'))

    def test_an_unknown_command_is_not_claimed(self):
        self.assertFalse(commands.is_offered("+definitely_not_a_command"))
        self.assertFalse(commands.is_offered(""))


class Options(unittest.TestCase):
    """What the picker is handed for one key."""

    def tearDown(self):
        commands._cache = None

    def test_it_works_with_nothing_scanned(self):
        """Opening the keyboard before scanning must not fail."""
        out = commands.options(None, "scancode26")
        self.assertEqual(out["binding"], "scancode26")
        self.assertEqual(out["label"], "W")
        self.assertIsNone(out["current"])
        self.assertTrue(out["groups"], "the engine commands are still offered")

    def test_the_stock_bind_is_separate_from_the_groups(self):
        """Putting a key back is a different kind of choice from picking."""
        with mock.patch.object(commands.defaults, "load",
                               return_value={"scancode26": "+forward"}):
            out = commands.options(None, "scancode26", cs2_install="anywhere")
        self.assertEqual(out["stock"], "+forward")
        flat = [c["command"] for g in out["groups"] for c in g["commands"]]
        self.assertIn("+forward", flat, "it is also an ordinary choice")

    def test_a_key_the_game_does_not_bind_has_no_stock(self):
        with mock.patch.object(commands.defaults, "load", return_value={}):
            out = commands.options(None, "scancode74", cs2_install="anywhere")
        self.assertEqual(out["stock"], "")

    def test_the_hold_note_is_passed_through(self):
        out = commands.options(None, "scancode26")
        self.assertIn("held", out["hold_note"])


class CurrentBinding(unittest.TestCase):
    class _Bind:
        def __init__(self, body, order, file="a.vcfg", line=1):
            self.body, self.order, self.file, self.line = body, order, file, line

    class _Scan:
        def __init__(self, binds):
            self.binds = binds

    def test_the_last_bind_to_load_is_the_one_that_counts(self):
        scan = self._Scan({"scancode26": [
            self._Bind('"+forward"', 1), self._Bind('"drop"', 9)]})
        found = commands.bound_to(scan, "scancode26")
        self.assertEqual(found["command"], "drop")
        self.assertEqual(found["shadowed"], 1, "the other one is shadowed")

    def test_an_unbound_key_reports_nothing(self):
        self.assertIsNone(commands.bound_to(self._Scan({}), "scancode26"))
        self.assertIsNone(commands.bound_to(None, "scancode26"))


if __name__ == "__main__":
    unittest.main()
