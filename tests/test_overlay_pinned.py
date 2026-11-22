"""See-through settings and native read-only models; no Windows calls required."""
import types
import unittest
from unittest import mock

from cs2cfg import profiles, webui
from cs2cfg.overlay import layout, settings, pinned
from cs2cfg.overlay.hud import Hud
from cs2cfg.overlay.service import OverlayService
from cs2cfg.overlay.regionlock import RegionLock


class SeeThroughPreferences(unittest.TestCase):
    def test_default_opacity_clamp_and_invalid_values(self):
        self.assertEqual(Hud().opacity, 10)
        for value, expected in [(-20, 0), (0, 0), (60, 60), (100, 100), (170, 100)]:
            self.assertEqual(layout.validate({'hardware': {'opacity': value}})['hardware']['opacity'], expected)
        for value in [True, '60', None, float('nan'), float('inf')]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                layout.validate({'hardware': {'opacity': value}})

    def test_opacity_pin_positions_and_dim_roundtrip_between_accounts(self):
        self.assertTrue(settings.read()['overlay_dim_game'])
        saved = {tool: {'opacity': 0 if i % 2 else 60, 'pinned': tool != 'settings',
                        'pinned_x': 30, 'pinned_y': 100 + i * 140}
                 for i, tool in enumerate(layout.IDS)}
        prefs = {}
        profiles.remember(prefs, 'one', settings.read({'overlay_layout': saved, 'overlay_dim_game': False}))
        restored = settings.read(profiles.ui_for(prefs, 'two'), strict=True)
        self.assertEqual(restored['overlay_layout'], saved)
        self.assertFalse(restored['overlay_dim_game'])
        with self.assertRaises(ValueError):
            layout.validate({'settings': {'pinned': True}})
        self.assertFalse(settings.read()['overlay_enabled'])

    def test_settings_endpoint_saves_dim_and_background(self):
        prefs = {}
        service = OverlayService()
        with (mock.patch('cs2cfg.cli.load_prefs', return_value=prefs),
              mock.patch('cs2cfg.cli.save_prefs') as save):
            webui._overlay_settings(types.SimpleNamespace(overlay=service), {
                'overlay_dim_game': False, 'overlay_layout': {'events': {'pinned': True, 'opacity': 0}}})
        save.assert_called_once()
        self.assertFalse(settings.read(prefs['ui'])['overlay_dim_game'])
        self.assertEqual(settings.read(prefs['ui'])['overlay_layout']['events']['opacity'], 0)
        self.assertIsNone(service._thread)


class NativeContent(unittest.TestCase):
    def test_performance_numbers_graph_and_unavailable_capture(self):
        data = {'current': {'fps': 287, 'one_percent_low': 182, 'frame_time_ms': 3.5},
                'history': [{'frame_time_ms': 3.5}] * 90}
        model = pinned.render('performance', data)
        text = ' '.join(model['lines'])
        for expected in ['FPS 287.0', '1% low 182.0', 'Frame 3.5 ms']:
            self.assertIn(expected, text)
        self.assertEqual(model['graph'], (3.5,) * 60)
        data['frame_capture_ready'] = False
        unavailable = pinned.render('performance', data)
        self.assertNotIn('287', ' '.join(unavailable['lines']))
        self.assertFalse(unavailable['graph'])

    def test_hardware_load_temperatures_memory_and_missing(self):
        model = pinned.render('hardware', {'cpu_percent': 32, 'gpu_percent': 56,
            'cpu_temp_c': 51, 'gpu_temp_c': 66, 'vram_used_mb': 4096, 'vram_total_mb': 12288,
            'ram_used_mb': 14000, 'ram_total_mb': 32000})
        text = ' '.join(model['lines'])
        for expected in ['CPU 32.0%', 'GPU 56.0%', '51.0 C', '66.0 C', 'VRAM 4096.0', 'RAM 14000.0']:
            self.assertIn(expected, text)
        self.assertIn('\u2014', ' '.join(pinned.render('hardware', {})['lines']))

    def test_four_events_profiles_and_region_state(self):
        model = pinned.render('events', {'events': [{'at': 100 + i, 'type': 'not_responding',
            'duration_ms': 212.4} for i in range(8)]})
        self.assertEqual(len(model['lines']), 5)
        self.assertIn('Freeze   212.4 ms', model['lines'][1])
        self.assertIn('No recent events', pinned.render('events', {})['lines'])
        self.assertEqual(pinned.render('profiles', {'setup': 'Balanced', 'layout': 'Match'})['lines'],
                         ('Profiles', 'Setup: Balanced', 'Layout: Match'))
        self.assertIn('Coming soon', pinned.render('serverlock', {})['lines'])
        self.assertIn('Locked to Dubai', pinned.render('serverlock', {'text': 'Locked to Dubai'})['lines'])

    def test_alpha_is_premultiplied_and_foreground_never_dims(self):
        # Transparent background, dark outline, white text, green graph mask.
        mask = bytes([0, 0, 0, 0, 24, 24, 24, 0, 255, 255, 255, 0, 0, 255, 0, 0])
        colors = ((20, 40, 60), (230, 240, 250), (100, 200, 250))
        clear = pinned.composite(mask, 0, colors)
        self.assertEqual(clear[:4], bytes(4))
        self.assertEqual(clear[4:8], bytes([12, 12, 12, 255]))
        self.assertEqual(clear[8:12], bytes([250, 240, 230, 255]))
        self.assertEqual(clear[12:16], bytes([250, 200, 100, 255]))
        sixty = pinned.composite(mask, 60, colors)
        self.assertEqual(sixty[:4], bytes([36, 24, 12, 153]))
        self.assertEqual(sixty[4:], clear[4:])
        self.assertEqual(pinned.composite(mask, 100, colors)[:4], bytes([60, 40, 20, 255]))
        for offset in range(0, len(sixty), 4):
            self.assertTrue(all(c <= sixty[offset+3] for c in sixty[offset:offset+3]))

    def test_native_palette_reads_app_theme_tokens(self):
        self.assertEqual(pinned.palette('carbon'), ((19, 22, 27), (234, 238, 244), (195, 208, 222)))
        self.assertEqual(pinned.palette('paper')[0], (255, 253, 248))

    def test_native_region_read_is_bounded_and_does_not_enable_actions(self):
        module = mock.Mock()
        module.lock_status.return_value = {'firewall': {'status': 'locked', 'city': 'Dubai'}}
        adapter = RegionLock(module, clock=lambda: 10)
        self.assertIn('Locked to Dubai', adapter.native_snapshot()['text'])
        adapter.native_snapshot()
        module.lock_status.assert_called_once()
        module.list_regions.assert_not_called()
        self.assertFalse(adapter.visible)
        with self.assertRaises(ValueError):
            adapter.request('dxb')
        self.assertEqual(RegionLock(None).native_snapshot()['text'], 'Coming soon')


