"""GSI and visibility checks; all writes stay inside TemporaryDirectory."""

import json
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from cs2cfg import profiles, webui
from cs2cfg.overlay import capture, gsi, settings
from cs2cfg.overlay.service import OverlayService

TOKEN = "a" * 64


def payload(**parts):
    return json.dumps({"auth": {"token": TOKEN}, **parts}).encode()


def live(phase="live", health=100, map_phase="live", player="local"):
    return gsi.parse_payload(payload(provider={"steamid": "local", "appid": 730},
        map={"phase": map_phase}, round={"phase": phase},
        player={"steamid": player, "state": {"health": health}}), TOKEN)


class GsiParsing(unittest.TestCase):
    def test_only_requested_components_are_retained(self):
        result = gsi.parse_payload(payload(provider={"steamid": "1", "appid": 730, "secret": 1},
            map={"name": "de_mirage", "phase": "live", "team_ct": {}}, round={"phase": "live"},
            player={"steamid": "1", "activity": "playing", "weapons": {"x": 1},
                    "state": {"health": 100, "money": 5000}}, bomb="planted", allplayers={}), TOKEN)
        self.assertEqual(set(result), set(gsi.COMPONENTS))
        self.assertEqual(result["player_state"], {"health": 100})
        self.assertNotIn("team_ct", result["map"])
        self.assertNotIn("secret", result["provider"])

    def test_auth_requires_exact_string_secret(self):
        for auth in (None, {}, [], {"token": "wrong"}, {"token": 1}, {"token": "é"}, {"token": "\ud800"}):
            with self.subTest(auth=auth), self.assertRaises(PermissionError):
                gsi.parse_payload(json.dumps({"auth": auth}).encode(), TOKEN)
        with mock.patch.object(gsi.hmac, "compare_digest", wraps=gsi.hmac.compare_digest) as compare:
            gsi.parse_payload(payload(), TOKEN)
        compare.assert_called_once()
        with self.assertRaises(PermissionError):
            gsi.parse_payload(payload(), "")

    def test_body_limit_and_malformed_json(self):
        for raw in (b"x" * (gsi.MAX_BODY + 1), b"{", b"\xff", b"[]", b"null"):
            with self.subTest(raw=raw[:10]), self.assertRaises(ValueError):
                gsi.parse_payload(raw, TOKEN)

    def test_wrong_component_shapes_are_missing(self):
        result = gsi.parse_payload(payload(provider=[], map="live", round=None, player=[]), TOKEN)
        self.assertTrue(all(v == {} for v in result.values()))


