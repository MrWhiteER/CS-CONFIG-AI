"""Regression cases from the 1.26.8 audit, using disposable data only."""
from pathlib import Path
import concurrent.futures
import tempfile
import unittest
from unittest import mock

from cs2cfg import autosync, backup, cfglang, cfgscan, fileio, mapconfig, scriptgen, scriptdebug, webui
from tests.test_autosync import PC, FakeCloud, ACCOUNT


class AuditHardening(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_encoding_error_preserves_original(self):
        path = self.root / 'legacy.cfg'
        original = '// café\n'.encode('cp1252')
        path.write_bytes(original)
        with self.assertRaises(UnicodeEncodeError):
            cfglang.write_config_text(path, '// café 🎮\n', 'cp1252')
        self.assertEqual(path.read_bytes(), original)

    def test_failed_replace_preserves_original_and_cleans_temp(self):
        path = self.root / 'autoexec.cfg'
        path.write_bytes(b'original')
        with mock.patch.object(fileio.os, 'replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                fileio.write_text(path, 'new')
        self.assertEqual(path.read_bytes(), b'original')
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_revision_check_rejects_stale_editor_even_when_force_is_true(self):
        folder = self.root / 'cfg' / 'me'
        folder.mkdir(parents=True)
        path = folder / 'settings.cfg'
        path.write_text('sensitivity 1\n')
        state = mock.Mock(cfg_scan=cfgscan.scan(folder, cfg_root=folder.parent))
        path.write_text('sensitivity 2\nvolume 0.6\n')
        out = webui._cfg_save(state, {'path': 'me/settings.cfg', 'text': 'sensitivity 1\n', 'force': True})
        self.assertTrue(out['conflict'])
        self.assertIn('volume', path.read_text())

    def test_failed_pull_stays_pending_and_cannot_push_stale_files(self):
        cloud = FakeCloud()
        home, work = PC(self.root, 'home'), PC(self.root, 'work')
        for pc, text in ((home, 'echo NEW\n'), (work, 'echo OLD\n')):
            folder = pc.cfg / 'mrwhiteer'
            folder.mkdir()
            (folder / 'autoexec.vcfg').write_text(text)
            pc.prefs['ui']['cfg_write_ok'] = True
            pc.ui().update(cfg_folder=str(folder), intent='competitive')
        with mock.patch.object(backup, 'backups_root', return_value=self.root/'backups'):
            home.sync(cloud)
            with mock.patch('cs2cfg.cfglang.write_config_text', side_effect=PermissionError('locked')):
                failed = work.sync(cloud)
                retried = work.sync(cloud)
            self.assertFalse(failed['ok'])
            self.assertGreater(failed['waiting'], 0)
            self.assertEqual(retried['action'], 'pull')
            self.assertEqual(cloud.pushes, 1)
            recovered = work.sync(cloud)
            self.assertEqual(recovered['action'], 'pull')
            self.assertIn('NEW', (work.cfg/'mrwhiteer'/'autoexec.vcfg').read_text())

    def test_direct_and_indirect_recursion_are_blocked(self):
        spec = dict(name='Audit', mode='press', binding='scancode13', steps=[{'id':'cmd:slot1'}])
        for text in ('alias "audit" "audit"', 'alias "audit" "audit_next"\nalias "audit_next" "audit"'):
            built = scriptgen.build(dict(spec, lines_text=text))
            self.assertFalse(built.ok)
            self.assertTrue(any('Recursive alias' in c.text for c in built.checks))

    def test_unreachable_release_is_blocked(self):
        built = scriptgen.build(dict(name='Audit', mode='press', binding='scancode13',
            steps=[{'id':'cmd:slot1'}], lines_text='alias "audit" "+duck"\nalias "audit_unused" "-duck"'))
        self.assertFalse(built.ok)
        self.assertTrue(any('reachable release' in c.text for c in built.checks))

    def test_stateful_toggle_simulates_both_presses_without_recursion(self):
        lines = ['alias "audit" "audit_on"', 'alias "audit_on" "+duck; alias audit audit_off"',
                 'alias "audit_off" "-duck; alias audit audit_on"']
        out = scriptdebug.simulate(lines, 'audit', mode='toggle')
        self.assertEqual(out['events'][0]['held'], ['duck'])
        self.assertEqual(out['held'], [])
        self.assertEqual(out['errors'], [])

    def test_documented_input_pairs_are_blocked(self):
        for pair in (('+jump','+use'), ('+attack','+reload')):
            built = scriptgen.build(dict(name='Audit', mode='hold', binding='scancode13',
                steps=[{'id':'cmd:'+x} for x in pair]))
            self.assertFalse(built.ok)
            self.assertTrue(any('CS2 blocks' in c.text for c in built.checks))

    def test_map_reset_uses_baseline_and_does_not_guess_unknown_values(self):
        folder = self.root/'cfg'/'me'
        folder.mkdir(parents=True)
        (folder/'autoexec.cfg').write_text('bind f6 "exec me/practice.cfg"\n')
        (folder/'practice.cfg').write_text('bind mouse1 noclip\nsensitivity 5\nbind f7 say\n')
        scan = cfgscan.scan(folder, cfg_root=folder.parent)
        with mock.patch.object(mapconfig, '_store', return_value=self.root/'maps.json'):
            setups = [{'file':'me/practice.cfg'}]
            text = mapconfig.reset_text(scan,setups)
            self.assertIn('bind "mouse1" "+attack"',text)
            self.assertNotIn('unbind "f7"',text)
            self.assertIn('Baseline unavailable',text)
            mapconfig.remember_baseline(scan, {'f7':''}, {'sensitivity':'1.2'})
            text = mapconfig.reset_text(scan,setups)
            self.assertIn('sensitivity "1.2"',text)
            self.assertIn('unbind "f7"',text)
            self.assertNotIn('Baseline unavailable',text)

    def test_concurrent_state_updates_are_serialized(self):
        with mock.patch.object(mapconfig, '_store', return_value=self.root/'maps.json'):
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(lambda n: mapconfig.update({str(n): n}), range(20)))
            result = mapconfig.load()
            self.assertTrue(all(result[str(n)] == n for n in range(20)))
            self.assertFalse(list(self.root.glob('*.tmp')))


if __name__ == '__main__':
    unittest.main()
