"""Modular shell contracts; mocks never launch capture or touch game files."""
import copy
import json
import threading
import types
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from cs2cfg import profiles, webui
from cs2cfg.overlay import layout, settings
from cs2cfg.overlay.service import OverlayService
from cs2cfg.overlay.tools import TOOLS, REGISTRY, dispatch
from cs2cfg.overlay.tools import performance, hardware, events, serverlock
from cs2cfg.overlay.tools import profiles as profile_tool, settings as settings_tool


class Registry(unittest.TestCase):
    def test_explicit_unique_registry_and_native_pin_support(self):
        self.assertEqual(tuple(REGISTRY), layout.IDS)
        self.assertEqual(len(TOOLS), 7)
        self.assertEqual({t.id for t in TOOLS if t.pinnable}, set(layout.IDS) - {'settings'})
        for tool in TOOLS:
            self.assertTrue(callable(tool.data))
            self.assertGreaterEqual(tool.refresh_hz, 0)
            self.assertLessEqual(tool.refresh_hz, 10)
            self.assertEqual(tool.manifest()['id'], tool.id)
            self.assertNotIn('actions', tool.manifest())

    def test_invalid_dispatch_identifiers_and_args(self):
        for body in ({'id': 'missing'}, {'id': []}, {'id': 'hardware', 'action': 'missing'},
                     {'id': 'hardware', 'action': []}, {'id': 'hardware', 'args': []}, []):
            with self.subTest(body=body), self.assertRaises(ValueError):
                dispatch(types.SimpleNamespace(), body)

    def test_hidden_and_disabled_shell_never_calls_sources(self):
        service = OverlayService()
        service.panel = types.SimpleNamespace(visible=False)
        with mock.patch.object(service, 'snapshot') as source:
            self.assertFalse(dispatch(types.SimpleNamespace(overlay=service),
                                      {'id': 'hardware'})['available'])
            service.panel.visible = True
            self.assertFalse(dispatch(types.SimpleNamespace(overlay=service),
                                      {'id': 'hardware'})['available'])
        source.assert_not_called()

    def test_disabled_tool_cannot_fetch_or_act(self):
        service = OverlayService()
        service.panel = types.SimpleNamespace(visible=True)
        service._settings.update(overlay_enabled=True, overlay_tools=['settings'])
        service._hwnd = 123
        with mock.patch.object(service, 'snapshot') as source, self.assertRaises(ValueError):
            dispatch(types.SimpleNamespace(overlay=service), {'id': 'hardware'})
        source.assert_not_called()


