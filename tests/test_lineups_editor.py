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
        game.update({'provider': {'steamid': 'local'},
                     'map': {'name': 'de_mirage', 'phase': 'live'},
                     'player': {'steamid': 'local', 'position': '10, 20, 30',
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