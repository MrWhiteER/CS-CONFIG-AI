"""Fake-only picture tests; every filesystem write uses a temporary directory."""
import copy
import ctypes
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from cs2cfg.lineups import load
from cs2cfg.lineups import pictures
from cs2cfg.lineups import window_capture


class Pictures(unittest.TestCase):
    def native_capture_apis(self):
        from ctypes import wintypes as w
        user, gdi, kernel = mock.Mock(), mock.Mock(), mock.Mock()
        user.GetForegroundWindow.return_value = 123
        user.IsIconic.return_value = False
        def pid(hwnd, pointer):
            ctypes.cast(pointer,ctypes.POINTER(w.DWORD)).contents.value = 42
            return 1
        def rect(hwnd, pointer):
            value = ctypes.cast(pointer,ctypes.POINTER(w.RECT)).contents
            value.left, value.top, value.right, value.bottom = 0,0,2,1
            return True
        def name(handle, flags, buffer, length):
            buffer.value = r'C:\Games\cs2.exe'
            return True
        def bits(dc, bitmap, start, height, pixels, info, usage):
            ctypes.memmove(pixels,bytes([1,2,3,0,4,5,6,0]),8)
            return 1
        user.GetWindowThreadProcessId.side_effect = pid
        user.GetClientRect.side_effect = rect
        user.GetDC.return_value = 10
        kernel.OpenProcess.return_value = 20
        kernel.QueryFullProcessImageNameW.side_effect = name
        gdi.CreateCompatibleDC.return_value = 30
        gdi.CreateCompatibleBitmap.return_value = 40
        gdi.SelectObject.return_value = 50
        gdi.BitBlt.return_value = True
        gdi.GetDIBits.side_effect = bits
        return user,gdi,kernel

    def test_native_capture_fake_frame_and_resource_cleanup(self):
        user,gdi,kernel = self.native_capture_apis()
        with mock.patch.object(ctypes,'WinDLL',side_effect=[user,gdi,kernel],create=True):
            self.assertEqual(window_capture.capture_cs2(),
                             (2,1,bytes([3,2,1,255,6,5,4,255])))
        kernel.OpenProcess.assert_called_once_with(0x1000,False,42)
        kernel.CloseHandle.assert_called_once_with(20)
        user.ReleaseDC.assert_called_once_with(123,10)
        gdi.DeleteDC.assert_called_once_with(30)
        gdi.DeleteObject.assert_called_once_with(40)

    def test_native_capture_failed_copy_releases_resources(self):
        user,gdi,kernel = self.native_capture_apis()
        gdi.BitBlt.return_value = False
        with mock.patch.object(ctypes,'WinDLL',side_effect=[user,gdi,kernel],create=True):
            with self.assertRaises(OSError): window_capture.capture_cs2()
        gdi.GetDIBits.assert_not_called()
        gdi.SelectObject.assert_called_with(30,50)
        gdi.DeleteObject.assert_called_once_with(40)
        user.ReleaseDC.assert_called_once_with(123,10)

    def test_native_capture_rejects_focus_change(self):
        user,gdi,kernel = self.native_capture_apis()
        user.GetForegroundWindow.side_effect = [123,456]
        with mock.patch.object(ctypes,'WinDLL',side_effect=[user,gdi,kernel],create=True):
            with self.assertRaises(OSError): window_capture.capture_cs2()
        gdi.DeleteObject.assert_called_once_with(40)

    def test_external_capture_conversion_and_blank_failure(self):
        self.assertEqual(window_capture.rgba_frame(2,1,bytes([1,2,3,0,4,5,6,0])),
                         (2,1,bytes([3,2,1,255,6,5,4,255])))
        for width,height,data in [(0,1,b''),(2,1,b'bad'),(2,1,bytes(8))]:
            with self.assertRaises(ValueError):
                window_capture.rgba_frame(width,height,data)

    def trial_state(self, row):
        pitch, yaw = (math.radians(row['aim'][k]) for k in ('pitch','yaw'))
        return {'provider': {'appid':730, 'steamid':'local'},
                'map': {'name':'de_mirage', 'phase':'warmup'},
                'player': {'steamid':'local', 'activity':'playing', 'state':{'health':100},
                           'position': ','.join(str(row['stand'][k]) for k in ('x','y','z')),
                           'forward': ','.join(map(str, (math.cos(pitch)*math.cos(yaw),
                                                       math.cos(pitch)*math.sin(yaw), -math.sin(pitch))))}}

    def test_capture_trial_waits_for_pose_and_new_launch_per_shot(self):
        doc = load(); doc['lineups'] = doc['lineups'][:2]
        capture = mock.Mock(return_value=(100,100,bytes([10,20,30,255])*10000))
        runner = pictures.CaptureTrial(doc, capture)
        state = self.trial_state(doc['lineups'][0])
        self.assertFalse(runner.feed(1,state))
        self.assertIn('setang', runner.begin_launch(1))
        with self.assertRaises(ValueError): runner.begin_launch(2)
        no_pose = copy.deepcopy(state)
        del no_pose['player']['position']
        self.assertFalse(runner.feed(1,no_pose))
        self.assertFalse(runner.feed(0,state))
        capture.assert_not_called()
        self.assertTrue(runner.feed(1,state))
        self.assertFalse(runner.feed(1,state))
        self.assertEqual(capture.call_count,1)
        with self.assertRaises(ValueError): runner.begin_launch(1)
        runner.begin_launch(2)
        self.assertFalse(runner.feed(1,state))
        self.assertFalse(runner.feed(2,state))
        self.assertTrue(runner.feed(2,self.trial_state(doc['lineups'][1])))
        self.assertEqual(capture.call_count,2)
        self.assertIn('<circle',runner.frames[0])
        with self.assertRaises(ValueError): runner.begin_launch(3)

    def test_capture_trial_rejects_wrong_or_missing_real_state(self):
        doc = load(); row = doc['lineups'][0]
        for component, field, value in [
                ('map','name','de_inferno'), ('map','phase','live'),
                ('player','steamid','spectated'), ('player','activity','menu'),
                ('provider','appid',440), ('player','position','0,0,0'),
                ('player','position','nan,0,0'), ('player','position','1,2'),
                ('player','forward','0,0,0'), ('player','forward',None)]:
            state = self.trial_state(row); state[component][field] = value
            with self.subTest(field=field,value=value):
                self.assertFalse(pictures.pose_matches(doc,row,state))
        self.assertFalse(pictures.pose_matches(doc,row,{}))

    def test_capture_failure_does_not_advance_trial(self):
        doc=load(); capture=mock.Mock(side_effect=OSError('No picture'))
        runner=pictures.CaptureTrial(doc,capture); runner.begin_launch(1)
        with self.assertRaises(OSError): runner.feed(1,self.trial_state(doc['lineups'][0]))
        self.assertEqual(runner.index,0)
        self.assertTrue(runner.waiting)

    def test_annotations_and_escaping(self):
        frame=(100,100,bytes([0,0,0,255])*10000)
        aim=pictures.annotate(frame,kind='aim',label='<tip>',point=(50,50))
        self.assertIn('<circle cx="50" cy="50"',aim)
        self.assertIn('&lt;tip&gt;',aim)
        stand=pictures.annotate(frame,kind='stand',label='Stand',point=(40,70))
        self.assertIn('L40 70',stand)
        with self.assertRaises(ValueError):
            pictures.annotate(frame,kind='stand',label='Stand',point=(100,70))

    def test_build_and_data_invalidate_cache(self):
        doc=load()
        self.assertNotEqual(pictures.cache_key(doc,'1'),pictures.cache_key(doc,'2'))
        changed=copy.deepcopy(doc); changed['lineups'][0]['aim']['pitch']+=1
        self.assertNotEqual(pictures.cache_key(doc,'1'),pictures.cache_key(changed,'1'))
        with self.assertRaises(ValueError): pictures.cache_key(doc,'')

    def test_events_gate_every_shot_and_completion(self):
        doc=load(); doc['lineups']=doc['lineups'][:2]
        frame=(100,100,bytes([0,0,0,255])*10000)
        with tempfile.TemporaryDirectory() as tmp:
            runner=pictures.DryRun(doc,'fake',tmp)
            event={'fake':True,'map':'mirage','phase':'warmup','shot':doc['lineups'][0]['id'],
                   'frames':{'stand':frame,'aim':frame},'points':{'stand':(40,70),'aim':(50,50)}}
            for key,value in [('fake',False),('phase','live'),('map','inferno'),('shot','other')]:
                wrong={**event,key:value}
                self.assertFalse(runner.feed(wrong))
            self.assertEqual(list(Path(tmp).iterdir()),[])
            self.assertTrue(runner.feed(event))
            self.assertFalse((runner.root/'complete.json').exists())
            self.assertFalse(runner.feed(event))
            event['shot']=doc['lineups'][1]['id']
            self.assertTrue(runner.feed(event))
            self.assertTrue(runner.complete)
            self.assertTrue((runner.root/'complete.json').exists())
            self.assertIn('setpos', (runner.root/'0/practice.cfg.txt').read_text())
            self.assertIn('TEST PICTURE', (runner.root/'0/aim.svg').read_text())