class LayoutSettings(unittest.TestCase):
    def test_roundtrip_machine_scope_and_detached_read(self):
        saved = {'performance': {'x': 10, 'y': 20, 'width': 530, 'height': 390,
                                 'open': True, 'pinned': True},
                 'hardware': {'open': False, 'pinned': False}}
        prefs = {}
        wanted = settings.read({'overlay_layout': saved,
                                'overlay_tools': ['settings', 'hardware', 'performance']}, strict=True)
        profiles.remember(prefs, 'one', wanted)
        restored = settings.read(profiles.ui_for(prefs, 'two'), strict=True)
        self.assertEqual(restored['overlay_layout'], saved)
        self.assertEqual(restored['overlay_tools'], ['settings', 'hardware', 'performance'])
        self.assertNotIn('overlay_layout', prefs.get('accounts', {}).get('one', {}))
        restored['overlay_layout']['performance']['pinned'] = False
        self.assertTrue(saved['performance']['pinned'])
        self.assertTrue(settings.read(prefs['ui'])['overlay_layout']['performance']['pinned'])

    def test_invalid_pins_ids_coordinates_and_order_rejected(self):
        for value in ({'unknown': {}}, {'settings': {'pinned': True}},
                      {'performance': {'x': float('nan')}}, {'hardware': {'pinned': 1}},
                      {'hardware': []}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                settings.read({'overlay_layout': value}, strict=True)
        for order in ([], ['hardware'], ['settings', 'settings'], ['settings', 'unknown'], {}):
            with self.subTest(order=order), self.assertRaises(ValueError):
                settings.read({'overlay_tools': order}, strict=True)
        self.assertEqual(settings.read({'overlay_layout': {'unknown': {}}})['overlay_layout'], {})

    def test_bounded_geometry_and_off_default(self):
        self.assertEqual(layout.validate({'performance': {'x': -99, 'width': 999999}}),
                         {'performance': {'x': 0, 'width': 16384}})
        self.assertFalse(settings.read()['overlay_enabled'])
        a = settings.read()
        a['overlay_tools'].clear()
        a['overlay_layout']['hardware'] = {'pinned': True}
        self.assertEqual(settings.read()['overlay_tools'], [k for k in layout.IDS if k != 'lineups'])
        self.assertEqual(settings.read()['overlay_layout'], {})

    def test_save_restore_endpoint_preserves_pins_and_existing_settings(self):
        prefs = {'ui': {'overlay_hotkey': 'Alt+F12'}}
        service = OverlayService()
        state = types.SimpleNamespace(overlay=service)
        with (mock.patch('cs2cfg.cli.load_prefs', return_value=prefs),
              mock.patch('cs2cfg.cli.save_prefs') as save):
            webui._overlay_settings(state, {'overlay_layout': {'hardware': {'pinned': True, 'open': False}}})
        save.assert_called_once()
        self.assertEqual(service._settings['overlay_hotkey'], 'Alt+F12')
        self.assertTrue(service._settings['overlay_layout']['hardware']['pinned'])
        self.assertFalse(service._settings['overlay_layout']['hardware']['open'])
        self.assertIsNone(service._thread)


class ToolSources(unittest.TestCase):
    def setUp(self):
        self.source = OverlayService().snapshot()
        self.source.update(current={'fps': 200, 'cpu_percent': 42, 'vram_used_mb': 123},
                           events=[{'at': 10, 'duration_ms': 20, 'type': 'frame_spike'}])
        self.service = mock.Mock()
        self.service.snapshot.side_effect = lambda *args: copy.deepcopy(self.source)
        self.state = types.SimpleNamespace(overlay=self.service)

    def test_performance_uses_existing_capture_snapshot(self):
        d = performance.data(self.state)
        self.service.snapshot.assert_called_once_with(600)
        self.assertEqual(d['current']['fps'], 200)
        self.assertIn('frame_capture_hint', d)
        self.assertIn('history', d)

    def test_hardware_available_and_missing_values(self):
        d = hardware.data(self.state)
        self.assertEqual(d['cpu_percent'], 42)
        self.assertEqual(d['vram_used_mb'], 123)
        self.assertIsNone(d['gpu_temp_c'])
        self.source['current'] = None
        self.assertTrue(all(v is None for v in hardware.data(self.state).values()))

    def test_events_delegate_without_own_history(self):
        self.assertEqual(events.data(self.state)['events'], self.source['events'])
        self.service.snapshot.assert_called_once_with(1)

    def test_profiles_delegate_existing_app_apis(self):
        with (mock.patch.object(webui, '_setups', return_value={'setups': []}) as setups,
              mock.patch.object(webui, '_cfg_layouts_profiles', return_value={'profiles': []}) as layouts):
            self.assertEqual(profile_tool.data(self.state),
                             {'setups': {'setups': []}, 'layouts': {'profiles': []}})
        setups.assert_called_once_with(self.state, {})
        layouts.assert_called_once_with(self.state, {})
        with (mock.patch.object(webui, '_setups_act') as setup,
              mock.patch.object(webui, '_cfg_layouts_apply') as apply):
            profile_tool.setup(self.state, {'name': 'Match', 'do': 'delete'})
            profile_tool.layout(self.state, {'file': 'match.vcfg'})
        setup.assert_called_once_with(self.state, {'do': 'use', 'name': 'Match'})
        apply.assert_called_once_with(self.state, {'file': 'match.vcfg'})

    def test_serverlock_only_uses_guarded_adapter(self):
        adapter = self.service.panel.regions
        adapter.visible = False
        serverlock.data(self.state)
        adapter.open.assert_called_once()
        adapter.visible = True
        serverlock.data(self.state)
        adapter.poll.assert_called_once()
        serverlock.lock(self.state, {'code': 'dxb'})
        adapter.request.assert_called_with('dxb')
        serverlock.unlock(self.state, {})
        adapter.request.assert_called_with()
        with self.assertRaises(ValueError):
            serverlock.lock(self.state, {})

    def test_settings_and_dismiss_delegate(self):
        self.assertEqual(settings_tool.data(self.state), {'settings': self.source['settings']})
        with mock.patch.object(webui, '_overlay_settings') as save:
            settings_tool.save(self.state, {'overlay_hide_in_rounds': False})
            save.assert_called_with(self.state, {'overlay_hide_in_rounds': False})
            performance.dismiss(self.state, {})
            save.assert_called_with(self.state, {'overlay_sign_out_hint_dismissed': True})


class ToolHttp(unittest.TestCase):
    def setUp(self):
        self.state = webui.State('mrwhiteer', 'autoperf.vcfg')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), webui.make_handler(self.state))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def request(self, path, body=None, token=True):
        request = urllib.request.Request(self.base + path,
                  data=json.dumps(body).encode() if body is not None else None,
                  headers={'Content-Type': 'application/json',
                           **({'X-CS2CFG-Token': self.state.token} if token else {})})
        return urllib.request.urlopen(request)

    def test_both_endpoints_require_token(self):
        for path, body in (('/api/overlay/tools', None),
                           ('/api/overlay/tool', {'id': 'hardware'})):
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as error:
                self.request(path, body, token=False)
            self.assertEqual(error.exception.code, 403)
        self.assertIsNone(self.state.overlay._thread)

    def test_get_registry_and_unknown_tool_action_errors(self):
        with (mock.patch('cs2cfg.cli.load_prefs', return_value={'ui': {'theme': 'paper'}}),
              mock.patch.object(webui, '_active_account', return_value=None)):
            with self.request('/api/overlay/tools') as response:
                result = json.load(response)
        self.assertEqual([t['id'] for t in result['tools']], list(layout.IDS))
        self.assertEqual(result['theme'], 'paper')
        for body in ({'id': 'unknown'}, {'id': 'hardware', 'action': 'unknown'}):
            with self.subTest(body=body), self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/overlay/tool', body)
            self.assertEqual(error.exception.code, 400)

    def test_hidden_data_and_action_never_query_sources(self):
        with mock.patch.object(self.state.overlay, 'snapshot') as source:
            for body in ({'id': 'performance'}, {'id': 'profiles', 'action': 'setup'}):
                with self.request('/api/overlay/tool', body) as response:
                    self.assertFalse(json.load(response)['available'])
        source.assert_not_called()


