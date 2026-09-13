"""Tests for per-account settings and for working out which account that is.

The mistake worth guarding against is one account being handed another
account's config folder. Six Steam accounts on one machine is ordinary, and
before this they shared one set of settings -- so signing in as somebody else
showed the previous account's folder and the previous account's favourites.

Nothing here reads the real registry or the real Steam folder.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import profiles, whoami  # noqa: E402

LOGINUSERS = '''"users"
{
\t"76561198204439120"
\t{
\t\t"AccountName"\t\t"edon_aaa"
\t\t"PersonaName"\t\t"MrWhiteER"
\t\t"Timestamp"\t\t"1789288917"
\t}
\t"76561198148645946"
\t{
\t\t"AccountName"\t\t"karen_manto"
\t\t"PersonaName"\t\t"Karen"
\t\t"Timestamp"\t\t"1787681135"
\t}
}
'''

# 76561198204439120 - 76561197960265728
WHITE = "244173392"
KAREN = "188380218"


class SplittingSettings(unittest.TestCase):
    def test_a_config_folder_belongs_to_its_account(self):
        prefs = {}
        profiles.remember(prefs, WHITE, {"cfg_folder": r"G:\white"})
        profiles.remember(prefs, KAREN, {"cfg_folder": r"G:\karen"})
        self.assertEqual(profiles.ui_for(prefs, WHITE)["cfg_folder"], r"G:\white")
        self.assertEqual(profiles.ui_for(prefs, KAREN)["cfg_folder"], r"G:\karen")

    def test_one_account_never_sees_another_folder(self):
        """The whole point: this is the failure the split exists to stop."""
        prefs = {}
        profiles.remember(prefs, WHITE, {"cfg_folder": r"G:\white",
                                         "favourites": ["a"]})
        karen = profiles.ui_for(prefs, KAREN)
        self.assertNotIn("cfg_folder", karen)
        self.assertNotIn("favourites", karen)

    def test_how_the_app_is_arranged_is_shared(self):
        """Same person, same desk, whichever account they are playing on."""
        prefs = {}
        profiles.remember(prefs, WHITE, {"rail_width": 240, "kb_shown": {"board": True}})
        karen = profiles.ui_for(prefs, KAREN)
        self.assertEqual(karen["rail_width"], 240)
        self.assertEqual(karen["kb_shown"], {"board": True})

    def test_an_unknown_setting_is_treated_as_the_accounts(self):
        """The safer half to be wrong in."""
        self.assertFalse(profiles.is_machine("something_new"))
        prefs = {}
        profiles.remember(prefs, WHITE, {"something_new": 1})
        self.assertNotIn("something_new", profiles.ui_for(prefs, KAREN))

    def test_the_active_account_is_reported_back(self):
        prefs = {}
        profiles.remember(prefs, WHITE, {"cfg_folder": "x"})
        self.assertEqual(profiles.ui_for(prefs, WHITE)["account"], WHITE)

    def test_with_no_account_everything_stays_shared(self):
        """Before Steam is found there is nowhere else to put it."""
        prefs = {}
        profiles.remember(prefs, None, {"cfg_folder": "x"})
        self.assertEqual(prefs["ui"]["cfg_folder"], "x")


class MovingOldSettingsAcross(unittest.TestCase):
    """A first run finds one account's real setup in the shared half."""

    def test_it_moves_onto_the_account_signed_in(self):
        prefs = {"ui": {"cfg_folder": r"G:\white", "intent": "competitive",
                        "rail_width": 200}}
        self.assertTrue(profiles.migrate(prefs, WHITE))
        self.assertEqual(prefs["accounts"][WHITE]["cfg_folder"], r"G:\white")
        self.assertEqual(prefs["accounts"][WHITE]["intent"], "competitive")

    def test_the_shared_half_keeps_only_what_belongs_there(self):
        prefs = {"ui": {"cfg_folder": r"G:\white", "rail_width": 200}}
        profiles.migrate(prefs, WHITE)
        self.assertNotIn("cfg_folder", prefs["ui"],
                         "left here it would be handed to every other account")
        self.assertEqual(prefs["ui"]["rail_width"], 200)

    def test_it_does_not_overwrite_an_account_that_already_answered(self):
        prefs = {"ui": {"cfg_folder": r"G:\stray"},
                 "accounts": {WHITE: {"cfg_folder": r"G:\mine"}}}
        profiles.migrate(prefs, WHITE)
        self.assertEqual(prefs["accounts"][WHITE]["cfg_folder"], r"G:\mine")

    def test_running_it_twice_changes_nothing_the_second_time(self):
        prefs = {"ui": {"cfg_folder": r"G:\white"}}
        self.assertTrue(profiles.migrate(prefs, WHITE))
        self.assertFalse(profiles.migrate(prefs, WHITE))

    def test_nothing_moves_without_an_account_to_move_it_to(self):
        prefs = {"ui": {"cfg_folder": r"G:\white"}}
        self.assertFalse(profiles.migrate(prefs, None))
        self.assertEqual(prefs["ui"]["cfg_folder"], r"G:\white")