class PictureWiring(unittest.TestCase):
    def state(self, row, kind='stand'):
        state = Pictures().trial_state(row)
        state['map']['mode'] = 'practice'
        state['allplayers'] = {'local': {}}
        pitch = math.radians(89 if kind == 'stand' else row['aim']['pitch'])
        yaw = math.radians(row['aim']['yaw'])
        state['player']['forward'] = ','.join(map(str, (math.cos(pitch)*math.cos(yaw), math.cos(pitch)*math.sin(yaw), -math.sin(pitch))))
        return state

    def test_offline_refuses_online_unknown_other_human(self):
        state = self.state(load()['lineups'][0])
        self.assertTrue(pictures.offline_ready(state))
        for mode in ('casual', 'competitive', '', None):
            state['map']['mode'] = mode
            self.assertFalse(pictures.offline_ready(state))
        state['map']['mode'] = 'offline'
        state['allplayers']['human'] = {'name': 'Other'}
        self.assertFalse(pictures.offline_ready(state))
        state['allplayers'] = {'local': {}, 'BOT1': {}}
        self.assertTrue(pictures.offline_ready(state))
        state['provider']['steamid'] = 'different'
        self.assertFalse(pictures.offline_ready(state))
        self.assertFalse(pictures.offline_ready({}))

    def test_cfg_two_views_binding_chain_undo(self):
        doc = load(); doc['lineups'] = doc['lineups'][:1]
        shots, undo = pictures.capture_cfg(doc, 'F9', '+lookatweapon')
        row = doc['lineups'][0]
        self.assertIn('sv_cheats 1', shots)
        self.assertIn('setang 89 '+str(row['aim']['yaw']), shots)
        self.assertIn('setang '+str(row['aim']['pitch']), shots)
        self.assertIn('alias cs2cfg_picture cs2cfg_picture_1', shots)
        self.assertIn('exec cs2cfg_lineup_shots_undo', shots)
        self.assertIn('bind "F9" "cs2cfg_picture"', shots)
        self.assertIn('bind "F9" "+lookatweapon"', undo)
        self.assertIn('sv_cheats 0', undo)
        self.assertIn('unbind "F8"', pictures.capture_cfg(doc)[1])
        with self.assertRaises(ValueError): pictures.capture_cfg(doc, 'F8;quit')
        self.assertIn('unbind', pictures.capture_cfg(doc, previous='quit;quit')[1])

    def runner(self, tmp, capture=None):
        doc = load(); doc['lineups'] = doc['lineups'][:1]
        return pictures.PictureSession(doc, 'test-build', tmp, tmp,
            capture or mock.Mock(return_value=(100,100,bytes([10,20,30,255])*10000)))

    def test_order_status_cache_cleanup_and_no_relaunch(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = self.runner(tmp); launch = mock.Mock()
            self.assertFalse(runner.start(launch, running=True))
            launch.assert_not_called(); self.assertEqual(list(Path(tmp).iterdir()), [])
            self.assertTrue(runner.start(launch))
            launch.assert_called_once_with('+map de_mirage +exec cs2cfg_lineup_shots')
            row = runner.document['lineups'][0]
            self.assertFalse(runner.feed(self.state(row, 'aim')))
            self.assertEqual(runner.text, 'Picture 1 of 2 - press F8')
            self.assertTrue(runner.feed(self.state(row)))
            self.assertEqual(runner.text, 'Picture 2 of 2 - press F8')
            self.assertFalse(runner.feed(self.state(row)))
            self.assertTrue(runner.feed(self.state(row, 'aim')))
            self.assertEqual(runner.text, 'Done - 2 pictures saved')
            self.assertFalse(runner.active)
            self.assertFalse((Path(tmp)/pictures.SHOTS_CFG).exists())
            self.assertFalse((Path(tmp)/pictures.UNDO_CFG).exists())
            pair = pictures.cached_pictures(runner.document, 'test-build', tmp)[row['id']]
            self.assertEqual(set(pair), {'stand', 'aim'})
            self.assertEqual(pictures.cached_pictures(runner.document, 'other-build', tmp), {})
            self.assertIn('L50 50', (runner.root/'0/stand.svg').read_text())
            self.assertIn('<circle cx="50" cy="50"', (runner.root/'0/aim.svg').read_text())

    def test_abort_keeps_partial_pictures_and_removes_owned_cfgs(self):
        for reason in ('online', 'left', 'closed', 'off'):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                runner = self.runner(tmp); runner.start(mock.Mock())
                row = runner.document['lineups'][0]; runner.feed(self.state(row))
                if reason in ('online', 'left'):
                    state = self.state(row)
                    state['map']['mode' if reason == 'online' else 'name'] = 'competitive'
                    runner.feed(state)
                elif reason == 'closed':
                    runner.game_running(True); runner.game_running(False)
                else: runner.abort()
                self.assertFalse(runner.active)
                self.assertTrue((runner.root/'0/stand.svg').exists())
                self.assertFalse((Path(tmp)/pictures.SHOTS_CFG).exists())
                self.assertFalse((Path(tmp)/pictures.UNDO_CFG).exists())

    def test_missing_pose_and_capture_failure_do_not_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            capture = mock.Mock(side_effect=OSError('Blank'))
            runner = self.runner(tmp, capture); runner.start(mock.Mock())
            state = self.state(runner.document['lineups'][0])
            self.assertFalse(runner.feed(state)); self.assertEqual(runner.index, 0)
            del state['player']['position']
            self.assertFalse(runner.feed(state)); self.assertFalse(runner.active)
            self.assertEqual(capture.call_count, 1)

    def test_launch_failure_cleans_up_and_reads_binding_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'keys.txt'; path.write_text('"F8" "+lookatweapon"')
            self.assertEqual(pictures.read_binding([path], 'F8'), '+lookatweapon')
            runner = self.runner(tmp)
            with self.assertRaises(OSError): runner.start(mock.Mock(side_effect=OSError()))
            self.assertFalse((Path(tmp)/pictures.SHOTS_CFG).exists())
            self.assertEqual(path.read_text(), '"F8" "+lookatweapon"')


class CaptureFiles(unittest.TestCase):
    def test_fake_screenshot_files_follow_pose_order(self):
        from cs2cfg.lineups.native import decode_png
        from cs2cfg.lineups.radar import png
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            files = []
            for i in range(2):
                path = directory/(str(i)+'.png')
                path.write_bytes(png(100,100,bytes([i+10,20,30,255])*10000))
                files.append(path)
            capture = mock.Mock(side_effect=lambda: decode_png(files.pop(0).read_bytes()))
            helper = PictureWiring(); runner = helper.runner(tmp, capture)
            runner.start(mock.Mock()); row = runner.document['lineups'][0]
            self.assertFalse(runner.feed({'provider': {'appid': 730}}))
            self.assertTrue(runner.active)
            self.assertEqual(capture.call_count, 0)
            runner.feed(helper.state(row, 'aim'))
            self.assertEqual(len(files), 2)
            runner.feed(helper.state(row)); runner.feed(helper.state(row, 'aim'))
            self.assertEqual(len(files), 0)
            self.assertEqual(runner.text, 'Done - 2 pictures saved')

    def test_gsi_capture_fields_are_optin_and_authenticated(self):
        from cs2cfg.overlay.gsi import parse_payload
        import json
        state = PictureWiring().state(load()['lineups'][0])
        state['auth'] = {'token': 'a'*64}
        raw = json.dumps(state).encode()
        ordinary = parse_payload(raw, 'a'*64)
        self.assertNotIn('mode', ordinary['map'])
        self.assertNotIn('player', ordinary)
        capture = parse_payload(raw, 'a'*64, pictures=True)
        self.assertTrue(pictures.offline_ready(capture))
        self.assertIn('position', capture['player'])
        with self.assertRaises(PermissionError): parse_payload(raw, 'b'*64, pictures=True)


class StrictPracticeLaunch(unittest.TestCase):
    def test_no_argumentless_fallback_for_picture_launch(self):
        from cs2cfg import launcher
        with mock.patch.object(launcher, 'steam_exe', return_value=None), mock.patch.object(launcher.os, 'startfile', create=True) as start:
            with self.assertRaises(launcher.LaunchError):
                launcher.launch_via_steam('+map de_mirage +exec cs2cfg_lineup_shots', require_args=True)
            start.assert_not_called()


class PictureButton(unittest.TestCase):
    def test_button_launches_only_from_closed_game_in_temporary_install(self):
        from cs2cfg import webui
        import threading
        import types
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)/'steamapps/common/CS2'
            cfg = install/'game/csgo/cfg'; cfg.mkdir(parents=True)
            overlay = types.SimpleNamespace(_lock=threading.RLock(), picture_session=None,
                _settings={'overlay_enabled': True, 'overlay_tools': ['lineups']},
                _configure_gsi=mock.Mock(), _gsi_token='a'*64, _gsi_notice='')
            state = types.SimpleNamespace(overlay=overlay, cs2_install=install, users=[])
            with mock.patch('cs2cfg.steam.cs2_running', return_value=True), mock.patch('cs2cfg.launcher.launch_via_steam') as launch:
                self.assertFalse(webui._lineups_pictures(state, {})['available'])
                self.assertEqual(list(cfg.iterdir()), []); launch.assert_not_called()
            with mock.patch('cs2cfg.steam.cs2_running', return_value=False), mock.patch('cs2cfg.launcher.launch_via_steam') as launch, mock.patch('cs2cfg.lineups.pictures.game_build', return_value='test'), mock.patch('cs2cfg.paths.user_data_dir', return_value=Path(tmp)/'cache'):
                self.assertTrue(webui._lineups_pictures(state, {'key': 'F8'})['available'])
                launch.assert_called_once_with('+map de_mirage +exec cs2cfg_lineup_shots', require_args=True)
                self.assertEqual(set(p.name for p in cfg.iterdir()), {pictures.SHOTS_CFG, pictures.UNDO_CFG})
                session = overlay.picture_session
                session.feed({'provider': {'appid': 730}, 'map': {'name': 'de_mirage', 'mode': 'casual'}})
                self.assertFalse(session.active); self.assertEqual(list(cfg.iterdir()), [])
            overlay._settings['overlay_enabled'] = False
            with mock.patch('cs2cfg.steam.cs2_running') as running:
                self.assertFalse(webui._lineups_pictures(state, {})['available'])
                running.assert_not_called()


if __name__ == "__main__": unittest.main()
