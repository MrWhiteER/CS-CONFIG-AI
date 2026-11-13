"""Valve discovery and measurements are entirely mocked; no network traffic."""
import json
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from cs2cfg import serverping as sp, webui


CONFIG = {"pops": {
    "bom": {"desc": "Mumbai (India)", "relays": [{"ipv4": "155.133.226.68"}]},
    "bom2": {"desc": "Mumbai (India)", "relays": [{"ipv4": "185.25.183.163"}]},
    "maa": {"desc": "Chennai (India)", "relays": [{"ipv4": "185.25.183.179"}]},
    "hel": {"desc": "Helsinki (Finland)"},
    "internal": {"desc": "Private", "relays": [{"ipv4": "127.0.0.1"}]},
    "blank": {"relays": [{"ipv4": "185.25.183.163"}]},
}}


class Regions(unittest.TestCase):
    def test_groups_numbered_city_variants_and_skips_unusable_entries(self):
        rows = sp.parse_regions(CONFIG)
        self.assertEqual(len(rows), 2)
        mumbai = next(r for r in rows if r["city"] == "Mumbai")
        self.assertEqual(mumbai["country"], "India")
        self.assertEqual(mumbai["codes"], ["bom", "bom2"])
        self.assertEqual(len(mumbai["relays"]), 2)

    def test_invalid_addresses_cannot_be_used_as_ping_arguments(self):
        config = {"pops": {"x": {"desc": "City", "relays": [
            {"ipv4": "-t"}, {"ipv4": "192.168.1.2"}, None, {}]}}}
        self.assertEqual(sp.parse_regions(config), [])

    def test_empty_directory(self):
        for config in ({}, {"pops": []}, {"pops": {"x": None}}):
            self.assertEqual(sp.parse_regions(config), [])

    def test_bundled_fallback_contains_verified_dubai_relays(self):
        dubai = next(r for r in sp.parse_regions(sp.FALLBACK) if r["code"] == "dxb")
        self.assertEqual(len(dubai["relays"]), 2)
        self.assertEqual(dubai["country"], "United Arab Emirates")


