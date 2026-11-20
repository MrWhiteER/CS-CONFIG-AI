"""Key changes made in the app have to be the ones CS2 actually loads.

Found on a real setup (Nov 20): the Keyboard tab and the profile switcher
changed files, but nothing changed in the game.

* The autoexec ran ``key_binds.vcfg`` and then ``imported.vcfg``. The first
  binds ``scancode8``, the second binds ``"e"`` -- one key to CS2 ("Interpreting
  bind command as: bind scancode8"), so the later one wins. The app counted them
  as two keys and edited the one that loses.
* A match profile that binds the same key was treated as the winner, so the
  Keyboard tab wrote the change into the profile file, which CS2 does not load
  at launch.
* Switching to a profile only changed keys the standard layout already bound
  under the very same spelling; every other key the profile sets was skipped.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cfgscan, webui  # noqa: E402
from sandbox import redirect_backups, redirect_layouts  # noqa: E402

FILES = {
    "mrwhiteer/autoexec.vcfg": (
        'unbindall\n'
        'exec "mrwhiteer/tools/alias.vcfg"\n'
        'exec "mrwhiteer/mainsettings/key_binds.vcfg"\n'
        'exec "mrwhiteer/mainsettings/imported.vcfg"\n'
    ),
    "mrwhiteer/tools/alias.vcfg": (
        'alias "!train" "exec mrwhiteer/lan/training.vcfg"\n'
    ),
    "mrwhiteer/mainsettings/key_binds.vcfg": (
        'bind "scancode26" "+forward"\n'
        'bind "scancode8" "+use"                 // USE {BUTTON - E}\n'
        'bind "mwheelup" "slot3; slot7"\n'
        'bind "scancode25" "switchhands"\n'
    ),
    "mrwhiteer/mainsettings/imported.vcfg": (
        'bind "e" "+invsmoke; !health"\n'
    ),
    "mrwhiteer/lan/training.vcfg": (
        'bind "mwheelup" "slot7"\n'
        'bind "scancode8" "+use"\n'
        'bind "scancode25" "+radialradio2"\n'
        'bind "scancode11" "+lookatweapon"\n'
        'bind "scancode99" ""\n'
    ),
}

BINDS = "mrwhiteer/mainsettings/key_binds.vcfg"
IMPORTED = "mrwhiteer/mainsettings/imported.vcfg"
PROFILE = "mrwhiteer/lan/training.vcfg"


class KeyboardReachesGame(unittest.TestCase):
    def setUp(self):
        redirect_backups(self)
        redirect_layouts(self)
        sandbox = Path(tempfile.mkdtemp(prefix="cs2cfg-kb-game-"))
        self.addCleanup(shutil.rmtree, sandbox, ignore_errors=True)
        self.cfg_root = sandbox / "cfg"
        for relative, text in FILES.items():
            path = self.cfg_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.state = mock.Mock()
        self.state.cfg_scan = cfgscan.scan(self.cfg_root / "mrwhiteer", cfg_root=self.cfg_root)
        self.state.cs2_install = None

    def read(self, relative):
        return (self.cfg_root / relative).read_text(encoding="utf-8")

    def in_game(self, key):
        """What CS2 is left with for ``key`` after the autoexec runs."""
        result = cfgscan.scan(self.cfg_root / "mrwhiteer", cfg_root=self.cfg_root)
        winner = cfgscan.startup_bind(result, cfgscan.startup_chain(result), key)
        return winner.body if winner else None

    # -- the Keyboard tab ----------------------------------------------------

    def test_e_spelled_two_ways_is_one_key(self):
        self.assertEqual(self.in_game("scancode8"), "+invsmoke; !health")
        answer = webui._cfg_bind(self.state, {"code": "KeyE", "command": "+use", "force": True})
        self.assertTrue(answer["ok"], answer.get("error"))
        # The line that wins was changed, so the game gets +use.
        self.assertEqual(answer["file"], IMPORTED)
        self.assertIn('bind "e" "+use"', self.read(IMPORTED))
        self.assertEqual(self.in_game("scancode8"), "+use")

    def test_a_change_never_lands_in_a_match_profile(self):
        answer = webui._cfg_bind(self.state, {"code": "mwheelup", "command": "slot8", "force": True})
        self.assertTrue(answer["ok"], answer.get("error"))
        self.assertEqual(answer["file"], BINDS)
        self.assertIn('bind "mwheelup" "slot8"', self.read(BINDS))
        self.assertEqual(self.read(PROFILE), FILES[PROFILE])
        self.assertEqual(self.in_game("mwheelup"), "slot8")

    def test_a_key_only_a_profile_binds_is_added_to_startup(self):
        answer = webui._cfg_bind(self.state, {"code": "KeyH", "command": "+jump", "force": True})
        self.assertTrue(answer["ok"], answer.get("error"))
        self.assertEqual(answer["file"], BINDS)
        self.assertEqual(self.in_game("scancode11"), "+jump")
        self.assertEqual(self.read(PROFILE), FILES[PROFILE])

    def test_clearing_takes_away_every_spelling(self):
        answer = webui._cfg_bind(self.state, {"code": "KeyE", "unbind": True, "force": True})
        self.assertTrue(answer["ok"], answer.get("error"))
        self.assertIsNone(self.in_game("scancode8"))

    def test_the_board_shows_what_the_game_runs(self):
        board = webui._cfg_keys(self.state, {})["bound"]
        self.assertEqual(board["scancode8"]["command"], "+invsmoke; !health")
        self.assertEqual(board["mwheelup"]["command"], "slot3; slot7")
        # Only the profile binds H; until it is switched to, H is free.
        self.assertNotIn("scancode11", board)

    # -- switching profiles --------------------------------------------------

    def test_switching_changes_every_key_the_profile_sets(self):
        answer = webui._cfg_layouts_apply(self.state, {"file": PROFILE})
        self.assertTrue(answer["ok"], answer.get("error"))
        self.assertEqual(self.in_game("mwheelup"), "slot7")
        self.assertEqual(self.in_game("scancode25"), "+radialradio2")
        self.assertEqual(self.in_game("scancode8"), "+use")       # was "e" in imported
        self.assertEqual(self.in_game("scancode11"), "+lookatweapon")  # newly added
        self.assertIsNone(self.in_game("scancode99"))              # empty bind: not added
        self.assertEqual(self.read(PROFILE), FILES[PROFILE])

    def test_default_puts_everything_back(self):
        webui._cfg_layouts_apply(self.state, {"file": PROFILE})
        answer = webui._cfg_layouts_default(self.state, {})
        self.assertTrue(answer["ok"], answer.get("error"))
        self.assertEqual(self.in_game("mwheelup"), "slot3; slot7")
        self.assertEqual(self.in_game("scancode25"), "switchhands")
        self.assertEqual(self.in_game("scancode8"), "+invsmoke; !health")
        self.assertEqual(self.in_game("scancode11"), "")             # unbound again

    def test_switching_twice_reports_already_active(self):
        webui._cfg_layouts_apply(self.state, {"file": PROFILE})
        again = webui._cfg_layouts_apply(self.state, {"file": PROFILE})
        self.assertFalse(again["changed"])


if __name__ == "__main__":
    unittest.main()
