"""The demo endpoints: what they write, and what they refuse.

Everything runs against a throwaway game folder with preferences stubbed out,
so no real install or saved preference is touched.
"""

import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg import demos, webui


class _Prefs:
    """A stand-in for the on-disk preferences."""

    def __init__(self):
        self.data = {"ui": {}}

    def load(self):
        return self.data

    def save(self, prefs):
        self.data = prefs


class Picking(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.install = Path(self.tmp.name) / "CS2"
        self.replays = self.install / "game" / "csgo" / "replays"
        self.cfg = self.install / "game" / "csgo" / "cfg" / "mrwhiteer"
        self.replays.mkdir(parents=True)
        self.cfg.mkdir(parents=True)
        (self.cfg / "autoexec.vcfg").write_text("// mine\n", encoding="utf-8")
        (self.replays / "faceit_0e4d6c2a_demirage.dem").write_bytes(b"x")
        self.state = types.SimpleNamespace(
            steam_root=Path(self.tmp.name), cs2_install=self.install,
            cfg_folder="mrwhiteer", demo=None, users=[],
            # _replays refreshes before answering; there is nothing to detect
            # here and detection is slow, so it is a no-op.
            refresh=lambda *a, **k: None)
        self.prefs = _Prefs()

    def tearDown(self):
        self.tmp.cleanup()

    def _pick(self, body):
        with mock.patch("cs2cfg.cli.load_prefs", self.prefs.load), \
             mock.patch("cs2cfg.cli.save_prefs", self.prefs.save):
            return webui._demo_pick(self.state, body)

    def _keyfile(self):
        return (self.cfg / webui.DEMO_CFG).read_text(encoding="utf-8")

    def _written(self):
        """The file the key execs -- where the chosen demo actually lives."""
        return (self.cfg / webui.DEMO_NOW).read_text(encoding="utf-8")

    def test_the_key_execs_the_file_holding_the_choice(self):
        """Two files on purpose: a bind is fixed when CS2 reads it, so binding
        straight to a demo would stick the key to whatever was chosen at
        startup. This way the choice can change with the game running."""
        out = self._pick({"name": "faceit_0e4d6c2a_demirage.dem", "key": "F9"})
        self.assertTrue(out["ok"])
        self.assertIn('bind "F9" "exec mrwhiteer/' + webui.DEMO_NOW + '"',
                      self._keyfile())
        self.assertIn("replays/faceit_0e4d6c2a_demirage", self._written())

    def test_choosing_another_demo_rewrites_only_the_payload(self):
        """What makes it work mid-session: the bind never moves."""
        self._pick({"name": "faceit_0e4d6c2a_demirage.dem"})
        first = self._keyfile()
        (self.replays / "faceit_11111111_denuke.dem").write_bytes(b"x")
        self._pick({"name": "faceit_11111111_denuke.dem"})
        self.assertEqual(self._keyfile(), first, "the bind should not have moved")
        self.assertIn("replays/faceit_11111111_denuke", self._written())
        self.assertNotIn("demirage", self._written())

    def test_it_remembers_the_pick(self):
        self._pick({"name": "faceit_0e4d6c2a_demirage.dem", "key": "F8"})
        self.assertEqual(self.prefs.data["ui"]["demo_pick"],
                         "faceit_0e4d6c2a_demirage.dem")
        self.assertEqual(self.prefs.data["ui"]["demo_key"], "F8")

    def test_it_links_the_file_from_the_autoexec_once(self):
        for _ in range(3):
            self._pick({"name": "faceit_0e4d6c2a_demirage.dem"})
        text = (self.cfg / "autoexec.vcfg").read_text(encoding="utf-8")
        self.assertEqual(text.count(webui.DEMO_CFG), 1)
        self.assertIn("// mine", text)

    def test_clearing_leaves_no_key_playing_last_weeks_demo(self):
        self._pick({"name": "faceit_0e4d6c2a_demirage.dem"})
        out = self._pick({"name": ""})
        self.assertTrue(out["cleared"])
        self.assertNotIn("playdemo", self._written())

    def test_a_demo_that_is_not_there_is_refused(self):
        """The name arrives from the page and ends up in a config file."""
        out = self._pick({"name": "../../../../evil.dem"})
        self.assertFalse(out["ok"])
        self.assertFalse((self.cfg / webui.DEMO_CFG).exists())

    def test_it_does_not_touch_the_generated_performance_config(self):
        perf = self.cfg / "autoperf.vcfg"
        perf.write_text("// applied earlier\n", encoding="utf-8")
        self._pick({"name": "faceit_0e4d6c2a_demirage.dem"})
        self.assertEqual(perf.read_text(encoding="utf-8"), "// applied earlier\n")


class WatchingOnLaunch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.install = Path(self.tmp.name) / "CS2"
        self.replays = self.install / "game" / "csgo" / "replays"
        self.replays.mkdir(parents=True)
        (self.replays / "faceit_0e4d6c2a_demirage.dem").write_bytes(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_arguments_go_through_applaunch_not_the_url(self):
        """steam://rungameid accepts the URL and silently drops everything
        after the app id, so launching "into" a demo that way started the game
        and left it in the menu. -applaunch is the documented way to pass a
        command line, and it is the only one that works."""
        from cs2cfg import launcher

        extra = "+" + demos.play_command("faceit_0e4d6c2a_demirage.dem").replace('"', "")
        self.assertEqual(extra, "+playdemo replays/faceit_0e4d6c2a_demirage")

        fake = Path(self.tmp.name) / "steam.exe"
        fake.write_text("", encoding="utf-8")
        with mock.patch.object(launcher, "steam_exe", return_value=fake), \
             mock.patch.object(launcher.subprocess, "Popen") as run:
            launcher.launch_via_steam(extra)
        argv = run.call_args[0][0]
        self.assertEqual(argv[1:], ["-applaunch", launcher.APP_ID,
                                    "+playdemo", "replays/faceit_0e4d6c2a_demirage"])

    def test_the_demo_path_survives_as_one_argument(self):
        """Split wrongly, "+playdemo" and the path become separate tokens or
        the path loses its tail, and the game opens on the menu again."""
        from cs2cfg import launcher

        fake = Path(self.tmp.name) / "steam.exe"
        fake.write_text("", encoding="utf-8")
        with mock.patch.object(launcher, "steam_exe", return_value=fake), \
             mock.patch.object(launcher.subprocess, "Popen") as run:
            launcher.launch_via_steam("+playdemo replays/faceit_ab997f74_dedust2")
        argv = run.call_args[0][0]
        self.assertEqual(argv[-1], "replays/faceit_ab997f74_dedust2")

    def test_a_plain_launch_still_goes_through_the_url(self):
        """No arguments, no need for Steam's path -- the URL starts Steam
        itself if it is closed."""
        from cs2cfg import launcher

        with mock.patch.object(launcher.os, "startfile") as opened:
            launcher.launch_via_steam("")
        self.assertEqual(opened.call_args[0][0], launcher.STEAM_RUN_URL)

    def test_a_missing_steam_exe_still_launches_the_game(self):
        """Without the demo beats not starting at all."""
        from cs2cfg import launcher

        with mock.patch.object(launcher, "steam_exe", return_value=None), \
             mock.patch.object(launcher.os, "startfile") as opened:
            launcher.launch_via_steam("+playdemo replays/x")
        self.assertEqual(opened.call_args[0][0], launcher.STEAM_RUN_URL)

    def test_only_a_demo_that_exists_can_be_launched_into(self):
        listed = {d["name"] for d in demos.installed(self.replays)}
        self.assertIn("faceit_0e4d6c2a_demirage.dem", listed)
        self.assertNotIn("../../evil.dem", listed)


if __name__ == "__main__":
    unittest.main()


class TheKeyDoesNotLinger(unittest.TestCase):
    """Watch binds the demo as a fallback for that one launch. A key that
    silently loads last week's match three sessions later is worse than no
    key, so the next ordinary launch clears it -- while a bind asked for
    deliberately is left alone."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.install = Path(self.tmp.name) / "CS2"
        self.replays = self.install / "game" / "csgo" / "replays"
        self.cfg = self.install / "game" / "csgo" / "cfg" / "mrwhiteer"
        self.replays.mkdir(parents=True)
        self.cfg.mkdir(parents=True)
        (self.cfg / "autoexec.vcfg").write_text("// mine\n", encoding="utf-8")
        (self.replays / "faceit_0e4d6c2a_demirage.dem").write_bytes(b"x")
        self.state = types.SimpleNamespace(
            steam_root=Path(self.tmp.name), cs2_install=self.install,
            cfg_folder="mrwhiteer", demo=None, users=[],
            refresh=lambda *a, **k: None)
        self.prefs = _Prefs()

    def tearDown(self):
        self.tmp.cleanup()

    def _with_prefs(self, fn):
        with mock.patch("cs2cfg.cli.load_prefs", self.prefs.load), \
             mock.patch("cs2cfg.cli.save_prefs", self.prefs.save):
            return fn()

    def _pick(self, **body):
        body.setdefault("name", "faceit_0e4d6c2a_demirage.dem")
        return self._with_prefs(lambda: webui._demo_pick(self.state, body))

    def _launch(self, watching):
        return self._with_prefs(lambda: webui._settle_demo(self.state, watching))

    def _bind(self):
        """The payload: what the key would actually play."""
        return (self.cfg / webui.DEMO_NOW).read_text(encoding="utf-8")

    def test_a_watch_bind_is_gone_by_the_next_launch(self):
        self._pick(once=True)
        self.assertIn("playdemo", self._bind())
        self.assertTrue(self._launch(watching=False))
        self.assertNotIn("playdemo", self._bind())

    def test_it_survives_the_launch_it_was_made_for(self):
        """Cleared before the next launch, not after the one it serves."""
        self._pick(once=True)
        self.assertFalse(self._launch(watching=True))
        self.assertIn("playdemo", self._bind())

    def test_a_deliberate_bind_is_left_alone(self):
        self._pick(once=False)
        self.assertFalse(self._launch(watching=False))
        self.assertIn("playdemo", self._bind())

    def test_clearing_happens_once_and_then_stops(self):
        self._pick(once=True)
        self.assertTrue(self._launch(watching=False))
        self.assertFalse(self._launch(watching=False))

    def test_the_remembered_pick_is_dropped_too(self):
        self._pick(once=True)
        self._launch(watching=False)
        from cs2cfg import profiles

        # Read it back the way the application does, rather than guessing
        # which half of the preferences it landed in.
        ui = profiles.ui_for(self.prefs.data, webui._active_account(self.state))
        self.assertFalse(ui.get("demo_pick"))
        self.assertFalse(ui.get("demo_once"))

    def test_the_players_own_autoexec_is_not_touched(self):
        self._pick(once=True)
        self._launch(watching=False)
        self.assertIn("// mine",
                      (self.cfg / "autoexec.vcfg").read_text(encoding="utf-8"))

    def test_a_missing_install_does_not_raise(self):
        self._pick(once=True)
        self.state.cs2_install = None
        self._launch(watching=False)   # must not raise
