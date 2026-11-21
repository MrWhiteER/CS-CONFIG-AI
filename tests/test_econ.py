"""Agents, stickers, graffiti, patches, charms and music kits read from the
game's own items_game.txt, plus the real item pictures and music kit songs
(cs2cfg.econ, cs2cfg.vtex)."""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import econ, skins_catalog, vtex  # noqa: E402

ITEMS = r'''
"items_game"
{
	"items"
	{
		"4619"
		{
			"name"		"customplayer_tm_balkan_variantk"
			"prefab"		"customplayertradable"
			"item_name"		"#CSGO_CustomPlayer_tm_balkan_variantk"
			"item_rarity"		"ancient"
			"image_inventory"		"econ/characters/customplayer_tm_balkan_variantk"
			"used_by_classes"
			{
				"terrorists"		"1"
			}
		}
		"4711"
		{
			"name"		"customplayer_ctm_fbi_variantb"
			"prefab"		"customplayertradable"
			"item_name"		"#CSGO_CustomPlayer_ctm_fbi_variantb"
			"item_rarity"		"rare"
			"used_by_classes"
			{
				"counter-terrorists"		"1"
			}
		}
		"7"
		{
			"name"		"weapon_knife"
			"prefab"		"melee"
		}
	}
	"sticker_kits"
	{
		"0"
		{
			"name"		"default"
			"item_name"		"#StickerKit_Default"
		}
		"1"
		{
			"name"		"kat2014_ibp_holo"
			"item_name"		"#StickerKit_kat2014_ibp_holo"
			"sticker_material"		"katowice2014/ibuypower_holo"
			"item_rarity"		"legendary"
		}
		"2"
		{
			"name"		"spray_ggwp"
			"item_name"		"#SprayKit_ggwp"
			"sticker_material"		"default/ggwp"
			"item_rarity"		"common"
		}
		"3"
		{
			"name"		"patch_dragon"
			"item_name"		"#PatchKit_dragon"
			"patch_material"		"case01/dragon"
			"item_rarity"		"mythical"
		}
		"4"
		{
			"name"		"plain_one"
			"item_name"		"#StickerKit_plain_one"
			"sticker_material"		"set/plain_one"
			"item_rarity"		"rare"
		}
	}
	"music_definitions"
	{
		"3"
		{
			"name"		"valve_csgo_01"
			"loc_name"		"#musickit_valve_csgo_01"
			"loc_description"		"#musickit_valve_csgo_01_desc"
			"image_inventory"		"econ/music_kits/valve_csgo_01"
		}
		"4"
		{
			"name"		"no_text_kit"
			"loc_name"		"#musickit_missing"
		}
	}
}
'''

TOKENS = {
    "csgo_customplayer_tm_balkan_variantk": "The Doctor' Romanov | Sabre",
    "csgo_customplayer_ctm_fbi_variantb": "Special Agent Ava | FBI",
    "stickerkit_kat2014_ibp_holo": "iBUYPOWER (Holo) | Katowice 2014",
    "spraykit_ggwp": "GGWP",
    "patchkit_dragon": "Dragon",
    "stickerkit_plain_one": "Plain One",
    "musickit_valve_csgo_01": "CS:GO",
    "musickit_valve_csgo_01_desc": "Valve",
}


def _mp3(frames=6):
    # MPEG 1 layer III, 128 kbps, 44.1 kHz: 417 bytes per frame.
    frame = b"\xff\xfb\x90\x00" + b"\x11" * 413
    return frame * frames


