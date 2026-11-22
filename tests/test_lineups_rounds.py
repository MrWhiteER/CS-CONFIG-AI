"""GSI card policy and native rendering with fake game frames only."""
import base64
import json
import time
import types
import unittest
import struct
import zlib
from unittest import mock
from cs2cfg import lineups
from cs2cfg.lineups import native, radar, rounds
from cs2cfg.overlay import gsi, pinned, settings
from cs2cfg.overlay.service import OverlayService


class RoundCard(unittest.TestCase):
    def setUp(self):
        self.service=OverlayService()
        self.service._settings.update(overlay_enabled=True,overlay_tools=['settings','lineups'])
        self.service._gsi_token='a'*64

    def send(self,phase='freezetime',side='T',map_name='de_mirage',map_phase='live',player='local'):
        self.service.receive_gsi(json.dumps({'auth':{'token':'a'*64},
            'provider':{'steamid':'local'},'player':{'steamid':player,'team':side},
            'map':{'name':map_name,'phase':map_phase},'round':{'phase':phase}}).encode())
        return self.service.lineups_state()

    def test_buy_warmup_live_pin_and_optout(self):
        self.assertTrue(self.send()['show'])
        self.assertFalse(self.send('live')['show'])
        self.assertTrue(self.send('live',map_phase='warmup')['show'])
        self.service._settings['overlay_lineups_round_start']=False
        self.assertFalse(self.send()['show'])
        self.service._settings['overlay_layout']={'lineups':{'pinned':True}}
        self.assertTrue(self.send('live')['show'])

    def test_switch_side_map_spectator_and_missing(self):
        self.assertEqual(self.send(side='CT')['side'],'CT')
        self.assertEqual(self.send(map_name='de_inferno')['name'],'Inferno')
        self.assertFalse(self.send(side='spectator')['show'])
        self.assertFalse(self.send(player='someone else')['show'])
        self.assertFalse(self.send(map_name='unknown')['show'])
        self.assertFalse(self.send(map_phase='gameover')['show'])
        self.send()
        self.service._game_state.received=time.monotonic()-16
        self.assertFalse(self.service.lineups_state()['show'])

    def test_disabled_never_reads_and_team_parsing_is_optin(self):
        self.service._settings['overlay_tools']=['settings']
        self.send()
        self.assertNotIn('team',self.service._game_state.state['player_id'])
        with mock.patch('cs2cfg.lineups.load') as source:
            self.service._update_lineups(None,True,{})
        source.assert_not_called()
        self.assertFalse(self.service.lineups_state()['show'])
        self.assertNotIn('lineups',settings.read()['overlay_tools'])
        self.assertTrue(settings.read()['overlay_lineups_round_start'])

    def test_native_auto_open_fold_pin_and_hide(self):
        self.send()
        self.service._hud=mock.Mock()
        self.service._hud.pin_requested.return_value=True
        self.service.panel=types.SimpleNamespace(visible=False)
        found=types.SimpleNamespace(rect=(0,0,1280,900))
        with mock.patch('cs2cfg.overlay.hud.Hud') as create:
            widget=create.return_value
            self.service._update_lineups(found,True,{'theme':'daylight'})
            create.assert_called_once()
            self.assertEqual(len(widget.update.call_args.args[0]['rows']),12)
            self.assertTrue(widget.set_allowed.call_args.args[0])
            self.send('live')
            self.service._update_lineups(found,True,{})
            self.assertFalse(widget.set_allowed.call_args.args[0])
            self.service._settings['overlay_layout']={'lineups':{'pinned':True,'opacity':27}}
            self.service._update_lineups(found,True,{})
            self.assertTrue(widget.set_allowed.call_args.args[0])
            self.assertEqual(widget.configure.call_args.kwargs['opacity'],27)
            self.service.panel.visible=True
            self.service._update_lineups(found,True,{})
            self.assertFalse(widget.set_allowed.call_args.args[0])


class NativeRadar(unittest.TestCase):
    def test_rgb_png_filter_reference_vectors(self):
        first=bytes([10,20,30,40,50,60]);second=bytes([15,25,35,45,55,65])
        encoded=[(first,second),
                 (bytes([10,20,30,30,30,30]),bytes([15,25,35,30,30,30])),
                 (first,bytes([5]*6)),
                 (bytes([10,20,30,35,40,45]),bytes([10,15,20,18,18,18])),
                 (bytes([10,20,30,30,30,30]),bytes([5]*6))]
        def chunk(tag,data):
            return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data))
        expected=b''.join(bytes((*row[x:x+3],255)) for row in (first,second) for x in (0,3))
        for kind,(a,b) in enumerate(encoded):
            raw=(radar.mapart.PNG_START+chunk(b'IHDR',struct.pack('>IIBBBBB',2,2,8,2,0,0,0))
                 +chunk(b'IDAT',zlib.compress(bytes([kind])+a+bytes([kind])+b))+chunk(b'IEND',b''))
            with self.subTest(kind=kind): self.assertEqual(native.decode_png(raw),(2,2,expected))

    def test_fake_frame_png_and_raster(self):
        raw=radar.png(2,2,bytes([100,150,200,255])*4)
        self.assertEqual(native.decode_png(raw),(2,2,bytes([100,150,200,255])*4))
        art={'image':'data:image/png;base64,'+base64.b64encode(raw).decode(),
             'overview':lineups.load()['overview']}
        rows=lineups.load()['lineups']
        model=pinned.render('lineups',{'round':{'name':'Mirage','side':'T'},'rows':rows,'art':art})
        self.assertEqual(len(model['raster']),336*336*4)
        self.assertIn('Mirage', ' '.join(model['lines']))
        self.assertIn(bytes([200,150,100,255]),model['raster'])
        with self.assertRaises(ValueError): native.decode_png(b'not an image')

    def test_missing_image_plain_list(self):
        model=pinned.render('lineups',{'round':{'name':'Mirage','side':'CT'},'rows':[]})
        self.assertNotIn('raster',model)
        self.assertIn('No smokes for this side yet',model['lines'])


if __name__=='__main__': unittest.main()