class NativePins(unittest.TestCase):
    def test_independent_pins_share_hud_safety_and_no_extra_hotkeys(self):
        service = OverlayService()
        service._settings = settings.read({'overlay_layout': {
            'performance': {'pinned': False}, 'hardware': {'pinned': True, 'x': 70, 'y': 90}}})
        service._hud = mock.Mock()
        service._hud._manual = False
        found = types.SimpleNamespace(rect=(100, 200, 2020, 1280))
        with (mock.patch.object(service._game_state, 'visible', return_value=True),
              mock.patch('cs2cfg.overlay.hud.Hud') as hud):
            service._update_pins({'cpu_percent': 42}, found, True)
            hud.assert_called_once_with(register_hotkeys=False)
            hud.return_value.start.assert_called_once()
            hud.return_value.set_allowed.assert_called_with(True)
            hud.return_value.update.assert_called_with({'cpu_percent': 42}, (170, 290))
            service._hud.set_allowed.assert_called_with(False)
            service.panel = types.SimpleNamespace(visible=True)
            service._update_pins({}, found, True)
            hud.return_value.set_allowed.assert_called_with(False)
            service.panel.visible = False
            service._update_pins({}, found, False)
            hud.return_value.set_allowed.assert_called_with(False)

    def test_live_round_auto_hide_gates_both_pins(self):
        service = OverlayService()
        service._settings['overlay_layout'] = {'performance': {'pinned': True}, 'hardware': {'pinned': True}}
        service._hud = mock.Mock()
        service._hardware_widget = mock.Mock()
        with mock.patch.object(service._game_state, 'visible', return_value=False):
            service._update_pins({}, types.SimpleNamespace(rect=(0, 0, 1920, 1080)), True)
        service._hud.set_allowed.assert_called_with(False)
        service._hardware_widget.set_allowed.assert_called_with(False)
        self.assertTrue(service._hardware_widget.configure.call_args.kwargs['exclude_from_capture'])