class ReadingTheExtraItems(unittest.TestCase):
    def setUp(self):
        self.items = econ.extra_items(ITEMS, TOKENS)
        self.by = {it["paintkit"]: it for it in self.items}

    def test_agents_get_their_side_and_agent_rarity_names(self):
        doc = self.by["customplayer_tm_balkan_variantk"]
        self.assertEqual(doc["kind"], "agent")
        self.assertEqual(doc["weapon_name"], "Terrorist")
        self.assertEqual(doc["rarity"], "Master")
        ava = self.by["customplayer_ctm_fbi_variantb"]
        self.assertEqual(ava["weapon_name"], "Counter-Terrorist")
        self.assertEqual(ava["rarity"], "Distinguished")
        self.assertIn("panorama/images/econ/characters/customplayer_ctm_fbi_variantb_png.vtex_c",
                      ava["_pictures"])

    def test_non_agent_items_are_left_out(self):
        self.assertNotIn("weapon_knife", self.by)

    def test_stickers_graffiti_and_patches_are_told_apart(self):
        self.assertEqual(self.by["kat2014_ibp_holo"]["kind"], "sticker")
        self.assertEqual(self.by["kat2014_ibp_holo"]["weapon_name"], "Holo")
        self.assertEqual(self.by["plain_one"]["weapon_name"], "Paper")
        self.assertEqual(self.by["spray_ggwp"]["kind"], "graffiti")
        self.assertEqual(self.by["spray_ggwp"]["display_name"], "Graffiti | GGWP")
        self.assertEqual(self.by["patch_dragon"]["kind"], "patch")
        self.assertIn("panorama/images/econ/patches/case01/dragon_png.vtex_c",
                      self.by["patch_dragon"]["_pictures"])
        self.assertNotIn("default", self.by)

    def test_music_kits_get_name_artist_and_picture(self):
        kit = self.by["valve_csgo_01"]
        self.assertEqual(kit["kind"], "music")
        self.assertEqual(kit["skin_name"], "CS:GO")
        self.assertEqual(kit["artist"], "Valve")
        self.assertNotIn("no_text_kit", self.by)

    def test_no_visible_text_is_an_internal_token(self):
        for it in self.items:
            for field in ("skin_name", "display_name", "weapon_name", "rarity"):
                self.assertNotIn("#", it[field])
                self.assertNotRegex(it[field], r"^[a-z0-9_]+$")

    def test_picture_names_are_safe(self):
        for it in self.items:
            self.assertRegex(it["art"], econ._SAFE_ID.pattern)


class CatalogCarriesPictures(unittest.TestCase):
    def setUp(self):
        skins_catalog.forget_all()
        self.addCleanup(skins_catalog.forget_all)
        lang = '"lang" { "Tokens" {' + "".join(f'"{k}" "{v}"\n' for k, v in TOKENS.items()) + "} }"
        patch = mock.patch.object(
            skins_catalog, "_load_text",
            side_effect=lambda _v, p: ITEMS if p == skins_catalog.ITEMS_GAME_PATH else lang)
        patch.start()
        self.addCleanup(patch.stop)

    def test_every_item_has_a_picture_name_the_server_can_resolve(self):
        items = skins_catalog.build(Path("fake.vpk"))
        self.assertTrue(any(it["kind"] == "knife" for it in items))
        self.assertTrue(any(it["kind"] == "music" for it in items))
        for it in items:
            self.assertNotIn("_pictures", it)
            self.assertTrue(skins_catalog.pictures_for(Path("fake.vpk"), it["art"]), it["art"])

    def test_knife_and_glove_pictures_point_at_the_generated_icons(self):
        skins_catalog.build(Path("fake.vpk"))
        knife = skins_catalog.pictures_for(Path("fake.vpk"), "knife__weapon_knife_karambit__aa_fade")
        self.assertEqual(knife[0], econ.GENERATED + "weapon_knife_karambit_aa_fade_light_png.vtex_c")
        glove = skins_catalog.pictures_for(Path("fake.vpk"), "glove__glove_sport__sporty_blue_pink")
        self.assertEqual(glove[0], econ.GENERATED + "sporty_gloves_sporty_blue_pink_light_png.vtex_c")

    def test_an_unknown_picture_name_gives_nothing(self):
        self.assertEqual(skins_catalog.pictures_for(Path("fake.vpk"), "gun__../../etc"), [])


PNG = vtex.to_png(1, 1, b"\x10\x20\x30\xff")


