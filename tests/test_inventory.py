"""Reading a Steam inventory, and nothing else.

No test here reaches the network: every request is a stub, the same
discipline cs2cfg.cloud's own tests hold to.
"""

from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import inventory  # noqa: E402


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _replies(payload, status=200):
    if status >= 400:
        def raiser(request, timeout=None):
            raise urllib.error.HTTPError(
                "u", status, "no", {}, io.BytesIO(b""))
        return raiser
    return lambda request, timeout=None: _Answer(json.dumps(payload).encode())


class TagsAndLinks(unittest.TestCase):
    def test_tags_are_flattened_by_category(self):
        description = {"tags": [
            {"category": "Type", "localized_tag_name": "Music Kit"},
            {"category": "Rarity", "localized_tag_name": "High Grade"},
        ]}
        tags = inventory._tag_map(description)
        self.assertEqual(tags["Type"], "Music Kit")
        self.assertEqual(tags["Rarity"], "High Grade")

    def test_an_item_with_no_tags_is_not_an_error(self):
        self.assertEqual(inventory._tag_map({}), {})

    def test_the_inspect_link_is_read_not_built(self):
        """Steam computes the S/A/D parameters itself; this only reads them
        back, which is the whole reason it does not need to understand what
        they mean."""
        description = {"actions": [
            {"link": "steam://rungame/730/.../+csgo_econ_action_preview%20S1A2D3",
             "name": "Inspect in Game..."}
        ]}
        self.assertIn("csgo_econ_action_preview", inventory._inspect_link(description))

    def test_an_item_that_cannot_be_inspected_has_no_link(self):
        self.assertEqual(inventory._inspect_link({"actions": []}), "")
        self.assertEqual(inventory._inspect_link({}), "")

    def test_the_icon_url_points_at_steams_own_cdn(self):
        url = inventory._icon_url({"icon_url": "abc123"})
        self.assertTrue(url.startswith("https://"))
        self.assertIn("abc123", url)

    def test_no_icon_is_an_empty_string_not_a_broken_url(self):
        self.assertEqual(inventory._icon_url({}), "")


class Combining(unittest.TestCase):
    def test_an_asset_is_matched_to_its_description_by_both_ids(self):
        assets = [{"assetid": "111", "classid": "9", "instanceid": "2"}]
        descriptions = [{"classid": "9", "instanceid": "2",
                         "market_hash_name": "AK-47 | Redline",
                         "tags": [{"category": "Type", "localized_tag_name": "Rifle"}]}]
        items = inventory._combine(assets, descriptions)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "AK-47 | Redline")
        self.assertEqual(items[0]["type"], "Rifle")
        self.assertEqual(items[0]["asset_id"], "111")

    def test_an_asset_with_no_matching_description_is_dropped_not_guessed_at(self):
        assets = [{"assetid": "111", "classid": "9", "instanceid": "2"}]
        items = inventory._combine(assets, [])
        self.assertEqual(items, [])

    def test_instanceid_defaults_to_zero_the_same_way_steam_does(self):
        assets = [{"assetid": "1", "classid": "5"}]
        descriptions = [{"classid": "5", "instanceid": "0", "market_hash_name": "Sticker"}]
        items = inventory._combine(assets, descriptions)
        self.assertEqual(len(items), 1)

    def test_stattrak_is_read_from_the_display_name(self):
        assets = [{"assetid": "1", "classid": "5", "instanceid": "0"}]
        descriptions = [{"classid": "5", "instanceid": "0",
                         "name": "StatTrak™ AK-47 | Redline"}]
        items = inventory._combine(assets, descriptions)
        self.assertTrue(items[0]["stattrak"])