class MemoryTelemetry(unittest.TestCase):
    def test_system_ram_uses_only_readonly_system_query(self):
        from cs2cfg.overlay.metrics import system_memory
        native = mock.Mock()
        def read(pointer):
            pointer._obj.total = 32 * 1024 ** 3
            pointer._obj.available = 12 * 1024 ** 3
            return True
        native.GlobalMemoryStatusEx.side_effect = read
        with mock.patch('cs2cfg.overlay.metrics.ctypes.WinDLL', return_value=native, create=True):
            self.assertEqual(system_memory(), {'ram_used_mb': 20480, 'ram_total_mb': 32768})
        native.OpenProcess.assert_not_called()

    def test_unavailable_memory_stays_missing(self):
        from cs2cfg.overlay.metrics import system_memory
        with mock.patch('cs2cfg.overlay.metrics.ctypes.WinDLL', side_effect=OSError, create=True):
            self.assertEqual(system_memory(), {'ram_used_mb': None, 'ram_total_mb': None})

class PinHotkey(unittest.TestCase):
    def test_hardware_only_can_be_toggled_while_primary_window_is_hidden(self):
        from cs2cfg.overlay.hud import Hud
        hud = Hud()
        hud.visible = False  # Performance unpinned; hardware can still be shown.
        self.assertTrue(hud.pin_requested())
        hud.toggle_requested()
        self.assertFalse(hud.pin_requested())
        hud.toggle_requested()
        self.assertTrue(hud.pin_requested())
        self.assertFalse(hud._thread.is_alive())

    def test_shell_open_suspends_both_native_surfaces(self):
        service = OverlayService()
        service._hud, service._hardware_widget = mock.Mock(), mock.Mock()
        service.suspend_pins()
        service._hud.set_allowed.assert_called_once_with(False)
        service._hardware_widget.set_allowed.assert_called_once_with(False)

class ActiveTheme(unittest.TestCase):
    def test_shell_uses_the_same_account_theme_as_main_app(self):
        from cs2cfg.overlay.tools import listing
        state = types.SimpleNamespace(overlay=OverlayService())
        prefs = {'ui': {}, 'accounts': {'one': {'theme': 'paper'}}}
        with (mock.patch('cs2cfg.cli.load_prefs', return_value=prefs),
              mock.patch.object(webui, '_active_account', return_value='one')):
            result = listing(state)
        self.assertEqual(result['theme'], 'paper')
        result['settings']['overlay_tools'].clear()
        self.assertEqual(state.overlay._settings['overlay_tools'], [k for k in layout.IDS if k != 'lineups'])

class PinPlacement(unittest.TestCase):
    def test_saved_positions_are_clamped_to_new_monitor(self):
        from cs2cfg.overlay.service import pinned_position
        self.assertEqual(pinned_position((-1920, 0, 0, 1080), {'x': 9999, 'y': 9999}), (-360, 960))
        self.assertEqual(pinned_position((100, 200, 2020, 1280), {'x': 70, 'y': 90}), (170, 290))
