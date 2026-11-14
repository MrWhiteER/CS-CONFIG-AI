"""Panel lifecycle and native focus handoff, without windows or workers."""

import os
import sys
import types
import unittest
from unittest import mock

from cs2cfg import profiles, webui
from cs2cfg.overlay import panel, settings
from cs2cfg.overlay.hud import Hud, Hotkeys
from cs2cfg.overlay.service import OverlayService


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class PanelLifecycle(unittest.TestCase):
    def setUp(self):
        self.service = OverlayService()
        self.window = mock.Mock()
        self.window.events = types.SimpleNamespace(loaded=Event(), closing=Event())
        self.factory = mock.Mock(return_value=self.window)
        self.focus = mock.Mock()
        self.panel = panel.Panel(self.service, self.factory, focus=self.focus, keyboard=mock.Mock(), setup=mock.Mock())
        self.module = mock.Mock()
        self.module.list_regions.return_value = []
        self.module.lock_status.return_value = {"busy": True}
        from cs2cfg.overlay.regionlock import RegionLock
        self.panel.regions = RegionLock(self.module)
        self.service.panel = self.panel
        self.state = types.SimpleNamespace(overlay=self.service)

    def enable_game(self):
        self.service._settings["overlay_enabled"] = True
        self.service._hwnd = 123

    def test_off_and_waiting_for_game_are_inert(self):
        with mock.patch("threading.Thread") as thread:
            self.panel.toggle()
            self.service._settings["overlay_enabled"] = True
            self.panel.toggle()
            self.panel.data("open")
        self.factory.assert_not_called()
        self.assertEqual(self.module.mock_calls, [])
        thread.assert_not_called()

    def test_open_is_lazy_reuses_window_and_activates_on_show(self):
        self.enable_game()
        self.panel.toggle()
        self.assertTrue(self.panel.visible)
        self.factory.assert_called_once()
        self.assertEqual(self.module.mock_calls, [])
        self.panel.loaded()
        self.window.evaluate_js.assert_called_with("window.overlayPanelActive(true)")
        self.panel.toggle()
        self.window.evaluate_js.assert_called_with("window.overlayPanelActive(false)")
        self.window.hide.assert_called_once()
        self.focus.assert_called_once_with(123)
        self.panel.toggle()
        self.factory.assert_called_once()
        self.window.show.assert_called_once()

    def test_closing_suspends_before_focus_and_hide(self):
        self.enable_game()
        self.panel.toggle()
        self.panel.loaded()
        self.panel.data("open")
        calls = mock.Mock()
        calls.attach_mock(self.window.evaluate_js, "script")
        calls.attach_mock(self.focus, "focus")
        calls.attach_mock(self.window.hide, "hide")
        self.panel.hide()
        self.assertEqual(calls.mock_calls, [mock.call.script("window.overlayPanelActive(false)"),
                                           mock.call.focus(123), mock.call.hide()])
        self.assertFalse(self.panel.regions.visible)
        self.module.reset_mock()
        self.panel.data()
        self.assertEqual(self.module.mock_calls, [])

    def test_window_x_defers_webview_calls_until_native_close_returns(self):
        self.enable_game()
        self.panel.toggle()
        with mock.patch.object(panel.threading, "Timer") as timer:
            self.assertFalse(self.panel.closing())
            timer.assert_called_once_with(.05, self.panel._finish_close)
            self.panel.closing()
            timer.assert_called_once()
            self.window.hide.assert_not_called()
            self.assertTrue(self.panel.visible)
            self.panel._finish_close()
        self.window.hide.assert_called_once()
        self.assertFalse(self.panel.visible)

    def test_failed_creation_is_reported_and_can_retry(self):
        self.enable_game()
        self.factory.side_effect = RuntimeError("window unavailable")
        self.panel.toggle()
        self.assertFalse(self.panel.visible)
        self.assertIn("window unavailable", self.panel.error)
        self.factory.side_effect = None
        self.panel.toggle()
        self.assertTrue(self.panel.visible)

    def test_failed_script_still_hides_native_view_and_stops_region_access(self):
        self.enable_game()
        self.panel.toggle()
        self.panel.loaded()
        self.panel.data("open")
        self.window.evaluate_js.side_effect = RuntimeError("view unavailable")
        self.panel.hide()
        self.window.hide.assert_called_once()
        self.assertFalse(self.panel.regions.visible)
        self.assertIn("view unavailable", self.panel.error)

    def test_late_load_after_hide_does_not_restart_view(self):
        self.enable_game()
        self.panel.toggle()
        self.panel.hide()
        self.panel.loaded()
        self.window.evaluate_js.assert_called_once_with("window.overlayPanelActive(false)")

    def test_game_exit_hides_without_focus(self):
        self.enable_game()
        self.panel.toggle()
        self.service._end_game()
        self.assertFalse(self.panel.visible)
        self.focus.assert_not_called()

    def test_disable_hides_panel_and_cancels_adapter(self):
        self.enable_game()
        self.panel.toggle()
        self.panel.data("open")
        self.service.configure(settings.read())
        self.assertFalse(self.panel.visible)
        self.assertFalse(self.panel.regions.visible)
        self.module.reset_mock()
        self.panel.data("open")
        self.assertEqual(self.module.mock_calls, [])

    def test_destroy_permits_native_close_without_restoring_focus(self):
        self.enable_game()
        self.panel.toggle()
        self.panel.destroy()
        self.assertTrue(self.panel.closing())
        self.window.destroy.assert_called_once()
        self.focus.assert_not_called()

    def test_api_close_and_navigation_use_controller(self):
        self.enable_game()
        self.panel.toggle()
        self.assertTrue(webui._overlay_panel(self.state, {"action":"keyboard"})["ok"])
        self.panel.keyboard.assert_called_once()
        self.assertFalse(self.panel.visible)
        self.focus.assert_not_called()
        self.panel.toggle()
        webui._overlay_panel(self.state, {"action":"close"})
        self.focus.assert_called_once_with(123)

    def test_api_gates_region_calls_and_validates_actions(self):
        self.enable_game()
        self.panel.toggle()
        result = webui._overlay_panel(self.state, {"action":"open"})
        self.assertTrue(result["available"])
        self.module.lock_status.assert_called_once()
        self.panel.data("open")
        self.module.lock_status.assert_called_once()
        with self.assertRaises(ValueError):
            self.panel.data("unknown")
        self.service._settings["overlay_enabled"] = False
        self.module.reset_mock()
        self.panel.data("open")
        self.assertEqual(self.module.mock_calls, [])

    def test_browser_fallback_returns_clear_error(self):
        self.service.panel = None
        self.assertFalse(webui._overlay_panel(self.state, {})["ok"])


