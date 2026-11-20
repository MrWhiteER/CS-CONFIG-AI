"""No real game discovery, config writes, capture, launch or waits."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from cs2cfg.lineups import load
from cs2cfg.lineups import pictures


class Pictures(unittest.TestCase):
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