class Measurements(unittest.TestCase):
    def setUp(self):
        self.region = next(r for r in sp.parse_regions(CONFIG) if r["code"] == "bom")
        self.region.pop("pop_relays")  # exercise a single POP's backup relay

    @patch.object(sp.netcheck, "_ping_once", side_effect=[20, 100, 21])
    def test_uses_median_not_mean(self, ping):
        result = sp.measure(self.region)
        self.assertEqual(result["ping_ms"], 21)
        self.assertEqual(result["loss"], 0)
        self.assertEqual(result["relays_tried"], 1)
        self.assertEqual(ping.call_count, 3)

    @patch.object(sp.netcheck, "_ping_once", side_effect=[None]*3+[30, None, 40])
    def test_second_relay_and_loss(self, ping):
        result = sp.measure(self.region)
        self.assertEqual(result["ping_ms"], 35)
        self.assertEqual(result["loss"], 66.7)
        self.assertEqual(result["relays_tried"], 2)
        self.assertEqual(result["status"], "bad")

    @patch.object(sp.netcheck, "_ping_once", return_value=None)
    def test_icmp_silence_is_unknown_not_down(self, ping):
        result = sp.measure(self.region)
        self.assertIsNone(result["ping_ms"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["loss"], 100)

    @patch.object(sp.netcheck, "_run", return_value="Reply: bytes=32 temps=18ms TTL=57")
    def test_reuses_localized_ping_parser(self, run):
        self.assertEqual(sp.measure(self.region)["ping_ms"], 18)

    def test_status_boundaries(self):
        for value, expected in ((0,"good"),(30,"good"),(31,"ok"),(90,"ok"),(91,"bad"),(None,"unknown")):
            self.assertEqual(sp.classify(value), expected)
        self.assertEqual(sp.classify(10, 33), "bad")
        self.assertEqual(sp.classify(10, 100), "unknown")

    @patch.object(sp.netcheck, "_ping_once", side_effect=[80, 81, 79, 20, 21, 19])
    def test_city_shows_best_numbered_pop_median(self, ping):
        region = next(r for r in sp.parse_regions(CONFIG) if r["code"] == "bom")
        result = sp.measure(region)
        self.assertEqual(result["ping_ms"], 20)
        self.assertEqual(result["relays_tried"], 2)

    def test_continuous_color_stops(self):
        self.assertEqual(sp.color_stop(-1), (0,0))
        self.assertEqual(sp.color_stop(45), (0,.5))
        self.assertEqual(sp.color_stop(110), (2,.5))
        self.assertEqual(sp.color_stop(1000), (4,0))
        self.assertIsNone(sp.color_stop(None))


class CachedSurvey(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "sdr.json"
        self.survey = sp.ServerPing(self.path)

    def response(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(CONFIG).encode()
        return response

    def test_daily_cache_survives_new_instance(self):
        with patch.object(sp, "urlopen", return_value=self.response()) as fetch:
            self.assertEqual(self.survey._regions()[1], "live")
            self.assertEqual(self.survey._regions()[1], "cache")
            self.assertEqual(sp.ServerPing(self.path)._regions()[1], "cache")
        self.assertEqual(fetch.call_count, 1)

    def test_stale_cache_is_used_if_valve_unavailable(self):
        self.path.write_text(json.dumps({"checked_at": 1, "config": CONFIG}))
        with patch.object(sp, "urlopen", side_effect=OSError("offline")) as fetch:
            self.assertEqual(self.survey._regions()[0], sp.parse_regions(CONFIG))
            self.survey._regions()
        self.assertEqual(fetch.call_count, 1)

    def test_corrupt_cache_and_invalid_response_use_fallback(self):
        self.path.write_text("not json")
        with patch.object(sp, "urlopen", return_value=self.response()) as fetch:
            fetch.return_value.__enter__.return_value.read.return_value = b'{}'
            rows, source, error = self.survey._regions()
        self.assertEqual(rows, sp.parse_regions(sp.FALLBACK))
        self.assertEqual(source, "fallback")
        self.assertTrue(error)

    def test_async_start_coalesces_and_progress_finishes(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        def regions():
            entered.set()
            release.wait(3)
            return sp.parse_regions(CONFIG), "live", ""
        original = self.survey._sweep
        def sweep():
            try:
                original()
            finally:
                finished.set()
        with patch.object(self.survey, "_regions", side_effect=regions) as load, \
             patch.object(self.survey, "_sweep", side_effect=sweep), \
             patch.object(sp.netcheck, "_ping_once", return_value=22):
            self.assertTrue(self.survey.start()["running"])
            self.assertTrue(entered.wait(2))
            self.assertTrue(self.survey.start()["running"])
            release.set()
            self.assertTrue(finished.wait(3))
        result = self.survey.snapshot()
        self.assertEqual(load.call_count, 1)
        self.assertFalse(result["running"])
        self.assertEqual(result["completed"], result["total"])
        self.assertTrue(result["updated_at"])
        result["regions"].clear()
        self.assertEqual(len(self.survey.snapshot()["regions"]), 2)

    def test_failure_releases_running_flag(self):
        self.survey.data["running"] = True
        with patch.object(self.survey, "_regions", side_effect=RuntimeError("test")):
            self.survey._sweep()
        self.assertFalse(self.survey.snapshot()["running"])
        self.assertIn("test", self.survey.snapshot()["error"])

    def test_optional_limit_is_read_only_and_handles_missing_file(self):
        self.assertIsNone(sp.read_max_ping(self.path))
        content = '"convars" { "mm_dedicated_search_maxping" "28" }'
        self.path.write_text(content)
        self.assertEqual(sp.read_max_ping(self.path), 28)
        self.assertEqual(self.path.read_text(), content)


class Api(unittest.TestCase):
    def handler(self, path, token="test-token"):
        import io
        from unittest.mock import MagicMock
        state = types.SimpleNamespace(server_ping=None, token="test-token", lock=threading.Lock())
        handler_type = webui.make_handler(state)
        handler = handler_type.__new__(handler_type)
        handler.path = path
        handler.headers = {"Host": "127.0.0.1:8765", "X-CS2CFG-Token": token,
                           "Content-Length": "2"}
        handler.rfile = io.BytesIO(b"{}")
        handler._send_json = MagicMock()
        return handler

    def test_http_get_returns_idle_snapshot_without_traffic(self):
        handler = self.handler("/api/servers/ping")
        with patch.object(sp, "urlopen") as fetch, patch.object(sp.netcheck, "_ping_once") as ping:
            handler.do_GET()
        payload = handler._send_json.call_args.args[0]
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["running"])
        fetch.assert_not_called()
        ping.assert_not_called()

    def test_http_post_start_uses_existing_token_protection(self):
        with patch.object(webui, "_servers_ping_start") as start:
            handler = self.handler("/api/servers/ping/start", token="wrong")
            handler.do_POST()
        start.assert_not_called()
        self.assertEqual(handler._send_json.call_args.args[1], 403)

    def test_http_post_start_routes_to_survey(self):
        with patch.object(webui, "_servers_ping_start", return_value={"running": True}) as start:
            handler = self.handler("/api/servers/ping/start")
            handler.do_POST()
        start.assert_called_once()
        self.assertEqual(handler._send_json.call_args.args[0], {"ok": True, "running": True})

    def test_get_does_not_start_a_sweep_or_write_cache(self):
        state = types.SimpleNamespace(server_ping=None)
        with patch.object(sp, "ServerPing") as factory:
            result = webui._servers_ping(state, {})
        factory.assert_not_called()
        self.assertFalse(result["running"])
        self.assertEqual(result["regions"], [])

    def test_start_and_snapshot_include_optional_limit(self):
        from unittest.mock import MagicMock
        survey = MagicMock()
        survey.snapshot.return_value = {"running": True, "regions": [], "updated_at": None}
        user = types.SimpleNamespace(video_cfg=Path("unused/cs2_video.txt"))
        state = types.SimpleNamespace(server_ping=survey, user_for=lambda _:user)
        with patch.object(webui, "_active_account", return_value=None), \
             patch.object(sp, "read_max_ping", return_value=28):
            result = webui._servers_ping_start(state, {})
        survey.start.assert_called_once()
        self.assertEqual(result["max_ping"], 28)
        self.assertEqual(result["preferred_code"], "dxb")


if __name__ == "__main__":
    unittest.main()
