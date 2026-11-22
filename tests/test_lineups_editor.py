"""Editor pose evidence; never reads or writes a game installation."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from cs2cfg.overlay.gsi import AutoHide
from cs2cfg.overlay.tools.lineups import player_position, editing


class Editor(unittest.TestCase):
    def state(self):
        game = AutoHide()
        game.update({'provider': {'appid': 730, 'steamid': 'local'},
                     'map': {'name': 'de_mirage', 'phase': 'live'},
                     'player': {'steamid': 'local', 'activity': 'playing', 'position': '10, 20, 30',
                                'forward': '0, 1, 0'}})
        return SimpleNamespace(overlay=SimpleNamespace(_lock=threading.RLock(),
            _game_state=game, _settings={'overlay_enabled': True}, _configure_gsi=Mock()))

    def test_live_position_and_forward_and_stale_or_other_player(self):
        state = self.state()
        pose = player_position(state)
        self.assertEqual(pose['map'], 'mirage')
        self.assertEqual(pose['stand'], {'x': 10, 'y': 20, 'z': 30})
        self.assertAlmostEqual(pose['aim']['yaw'], 90)
        state.overlay._game_state.state['player']['steamid'] = 'spectated'
        self.assertIsNone(player_position(state))
        state = self.state(); state.overlay._game_state.received -= 20
        self.assertIsNone(player_position(state))

    def test_missing_or_invalid_vectors_fail_closed(self):
        for value in ('', 'nan,0,0', '1,2', '0,0,0'):
            state = self.state()
            state.overlay._game_state.state['player']['forward'] = value
            self.assertIsNone(player_position(state))

    def test_editing_reconfigures_only_on_explicit_action(self):
        state = self.state()
        with patch('cs2cfg.overlay.tools.lineups.data', return_value={}):
            editing(state, {'active': True})
            self.assertTrue(state.overlay.lineups_editing)
            editing(state, {'active': False})
            self.assertFalse(state.overlay.lineups_editing)
        self.assertEqual(state.overlay._configure_gsi.call_count, 2)
    def test_position_messages(self):
        from cs2cfg.overlay.tools.lineups import position_notice
        state = self.state()
        state.overlay._gsi_written_at = 200
        with patch('cs2cfg.lineups.window_capture.process_started', return_value=100):
            self.assertEqual(position_notice(state), 'Restart CS2 once so the game can share your position.')
        with patch('cs2cfg.lineups.window_capture.process_started', return_value=300):
            self.assertEqual(position_notice(state), 'The game has not shared your position yet. Move a step and press again.')

    def test_position_component_before_launch_and_off(self):
        import tempfile
        from pathlib import Path
        from cs2cfg.overlay.service import OverlayService
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'game/csgo/cfg').mkdir(parents=True)
            with patch('cs2cfg.overlay.settings.read', return_value={'overlay_tools':['lineups'],'overlay_enabled':True}), patch('cs2cfg.paths.user_data_dir', return_value=root/'user'):
                service = OverlayService()
                service.bind_gsi(root, 1234)
                service._configure_gsi(True)
                path = root/'game/csgo/cfg/gamestate_integration_cs2cfg.cfg'
                self.assertIn('"player_position" "1"', path.read_text())
                before = path.stat().st_mtime_ns
                service._configure_gsi(True)
                self.assertEqual(before, path.stat().st_mtime_ns)
                service._settings['overlay_tools'] = []
                service._configure_gsi(True)
                self.assertNotIn('player_position', path.read_text())
