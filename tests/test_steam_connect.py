"""One Steam connection: Steam's website and the app's cloud, signed in together.

The accounts dock shows a single Steam row. Connecting it opens one Steam
window; when the app's cloud is not signed in yet, that window is Steam's
OpenID page, which signs both in at once. Cloud sync then needs nothing from
the player. Nothing here reaches the network or opens a window.
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cloud, cloudconfig, steamweb, webui  # noqa: E402


def _state():
    return types.SimpleNamespace(refresh=lambda *a, **k: None)


class Connecting(unittest.TestCase):
    def setUp(self):
        self.marks = {}
        patches = [
            mock.patch.object(steamweb, "window_factory", object()),
            mock.patch.object(steamweb, "mark",
                              side_effect=lambda update=None: self.marks.update(update or {}) or dict(self.marks)),
            mock.patch.object(cloudconfig, "configured", return_value=True),
            mock.patch.object(webui, "_steam_hooks"),
            mock.patch.object(webui, "_cloud_claim_later"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_no_cloud_yet_opens_steams_openid_page_once(self):
        """One window signs in Steam's website and the cloud together."""
        started = {"state": "S", "verifier": "V", "url": "https://steamcommunity.com/openid/login?x"}
        with mock.patch.object(cloud, "signed_in", return_value=False), \
             mock.patch.object(cloud, "begin_login", return_value=started), \
             mock.patch.object(steamweb, "sign_in", return_value=True) as sign_in:
            out = webui._steam_connect(_state(), {})
        self.assertTrue(out["ok"])
        self.assertTrue(out["opened"])
        sign_in.assert_called_once_with(started["url"])
        webui._cloud_claim_later.assert_called_once()
        self.assertNotIn("verifier", out)

    def test_cloud_signed_in_but_no_steam_website_shows_steams_login(self):
        with mock.patch.object(cloud, "signed_in", return_value=True), \
             mock.patch.object(steamweb, "sign_in", return_value=True) as sign_in:
            self.marks["linked"] = False
            out = webui._steam_connect(_state(), {})
        self.assertTrue(out["opened"])
        sign_in.assert_called_once_with()

    def test_already_connected_opens_nothing(self):
        self.marks["linked"] = True
        with mock.patch.object(cloud, "signed_in", return_value=True), \
             mock.patch.object(steamweb, "sign_in") as sign_in:
            out = webui._steam_connect(_state(), {})
        self.assertTrue(out["ok"])
        self.assertFalse(out["opened"])
        sign_in.assert_not_called()
        self.assertTrue(out["connection"]["connected"])

    def test_a_browser_tab_says_so_in_plain_words(self):
        with mock.patch.object(steamweb, "window_factory", None):
            out = webui._steam_connect(_state(), {})
        self.assertFalse(out["ok"])
        self.assertIn("app's own window", out["error"])


class CloudWithNothingToDo(unittest.TestCase):
    def setUp(self):
        self.marks = {"linked": True}
        patches = [
            mock.patch.object(steamweb, "window_factory", object()),
            mock.patch.object(steamweb, "mark",
                              side_effect=lambda update=None: self.marks.update(update or {}) or dict(self.marks)),
            mock.patch.object(cloudconfig, "configured", return_value=True),
            mock.patch.object(webui.threading, "Thread"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_steam_connected_signs_the_cloud_in_quietly_once(self):
        state = _state()
        with mock.patch.object(cloud, "signed_in", return_value=False):
            webui._cloud_quietly(state)
            webui._cloud_quietly(state)
        self.assertEqual(webui.threading.Thread.call_count, 1)

    def test_not_while_steam_is_not_connected(self):
        self.marks["linked"] = False
        with mock.patch.object(cloud, "signed_in", return_value=False):
            webui._cloud_quietly(_state())
        webui.threading.Thread.assert_not_called()

    def test_not_after_signing_out_on_purpose(self):
        self.marks["cloud_off"] = True
        with mock.patch.object(cloud, "signed_in", return_value=False):
            webui._cloud_quietly(_state())
        webui.threading.Thread.assert_not_called()

    def test_not_when_already_signed_in(self):
        with mock.patch.object(cloud, "signed_in", return_value=True):
            webui._cloud_quietly(_state())
        webui.threading.Thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class ANewPcIsSetUpOnItsOwn(unittest.TestCase):
    """Edy: signing in on a friend's PC brings the whole setup and applies it."""

    def _state(self):
        return types.SimpleNamespace(overlay=mock.Mock(), rgb=mock.Mock(),
                                     refresh=lambda *a, **k: None)

    def test_overlay_and_lighting_settings_travel(self):
        from cs2cfg import autosync
        for key in ("overlay_enabled", "overlay_hotkey", "rgb_enabled", "rgb_brightness"):
            self.assertIn(key, autosync.SYNCED_PREFS)

    def test_a_pull_with_picture_choices_applies_for_this_pc(self):
        state = self._state()
        prefs = {"ui": {"cfg_write_ok": True, "overlay_enabled": True},
                 "accounts": {"1": {"intent": "competitive", "target_fps": 400}}}
        with mock.patch("cs2cfg.cli.load_prefs", return_value=prefs), \
             mock.patch.object(webui, "_active_account", return_value="1"), \
             mock.patch.object(webui, "_apply", return_value={"ok": True}) as apply:
            done = webui._after_pull(state, {"prefs": ["intent", "overlay_enabled"]})
        self.assertTrue(done["apply"])
        self.assertTrue(done["overlay"])
        body = apply.call_args[0][1]
        self.assertEqual(body["intent"], "competitive")
        self.assertEqual(body["account"], "1")
        state.overlay.configure.assert_called_once()

    def test_nothing_is_written_before_setup_allowed_it(self):
        prefs = {"ui": {}, "accounts": {"1": {"intent": "competitive"}}}
        with mock.patch("cs2cfg.cli.load_prefs", return_value=prefs), \
             mock.patch.object(webui, "_active_account", return_value="1"), \
             mock.patch.object(webui, "_apply") as apply:
            webui._after_pull(self._state(), {"prefs": ["intent"]})
        apply.assert_not_called()
