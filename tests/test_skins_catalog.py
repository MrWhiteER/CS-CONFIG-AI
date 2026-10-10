"""Parsing the skin catalog out of a fixture items_game.txt, not the real
8MB file -- this is about the parsing logic, not any one account's install.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import skins_catalog  # noqa: E402

ITEMS_GAME = r'''
"items_game"
{
	"prefabs"
	{
		"weapon_ak47_prefab"
		{
			"item_class"		"weapon_ak47"
			"item_name"		"#SFUI_WPNHUD_AK47"
			"model_player"		"weapons/models/ak47/weapon_rif_ak47.vmdl"
		}
		"weapon_m4a1_prefab"
		{
			"item_class"		"weapon_m4a1"
			"item_name"		"#SFUI_WPNHUD_M4A1"
			"model_player"		"weapons/models/m4a4/weapon_rif_m4a4.vmdl"
		}
		"weapon_m4a1_silencer_prefab"
		{
			"item_class"		"weapon_m4a1"
			"anim_class"		"weapon_m4a1_silencer"
			"item_name"		"#SFUI_WPNHUD_M4_SILENCER"
			"model_player"		"weapons/models/m4a1_silencer/weapon_rif_m4a1_silencer.vmdl"
		}
	}
	"paint_kits"
	{
		"3"
		{
			"name"		"so_red"
			"description_tag"		"#PaintKit_so_red_Tag"
			"wear_remap_min"		"0.000000"
			"wear_remap_max"		"0.300000"
		}
	}
	"paint_kits_rarity"
	{
		"so_red"		"uncommon"
	}
	"item_sets"
	{
		"set_one"
		{
			"items"
			{
				"[so_red]weapon_ak47"		"1"
				"[so_red]weapon_m4a1_silencer"		"1"
			}
		}
	}
	"paint_kits"
	{
		"900"
		{
			"name"		"late_addition"
			"description_tag"		"#PaintKit_late_addition_Tag"
		}
	}
	"paint_kits_rarity"
	{
		"late_addition"		"legendary"
	}
	"item_sets"
	{
		"set_two"
		{
			"items"
			{
				"[late_addition]weapon_ak47"		"1"
			}
		}
	}
}
'''

LANG = '''﻿"lang"
{
	"Language"	"English"
	"Tokens"
	{
		"SFUI_WPNHUD_AK47"					"AK-47"
		"SFUI_WPNHUD_M4A1"					"M4A4"
		"SFUI_WPNHUD_M4_SILENCER"					"M4A1-S"
		"PaintKit_so_red_Tag"					"Candy Apple"
		"PaintKit_late_addition_Tag"					"Late Addition"
	}
}
'''


def _fake_load_text(dir_vpk, internal_path):
    if internal_path == skins_catalog.ITEMS_GAME_PATH:
        return ITEMS_GAME
    if internal_path == skins_catalog.LOCALIZATION_PATH:
        return LANG
    raise AssertionError(internal_path)


class BuildingTheCatalog(unittest.TestCase):
    def setUp(self):
        skins_catalog.forget_all()
        self.addCleanup(skins_catalog.forget_all)
        patch = mock.patch.object(skins_catalog, "_load_text", side_effect=_fake_load_text)
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_combo_resolves_both_display_names(self):
        catalog = skins_catalog.build(Path("fake.vpk"))
        names = {it["display_name"] for it in catalog}
        self.assertIn("AK-47 | Candy Apple", names)

    def test_m4a4_and_m4a1s_are_told_apart_by_anim_class_not_item_class(self):
        """Both share item_class "weapon_m4a1"; the collection list tells
        them apart by anim_class, and the catalog has to use the same key
        or one of the two silently vanishes."""
        catalog = skins_catalog.build(Path("fake.vpk"))
        names = {it["display_name"] for it in catalog}
        self.assertIn("M4A1-S | Candy Apple", names)
        self.assertNotIn("M4A4 | Candy Apple", names)  # only the silencer variant was in item_sets

    def test_a_paint_kits_block_appended_later_in_the_file_is_not_dropped(self):
        """Valve re-opens "paint_kits" as a fresh sibling instead of editing
        the first one; a catalog that only reads the first occurrence loses
        every skin defined in a later one."""
        catalog = skins_catalog.build(Path("fake.vpk"))
        names = {it["display_name"] for it in catalog}
        self.assertIn("AK-47 | Late Addition", names)

    def test_rarity_is_resolved_to_a_display_name_and_colour(self):
        catalog = skins_catalog.build(Path("fake.vpk"))
        candy_apple = next(it for it in catalog if it["skin_name"] == "Candy Apple")
        self.assertEqual(candy_apple["rarity"], "Industrial Grade")
        self.assertTrue(candy_apple["rarity_color"].startswith("#"))

    def test_wear_range_comes_from_the_paint_kit_not_a_guess(self):
        catalog = skins_catalog.build(Path("fake.vpk"))
        candy_apple = next(it for it in catalog if it["skin_name"] == "Candy Apple")
        self.assertEqual(candy_apple["wear_min"], 0.0)
        self.assertEqual(candy_apple["wear_max"], 0.3)

    def test_a_kit_with_no_wear_remap_falls_back_to_the_full_range(self):
        catalog = skins_catalog.build(Path("fake.vpk"))
        late = next(it for it in catalog if it["skin_name"] == "Late Addition")
        self.assertEqual(late["wear_min"], 0.0)
        self.assertEqual(late["wear_max"], 1.0)

    def test_an_unresolved_weapon_or_paintkit_is_skipped_not_guessed_at(self):
        catalog = skins_catalog.build(Path("fake.vpk"))
        for it in catalog:
            self.assertNotEqual(it["weapon_class"], "weapon_doesnotexist")

    def test_the_same_combo_is_not_duplicated(self):
        catalog = skins_catalog.build(Path("fake.vpk"))
        keys = [(it["weapon_class"], it["paintkit"]) for it in catalog]
        self.assertEqual(len(keys), len(set(keys)))

    def test_results_are_cached_until_a_refresh_is_asked_for(self):
        with mock.patch.object(skins_catalog, "_load_text",
                               side_effect=_fake_load_text) as loader:
            skins_catalog.build(Path("fake.vpk"))
            skins_catalog.build(Path("fake.vpk"))
        self.assertEqual(loader.call_count, 2)  # one build call = 2 files read

    def test_force_rereads_rather_than_trusting_the_cache(self):
        with mock.patch.object(skins_catalog, "_load_text",
                               side_effect=_fake_load_text) as loader:
            skins_catalog.build(Path("fake.vpk"))
            skins_catalog.build(Path("fake.vpk"), force=True)
        self.assertEqual(loader.call_count, 4)


class DetectingLeakedTokens(unittest.TestCase):
    """A handful of real paint kits have their own description_tag
    miscopied in items_game.txt, pointing at a sibling skin's tag -- a
    genuine upstream data slip (confirmed by hand against several real
    examples: aq_ak47_cartel, cu_ak47_mastery, cu_awp_hyper_beast, among
    others), not something to fix at the source. This only has to notice
    the result doesn't look like real text and fall back cleanly."""

    def test_a_leaked_paintkit_token_is_detected(self):
        self.assertTrue(skins_catalog._looks_like_a_leaked_token("PaintKit_cu_bizon_citizen"))

    def test_real_display_text_is_not_flagged(self):
        for real in ("Candy Apple", "Case Hardened", "Triumvirate", "Dragon Lore", "AUTOEXEC"):
            self.assertFalse(skins_catalog._looks_like_a_leaked_token(real))

    def test_a_leaked_token_falls_back_to_the_paintkit_codename(self):
        index = {
            "scripts/items/items_game.txt": None,  # replaced by the mock below
        }
        items_game = ITEMS_GAME.replace(
            '"description_tag"\t\t"#PaintKit_so_red_Tag"',
            '"description_tag"\t\t"#PaintKit_so_red_Tag"\n\t\t}\n\t\t"4"\n\t\t{\n'
            '\t\t\t"name"\t\t"broken_kit"\n'
            '\t\t\t"description_tag"\t\t"#PaintKit_broken_kit_Tag"')
        lang = LANG.replace(
            '"PaintKit_so_red_Tag"\t\t\t\t\t"Candy Apple"',
            '"PaintKit_so_red_Tag"\t\t\t\t\t"Candy Apple"\n\t\t"PaintKit_broken_kit_Tag"\t\t\t\t\t"PaintKit_some_other_kit"')
        items_game = items_game.replace(
            '"[so_red]weapon_ak47"\t\t"1"',
            '"[so_red]weapon_ak47"\t\t"1"\n\t\t\t\t"[broken_kit]weapon_ak47"\t\t"1"')

        def fake_load(dir_vpk, path):
            if path == skins_catalog.ITEMS_GAME_PATH:
                return items_game
            if path == skins_catalog.LOCALIZATION_PATH:
                return lang
            raise AssertionError(path)

        skins_catalog.forget_all()
        with mock.patch.object(skins_catalog, "_load_text", side_effect=fake_load):
            catalog = skins_catalog.build(Path("fake.vpk"))
        broken = next(it for it in catalog if it["paintkit"] == "broken_kit")
        self.assertEqual(broken["skin_name"], "broken_kit")


class GroupingWeapons(unittest.TestCase):
    def test_a_known_weapon_lands_in_its_family(self):
        self.assertEqual(skins_catalog.group_of("weapon_ak47"), "Rifle")
        self.assertEqual(skins_catalog.group_of("weapon_deagle"), "Pistol")

    def test_an_unrecognised_class_is_not_an_error(self):
        self.assertEqual(skins_catalog.group_of("weapon_mystery"), "Other")


if __name__ == "__main__":
    unittest.main()