class PanelSettings(unittest.TestCase):
    def test_default_and_machine_scope(self):
        self.assertEqual(settings.read()["overlay_panel_hotkey"], "Ctrl+Alt+P")
        self.assertIn("overlay_panel_hotkey", profiles.MACHINE_KEYS)
        self.assertFalse(settings.read()["overlay_enabled"])

    def test_configurable_and_invalid_shortcuts(self):
        self.assertEqual(settings.read({"overlay_panel_hotkey":"Shift+F24"}, strict=True)
                         ["overlay_panel_hotkey"], "Shift+F24")
        for chord in ("P", "Ctrl+Ctrl+P", "Ctrl+Alt+O", "Alt+Ctrl+O"):
            with self.subTest(chord=chord), self.assertRaises(ValueError):
                settings.read({"overlay_panel_hotkey":chord}, strict=True)

    def test_hud_accepts_both_chords_without_starting(self):
        hud = Hud(on_panel=mock.Mock())
        hud.configure(fields=settings.FIELDS, hotkey="Alt+F12", panel_hotkey="Shift+F8")
        self.assertEqual(hud._panel_chord, settings.hotkey("Shift+F8"))
        self.assertFalse(hud._thread.is_alive())


class FocusHandoff(unittest.TestCase):
    def test_only_foreground_app_can_return_focus(self):
        for pid in (os.getpid(), os.getpid() + 1):
            with self.subTest(pid=pid):
                native = mock.Mock()
                native.GetForegroundWindow.return_value = 321

                def identify(hwnd, pointer):
                    pointer._obj.value = pid

                native.GetWindowThreadProcessId.side_effect = identify
                with mock.patch.object(panel.ctypes, "WinDLL", return_value=native, create=True):
                    panel.return_to_game(123)
                if pid == os.getpid():
                    native.SetForegroundWindow.assert_called_once_with(123)
                else:
                    native.SetForegroundWindow.assert_not_called()

    def test_no_game_does_not_load_native_library(self):
        with mock.patch.object(panel.ctypes, "WinDLL", create=True) as native:
            panel.return_to_game(None)
        native.assert_not_called()