class CuttingPictures(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.vpk = self.tmp / "pak01_dir.vpk"
        self.vpk.write_bytes(b"x")

    def _picture(self, index, art_id, candidates):
        with mock.patch.object(econ.vpk, "read_index", return_value=index), \
             mock.patch.object(econ.vpk, "read_file", side_effect=lambda _v, e: b"RED2" + b"\0" * 40 + PNG):
            return econ.picture(self.vpk, self.tmp / "data", art_id, candidates)

    def test_the_embedded_png_is_cut_out_and_kept(self):
        index = {"panorama/images/econ/x/a_png.vtex_c": "e"}
        out = self._picture(index, "sticker__a", ["panorama/images/econ/x/a_png.vtex_c"])
        self.assertEqual(out.read_bytes(), PNG)

    def test_a_picture_in_another_folder_is_still_found_by_name(self):
        index = {"panorama/images/econ/moved/a_png.vtex_c": "e"}
        out = self._picture(index, "sticker__a", ["panorama/images/econ/x/a_png.vtex_c"])
        self.assertIsNotNone(out)

    def test_no_picture_is_remembered_and_answers_none(self):
        self.assertIsNone(self._picture({}, "sticker__b", ["panorama/images/econ/x/b_png.vtex_c"]))
        self.assertTrue((self.tmp / "data" / "item-art" / "sticker__b.none").is_file())

    def test_unsafe_names_are_refused(self):
        self.assertIsNone(self._picture({}, "../x", ["a"]))
        self.assertIsNone(econ.picture(None, self.tmp, "sticker__a", ["a"]))

    def test_raw_bgra_pixels_become_a_png(self):
        # A minimal Source 2 resource: one DATA block with a 1x1 BGRA texture.
        block_dir = 16
        data_at = 40
        header = struct.pack("<IHHII", 0, 12, 0, block_dir - 8, 1)
        entry = struct.pack("<4sII", b"DATA", data_at - (block_dir + 4), 40)
        tex = struct.pack("<HH", 1, 0) + b"\0" * 16 + struct.pack("<HHHBB", 1, 1, 1, 28, 1)
        tex += b"\0" * 4 + struct.pack("<II", 0, 0)
        raw = header + entry + b"\0" * (data_at - len(header) - len(entry)) + tex
        raw += b"\0" * (data_at + 40 - len(raw)) + bytes((0x30, 0x20, 0x10, 0xff))
        self.assertEqual(vtex.picture(raw), PNG)


class MusicKitSongs(unittest.TestCase):
    INDEX = {
        "sounds/music/valve_csgo_01/mainmenu.vsnd_c": "a",
        "sounds/music/valve_csgo_01/roundmvpanthem_01.vsnd_c": "b",
        "sounds/music/valve_csgo_01/wonround.vsnd_c": "c",
        "sounds/music/valve_csgo_01/something_new.vsnd_c": "d",
        "sounds/music/other/mainmenu.vsnd_c": "e",
    }

    def setUp(self):
        econ._SONG_CACHE.clear()
        self.addCleanup(econ._SONG_CACHE.clear)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.vpk = Path(tmp.name) / "pak01_dir.vpk"
        self.vpk.write_bytes(b"x")
        patch = mock.patch.object(econ.vpk, "read_index", return_value=self.INDEX)
        patch.start()
        self.addCleanup(patch.stop)

    def test_the_mvp_song_comes_first_with_plain_names(self):
        parts = econ.song_parts(self.vpk, "valve_csgo_01")
        self.assertEqual([p["label"] for p in parts], ["MVP song", "Main menu", "Round won"])
        self.assertEqual(parts[0]["part"], "roundmvpanthem_01")

    def test_a_kit_without_songs_has_no_parts(self):
        self.assertEqual(econ.song_parts(self.vpk, "missing"), [])
        self.assertEqual(econ.song_parts(None, "valve_csgo_01"), [])

    def test_only_listed_parts_are_served(self):
        with mock.patch.object(econ.vpk, "read_file", return_value=b"hdr" + _mp3()):
            self.assertIsNone(econ.song(self.vpk, "valve_csgo_01", "something_new"))
            data, kind = econ.song(self.vpk, "valve_csgo_01", "roundmvpanthem_01")
        self.assertEqual(kind, "audio/mpeg")
        self.assertEqual(data, _mp3())

    def test_wav_inside_a_sound_file_is_cut_out(self):
        wav = b"RIFF" + struct.pack("<I", 8) + b"WAVEdata"
        self.assertEqual(econ.cut_song(b"junk" + wav + b"tail"), (wav, "audio/wav"))

    def test_stray_ff_bytes_are_not_mistaken_for_a_song(self):
        self.assertIsNone(econ.cut_song(b"\xff\xfb\x90\x00" + b"\0" * 100))


if __name__ == "__main__":
    unittest.main()
