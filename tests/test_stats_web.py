"""The combined stats endpoint and CS2's stats feed, through the web handlers."""

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg import matchlog, webui

ME = "76561198000000001"  # account id 39734273


class Endpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = types.SimpleNamespace(
            stats_store=matchlog.Store(Path(self.tmp.name)),
            stats_recorder=None, stats_token="c" * 64, faceit=None)
        self.state.stats_store.add({
            "source": "cs2", "match_id": "cs2-1", "steamid": ME, "map": "de_nuke",
            "started_at": 50, "played_at": 100, "won": True, "kills": 20, "deaths": 10,
            "assists": 2, "rounds": 20, "adr": 80.0, "hs_percent": 40})
        self.faceit = {"ok": True, "linked": True, "player": {"nickname": "me"},
                       "matches": [{"match_id": "1-x", "map": "de_mirage", "played_at": 90_000,
                                    "won": False, "kills": 10, "deaths": 20, "assists": 1,
                                    "rounds": 20, "adr": 60.0, "hs_percent": 30.0}]}

    def tearDown(self):
        self.tmp.cleanup()

    def _stats(self, body):
        with mock.patch.object(webui, "_faceit", return_value=self.faceit), \
             mock.patch.object(webui, "_active_account", return_value="39734273"), \
             mock.patch("cs2cfg.steamweb.linked", return_value=False):
            return webui._stats(self.state, body)

    def test_both_sources(self):
        out = self._stats({})
        self.assertEqual([m["source"] for m in out["matches"]], ["faceit", "cs2"])
        self.assertEqual(out["counts"], {"all": 2, "faceit": 1, "cs2": 1})
        self.assertTrue(out["faceit"]["linked"])
        self.assertTrue(out["cs2"]["recording"])

    def test_filter_cs2(self):
        out = self._stats({"source": "cs2"})
        self.assertEqual([m["match_id"] for m in out["matches"]], ["cs2-1"])
        self.assertEqual(out["summary"]["kd"], 2.0)

    def test_without_faceit_linked_cs2_still_lists(self):
        self.faceit = {"ok": True, "linked": False}
        out = self._stats({})
        self.assertEqual([m["source"] for m in out["matches"]], ["cs2"])
        self.assertFalse(out["faceit"]["linked"])

    def test_steam_sign_in_without_the_app_window(self):
        from cs2cfg import steamweb
        with mock.patch.object(steamweb, "window_factory", None), \
             mock.patch.object(steamweb, "linked", return_value=False):
            out = webui._stats_steam(self.state, {"action": "signin"})
        self.assertFalse(out["ok"])
        self.assertFalse(out["available"])

    def test_steam_sign_in_opens_steam_and_reads_history_after(self):
        from cs2cfg import steamweb
        opened, started = [], []
        with mock.patch.object(steamweb, "window_factory", object()), \
             mock.patch.object(steamweb, "sign_in", side_effect=lambda url=None: opened.append(url) or True), \
             mock.patch.object(steamweb, "linked", return_value=False), \
             mock.patch.object(webui, "_steam_history_start", side_effect=lambda st: started.append(st)):
            out = webui._stats_steam(self.state, {"action": "signin"})
            self.assertTrue(out["ok"])
            self.assertEqual(opened, [None])
            steamweb.on_signed_in[0]()
        self.assertEqual(started, [self.state])

    def test_feed_reaches_the_recorder(self):
        seen = []
        self.state.stats_recorder = types.SimpleNamespace(feed=seen.append)
        raw = json.dumps({"auth": {"token": "c" * 64}, "provider": {"steamid": ME}}).encode()
        webui._stats_receive(self.state, raw)
        self.assertEqual(seen[0]["provider"], {"steamid": ME})
        with self.assertRaises(PermissionError):
            webui._stats_receive(self.state, json.dumps({"auth": {"token": "d" * 64}}).encode())


if __name__ == "__main__":
    unittest.main()