class NativeShortcuts(unittest.TestCase):
    def setUp(self):
        self.user = mock.Mock()
        self.keys = Hotkeys(self.user, 123)
        self.hud, self.panel = settings.hotkey("Ctrl+Alt+O"), settings.hotkey("Ctrl+Alt+P")

    def test_both_register_without_repeat_and_unchanged_never_retries(self):
        self.assertEqual(self.user.mock_calls, [])
        self.keys.configure(self.hud, self.panel)
        self.assertEqual(self.user.mock_calls, [mock.call.RegisterHotKey(123, 1, *self.hud),
                                                mock.call.RegisterHotKey(123, 2, *self.panel)])
        self.assertTrue(self.panel[0] & 0x4000)
        self.user.reset_mock()
        self.keys.configure(self.hud, self.panel)
        self.assertEqual(self.user.mock_calls, [])

    def test_exchanging_chords_releases_both_before_registering(self):
        self.keys.configure(self.hud, self.panel)
        self.user.reset_mock()
        self.keys.configure(self.panel, self.hud)
        self.assertEqual(self.user.mock_calls, [mock.call.UnregisterHotKey(123, 1),
                                                mock.call.UnregisterHotKey(123, 2),
                                                mock.call.RegisterHotKey(123, 1, *self.panel),
                                                mock.call.RegisterHotKey(123, 2, *self.hud)])

    def test_collisions_report_both_and_cleanup_only_owned_keys(self):
        self.user.RegisterHotKey.side_effect = [False, False]
        self.keys.configure(self.hud, self.panel)
        self.assertIn("HUD shortcut unavailable", self.keys.warning)
        self.assertIn("Panel shortcut unavailable", self.keys.warning)
        self.keys.close()
        self.user.UnregisterHotKey.assert_not_called()

    def test_probe_has_no_panel_shortcut_and_attach_can_enable_it(self):
        self.keys.configure(self.hud)
        self.user.RegisterHotKey.assert_called_once_with(123, 1, *self.hud)
        self.keys.configure(self.hud, self.panel)
        self.assertEqual(self.keys.registered, [1, 2])
        self.keys.close()
        self.assertEqual(self.keys.registered, [])


class DesktopPanel(unittest.TestCase):
    def test_desktop_attaches_inert_controller_and_lazy_focused_window_factory(self):
        from cs2cfg import desktop

        fake = types.ModuleType("webview")
        main = mock.Mock()
        main.events = types.SimpleNamespace(closed=Event())
        fake.create_window = mock.Mock(return_value=main)
        fake.start = mock.Mock()
        service, controller = OverlayService(), mock.Mock()
        with (mock.patch.dict(sys.modules, {"webview":fake}),
              mock.patch.object(panel, "Panel", return_value=controller) as create_panel,
              mock.patch.object(desktop, "_keep_running_in_the_tray")):
            self.assertTrue(desktop._launch_webview("http://127.0.0.1:8765/", None, mock.Mock(), overlay=service))
        self.assertIs(service.panel, controller)
        fake.create_window.assert_called_once()
        self.assertIsNone(service._thread)
        self.assertIn(controller.destroy, main.events.closed.handlers)
        create_panel.call_args.args[1]()
        self.assertEqual(fake.create_window.call_args.args[1], "http://127.0.0.1:8765/overlay-panel.html")
        self.assertTrue(fake.create_window.call_args.kwargs["on_top"])
        create_panel.call_args.kwargs["keyboard"]()
        main.load_url.assert_called_once_with("http://127.0.0.1:8765/?tab=keyboard")
        main.show.assert_called_once()
