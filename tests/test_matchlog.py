"""The CS2 match recorder: payloads in, one finished match row out."""

import json
import tempfile
import unittest
from pathlib import Path

from cs2cfg import matchlog

ME = "76561198000000001"
OTHER = "76561198000000002"
TOKEN = "a" * 64


def payload(phase="live", round_phase="live", ct=0, t=0, who=ME, kills=0, hs=0,
            dmg=0, stats=None, mode="competitive", name="de_mirage", team="CT"):
    p = {
        "provider": {"steamid": ME},
        "map": {"name": name, "mode": mode, "phase": phase,
                "team_ct": {"score": ct}, "team_t": {"score": t}},
        "round": {"phase": round_phase},
        "player": {"steamid": who, "team": team,
                   "state": {"health": 100, "round_kills": kills,
                             "round_killhs": hs, "round_totaldmg": dmg},
                   "match_stats": stats or {}},
    }
    return p


class Clock:
    def __init__(self):
        self.now = 1_000_000

    def __call__(self):
        self.now += 1
        return self.now


def play(rec, rounds, final_stats, ct, t, team="CT"):
    """Each round: (kills, hs, dmg). A freezetime precedes each one."""
    rec.feed(payload(phase="warmup", round_phase="warmup", kills=4, dmg=300))
    for k, h, d in rounds:
        rec.feed(payload(round_phase="freezetime", team=team))
        rec.feed(payload(kills=k, hs=h, dmg=d, team=team))
        # Dead and spectating a teammate: their numbers must not count.
        rec.feed(payload(who=OTHER, kills=5, hs=5, dmg=500, team=team))
        rec.feed(payload(round_phase="over", kills=k, hs=h, dmg=d, team=team))
    return rec.feed(payload(phase="gameover", round_phase="over", ct=ct, t=t,
                            stats=final_stats, team=team))


class Recording(unittest.TestCase):
    def setUp(self):
        self.saved = []
        self.rec = matchlog.Recorder(self.saved.append, clock=Clock())

    def test_one_match_becomes_one_row(self):
        row = play(self.rec, [(2, 1, 180), (0, 0, 40), (3, 2, 260), (1, 0, 100)],
                   {"kills": 6, "deaths": 2, "assists": 1, "mvps": 2}, ct=3, t=1)
        self.assertEqual(self.saved, [row])
        self.assertEqual(row["source"], "cs2")
        self.assertEqual(row["map"], "de_mirage")
        self.assertEqual(row["mode"], "Competitive")
        self.assertTrue(row["won"])
        self.assertEqual(row["score"], "3 / 1")
        self.assertEqual(row["rounds"], 4)
        self.assertEqual((row["kills"], row["deaths"], row["assists"], row["mvps"]), (6, 2, 1, 2))
        self.assertEqual(row["kd"], 3.0)
        self.assertEqual(row["adr"], round(580 / 4, 1))
        self.assertEqual(row["hs_percent"], 50)
        self.assertEqual((row["double"], row["triple"]), (1, 1))

    def test_score_is_read_from_your_side(self):
        row = play(self.rec, [(1, 0, 100)], {"kills": 1, "deaths": 1}, ct=13, t=9, team="T")
        self.assertFalse(row["won"])
        self.assertEqual(row["score"], "9 / 13")

    def test_end_screen_is_saved_once(self):
        play(self.rec, [(1, 0, 100)], {"kills": 1, "deaths": 0}, ct=1, t=0)
        self.rec.feed(payload(phase="gameover", round_phase="over", ct=1, t=0))
        self.assertEqual(len(self.saved), 1)

    def test_deathmatch_is_not_recorded(self):
        rec = matchlog.Recorder(self.saved.append, clock=Clock())
        self.assertIsNone(rec.feed(payload(mode="deathmatch", phase="gameover", ct=0, t=0,
                                           stats={"kills": 40})))
        self.assertEqual(self.saved, [])

    def test_leaving_early_records_nothing(self):
        self.rec.feed(payload(kills=2, dmg=200))
        self.rec.feed({"provider": {"steamid": ME}, "map": {}, "round": {}, "player": {}})
        self.rec.feed(payload(phase="gameover", round_phase="over", ct=1, t=0, name="de_nuke"))
        # Nuke was only seen at its end screen: nothing of yours to record.
        self.assertEqual(self.saved, [])


