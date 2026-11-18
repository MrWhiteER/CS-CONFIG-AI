"""Steam's Personal Game Data page -> match rows, and merging with recordings."""

import unittest
from pathlib import Path

from cs2cfg import matchlog, steamhistory

ME = "76561198000000001"  # account id 39734273
PAGE = (Path(__file__).parent / "fixtures" / "steam_gcpd_premier.html").read_text(encoding="utf-8")


class Parsing(unittest.TestCase):
    def setUp(self):
        self.rows = steamhistory.parse([PAGE], ME, "Premier")

    def test_every_match_with_you_in_it(self):
        self.assertEqual([r["map"] for r in self.rows], ["de_mirage", "de_anubis"])
        self.assertTrue(all(r["source"] == "cs2" and r["origin"] == "steam" for r in self.rows))

    def test_your_line_and_side(self):
        win, loss = self.rows
        self.assertEqual((win["kills"], win["assists"], win["deaths"], win["mvps"], win["hs_percent"]),
                         (24, 5, 14, 4, 50))
        self.assertTrue(win["won"])
        self.assertEqual(win["score"], "13 / 9")
        self.assertEqual(win["rounds"], 22)
        # Bottom team: the score reads the other way round.
        self.assertFalse(loss["won"])
        self.assertEqual(loss["score"], "11 / 13")
        self.assertIsNone(win["adr"])
        self.assertEqual(win["played_at"], 1794336151)
        self.assertEqual(len(win["players"]), 10)

    def test_found_by_profile_link_without_avatar_id(self):
        page = PAGE.replace('data-miniprofile="39734273"', 'data-miniprofile="1"')
        rows = steamhistory.parse([page], ME, "Premier", me="https://steamcommunity.com/id/edyvanity/")
        self.assertEqual(len(rows), 2)
        self.assertEqual(steamhistory.parse([page], ME, "Premier"), [])

    def test_map_names(self):
        self.assertEqual(steamhistory.map_id("Dust II"), "de_dust2")
        self.assertEqual(steamhistory.map_id("Ancient Night"), "de_ancient_night")
        self.assertEqual(steamhistory.map_id("Office"), "cs_office")
        self.assertEqual(steamhistory.map_id("cs_office"), "cs_office")

    def test_title_that_is_only_the_mode(self):
        page = PAGE.replace("<td>Premier Mirage</td>", "<td>Premier</td>", 1)
        page = page.replace("<td>Wait Time", '<td><img src="https://cdn/maps/de_mirage.png"></td></tr><tr><td>Wait Time', 1)
        self.assertEqual(steamhistory.parse([page], ME, "Premier")[0]["map"], "de_mirage")

    def test_tab_scoreboard_fields(self):
        players = self.rows[0]["players"]
        self.assertEqual([p["team"] for p in players], [0] * 5 + [1] * 5)
        you = next(p for p in players if p["you"])
        self.assertEqual(you["ping"], 48)
        # Only https pictures are kept; the fixture's are relative.
        self.assertEqual(you["avatar"], "")


class Merging(unittest.TestCase):
    def test_a_match_recorded_here_is_listed_once(self):
        steam = steamhistory.parse([PAGE], ME, "Premier")
        local = {"source": "cs2", "match_id": "cs2-x", "map": "de_mirage",
                 "started_at": 1794336151 + 120, "played_at": 1794336151 + 2400,
                 "kills": 24, "deaths": 14, "rounds": 22, "adr": 91.0, "won": True}
        out = matchlog.combined([], steam + [local], "cs2")
        self.assertEqual([r["match_id"] for r in out["matches"]],
                         ["cs2-x", f"steam-{ME}-1794168000"])
        self.assertEqual(out["counts"]["cs2"], 2)


class SharedSession(unittest.TestCase):
    def test_sign_in_closes_itself_and_tells_the_app(self):
        from unittest import mock
        from cs2cfg import steamweb

        urls = iter(["https://steamcommunity.com/openid/login?x", "https://cloud.example/callback"])
        win = mock.Mock()
        win.get_current_url.side_effect = lambda: next(urls, "https://cloud.example/callback")
        heard = []
        with mock.patch.object(steamweb, "mark") as mark, \
             mock.patch.object(steamweb.time, "sleep"), \
             mock.patch.object(steamweb, "on_signed_in", [lambda: heard.append(1)]):
            steamweb._finished(win, steamweb._left_steam)
        mark.assert_called_once()
        self.assertTrue(mark.call_args[0][0]["linked"])
        self.assertEqual(heard, [1])
        win.destroy.assert_called_once()

    def test_what_counts_as_finished(self):
        from cs2cfg import steamweb
        self.assertFalse(steamweb._signed_in_page("https://steamcommunity.com/login/home/?goto=my/"))
        self.assertTrue(steamweb._signed_in_page("https://steamcommunity.com/id/edy/"))
        self.assertFalse(steamweb._left_steam("https://steamcommunity.com/openid/login"))
        self.assertTrue(steamweb._left_steam("https://cfg.example/auth/steam/callback"))


if __name__ == "__main__":
    unittest.main()
