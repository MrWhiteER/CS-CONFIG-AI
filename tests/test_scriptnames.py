"""Plain-word names for the user's own scripts in the key picker.

The picker used to show a block's banner ("RIFLES", "CUSTOM MATCH CONTROL")
as the name of whatever alias happened to sort first in it. These check that
each alias is now named for what it does, and that a block of shortcuts
offers every shortcut, not just one.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cfgscan, commands, scriptnames  # noqa: E402

CONFIG = """\
// --------------------------
// RIFLES
// --------------------------
alias "!ak" "buy ak47; give weapon_ak47"   // AK-47
alias "!m4s" "buy m4a1_silencer; give weapon_m4a1_silencer"

// --------------------------
// GENERAL COMMAND ALIASES
// --------------------------
alias "!dc" "disconnect"
alias "!gg" "say GG everyone"
alias "!help" "echo nothing"   // CUSTOM TEXT {BUTTON - NUM-DEL}
alias "shield" "ui_vanitysetting_loadoutslot_t heavy5"  // Equip shield in menu

// --------------------------
// CUSTOM MATCH CONTROL
// --------------------------
alias "1pause" "mp_pause_match; say Paused; alias matchpause 2pause"
alias "2pause" "mp_unpause_match; say Live; alias matchpause 1pause"
alias "matchpause" "1pause"

// --------------------------
// Game Volume
// --------------------------
alias "!vol_off" "volume 0; echo off; alias !vol !vol_on"
alias "!vol_on" "volume 1; echo on; alias !vol !vol_off"
alias "!vol" "!vol_off"

// --------------------------
// ALIASES / CUSTOM ACTIONS
// --------------------------
alias "+fast" "host_timescale 20"
alias "-fast" "host_timescale 1"

// --------------------------
// MAPS
// --------------------------
alias "mirage" "map de_mirage"
"""


class Names(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cfg = Path(cls.tmp.name) / "cfg"
        cfg.mkdir()
        (cfg / "autoexec.cfg").write_text(CONFIG, encoding="utf-8")
        commands._cache = None
        scan = cfgscan.scan(cfg)
        group = commands._script_group(scan)
        cls.labels = {c["command"]: c["label"] for c in group["commands"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        commands._cache = None

    def test_a_buy_alias_names_the_weapon(self):
        self.assertEqual(self.labels["!ak"], "Buy AK-47")

    def test_every_shortcut_in_a_block_is_offered(self):
        """Not only the first one the banner happened to sit over."""
        self.assertEqual(self.labels["!m4s"], "Buy M4A1-S")

    def test_no_banner_is_used_as_a_name(self):
        for label in self.labels.values():
            self.assertNotIn(label, ("RIFLES", "GENERAL COMMAND ALIASES",
                                     "CUSTOM MATCH CONTROL",
                                     "ALIASES / CUSTOM ACTIONS", "MAPS"))

    def test_a_toggle_is_named_for_both_halves(self):
        self.assertEqual(self.labels["matchpause"], "Pause / unpause the match")

    def test_an_on_off_setting_reads_as_on_off(self):
        self.assertEqual(self.labels["!vol"], "Game sound on/off")

    def test_engine_commands_and_chat(self):
        self.assertEqual(self.labels["!dc"], "Leave the server")
        self.assertEqual(self.labels["!gg"], "Say in chat: “GG everyone”")

    def test_a_map_shortcut_names_the_map(self):
        self.assertEqual(self.labels["mirage"], "Load map Mirage")

    def test_the_authors_note_is_used_when_nothing_else_says_it(self):
        self.assertEqual(self.labels["shield"], "Equip shield in menu")

    def test_a_note_about_keys_is_not_used_as_a_name(self):
        self.assertNotIn("BUTTON", self.labels["!help"])

    def test_a_hold_under_a_filing_banner_is_described(self):
        self.assertEqual(self.labels["+fast"], "Speed up the game ×20")


class Pieces(unittest.TestCase):
    def test_shouting_titles_become_sentence_case(self):
        self.assertEqual(scriptnames.readable_title("Anti-AFK Script"), "Anti-AFK")
        self.assertEqual(scriptnames.readable_title("GAME VOLUME"), "Game volume")

    def test_filing_titles_are_recognised(self):
        self.assertTrue(scriptnames.is_filing_title("ALIASES / CUSTOM ACTIONS"))
        self.assertTrue(scriptnames.is_filing_title("GENERAL COMMAND ALIASES"))
        self.assertFalse(scriptnames.is_filing_title("Game Volume"))

    def test_an_unknown_command_is_not_guessed_at(self):
        self.assertIsNone(scriptnames.describe_body("r_aoproxy_show 1", {}))


class Catalogue(unittest.TestCase):
    def test_weapon_slots_say_what_they_hold(self):
        commands._cache = None
        labels = {c["command"]: c["label"]
                  for g in commands.catalogue()["groups"] for c in g["commands"]}
        self.assertEqual(labels["slot2"], "Secondary (pistol)")
        self.assertEqual(labels["slot3"], "Knife")
        self.assertEqual(labels["slot8"], "Smoke grenade")
        self.assertEqual(labels["+attack"], "Shoot")


if __name__ == "__main__":
    unittest.main()
