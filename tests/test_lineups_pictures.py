"""No real game discovery, config writes, capture, launch or waits."""
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

    def test_action_never_touches_game_or_disk(self):
        with mock.patch('pathlib.Path.write_text') as write:
            self.assertFalse(pictures.request(enabled=False)['available'])
            self.assertFalse(pictures.request(enabled=True)['available'])
        write.assert_not_called()

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


if __name__ == '__main__': unittest.main()
