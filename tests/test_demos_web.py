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

    def _written(self):
        return (self.cfg / webui.DEMO_CFG).read_text(encoding="utf-8")

    def test_it_binds_the_demo_to_the_key(self):
        out = self._pick({"name": "faceit_0e4d6c2a_demirage.dem", "key": "F9"})
        self.assertTrue(out["ok"])
        body = self._written()
        self.assertIn('bind "F9"', body)
        self.assertIn("replays/faceit_0e4d6c2a_demirage", body)

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
        self.assertNotIn("bind", self._written())

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

    def test_the_argument_is_a_console_command_steam_can_carry(self):
        from cs2cfg import launcher

        extra = "+" + demos.play_command("faceit_0e4d6c2a_demirage.dem").replace('"', "")
        self.assertEqual(extra, "+playdemo replays/faceit_0e4d6c2a_demirage")
        url = launcher.run_url(extra)
        self.assertTrue(url.startswith(launcher.STEAM_RUN_URL + "//"))
        self.assertNotIn(" ", url, "an unescaped space would truncate the argument")

    def test_no_demo_means_the_plain_url(self):
        from cs2cfg import launcher

        self.assertEqual(launcher.run_url(""), launcher.STEAM_RUN_URL)
        self.assertEqual(launcher.run_url("   "), launcher.STEAM_RUN_URL)

    def test_only_a_demo_that_exists_can_be_launched_into(self):
        listed = {d["name"] for d in demos.installed(self.replays)}
        self.assertIn("faceit_0e4d6c2a_demirage.dem", listed)
        self.assertNotIn("../../evil.dem", listed)


if __name__ == "__main__":
    unittest.main()
