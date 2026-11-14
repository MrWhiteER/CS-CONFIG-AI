"""The wizard and sync endpoints, driven the way the page drives them."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cloud, webui  # noqa: E402


class Endpoints(unittest.TestCase):
    def setUp(self):
        self.prefs = {"ui": {}, "accounts": {}}
        self.state = mock.Mock(steam_root=None, cs2_install=None, cfg_folder="mrwhiteer",
                               sync=None, machine=None, kb=None)
        patches = [
            mock.patch("cs2cfg.cli.load_prefs",
                       side_effect=lambda: json.loads(json.dumps(self.prefs))),
            mock.patch("cs2cfg.cli.save_prefs", side_effect=self._save),
            mock.patch.object(webui, "_active_account", return_value="244173392"),
            mock.patch.object(webui, "_audio_pin", return_value={}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _save(self, prefs):
        self.prefs = json.loads(json.dumps(prefs))

    def test_finishing_files_each_answer_in_its_own_half(self):
        out = webui._firstrun_finish(self.state, {"answers": {
            "cfg_write": True, "preset": "competitive", "theme": "pro",
            "sound": {"output": "{o}", "input": "{i}"}}})
        self.assertTrue(out["ok"])
        machine, mine = self.prefs["ui"], self.prefs["accounts"]["244173392"]
        self.assertTrue(machine["firstrun_done"])
        self.assertTrue(machine["cfg_write_ok"])
        self.assertEqual(machine["audio_output"], "{o}")
        self.assertEqual(mine["intent"], "competitive")
        self.assertEqual(mine["theme"], "pro")
        webui._audio_pin.assert_called_once()

    def test_a_pc_that_is_not_signed_in_never_touches_steam_to_sync(self):
        with mock.patch.object(cloud, "signed_in", return_value=False):
            out = webui._sync_round(self.state)
        self.assertFalse(out["ok"])
        self.state.refresh.assert_not_called()

    def test_sync_can_be_switched_off(self):
        webui._sync_auto(self.state, {"on": False})
        self.assertIs(self.prefs["ui"]["sync_auto"], False)
        self.assertFalse(webui._sync_status(self.state, {})["auto"])


if __name__ == "__main__":
    unittest.main()
