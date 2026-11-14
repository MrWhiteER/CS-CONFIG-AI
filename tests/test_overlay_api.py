"""Settings persistence and passive permission notices, without changing Windows."""

import sys
import types
import unittest
from unittest import mock

from cs2cfg import profiles, webui
from cs2cfg.overlay import permissions, settings
from cs2cfg.overlay.hud import display_lines
from cs2cfg.overlay.service import OverlayService


class SettingsApi(unittest.TestCase):
    def test_read_only_data_api_leaves_disabled_service_inert(self):
        state = types.SimpleNamespace(overlay=OverlayService())
        with mock.patch("cs2cfg.overlay.service.threading.Thread") as thread:
            result = webui._overlay(state, {"seconds": 120})
        self.assertTrue(result["ok"])
        self.assertFalse(result["settings"]["overlay_enabled"])
        self.assertEqual(result["history"], [])
        thread.assert_not_called()

    def test_settings_save_only_known_machine_keys(self):
        prefs = {"ui": {"overlay_corner": "bottom_right"}, "accounts": {"one": {"cfg_folder": "mine"}}}
        overlay = mock.Mock()
        overlay.snapshot.return_value = {"status": "disabled"}
        state = types.SimpleNamespace(overlay=overlay)
        with (mock.patch("cs2cfg.cli.load_prefs", return_value=prefs),
              mock.patch("cs2cfg.cli.save_prefs") as save):
            webui._overlay_settings(state, {"overlay_enabled": False, "unrelated": "ignored"})
        save.assert_called_once_with(prefs)
        self.assertEqual(prefs["ui"]["overlay_corner"], "bottom_right")
        self.assertNotIn("unrelated", prefs["ui"])
        self.assertEqual(prefs["accounts"]["one"], {"cfg_folder": "mine"})
        overlay.configure.assert_called_once_with(settings.read(prefs["ui"]))

    def test_invalid_settings_are_rejected_before_save_or_start(self):
        overlay = mock.Mock()
        with (mock.patch("cs2cfg.cli.load_prefs", return_value={}),
              mock.patch("cs2cfg.cli.save_prefs") as save,
              self.assertRaises(ValueError)):
            webui._overlay_settings(types.SimpleNamespace(overlay=overlay), {"overlay_enabled": "yes"})
        save.assert_not_called()
        overlay.configure.assert_not_called()

    def test_sign_out_dismissal_survives_settings_reload_and_account_switch(self):
        prefs = {}
        helper = types.ModuleType("cs2cfg.elevated")
        helper.ready, helper.run = mock.Mock(return_value=True), mock.Mock()
        service = OverlayService()
        state = types.SimpleNamespace(overlay=service)
        with (mock.patch.object(permissions, "frame_capture_ready", return_value=False),
              mock.patch.dict(sys.modules, {"cs2cfg.elevated": helper}),
              mock.patch("cs2cfg.elevated", helper, create=True),
              mock.patch("cs2cfg.cli.load_prefs", side_effect=lambda: prefs),
              mock.patch("cs2cfg.cli.save_prefs") as save):
            self.assertEqual(webui._overlay(state, {})["frame_capture_hint"], permissions.SIGN_OUT_HINT)
            result = webui._overlay_settings(state, {permissions.DISMISSED_KEY: True})
            self.assertEqual(result["frame_capture_hint"], "")
            self.assertFalse(result["frame_capture_hint_dismissible"])
            self.assertTrue(prefs["ui"][permissions.DISMISSED_KEY])
            save.assert_called_once_with(prefs)
            # A normal settings save must preserve the dismissal.
            webui._overlay_settings(state, {"overlay_corner": "bottom_right"})
            profiles.migrate(prefs, "another-account")
            reloaded = OverlayService()
            reloaded.configure(profiles.ui_for(prefs, "another-account"))
            self.assertEqual(reloaded.snapshot()["frame_capture_hint"], "")
        helper.run.assert_not_called()

    def test_unavailable_frame_capture_has_dashes_in_api_and_hud(self):
        service = OverlayService()
        service._hwnd = 123
        service.ingest({"fps": None, "one_percent_low": None, "frame_time_ms": None,
                        "cpu_percent": 12, "gpu_percent": 25, "gpu_temp_c": 60,
                        "frame_capture_ready": False})
        with (mock.patch.object(permissions, "frame_capture_ready", return_value=False),
              mock.patch.object(permissions, "frame_capture_hint", return_value=permissions.SETUP_HINT)):
            result = webui._overlay(types.SimpleNamespace(overlay=service), {})
        self.assertFalse(result["frame_capture_ready"])
        for field in settings.FIELDS[:3]:
            self.assertIsNone(result["current"][field])
            self.assertEqual(result["display"][field], "\u2014")
        self.assertEqual(result["display"]["cpu_percent"], "12.0%")
        self.assertEqual(result["frame_capture_hint"], permissions.SETUP_HINT)
        self.assertFalse(result["frame_capture_hint_dismissible"])
        text = " ".join(display_lines(result["current"]))
        for label in ("FPS", "1% low", "Frame"):
            self.assertIn(label + " \u2014", text)
        self.assertIn("GPU 25.0%", text)

    def test_unready_api_and_hud_mask_stale_frame_values(self):
        service = OverlayService()
        service._hwnd = 123
        service.ingest({"fps": 200, "one_percent_low": 150, "frame_time_ms": 5})
        with (mock.patch.object(permissions, "frame_capture_ready", return_value=False),
              mock.patch.object(permissions, "frame_capture_hint", return_value="")):
            result = webui._overlay(types.SimpleNamespace(overlay=service), {})
        self.assertEqual(result["display"]["fps"], "\u2014")
        self.assertIsNone(result["current"]["fps"])
        self.assertIsNone(result["current"]["frame_time_ms"])
        text = " ".join(display_lines(result["current"]))
        self.assertIn("FPS \u2014", text)
        self.assertIn("Frame \u2014", text)


if __name__ == "__main__":
    unittest.main()
