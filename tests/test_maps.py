"""Every map and mode the user sees reads as a name, never an id."""

import unittest

from cs2cfg import maps, matchlog


class Names(unittest.TestCase):
    def test_known_maps(self):
        self.assertEqual(maps.display("de_dust2"), "Dust II")
        self.assertEqual(maps.display("de_dustii"), "Dust II")
        self.assertEqual(maps.display("cs_office"), "Office")
        self.assertEqual(maps.display("de_ancient_night"), "Ancient Night")
        self.assertEqual(maps.display("workshop/123/de_mirage"), "Mirage")

    def test_translated_steam_page(self):
        # Steam writes the mode in the player's language before the map.
        self.assertEqual(maps.from_name("Премьер-режим Mirage"), "de_mirage")
        self.assertEqual(maps.from_name("Премьер-режим Dust II"), "de_dust2")
        self.assertEqual(maps.from_name("Премьер-режим"), "")
        # Rows already saved with the label stuck to the name are repaired.
        self.assertEqual(maps.canonical("de_премьер-режимdustii"), "de_dust2")
        self.assertEqual(maps.canonical("de_премьер-режимancient"), "de_ancient")

    def test_unknown_map_reads_as_words(self):
        self.assertEqual(maps.display("de_brand_new"), "Brand New")
        self.assertEqual(maps.display(""), "Unknown map")

    def test_modes(self):
        self.assertEqual(maps.mode("scrimcomp2v2"), "Wingman")
        self.assertEqual(maps.mode("competitive"), "Competitive")
        self.assertEqual(maps.mode("Premier"), "Premier")
        self.assertEqual(maps.mode("gungameprogressive"), "Arms Race")
        self.assertEqual(maps.mode("some_new_mode"), "Some New Mode")

    def test_stats_rows_carry_plain_names(self):
        out = matchlog.combined([], [{"source": "cs2", "match_id": "a", "map": "de_dustii",
                                      "mode": "scrimcomp2v2", "played_at": 1}], "cs2")
        row = out["matches"][0]
        self.assertEqual((row["map"], row["map_name"], row["mode"]), ("de_dust2", "Dust II", "Wingman"))


if __name__ == "__main__":
    unittest.main()