class GsiFiles(unittest.TestCase):
    def test_write_and_remove_only_owned_cfg(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            folder = install / "game" / "csgo" / "cfg"
            folder.mkdir(parents=True)
            other = folder / "other.cfg"
            other.write_bytes(b"unchanged")
            path = gsi.write_cfg(install, 18765, TOKEN)
            text = path.read_text()
            self.assertIn('http://127.0.0.1:18765/api/overlay/gsi', text)
            self.assertIn(TOKEN, text)
            for component in gsi.COMPONENTS:
                self.assertIn(f'"{component}" "1"', text)
            self.assertEqual(text.count('"1"'), 5)
            gsi.remove_cfg(install)
            gsi.remove_cfg(install)
            self.assertEqual(list(folder.iterdir()), [other])
            self.assertEqual(other.read_bytes(), b"unchanged")

    def test_token_is_random_per_install_and_persistent(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            token = gsi.install_token(Path(a))
            self.assertEqual(len(token), 64)
            self.assertEqual(gsi.install_token(Path(a)), token)
            self.assertNotEqual(gsi.install_token(Path(b)), token)

    def test_missing_game_folder_is_not_created(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(OSError):
            gsi.write_cfg(Path(tmp), 8765, TOKEN)
        for token in ('"bad', "x" * 64):
            with self.assertRaises(ValueError):
                gsi.write_cfg(Path("unused"), 8765, token)

    def test_enable_disable_lifecycle_without_game_or_real_app_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "install"
            folder = install / "game" / "csgo" / "cfg"
            folder.mkdir(parents=True)
            service = OverlayService()
            service.bind_gsi(install, 18888)
            with (mock.patch("cs2cfg.paths.user_data_dir", return_value=Path(tmp) / "data"),
                  mock.patch("cs2cfg.overlay.service.threading.Thread") as thread,
                  mock.patch("cs2cfg.telemetry.subscribe", return_value=lambda: None)):
                thread.return_value.is_alive.return_value = True
                self.assertFalse((folder / gsi.CFG_NAME).exists())
                service.configure(settings.read({"overlay_enabled": True}))
                self.assertTrue((folder / gsi.CFG_NAME).exists())
                with mock.patch("cs2cfg.overlay.service.write_cfg") as write:
                    service.configure(settings.read({"overlay_enabled": True, "overlay_corner": "top_right"}))
                write.assert_not_called()
                thread.return_value.is_alive.return_value = False
                service.configure(settings.read())
                self.assertFalse((folder / gsi.CFG_NAME).exists())
                self.assertEqual(service._gsi_token, "")

    def test_off_does_not_resolve_install_or_create_token(self):
        service = OverlayService()
        resolve = mock.Mock()
        service.bind_gsi(resolve, 8765)
        with mock.patch("cs2cfg.overlay.service.install_token") as token:
            service.configure(settings.read())
            service.stop()
        resolve.assert_not_called()
        token.assert_not_called()


class AutoHideState(unittest.TestCase):
    def setUp(self):
        self.state = gsi.AutoHide()

    def test_live_alive_hidden_and_transition_to_freeze_shows(self):
        self.state.update(live(), now=10)
        self.assertFalse(self.state.visible(now=10))
        self.state.update(live("freezetime"), now=11)
        self.assertTrue(self.state.visible(now=11))
        self.state.update(live(), now=12)
        self.assertFalse(self.state.visible(now=12))

    def test_warmup_round_over_dead_and_gameover_show(self):
        for state in (live(map_phase="warmup"), live("over"), live(health=0), live(map_phase="gameover")):
            with self.subTest(state=state):
                self.state.update(state, now=10)
                self.assertTrue(self.state.visible(now=10))

    def test_dead_local_spectating_alive_player_shows(self):
        self.state.update(live(player="spectated"), now=10)
        self.assertTrue(self.state.visible(now=10))

    def test_unknown_stale_and_removed_state_hide(self):
        self.assertFalse(self.state.visible(now=10))
        self.state.update(live("freezetime"), now=10)
        self.assertFalse(self.state.visible(now=26))
        self.state.update({}, now=27)
        self.assertFalse(self.state.visible(now=27))

    def test_always_visible_and_disabled_auto_hide_override_unknown_state(self):
        self.assertTrue(self.state.visible(always_visible=True))
        self.assertTrue(self.state.visible(auto_hide=False))

    def test_service_applies_state_and_rejects_posts_while_disabled(self):
        service = OverlayService()
        service._gsi_token = TOKEN
        with self.assertRaises(PermissionError):
            service.receive_gsi(payload())
        service._settings["overlay_enabled"] = True
        service._hud = mock.Mock()
        service.receive_gsi(payload(round={"phase": "freezetime"}))
        self.assertTrue(service._hud.configure.call_args.kwargs["auto_visible"])
        service.receive_gsi(payload(round={"phase": "live"}, player={"state": {"health": 100}}))
        self.assertFalse(service._hud.configure.call_args.kwargs["auto_visible"])


class CaptureSettings(unittest.TestCase):
    def test_defaults_and_machine_scope(self):
        defaults = settings.read()
        self.assertFalse(defaults["overlay_enabled"])
        self.assertFalse(defaults["overlay_always_visible"])
        for key in ("overlay_auto_hide", "overlay_hide_from_capture"):
            self.assertTrue(defaults[key])
            self.assertIn(key, profiles.MACHINE_KEYS)
            with self.assertRaises(ValueError):
                settings.read({key: "yes"}, strict=True)

    def test_capture_affinity_enable_disable_and_silent_failure(self):
        user = mock.Mock()
        with mock.patch.object(capture.ctypes, "WinDLL", return_value=user, create=True):
            capture.set_capture_exclusion(123, True)
            capture.set_capture_exclusion(123, False)
        self.assertEqual(user.SetWindowDisplayAffinity.call_args_list, [mock.call(123, 0x11), mock.call(123, 0)])
        with mock.patch.object(capture.ctypes, "WinDLL", side_effect=OSError, create=True):
            capture.set_capture_exclusion(123, True)

    def test_panel_uses_its_own_native_handle(self):
        from cs2cfg.overlay.panel import Panel
        service = OverlayService()
        panel = Panel(service, mock.Mock())
        panel.window, panel._loaded = mock.Mock(), True
        with mock.patch("cs2cfg.overlay.panel.configure_panel") as configure:
            panel.configure_capture()
            configure.assert_called_once_with(panel.window, True)
            service._settings["overlay_hide_from_capture"] = False
            panel.configure_capture()
            configure.assert_called_with(panel.window, False)


class GsiHttp(unittest.TestCase):
    def setUp(self):
        self.service = OverlayService()
        self.service._settings["overlay_enabled"] = True
        self.service._gsi_token = TOKEN
        state = types.SimpleNamespace(overlay=self.service)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), webui.make_handler(state))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def post(self, raw, **headers):
        request = urllib.request.Request(f"http://127.0.0.1:{self.server.server_port}/api/overlay/gsi",
            data=raw, headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status
        except urllib.error.HTTPError as response:
            return response.code

    def test_gsi_auth_is_independent_of_browser_header(self):
        self.assertEqual(self.post(payload(round={"phase": "freezetime"})), 200)
        self.assertTrue(self.service._game_state.visible())
        self.assertEqual(self.post(b'{"auth":{"token":"wrong"}}'), 403)

    def test_size_json_host_and_disabled_gates(self):
        self.assertEqual(self.post(b"x" * (gsi.MAX_BODY + 1)), 413)
        self.assertEqual(self.post(b"{"), 400)
        self.assertEqual(self.post(payload(), Host="evil.example"), 403)
        self.service._settings["overlay_enabled"] = False
        self.assertEqual(self.post(payload()), 403)


if __name__ == "__main__":
    unittest.main()
