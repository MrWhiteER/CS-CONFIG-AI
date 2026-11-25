"""Exercise new tools against disposable recordings, configs and game files."""
import base64
import io
import json
import os
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cs2cfg import autosync, benchmarks, cfgscan, mapconfig, workbench, webui
from tests.test_autosync import PC, FakeCloud, ACCOUNT


class ToolsCase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.folder=self.root/'cfg'/'me'
        self.folder.mkdir(parents=True)
        (self.folder/'autoexec.cfg').write_text('sensitivity 1\nbind mouse1 +attack\nbind f6 "exec me/practice.cfg"\n')
        (self.folder/'practice.cfg').write_text('bind mouse1 noclip\nsensitivity 5\n')
        self.state=SimpleNamespace(cfg_scan=cfgscan.scan(self.folder,cfg_root=self.folder.parent),
                                   cfg_folder='me',steam_root=None,cs2_install=None,users=[],machine=None)
        for owner,name,value in ((benchmarks,'_path',self.root/'bench.json'),
                                 (mapconfig,'_store',self.root/'maps.json'),
                                 (workbench,'_practice_path',self.root/'practice.json')):
            patch=mock.patch.object(owner,name,return_value=value)
            patch.start(); self.addCleanup(patch.stop)
        patch=mock.patch.object(webui,'_active_account',return_value='123')
        patch.start();self.addCleanup(patch.stop)

    def test_diagnostic_export_matches_preview_and_contains_no_credentials(self):
        preview=workbench.diagnostics(self.state,{})
        self.assertNotIn('token',preview['data'])
        data=workbench.diagnostics(self.state,{'action':'export','token':preview['token']})
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(data['data']))) as archive:
            self.assertEqual(json.loads(archive.read('diagnostics.json')),preview['data'])
            self.assertEqual(set(archive.namelist()),{'diagnostics.json','README.txt'})
        with self.assertRaises(ValueError):
            workbench.diagnostics(self.state,{'action':'export','token':'wrong'})
        self.state.diagnostic_preview['at']=time.time()-601
        with self.assertRaises(ValueError):
            workbench.diagnostics(self.state,{'action':'export','token':preview['token']})

    def test_redaction_removes_sensitive_keys_and_values(self):
        out=workbench.redact({'password':'abc','api_key':'xyz','nested':{'error':r'C:\Users\Ed\private\file.cfg'},
                             'note':'Bearer abcdef email@example.com access_token=hidden 76561198000000000'})
        rendered=json.dumps(out)
        for secret in ('abc','xyz','Users','email@example.com','hidden','76561198000000000'):
            self.assertNotIn(secret,rendered)

    def test_trace_distinguishes_startup_from_manually_loaded_config(self):
        with mock.patch('cs2cfg.history.entries',return_value=[]):
            out=workbench.config_trace(self.state,{'name':'sensitivity'})
        self.assertEqual(out['winner']['value'],'1')
        self.assertEqual(len(out['definitions']),2)
        self.assertFalse(next(r for r in out['definitions'] if r['value']=='5')['startup'])

    def test_trace_refuses_unrelated_undo(self):
        with mock.patch('cs2cfg.history.entries',return_value=[]), mock.patch('cs2cfg.history.swing') as swing:
            with self.assertRaises(ValueError):
                workbench.trace_undo(self.state,{'name':'sensitivity','id':'app:other'})
            swing.assert_not_called()

    def test_benchmark_is_consumed_once_and_context_is_recorded(self):
        benchmarks.arm('A','Mirage route',{'driver':'test','preset':'competitive'})
        record=benchmarks.claim({'intent':'competitive','resolution':'1920x1080'})
        self.assertEqual(record['slot'],'A')
        self.assertEqual(record['resolution'],'1920x1080')
        self.assertEqual(benchmarks.claim({}),{})

    def test_benchmark_requires_real_measurements_and_reports_variation(self):
        def run(identity,fps,preset):
            return {'stamp':identity,'duration':180,'resolution':'1920x1080','intent':preset,
                    'overlay':{'frame_count':20000,'avg_fps':fps,'one_percent_low':fps/2,'worst_frame_ms':40},
                    'benchmark':{'map':'Mirage','context':{'gpu':'same','preset':preset}}}
        sessions=[run('a1',100,'competitive'),run('a2',120,'competitive'),run('b',132,'quality')]
        out=benchmarks.compare(sessions,['a1','a2'],['b'])
        self.assertEqual(out['A']['avg_fps'],110)
        self.assertEqual(out['fps_change_percent'],20)
        self.assertEqual(out['A']['fps_range'],[100,120])
        self.assertFalse(any('Context differs' in warning for warning in out['warnings']))
        sessions[-1]['overlay']['frame_count']=10
        with self.assertRaises(ValueError): benchmarks.compare(sessions,['a1'],['b'])
        with self.assertRaises(ValueError): benchmarks.compare(sessions,['a1'],['a1'])

    def test_debugger_calls_production_builder_and_simulates_without_saving(self):
        built={'lines':['alias "+audit" "+duck"','alias "-audit" "-duck"'],'entry':'+audit'}
        with mock.patch.object(webui,'_scriptgen_check',return_value={'built':built}):
            out=workbench.script_debug(self.state,{'spec':{'mode':'hold'}})
        self.assertEqual(out['simulation']['events'][0]['held'],['duck'])
        self.assertEqual(out['simulation']['held'],[])
        self.assertEqual((self.folder/'autoexec.cfg').read_text(),'sensitivity 1\nbind mouse1 +attack\nbind f6 "exec me/practice.cfg"\n')

    def test_practice_verification_requires_fresh_saved_game_values(self):
        self.state.steam_root=self.root/'steam'
        self.state.users=[object()]
        game=self.state.steam_root/'userdata'/'123'/'730'/'local'/'cfg'
        game.mkdir(parents=True)
        keyfile=game/'cs2_user_keys_0_slot0.vcfg'
        settingsfile=game/'cs2_user_convars_0_slot0.vcfg'
        keyfile.write_text('"config" { "bindings" { "mouse1" "+attack" } }')
        settingsfile.write_text('"config" { "convars" { "sensitivity" "1" } }')
        with mock.patch('cs2cfg.quickfix._game_running',return_value=False),mock.patch.object(webui,'_refresh_apply_now'):
            started=workbench.practice(self.state,{'action':'start','file':'me/practice.cfg','map':'de_mirage'})
            self.assertEqual(started['session']['status'],'active')
            os.utime(keyfile,(1,1))
            with self.assertRaises(ValueError):workbench.practice(self.state,{'action':'verify'})
            workbench.practice(self.state,{'action':'end'})
            keyfile.write_text('"config" { "bindings" { "mouse1" "noclip" } }')
            settingsfile.write_text('"config" { "convars" { "sensitivity" "1" } }')
            failed=workbench.practice(self.state,{'action':'verify'})
            self.assertFalse(failed['verified'])
            self.assertIn('mouse1',failed['mismatches'])
            keyfile.write_text('"config" { "bindings" { "mouse1" "+attack" } }')
            done=workbench.practice(self.state,{'action':'verify'})
            self.assertTrue(done['verified'])
            self.assertEqual(mapconfig.load()['setups'],[])

    def test_explicit_sync_resolution_checks_the_compared_revisions(self):
        cloud=FakeCloud()
        pc=PC(self.root,'pc')
        pc.prefs['ui']['cfg_write_ok']=True
        pc.ui().update(intent='balanced')
        def run(**kwargs):
            return pc.sync(cloud,force=True,**kwargs)
        preview=run(preview=True)['comparison']
        pc.ui()['intent']='competitive'
        refused=run(resolution='push',expected_local=preview['local_hash'],expected_remote=preview['remote_hash'])
        self.assertFalse(refused['ok'])
        self.assertEqual(cloud.pushes,0)


if __name__=='__main__':
    unittest.main()
