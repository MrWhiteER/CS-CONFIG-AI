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
import re
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
        """What CS2 is left with for ``key`` after the autoexec runs: follows
        the exec lines the way the game does, bind/unbind/unbindall included."""
        keys = {}

        def run(relative, depth=0):
            path = self.cfg_root / relative
            if depth > 8 or not path.is_file():
                return
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.split("//", 1)[0].strip()
                words = re.findall(r'"([^"]*)"|(\S+)', line)
                words = [a or b for a, b in words]
                if not words:
                    continue
                verb = words[0].lower()
                if verb == "exec" and len(words) > 1:
                    run(words[1].replace("\\", "/"), depth + 1)
                elif verb == "unbindall":
                    keys.clear()
                elif verb == "unbind" and len(words) > 1:
                    keys.pop(cfgscan.physical_key(words[1]), None)
                elif verb == "bind" and len(words) > 2:
                    keys[cfgscan.physical_key(words[1])] = words[2]

        run("mrwhiteer/autoexec.vcfg")
        return keys.get(cfgscan.physical_key(key))

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

    # -- switching profiles: separate keyboards ------------------------------

    def switch(self):
        answer = webui._cfg_layouts_apply(self.state, {"file": PROFILE})
        self.assertTrue(answer["ok"], answer.get("error"))
        return answer

    def test_switching_gives_exactly_the_profile_keys(self):
        before = {f: self.read(f) for f in (BINDS, IMPORTED)}
        self.switch()
        self.assertEqual(self.in_game("mwheelup"), "slot7")
        self.assertEqual(self.in_game("scancode25"), "+radialradio2")
        self.assertEqual(self.in_game("scancode8"), "+use")
        self.assertEqual(self.in_game("scancode11"), "+lookatweapon")
        # W is only on the default layout: it does not come along.
        self.assertIsNone(self.in_game("scancode26"))
        # The default layout's own files are untouched.
        self.assertEqual({f: self.read(f) for f in (BINDS, IMPORTED)}, before)

    def test_mouse_look_survives_a_profile_that_clears_it(self):
        path = self.cfg_root / PROFILE
        path.write_text(path.read_text(encoding="utf-8") + 'bind "mouse_x" ""\n', encoding="utf-8")
        binds = self.cfg_root / BINDS
        binds.write_text(binds.read_text(encoding="utf-8") + 'bind "mouse_x" "yaw"\n', encoding="utf-8")
        self.state.cfg_scan = cfgscan.scan(self.cfg_root / "mrwhiteer", cfg_root=self.cfg_root)
        self.switch()
        self.assertEqual(self.in_game("mouse_x"), "yaw")

    def test_a_key_changed_in_a_profile_stays_in_that_profile(self):
        self.switch()
        answer = webui._cfg_bind(self.state, {"code": "KeyW", "command": "+jump", "force": True})
        self.assertTrue(answer["ok"], answer.get("error"))
        self.assertEqual(answer["file"], PROFILE)
        self.assertIn('bind "scancode26" "+jump"', self.read(PROFILE))
        self.assertEqual(self.in_game("scancode26"), "+jump")
        # Default is untouched, and gets W back as it was.
        self.assertEqual(self.read(BINDS), FILES[BINDS])
        webui._cfg_layouts_default(self.state, {})
        self.assertEqual(self.in_game("scancode26"), "+forward")

    def test_the_board_shows_the_profile_while_it_is_on(self):
        self.switch()
        board = webui._cfg_keys(self.state, {})["bound"]
        self.assertEqual(board["mwheelup"]["command"], "slot7")
        self.assertNotIn("scancode26", board)

    def test_default_puts_your_own_keys_back(self):
        self.switch()
        answer = webui._cfg_layouts_default(self.state, {})
        self.assertTrue(answer["ok"], answer.get("error"))
        self.assertEqual(self.in_game("mwheelup"), "slot3; slot7")
        self.assertEqual(self.in_game("scancode25"), "switchhands")
        self.assertEqual(self.in_game("scancode8"), "+invsmoke; !health")
        self.assertEqual(self.in_game("scancode26"), "+forward")
        self.assertIsNone(self.in_game("scancode11"))

    def test_switching_twice_reports_already_active(self):
        self.switch()
        again = webui._cfg_layouts_apply(self.state, {"file": PROFILE})
        self.assertFalse(again["changed"])

    def test_the_apply_now_file_matches_the_profile(self):
        from cs2cfg import applynow

        self.switch()
        text = applynow.render(self.state.cfg_scan)
        self.assertIn('unbind "scancode26"', text)
        self.assertIn('bind "mwheelup" "slot7"', text)
        self.assertNotIn('bind "mwheelup" "slot3; slot7"', text)


if __name__ == "__main__":
    unittest.main()