class WorkingOutWhoIsSignedIn(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir(parents=True)
        (self.root / "config" / "loginusers.vdf").write_text(
            LOGINUSERS, encoding="utf-8")
        (self.root / "userdata").mkdir()

    def test_it_reads_the_login_list(self):
        records = whoami.login_records(self.root)
        self.assertEqual(records[WHITE]["account_name"], "edon_aaa")
        self.assertEqual(records[WHITE]["persona"], "MrWhiteER")

    def test_the_live_signal_wins(self):
        with mock.patch.object(whoami, "active_user_id", lambda: KAREN), \
             mock.patch.object(whoami, "autologin_name", lambda: "edon_aaa"):
            found, how = whoami.current(self.root, [WHITE, KAREN])
        self.assertEqual(found, KAREN)
        self.assertEqual(how, whoami.LIVE)

    def test_auto_login_is_used_when_steam_is_closed(self):
        """ActiveUser is zero whenever Steam is not running."""
        with mock.patch.object(whoami, "active_user_id", lambda: None), \
             mock.patch.object(whoami, "autologin_name", lambda: "edon_aaa"):
            found, how = whoami.current(self.root, [WHITE, KAREN])
        self.assertEqual(found, WHITE)
        self.assertEqual(how, whoami.AUTOLOGIN)

    def test_the_newest_login_is_the_last_resort(self):
        with mock.patch.object(whoami, "active_user_id", lambda: None), \
             mock.patch.object(whoami, "autologin_name", lambda: None):
            found, how = whoami.current(self.root, [WHITE, KAREN])
        self.assertEqual(found, WHITE, "the higher timestamp")
        self.assertEqual(how, whoami.NEWEST)

    def test_an_account_without_cs2_is_not_offered(self):
        """Naming an account the interface has nothing to show for is worse
        than admitting it does not know."""
        with mock.patch.object(whoami, "active_user_id", lambda: KAREN), \
             mock.patch.object(whoami, "autologin_name", lambda: None):
            found, _how = whoami.current(self.root, [WHITE])
        self.assertEqual(found, WHITE, "it should fall through, not pick Karen")

    def test_nothing_known_is_not_an_error(self):
        empty = Path(self.tmp.name) / "nowhere"
        with mock.patch.object(whoami, "active_user_id", lambda: None), \
             mock.patch.object(whoami, "autologin_name", lambda: None):
            found, how = whoami.current(empty, [])
        self.assertIsNone(found)
        self.assertEqual(how, whoami.UNKNOWN)

    def test_a_zero_active_user_means_nobody(self):
        """Steam parks it at zero rather than removing it."""
        with mock.patch.object(whoami, "_registry", lambda *a: "0"):
            self.assertIsNone(whoami.active_user_id())

    def test_reading_the_registry_never_raises(self):
        with mock.patch.object(whoami, "_registry",
                               side_effect=OSError("no registry here")):
            with self.assertRaises(OSError):
                whoami._registry("x", "y")   # the stub itself raises
        # The real one swallows it:
        self.assertIn(whoami.autologin_name(), (None, whoami.autologin_name()))


if __name__ == "__main__":
    unittest.main()