class Fetching(unittest.TestCase):
    def setUp(self):
        inventory.forget_all()
        self.addCleanup(inventory.forget_all)

    def test_a_successful_inventory_is_split_into_items(self):
        payload = {"success": True,
                  "assets": [{"assetid": "1", "classid": "5", "instanceid": "0"}],
                  "descriptions": [{"classid": "5", "instanceid": "0", "name": "Case"}]}
        with mock.patch.object(inventory.urllib.request, "urlopen",
                               side_effect=_replies(payload)):
            result = inventory.fetch(123)
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)

    def test_a_private_inventory_says_so_rather_than_a_bare_403(self):
        with mock.patch.object(inventory.urllib.request, "urlopen",
                               side_effect=_replies({}, status=403)):
            result = inventory.fetch(123)
        self.assertFalse(result["ok"])
        self.assertTrue(result.get("private"))

    def test_unreachable_steam_is_reported_not_raised(self):
        with mock.patch.object(inventory.urllib.request, "urlopen",
                               side_effect=urllib.error.URLError("down")):
            result = inventory.fetch(123)
        self.assertFalse(result["ok"])
        self.assertIn("error", result)

    def test_every_request_names_the_application(self):
        """Third time this project has needed this. See cs2cfg.cloud."""
        sent = {}

        def capture(request, timeout=None):
            sent.update({k.lower(): v for k, v in request.header_items()})
            return _Answer(json.dumps({"success": True, "assets": [],
                                       "descriptions": []}).encode())

        with mock.patch.object(inventory.urllib.request, "urlopen", side_effect=capture):
            inventory.fetch(123)
        self.assertIn("user-agent", sent)
        self.assertNotIn("python-urllib", sent["user-agent"].lower())

    def test_a_second_call_within_the_cache_window_does_not_ask_steam_again(self):
        payload = {"success": True, "assets": [], "descriptions": []}
        with mock.patch.object(inventory.urllib.request, "urlopen",
                               side_effect=_replies(payload)) as called:
            inventory.fetch(123)
            inventory.fetch(123)
        self.assertEqual(called.call_count, 1)

    def test_force_bypasses_the_cache(self):
        payload = {"success": True, "assets": [], "descriptions": []}
        with mock.patch.object(inventory.urllib.request, "urlopen",
                               side_effect=_replies(payload)) as called:
            inventory.fetch(123)
            inventory.fetch(123, force=True)
        self.assertEqual(called.call_count, 2)

    def test_forgetting_one_account_does_not_clear_another(self):
        payload = {"success": True, "assets": [], "descriptions": []}
        with mock.patch.object(inventory.urllib.request, "urlopen",
                               side_effect=_replies(payload)) as called:
            inventory.fetch(111)
            inventory.fetch(222)
            inventory.forget(111)
            inventory.fetch(111)
            inventory.fetch(222)
        self.assertEqual(called.call_count, 3)


class Grouping(unittest.TestCase):
    def _item(self, **over):
        base = {"asset_id": "1", "name": "x", "type": "", "rarity": "", "exterior": "",
               "weapon": "", "category": "", "stattrak": False, "tradable": True,
               "marketable": True, "icon": "", "inspect": ""}
        base.update(over)
        return base

    def test_a_music_kit_lands_in_its_own_group(self):
        items = [self._item(type="Music Kit", name="Music Kit | Austin Wintory")]
        groups = inventory.grouped(items)
        self.assertEqual(groups[0]["name"], "Music kits")

    def test_a_weapon_skin_is_told_apart_from_a_music_kit(self):
        items = [self._item(type="Rifle", weapon="AK-47", name="AK-47 | Redline")]
        groups = inventory.grouped(items)
        self.assertEqual(groups[0]["name"], "Weapon skins")

    def test_an_unrecognised_type_still_shows_up(self):
        """A tag Valve adds later must not make an owned item vanish."""
        items = [self._item(type="Something New")]
        groups = inventory.grouped(items)
        self.assertEqual(groups[0]["name"], "Other")

    def test_every_item_lands_in_exactly_one_group(self):
        items = [self._item(type="Music Kit"), self._item(type="Sticker"),
                self._item(type="Rifle", weapon="M4A4")]
        groups = inventory.grouped(items)
        total = sum(len(g["items"]) for g in groups)
        self.assertEqual(total, len(items))


if __name__ == "__main__":
    unittest.main()
