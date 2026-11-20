"""Lineup contracts: no game, app launch, or game configuration writes."""
import copy
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from cs2cfg import lineups
from cs2cfg.lineups import radar


class Data(unittest.TestCase):
    def test_seed_fields_bounds_counts_and_detached_load(self):
        doc = lineups.load('de_mirage')
        self.assertEqual(lineups.validate(doc), doc)
        self.assertEqual(sum(r['side']=='T' for r in doc['lineups']),12)
        self.assertEqual(sum(r['side']=='CT' for r in doc['lineups']),1)
        self.assertTrue(all(not r['checked'] for r in doc['lineups']))
        doc['lineups'].clear()
        self.assertEqual(len(lineups.load()['lineups']),13)
        self.assertIsNone(lineups.load('../../anything'))

    def test_invalid_fields_and_command_text(self):
        for key in lineups.load()['lineups'][0]:
            doc=lineups.load(); del doc['lineups'][0][key]
            with self.subTest(missing=key), self.assertRaises(ValueError): lineups.validate(doc)
        for key,value in [('name','de_mirage'),('steps',['setpos 1 2 3']),
                          ('checked',1),('type','smokegrenade'),('aim',{'pitch':float('nan'),'yaw':1}),
                          ('stand',{'x':999999,'y':0,'z':0})]:
            doc=lineups.load()
            doc['lineups'][0][key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                lineups.validate(doc)
        doc=lineups.load()
        doc['lineups'].append(copy.deepcopy(doc['lineups'][0]))
        with self.assertRaises(ValueError): lineups.validate(doc)

    def test_instruction_quality(self):
        for field, value in [('area', 'Mid site'),
                             ('steps', ['Stand by T spawn.', 'Stand by T spawn.']),
                             ('steps', ['Stand at the marked point on the radar.']),
                             ('steps', ['Aim at the corner.'])]:
            doc=lineups.load(); doc['lineups'][0][field]=value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                lineups.validate(doc)

    def test_synonyms_and_filters(self):
        row={**lineups.load()['lineups'][0], 'name':'Default corner','area':'B','type':'fire'}
        for query in ('b site molly','B molotov','incendiary','fire'):
            self.assertEqual(lineups.search([row],query,'T'),[row])
        self.assertEqual(lineups.search([row],'','CT'),[])
        self.assertEqual(lineups.search([row],'','','smoke'),[])
        for kind, terms in [('grenade',['nade','he','grenade']),('flash',['flash','pop'])]:
            row['type']=kind
            for term in terms: self.assertEqual(lineups.search([row],term),[row])


class Radar(unittest.TestCase):
    def test_lz4_literals_matches_and_limits(self):
        self.assertEqual(radar.lz4(b'\x40abcd',4),b'abcd')
        self.assertEqual(radar.lz4(b'\x40abcd\x04\x00',8),b'abcdabcd')
        for raw,size in [(b'\x40abc',4),(b'\x00\x00\x00',4),(b'\x40abcd',3)]:
            with self.subTest(raw=raw), self.assertRaises(ValueError): radar.lz4(raw,size)

    def test_transform(self):
        o={'pos_x':-3230,'pos_y':1713,'scale':5}
        self.assertEqual(lineups.pixel({'x':-3230,'y':1713},o),(0,0))
        self.assertEqual(lineups.pixel({'x':-2230,'y':713},o),(200,200))

    def test_bc1_color_and_transparency(self):
        red=struct.pack('<HHI',0xf800,0,0)
        self.assertEqual(radar.decode_blocks(red,4,4), bytes([255,0,0,255])*16)
        transparent=struct.pack('<HHI',0,0xffff,0xffffffff)
        self.assertEqual(radar.decode_blocks(transparent,4,4),bytes(64))
        with self.assertRaises(ValueError): radar.decode_blocks(red[:7],4,4)

    def test_bc3_alpha_and_partial_blocks(self):
        block=bytes([255,0])+bytes(6)+struct.pack('<HHI',0x07e0,0,0)
        self.assertEqual(radar.decode_blocks(block,2,3,True),bytes([0,255,0,255])*6)
        block=bytes([0,255])+int(7*(sum(1<<(i*3) for i in range(16)))).to_bytes(6,'little')+struct.pack('<HHI',0x07e0,0,0)
        self.assertEqual(radar.decode_blocks(block,4,4,True)[3],255)

    def test_compiled_texture_and_missing_format(self):
        header=struct.pack('<IHHII',76,12,1,8,1)
        directory=struct.pack('<4sII',b'DATA',8,40)
        texture=struct.pack('<HH4fHHHBBIII',1,0,0,0,0,0,4,4,1,1,1,0,0,0)
        raw=header+directory+texture+struct.pack('<HHI',0xf800,0,0)
        self.assertTrue(radar.cut_texture(raw).startswith(radar.mapart.PNG_START))
        self.assertIsNone(radar.cut_texture(b'broken'))
        self.assertIsNone(radar.cut_texture(raw[:-1]))

    def test_bgra_raw_and_lz4(self):
        import zlib
        pixels=bytes([3,2,251,255,240,20,10,128])
        for compressed in (False, True):
            payload=bytes([0x80])+pixels if compressed else pixels
            size=68 if compressed else 40
            header=struct.pack('<IHHII',28+size+len(payload),12,1,8,1)
            directory=struct.pack('<4sII',b'DATA',8,size)
            texture=struct.pack('<HH4fHHHBBIII',1,0,0,0,0,0,2,1,1,28,1,0,8 if compressed else 0,1 if compressed else 0)
            extra=struct.pack('<III',4,8,16)+struct.pack('<IIII',1,8,1,len(payload)) if compressed else b''
            result=radar.cut_texture(header+directory+texture+extra+payload)
            self.assertIsNotNone(result)
            at=result.index(b'IDAT')
            length=struct.unpack_from('>I',result,at-4)[0]
            self.assertEqual(zlib.decompress(result[at+4:at+4+length]),b'\0'+bytes([251,2,3,255,10,20,240,128]))

    def test_overview_and_art_missing(self):
        self.assertEqual(radar.read_overview('"de_mirage" { "pos_x" "-3230" "pos_y" "1713" "scale" "5" }')['scale'],5)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(radar.picture(None,Path(tmp),'mirage'))
            self.assertEqual(list(Path(tmp).iterdir()),[])
        self.assertEqual(radar.draw(None,[]),'')

    def test_cache_and_annotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); package=root/'pak01_dir.vpk'; package.write_bytes(b'x')
            image=radar.png(1,1,bytes([255,0,0,255]))
            index={'resource/overviews/de_mirage.txt':'overview',
                   'panorama/images/overheadmaps/de_mirage_radar.vtex_c':'image'}
            def read(_,entry):
                return image if entry=='image' else b'"Mirage" { "pos_x" "-3230" "pos_y" "1713" "scale" "5" }'
            with mock.patch.object(radar.vpk,'read_index',return_value=index), mock.patch.object(radar.vpk,'read_file',side_effect=read) as source:
                art=radar.picture(package,root,'mirage')
                self.assertEqual(radar.picture(package,root,'mirage'),art)
                self.assertEqual(source.call_count,2)
                package.touch()
            svg=radar.draw(art,lineups.load()['lineups'][:1])
            self.assertIn('<image',svg)
            self.assertIn('stroke-dasharray',svg)
            self.assertIn('Window',svg)


if __name__ == '__main__': unittest.main()