class Feed(unittest.TestCase):
    def test_wrong_secret_is_refused(self):
        raw = json.dumps({"auth": {"token": "b" * 64}}).encode()
        with self.assertRaises(PermissionError):
            matchlog.parse_payload(raw, TOKEN)

    def test_keeps_only_what_it_reads(self):
        raw = json.dumps({"auth": {"token": TOKEN},
                          "provider": {"steamid": ME, "name": "me"},
                          "map": {"name": "de_inferno", "mode": "competitive",
                                  "phase": "live", "team_ct": {"score": 3, "name": "x"}},
                          "player": {"steamid": ME, "name": "me",
                                     "state": {"round_kills": 2, "money": 800},
                                     "match_stats": {"kills": 9}}}).encode()
        p = matchlog.parse_payload(raw, TOKEN)
        self.assertEqual(p["provider"], {"steamid": ME})
        self.assertEqual(p["map"]["team_ct"], {"score": 3})
        self.assertEqual(p["player"]["state"], {"round_kills": 2})
        self.assertNotIn("name", p["player"])

    def test_cfg_is_only_rewritten_when_it_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            (install / "game" / "csgo" / "cfg").mkdir(parents=True)
            self.assertIsNotNone(matchlog.write_cfg(install, 8765, TOKEN))
            self.assertIsNone(matchlog.write_cfg(install, 8765, TOKEN))
            path = matchlog.write_cfg(install, 8766, TOKEN)
            text = path.read_text(encoding="utf-8")
            self.assertIn("127.0.0.1:8766/api/stats/gsi", text)
            self.assertIn('"player_match_stats" "1"', text)
            matchlog.remove_cfg(install)
            self.assertFalse(path.exists())


class Combined(unittest.TestCase):
    def faceit(self, when, map_="de_mirage"):
        return {"match_id": f"1-{when}", "map": map_, "played_at": when, "won": True,
                "kills": 20, "deaths": 10, "assists": 3, "rounds": 20, "adr": 90.0,
                "hs_percent": 50.0}

    def cs2(self, when, map_="de_mirage"):
        return {"source": "cs2", "match_id": f"cs2-{when}", "map": map_,
                "started_at": when - 1800, "played_at": when, "won": False,
                "kills": 10, "deaths": 20, "assists": 1, "rounds": 20, "adr": 60.0,
                "hs_percent": 30}

    def test_both_sources_newest_first(self):
        out = matchlog.combined([self.faceit(100_000)], [self.cs2(200_000, "de_nuke")])
        self.assertEqual([r["source"] for r in out["matches"]], ["cs2", "faceit"])
        self.assertEqual(out["counts"], {"all": 2, "faceit": 1, "cs2": 1})
        self.assertEqual(out["summary"]["kd"], 1.0)
        self.assertEqual(out["summary"]["win_rate"], 50)

    def test_filter(self):
        f, c = [self.faceit(100_000)], [self.cs2(200_000, "de_nuke")]
        self.assertEqual([r["source"] for r in matchlog.combined(f, c, "faceit")["matches"]], ["faceit"])
        self.assertEqual([r["source"] for r in matchlog.combined(f, c, "cs2")["matches"]], ["cs2"])
        self.assertEqual(matchlog.combined(f, c, "cs2")["summary"]["kd"], 0.5)

    def test_faceit_match_seen_by_cs2_is_shown_once(self):
        out = matchlog.combined([self.faceit(200_100)], [self.cs2(200_000)])
        self.assertEqual([r["source"] for r in out["matches"]], ["faceit"])

    def test_store_keeps_rows_per_player(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = matchlog.Store(Path(tmp))
            store.add(dict(self.cs2(1), steamid=ME))
            store.add(dict(self.cs2(2), steamid=OTHER))
            self.assertEqual([r["match_id"] for r in store.matches(ME)], ["cs2-1"])
            self.assertEqual(len(store.matches()), 2)

    def test_account_id_to_steam64(self):
        self.assertEqual(matchlog.account_to_steam64("39734273"), "76561198000000001")


if __name__ == "__main__":
    unittest.main()
