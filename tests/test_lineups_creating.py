"""Personal-picture fallback: no unsupported capture or game config writes."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from cs2cfg.overlay.settings import read
from cs2cfg.overlay.tools.lineups import creating


class CreatingFallback(unittest.TestCase):
    def test_keys_default_to_separate_keys_and_reject_collisions(self):
        settings = read({}, strict=True)
        self.assertEqual(settings['overlay_lineups_picture_key'], 'F8')
        self.assertEqual(settings['overlay_lineups_create_key'], 'F9')
        for changes in ({'overlay_lineups_create_key': 'F8'},
                        {'overlay_lineups_picture_key': 'F9'},
                        {'overlay_panel_hotkey': 'Ctrl+Alt+F9'},
                        {'overlay_hotkey': 'Ctrl+F8'},
                        {'overlay_lineups_create_key': 'F9;quit'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                read(changes, strict=True)
        settings = read({'overlay_lineups_create_key': 'F8'})
        self.assertNotEqual(settings['overlay_lineups_picture_key'], settings['overlay_lineups_create_key'])
        settings = read({'overlay_lineups_create_key': 'F10'}, strict=True)
        self.assertEqual(settings['overlay_lineups_create_key'], 'F10')

    def test_picture_request_never_captures_on_unverified_game_state(self):
        frame = (2, 2, bytes([10, 20, 30, 255]) * 4)
        capture = Mock(return_value=frame)
        for event in ({}, {'map': {'name': 'de_mirage', 'mode': 'casual'}},
                      {'hud_hidden': True, 'picture_key': 'F9'}):
            with self.subTest(event=event), patch('cs2cfg.lineups.window_capture.capture_cs2', capture), patch('cs2cfg.launcher.launch_via_steam') as launch, patch('pathlib.Path.write_text') as write:
                answer = creating(SimpleNamespace(game=event), {'map': 'mirage'})
                self.assertFalse(answer['available'])
                self.assertFalse(answer['active'])
                self.assertIn('radar', answer['text'])
                capture.assert_not_called()
                launch.assert_not_called()
                write.assert_not_called()