class NativeLifecycle(unittest.TestCase):
    def test_all_pins_share_capture_visibility_and_stop_gates(self):
        service = OverlayService()
        service._settings = settings.read({'overlay_layout': {
            tool: {'pinned': True, 'opacity': 0} for tool in pinned.TITLES}})
        service._hud, service._hardware_widget = mock.Mock(), mock.Mock()
        service._widgets = {tool: mock.Mock() for tool in ('events', 'profiles', 'serverlock')}
        service.pinned_context = mock.Mock(return_value={'profiles': {'setup': 'Balanced', 'layout': 'Match'}})
        service.panel = types.SimpleNamespace(visible=False, regions=RegionLock(None))
        found = types.SimpleNamespace(rect=(0, 0, 1920, 1080))
        with mock.patch.object(service._game_state, 'visible', return_value=True):
            service._update_pins({'fps': 287}, found, True)
            for widget in [service._hud, service._hardware_widget, *service._widgets.values()]:
                self.assertEqual(widget.configure.call_args.kwargs['opacity'], 0)
                self.assertTrue(widget.configure.call_args.kwargs['exclude_from_capture'])
                widget.set_allowed.assert_called_with(True)
            self.assertEqual(service._widgets['profiles'].update.call_args.args[0]['setup'], 'Balanced')
            service.panel.visible = True
            service._update_pins({}, found, True)
            for widget in [service._hud, service._hardware_widget, *service._widgets.values()]:
                widget.set_allowed.assert_called_with(False)
            service.panel.visible = False
        with mock.patch.object(service._game_state, 'visible', return_value=False):
            service._update_pins({}, found, True)
            service._widgets['events'].set_allowed.assert_called_with(False)
        service.pinned_context.assert_called_once()
        service.suspend_pins()
        service._widgets['serverlock'].set_allowed.assert_called_with(False)

    def test_native_profile_source_never_refreshes_or_scans(self):
        state = types.SimpleNamespace(steam_root=None, cfg_scan=types.SimpleNamespace(root='cfg'), refresh=mock.Mock())
        with (mock.patch('cs2cfg.cli.load_prefs', return_value={'ui': {'theme': 'paper'}}),
              mock.patch('cs2cfg.setups.listing', return_value={'live': 'Balanced'}),
              mock.patch('cs2cfg.layouts.load_current', return_value='match.vcfg'),
              mock.patch.object(webui, '_active_account') as active):
            context = webui._overlay_pinned_context(state)
        self.assertEqual(context, {'theme': 'paper', 'profiles': {'setup': 'Balanced', 'layout': 'match.vcfg'}})
        state.refresh.assert_not_called()
        active.assert_not_called()
