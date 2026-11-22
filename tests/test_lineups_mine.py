"""All persistence tests use a temporary user-data directory, never CS2."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cs2cfg.lineups import load, validate
from cs2cfg.lineups import mine


class Personal(unittest.TestCase):
    def test_radar_only_points_are_personal_and_bounded(self):
        doc = load()
        row = doc['lineups'][0]
        row.update(mine=True, aim=None, stand={'radar_x': 300, 'radar_y': 500}, land=None)
        validate(doc)
        row['land'] = {'radar_x': 600, 'radar_y': 700}
        validate(doc)
        for bad in (float('nan'), -1, 2000):
            row['stand']['radar_x'] = bad
            with self.assertRaises(ValueError): validate(doc)
        row['stand']['radar_x'] = 300
        row.pop('mine')
        row['aim'] = {'pitch': 0, 'yaw': 0}
        with self.assertRaisesRegex(ValueError, 'Invalid point'): validate(doc)

    def test_save_edit_delete_restore_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(mine, 'user_data_dir', return_value=Path(tmp)):
            row = copy.deepcopy(load()['lineups'][0])
            row.pop('id'); row.update(aim=None, land=None, steps=['Stand beside your chosen wall.'])
            saved = mine.save('mirage', row)
            self.assertTrue(saved['mine'])
            self.assertEqual(len(mine.combined('mirage')['lineups']), 19)
            validate(mine.personal('mirage'))
            saved['name'] = 'My corner'
            mine.save('mirage', saved)
            removed = mine.delete('mirage', saved['id'])
            self.assertEqual(len(mine.combined('mirage')['lineups']), 18)
            mine.restore('mirage', removed)
            self.assertEqual(mine.personal('mirage')['lineups'][0]['name'], 'My corner')
            self.assertTrue((Path(tmp)/'lineups/mine/mirage.json').is_file())
            with self.assertRaises(ValueError): mine.save('../escape', saved)
            with self.assertRaises(ValueError): mine.delete('mirage', load()['lineups'][0]['id'])

    def test_invalid_save_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(mine, 'user_data_dir', return_value=Path(tmp)):
            row = copy.deepcopy(load()['lineups'][0]); row.pop('id')
            saved = mine.save('mirage', row)
            before = (Path(tmp)/'lineups/mine/mirage.json').read_bytes()
            saved['stand']['x'] = float('nan')
            with self.assertRaises(ValueError): mine.save('mirage', saved)
            self.assertEqual((Path(tmp)/'lineups/mine/mirage.json').read_bytes(), before)
