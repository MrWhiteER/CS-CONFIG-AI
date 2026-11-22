"""Player-triggered app pictures with fake frames; no real game folders."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from cs2cfg.overlay.settings import read
from cs2cfg.overlay.tools.lineups import creating


class CreatingPictures(unittest.TestCase):
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

    def test_order_retake_failure_cancel_and_saved_location(self):
        import tempfile
        from pathlib import Path
        from cs2cfg.lineups.creating import CreatingSession, crop_frame
        frame = (4, 4, bytes(range(64)))
        capture = Mock(return_value=frame)
        keys = []
        def factory(key, callback):
            handle = Mock()
            keys.append(handle)
            return handle
        session = CreatingSession(capture, hotkey=factory)
        session.wait()
        self.assertEqual(session.waiting, 'stand')
        keys[0].start.assert_called_once()
        capture.side_effect = OSError('failed')
        session.press()
        self.assertEqual(session.waiting, 'stand')
        capture.side_effect = None
        session.press()
        self.assertEqual(session.waiting, 'aim')
        keys[0].close.assert_not_called()
        session.press()
        keys[0].close.assert_called_once()
        self.assertTrue(session.snapshot()['review'])
        session.wait('aim')
        session.press()
        keys[1].close.assert_called_once()
        self.assertEqual(crop_frame(frame, [.25,.25,.5,.5]), (2,2,frame[2][20:28]+frame[2][36:44]))
        with self.assertRaises(ValueError):
            crop_frame(frame, [0,0,2,1])
        with tempfile.TemporaryDirectory() as directory:
            saved = session.save({'stand':{'crop':[.25,.25,.5,.5],'marker':[.2,.3]}}, directory)
            for image in saved.values():
                path = Path(directory)/'lineups'/image['file']
                self.assertTrue(path.is_file())
                self.assertIn(Path(directory)/'lineups'/'pictures', path.parents)
            self.assertEqual(saved['stand']['marker'], [.2,.3])
        session.wait('stand')
        session.cancel()
        keys[2].close.assert_called_once()
        self.assertFalse(session.active)
        self.assertEqual(session.frames, {})

    def test_app_wiring_hides_panel_excludes_status_and_reopens_review(self):
        from cs2cfg.overlay.service import OverlayService
        from cs2cfg.lineups.creating import PictureHotkey
        service = OverlayService()
        service._settings.update(overlay_enabled=True, overlay_tools=['lineups'], overlay_lineups_create_key='F9')
        service.panel = Mock(visible=False)
        state = SimpleNamespace(overlay=service)
        with patch.object(PictureHotkey, 'start'), patch.object(PictureHotkey, 'close'), patch('cs2cfg.overlay.hud.Hud') as hud, patch('cs2cfg.lineups.window_capture.capture_cs2', return_value=(2,2,bytes(range(16)))) as capture, patch('cs2cfg.launcher.launch_via_steam') as launch:
            answer = creating(state, {'action':'start'})
            self.assertTrue(answer['active'])
            hud.assert_called_once_with(exclude_from_capture=True, register_hotkeys=False)
            service.panel.window.hide.assert_called_once()
            capture.assert_not_called()
            service.creating_session.press()
            service.creating_session.press()
            self.assertEqual(capture.call_count, 2)
            service.panel.toggle.assert_called_once()
            self.assertTrue(creating(state, {'action':'status'})['review'])
            creating(state, {'action':'cancel'})
            self.assertIsNone(service.creating_session)
            launch.assert_not_called()
