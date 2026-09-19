"""Match demos: reading a link, fetching the file, making it playable.

Nothing here touches the network. The opener is injected, so the tests
exercise the real parsing, decompression and naming against fixtures.
"""

import bz2
import gzip
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from cs2cfg import demos

MATCH = "1-0e4d6c2a-8b31-4f2d-9c77-1a2b3c4d5e6f"


class _Response(io.BytesIO):
    """Just enough of an HTTP response to stand in for one."""

    def __init__(self, data: bytes, headers=None):
        super().__init__(data)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _opener(data, headers=None):
    return lambda url, timeout=None: _Response(data, headers)


class ReadingTheLink(unittest.TestCase):
    def test_it_takes_a_room_url(self):
        self.assertEqual(
            demos.match_id(f"https://www.faceit.com/en/cs2/room/{MATCH}"), MATCH)

    def test_it_takes_a_bare_id(self):
        self.assertEqual(demos.match_id(MATCH), MATCH)

    def test_it_takes_a_url_with_a_scoreboard_tab_on_the_end(self):
        self.assertEqual(
            demos.match_id(f"https://www.faceit.com/en/cs2/room/{MATCH}/scoreboard"),
            MATCH)

    def test_it_is_case_insensitive_but_settles_on_one(self):
        self.assertEqual(demos.match_id(MATCH.upper()), MATCH)

    def test_nonsense_is_not_a_match(self):
        for text in ["", "hello", "https://www.faceit.com/en/cs2", None,
                     "1-not-a-uuid"]:
            self.assertIsNone(demos.match_id(text), text)

    def test_a_uuid_without_the_faceit_prefix_is_refused(self):
        """Other ids appear in these URLs; only the match id starts 1-."""
        self.assertIsNone(demos.match_id("0e4d6c2a-8b31-4f2d-9c77-1a2b3c4d5e6f"))


class FindingTheDemo(unittest.TestCase):
    """The URL is hunted for by shape, so a field rename cannot break it."""

    def test_it_finds_a_flat_demo_url(self):
        found = demos.demo_urls({"demo_url": ["https://cdn.faceit.com/a.dem.gz"]})
        self.assertEqual(found, ["https://cdn.faceit.com/a.dem.gz"])

    def test_it_finds_one_nested_anywhere(self):
        found = demos.demo_urls(
            {"payload": {"some": {"thing": [{"x": "https://c.net/b.dem.gz"}]}}})
        self.assertEqual(found, ["https://c.net/b.dem.gz"])

    def test_it_accepts_plain_and_bzipped_demos(self):
        found = demos.demo_urls(["https://c/a.dem", "https://c/b.dem.bz2"])
        self.assertEqual(len(found), 2)

    def test_it_does_not_invent_one(self):
        self.assertEqual(demos.demo_urls({"nothing": "here", "n": 5}), [])

    def test_it_ignores_things_that_merely_contain_dem(self):
        self.assertEqual(demos.demo_urls({"a": "https://c/academy.demo.html"}), [])

    def test_duplicates_collapse(self):
        url = "https://c/a.dem.gz"
        self.assertEqual(demos.demo_urls({"a": url, "b": {"c": url}}), [url])


class Resolving(unittest.TestCase):
    def _payload(self, **over):
        body = {"payload": {
            "demoURLs": ["https://cdn.faceit.net/x.dem.gz"],
            "voting": {"map": {"pick": ["de_mirage"]}},
            "teams": {"faction1": {"name": "team_one"},
                      "faction2": {"name": "team_two"}},
            "state": "FINISHED",
        }}
        body["payload"].update(over)
        return json.dumps(body).encode()

    def test_it_returns_the_demo_and_what_the_match_was(self):
        out = demos.resolve(MATCH, opener=_opener(self._payload()))
        self.assertEqual(out["url"], "https://cdn.faceit.net/x.dem.gz")
        self.assertEqual(out["match_id"], MATCH)
        self.assertEqual(out["map"], "de_mirage")
        self.assertEqual(out["team1"], "team_one")

    def test_a_bad_link_is_rejected_before_any_request(self):
        def explode(url, timeout=None):
            raise AssertionError("should not have asked FACEIT anything")
        with self.assertRaises(demos.DemoError) as caught:
            demos.resolve("not a link", opener=explode)
        self.assertIn("FACEIT match link", str(caught.exception))

    def test_a_match_with_no_demo_says_so_usefully(self):
        data = json.dumps({"payload": {"state": "ONGOING"}}).encode()
        with self.assertRaises(demos.DemoError) as caught:
            demos.resolve(MATCH, opener=_opener(data))
        said = str(caught.exception)
        self.assertIn("no demo", said)
        self.assertIn("ONGOING", said)

    def test_an_unknown_match_is_reported_as_such(self):
        def missing(url, timeout=None):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        with self.assertRaises(demos.DemoError) as caught:
            demos.resolve(MATCH, opener=missing)
        self.assertIn("does not know", str(caught.exception))

    def test_a_broken_answer_does_not_raise_something_raw(self):
        with self.assertRaises(demos.DemoError):
            demos.resolve(MATCH, opener=_opener(b"<html>nope</html>"))

    def test_missing_metadata_is_not_fatal(self):
        data = json.dumps({"demo_url": ["https://c/a.dem"]}).encode()
        out = demos.resolve(MATCH, opener=_opener(data))
        self.assertEqual(out["url"], "https://c/a.dem")
        self.assertEqual(out["map"], "")


class Naming(unittest.TestCase):
    def test_the_name_comes_from_the_match_not_the_server(self):
        name = demos.local_name(MATCH, {"map": "de_mirage"})
        self.assertTrue(name.startswith("faceit_"))
        self.assertIn("demirage", name)
        self.assertTrue(name.endswith(".dem"))

    def test_it_refuses_an_id_that_is_not_one(self):
        """The filename is the one place a remote value could become a path."""
        for bad in ["../../evil", "1-x", "", "a/b"]:
            with self.assertRaises(demos.DemoError):
                demos.local_name(bad)

    def test_a_hostile_map_name_cannot_escape(self):
        name = demos.local_name(MATCH, {"map": "../../../etc/passwd"})
        self.assertNotIn("/", name)
        self.assertNotIn("..", name)

    def test_no_map_is_still_a_valid_name(self):
        self.assertTrue(demos.local_name(MATCH, {}).endswith(".dem"))


class Downloading(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_gzipped_demo_arrives_decompressed(self):
        body = b"DEMO-CONTENT" * 500
        packed = gzip.compress(body)
        out = demos.download("https://c/a.dem.gz", self.dir / "a.dem",
                             opener=_opener(packed))
        self.assertEqual(out.read_bytes(), body)

    def test_a_bzipped_demo_arrives_decompressed(self):
        body = b"DEMO" * 400
        out = demos.download("https://c/a.dem.bz2", self.dir / "b.dem",
                             opener=_opener(bz2.compress(body)))
        self.assertEqual(out.read_bytes(), body)

    def test_a_zstd_demo_arrives_decompressed(self):
        """What FACEIT actually serves for CS2 now -- not gzip."""
        try:
            import zstandard
        except ImportError:
            self.skipTest("zstandard is not installed")
        body = b"PBDEMS2" + bytes(64) + b"ROUND" * 2000
        out = demos.download("https://c/a.dem.zst", self.dir / "z.dem",
                             opener=_opener(zstandard.ZstdCompressor().compress(body)))
        self.assertEqual(out.read_bytes(), body)

    def test_a_zst_link_is_recognised_as_a_demo(self):
        url = "https://demos-europe.faceit-cdn.net/cs2/1-abc-1-1.dem.zst"
        self.assertEqual(demos.demo_urls({"demoURLs": [url]}), [url])

    def test_a_host_that_does_not_resolve_blames_the_right_thing(self):
        """Seen for real: a finished match whose link named a CDN host with no
        DNS record, while FACEIT's other demo hosts resolved. Not the user's
        connection, so the message must not read like it is."""
        def unresolvable(url, timeout=None):
            raise urllib.error.URLError(
                "[Errno 11001] getaddrinfo failed")
        target = self.dir / "n.dem"
        with self.assertRaises(demos.DemoError) as caught:
            demos.download("https://demos-europe.faceit-cdn.net/a.dem.zst",
                           target, opener=unresolvable)
        said = str(caught.exception)
        self.assertIn("does not exist", said)
        self.assertIn("demos-europe.faceit-cdn.net", said)
        self.assertNotIn("your internet", said.lower())
        self.assertFalse(target.exists())

    def test_an_uncompressed_demo_is_copied_through(self):
        out = demos.download("https://c/a.dem", self.dir / "c.dem",
                             opener=_opener(b"RAW"))
        self.assertEqual(out.read_bytes(), b"RAW")

    def test_progress_counts_bytes_off_the_wire(self):
        packed = gzip.compress(b"x" * 20000)
        seen = []
        demos.download("https://c/a.dem.gz", self.dir / "d.dem",
                       progress=lambda n, t: seen.append((n, t)),
                       opener=_opener(packed, {"Content-Length": str(len(packed))}))
        self.assertTrue(seen)
        self.assertEqual(seen[-1][0], len(packed))
        self.assertEqual(seen[-1][1], len(packed))

    def test_a_cancelled_download_leaves_nothing_behind(self):
        packed = gzip.compress(b"y" * 100000)
        target = self.dir / "e.dem"
        with self.assertRaises(demos.Cancelled):
            demos.download("https://c/a.dem.gz", target,
                           cancelled=lambda: True, opener=_opener(packed))
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name(target.name + ".part").exists())

    def test_a_failed_download_leaves_nothing_behind(self):
        def broken(url, timeout=None):
            raise urllib.error.URLError("connection reset")
        target = self.dir / "f.dem"
        with self.assertRaises(demos.DemoError):
            demos.download("https://c/a.dem", target, opener=broken)
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name(target.name + ".part").exists())

    def test_a_truncated_archive_is_not_left_looking_watchable(self):
        # Random rather than repeated bytes: 50k of the same character
        # compresses to under 200, so truncating it would cut nothing.
        import os
        packed = gzip.compress(os.urandom(50000))[:200]
        target = self.dir / "g.dem"
        with self.assertRaises(demos.DemoError):
            demos.download("https://c/a.dem.gz", target, opener=_opener(packed))
        self.assertFalse(target.exists())

    def test_an_existing_demo_is_only_replaced_once_the_new_one_is_whole(self):
        target = self.dir / "h.dem"
        target.write_bytes(b"THE OLD ONE")
        def broken(url, timeout=None):
            raise urllib.error.URLError("dropped")
        with self.assertRaises(demos.DemoError):
            demos.download("https://c/a.dem", target, opener=broken)
        self.assertEqual(target.read_bytes(), b"THE OLD ONE")


class OnDisk(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_it_lists_demos_newest_first(self):
        import os, time
        for i, name in enumerate(["old.dem", "new.dem"]):
            p = self.dir / name
            p.write_bytes(b"x")
            os.utime(p, (time.time() + i * 100, time.time() + i * 100))
        listed = demos.installed(self.dir)
        self.assertEqual([d["name"] for d in listed], ["new.dem", "old.dem"])

    def test_it_ignores_everything_that_is_not_a_demo(self):
        (self.dir / "a.dem").write_bytes(b"x")
        (self.dir / "a.dem.info").write_bytes(b"x")
        (self.dir / "notes.txt").write_bytes(b"x")
        self.assertEqual([d["name"] for d in demos.installed(self.dir)], ["a.dem"])

    def test_a_missing_folder_is_empty_rather_than_an_error(self):
        self.assertEqual(demos.installed(self.dir / "nope"), [])

    def test_each_entry_carries_the_command_that_plays_it(self):
        (self.dir / "faceit_0e4d6c2a_demirage.dem").write_bytes(b"x")
        entry = demos.installed(self.dir)[0]
        self.assertEqual(entry["command"], "replays/faceit_0e4d6c2a_demirage")
        self.assertTrue(entry["ours"])


class Scoreboard(unittest.TestCase):
    """The stat keys are opaque (i6, c4, i40), so the mapping is pinned here.

    The values are a real finished match, cross-checked against the scoreboard
    FACEIT renders for it. If FACEIT renumbers a column these fail, which is
    the point -- silently reading the wrong key would show wrong numbers.
    """

    def _payload(self):
        def player(nick, i6, i7, i8, i9, i13, i14, i15, i16, i40, c2, c3, c4, c10):
            return {"nickname": nick, "playerId": "p-" + nick,
                    "i6": str(i6), "i7": str(i7), "i8": str(i8), "i9": str(i9),
                    "i13": str(i13), "i14": str(i14), "i15": str(i15),
                    "i16": str(i16), "i40": str(i40), "c2": str(c2),
                    "c3": str(c3), "c4": str(c4), "c10": str(c10)}
        return [{
            "i0": "EU", "i1": "de_ancient", "i12": "17", "i18": "13 / 4",
            "gameMode": "5v5", "date": 1789844333000,
            "teams": [
                {"i5": "team_HyperB74", "c5": "13", "i3": "9", "i4": "4", "i17": "1",
                 "players": [
                     player("MrWhiteE_R", 16, 2, 9, 4, 7, 0, 1, 0, 3, 1.78, 0.94, 44, 93.9),
                     player("RespecT2324", 19, 4, 9, 5, 7, 1, 0, 0, 6, 2.11, 1.12, 37, 118.2),
                 ]},
                {"i5": "team_Waseem", "c5": "4", "i3": "3", "i4": "1", "i17": "0",
                 "players": [
                     player("Waseem", 9, 3, 15, 1, 3, 0, 0, 0, 3, 0.60, 0.53, 33, 79.9),
                 ]},
            ],
        }]

    def _stats(self):
        return demos.stats(MATCH, opener=_opener(json.dumps(self._payload()).encode()))

    def test_the_match_reads_correctly(self):
        s = self._stats()
        self.assertEqual(s["map"], "de_ancient")
        self.assertEqual(s["score"], "13 / 4")
        self.assertEqual(s["rounds"], 17)
        self.assertEqual(s["region"], "EU")

    def test_the_teams_carry_their_score_and_halves(self):
        won, lost = self._stats()["teams"]
        self.assertEqual((won["name"], won["score"]), ("team_HyperB74", 13))
        self.assertEqual((won["first_half"], won["second_half"]), (9, 4))
        self.assertTrue(won["won"])
        self.assertFalse(lost["won"])

    def test_every_column_lands_where_it_belongs(self):
        """The whole mapping, on one known row."""
        top = self._stats()["teams"][0]["players"]
        me = next(p for p in top if p["nickname"] == "MrWhiteE_R")
        self.assertEqual(me["kills"], 16)
        self.assertEqual(me["deaths"], 9)
        self.assertEqual(me["assists"], 2)
        self.assertEqual(me["mvps"], 4)
        self.assertEqual(me["headshots"], 7)
        self.assertEqual(me["hs_percent"], 44)
        self.assertEqual(me["kd"], 1.78)
        self.assertEqual(me["kr"], 0.94)
        self.assertEqual(me["adr"], 93.9)
        self.assertEqual((me["penta"], me["quadro"], me["triple"], me["double"]),
                         (0, 1, 0, 3))

    def test_kills_and_deaths_are_not_swapped(self):
        """i6 and i8 sit next to each other and are easy to transpose."""
        top = self._stats()["teams"][0]["players"]
        loser = next(p for p in self._stats()["teams"][1]["players"])
        self.assertGreater(top[0]["kills"], top[0]["deaths"])
        self.assertLess(loser["kills"], loser["deaths"])

    def test_players_are_ordered_best_first(self):
        names = [p["nickname"] for p in self._stats()["teams"][0]["players"]]
        self.assertEqual(names[0], "RespecT2324")

    def test_a_match_with_no_scoreboard_says_so(self):
        with self.assertRaises(demos.DemoError):
            demos.stats(MATCH, opener=_opener(b'[{"teams": []}]'))

    def test_a_bad_link_is_refused_before_asking(self):
        def explode(url, timeout=None):
            raise AssertionError("should not have asked FACEIT anything")
        with self.assertRaises(demos.DemoError):
            demos.stats("nonsense", opener=explode)

    def test_a_missing_stat_reads_as_zero_rather_than_exploding(self):
        thin = [{"teams": [{"i5": "t", "c5": "1", "players": [{"nickname": "x"}]}]}]
        got = demos.stats(MATCH, opener=_opener(json.dumps(thin).encode()))
        self.assertEqual(got["teams"][0]["players"][0]["kills"], 0)


class FollowingAnAccount(unittest.TestCase):
    def _profile(self):
        return json.dumps({"payload": {
            "id": "a855d096-c031-4110-bab6-2b58f20548c2",
            "nickname": "MrWhiteE_R", "country": "ae",
            "avatar": "https://cdn/av.jpg",
            "games": {"cs2": {"faceit_elo": 1448, "skill_level": 7}},
        }}).encode()

    def test_a_player_reads_back_with_their_level(self):
        me = demos.player("MrWhiteE_R", opener=_opener(self._profile()))
        self.assertEqual(me["player_id"], "a855d096-c031-4110-bab6-2b58f20548c2")
        self.assertEqual((me["elo"], me["level"]), (1448, 7))
        self.assertEqual(me["country"], "AE")

    def test_an_unknown_player_says_so(self):
        def missing(url, timeout=None):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        with self.assertRaises(demos.DemoError) as caught:
            demos.player("nobody", opener=missing)
        self.assertIn("no player called", str(caught.exception))

    def test_an_empty_nickname_never_reaches_faceit(self):
        def explode(url, timeout=None):
            raise AssertionError("should not have asked")
        with self.assertRaises(demos.DemoError):
            demos.player("   ", opener=explode)

    def test_a_nickname_with_punctuation_is_escaped_into_the_url(self):
        seen = {}
        def watch(url, timeout=None):
            seen["url"] = url
            return _Response(self._profile())
        demos.player("a b/c", opener=watch)
        self.assertNotIn(" ", seen["url"])
        self.assertNotIn("/c", seen["url"].split("nicknames/")[1])

    def _rows(self):
        def row(mid, map_, mine, line, won, elo, delta, when):
            return {"matchId": mid, "i1": map_, "c5": str(mine), "i18": line,
                    "i10": "1" if won else "0", "elo": str(elo),
                    "elo_delta": str(delta), "date": when * 1000,
                    "i6": "16", "i8": "9", "i7": "2", "c2": "1.78",
                    "c10": "93.9", "i12": "17", "i5": "team_x"}
        return json.dumps([
            row("1-a", "de_ancient", 13, "13 / 4", True, 1448, 29, 3000),
            # The score line does not always lead with the player's team.
            row("1-b", "de_dust2", 22, "20 / 22", True, 1362, 23, 2000),
            row("1-c", "de_nuke", 10, "13 / 10", False, 1291, -21, 1000),
        ]).encode()

    def test_history_reads_the_players_own_score_first(self):
        """c5 is their rounds; the string is ordered however FACEIT likes."""
        got = demos.history("pid", opener=_opener(self._rows()))
        self.assertEqual(got[1]["score"], "22 / 20")

    def test_a_loss_is_marked_as_one(self):
        got = demos.history("pid", opener=_opener(self._rows()))
        lost = next(m for m in got if m["match_id"] == "1-c")
        self.assertFalse(lost["won"])
        self.assertEqual(lost["elo_delta"], -21)

    def test_newest_first(self):
        got = demos.history("pid", opener=_opener(self._rows()))
        self.assertEqual([m["match_id"] for m in got], ["1-a", "1-b", "1-c"])

    def test_rows_without_a_match_id_are_skipped(self):
        data = json.dumps([{"i1": "de_x"}, {"matchId": "1-a", "c5": "13"}]).encode()
        self.assertEqual(len(demos.history("pid", opener=_opener(data))), 1)

    def test_the_size_asked_for_is_kept_sane(self):
        seen = {}
        def watch(url, timeout=None):
            seen["url"] = url
            return _Response(b"[]")
        demos.history("pid", size=5000, opener=watch)
        self.assertIn("size=50", seen["url"])

    def test_no_player_never_reaches_faceit(self):
        def explode(url, timeout=None):
            raise AssertionError("should not have asked")
        with self.assertRaises(demos.DemoError):
            demos.history("", opener=explode)


class TakingOverFromTheBrowser(unittest.TestCase):
    """FACEIT's CDN answers a browser and challenges anything else, so the
    browser does the download and this takes the file from there."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.downloads = Path(self.tmp.name) / "Downloads"
        self.replays = Path(self.tmp.name) / "replays"
        self.downloads.mkdir()
        self.replays.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _drop(self, name, data=b"PBDEMS2" + b"x" * 400):
        path = self.downloads / name
        path.write_bytes(data)
        return path

    def test_it_recognises_a_demo_by_its_match_id(self):
        self._drop(f"{MATCH}-1-1.dem")
        found = demos.waiting(MATCH, [self.downloads])
        self.assertIsNotNone(found)
        self.assertEqual(found["name"], f"{MATCH}-1-1.dem")

    def test_another_matchs_demo_is_not_mistaken_for_this_one(self):
        self._drop("1-11111111-2222-3333-4444-555555555555-1-1.dem")
        self.assertIsNone(demos.waiting(MATCH, [self.downloads]))

    def test_unrelated_downloads_are_ignored(self):
        self._drop("holiday.jpg")
        self._drop("song.mp3")
        self.assertIsNone(demos.waiting(MATCH, [self.downloads]))

    def test_the_unpacked_copy_is_preferred_when_both_are_there(self):
        """Browsers leave both; adopting the plain one skips a decompress."""
        self._drop(f"{MATCH}-1-1.dem.zst", b"\x28\xb5\x2f\xfd" + b"\0" * 40)
        self._drop(f"{MATCH}-1-1.dem")
        self.assertTrue(demos.waiting(MATCH, [self.downloads])["name"].endswith(".dem"))

    def test_a_browser_download_in_flight_is_reported_not_adopted(self):
        """Chrome writes .crdownload until it is done. Importing that would
        put half a demo in the replay folder and call it ready."""
        self._drop(f"{MATCH}-1-1.dem.crdownload", b"half a demo")
        found = demos.waiting(MATCH, [self.downloads])
        self.assertIsNotNone(found)
        self.assertTrue(found["pending"])

    def test_a_finished_file_wins_over_one_still_arriving(self):
        self._drop(f"{MATCH}-1-1.dem.crdownload", b"half")
        self._drop(f"{MATCH}-1-1.dem")
        found = demos.waiting(MATCH, [self.downloads])
        self.assertFalse(found["pending"])
        self.assertTrue(found["name"].endswith(".dem"))

    def test_firefox_part_files_count_as_in_flight_too(self):
        self._drop(f"{MATCH}-1-1.dem.part", b"half")
        self.assertTrue(demos.waiting(MATCH, [self.downloads])["pending"])

    def test_an_empty_file_does_not_count_as_arrived(self):
        """A download still in flight is a zero-byte file for a moment."""
        (self.downloads / f"{MATCH}-1-1.dem").write_bytes(b"")
        self.assertIsNone(demos.waiting(MATCH, [self.downloads]))

    def test_a_missing_downloads_folder_is_not_an_error(self):
        self.assertIsNone(demos.waiting(MATCH, [Path(self.tmp.name) / "nope"]))

    def test_adopting_names_it_the_way_everything_else_expects(self):
        src = self._drop(f"{MATCH}-1-1.dem")
        out = demos.adopt(src, MATCH, self.replays, {"map": "de_mirage"})
        self.assertEqual(out.name, demos.local_name(MATCH, {"map": "de_mirage"}))
        self.assertTrue(out.read_bytes().startswith(b"PBDEMS2"))

    def test_adopting_decompresses_a_zstd_download(self):
        try:
            import zstandard
        except ImportError:
            self.skipTest("zstandard is not installed")
        body = b"PBDEMS2" + b"ROUND" * 900
        src = self._drop(f"{MATCH}-1-1.dem.zst",
                         zstandard.ZstdCompressor().compress(body))
        out = demos.adopt(src, MATCH, self.replays)
        self.assertEqual(out.read_bytes(), body)

    def test_the_users_own_download_is_left_alone(self):
        """It is their file in their folder. Not ours to delete."""
        src = self._drop(f"{MATCH}-1-1.dem")
        demos.adopt(src, MATCH, self.replays)
        self.assertTrue(src.is_file())

    def test_a_file_that_vanished_reports_rather_than_crashes(self):
        with self.assertRaises(demos.DemoError):
            demos.adopt(self.downloads / "gone.dem", MATCH, self.replays)

    def test_a_corrupt_archive_leaves_no_half_demo_behind(self):
        src = self._drop(f"{MATCH}-1-1.dem.gz", b"not actually gzip")
        with self.assertRaises(demos.DemoError):
            demos.adopt(src, MATCH, self.replays)
        self.assertEqual(list(self.replays.iterdir()), [])


class WhereTheyLive(unittest.TestCase):
    def test_the_replay_folder_is_beside_cfg_not_inside_it(self):
        """The game's own downloads land here, and playdemo resolves from
        game/csgo -- putting them under cfg would need the full path typed."""
        found = demos.replay_dir(Path("C:/games/CS2"))
        self.assertEqual(found, Path("C:/games/CS2/game/csgo/replays"))
        self.assertNotIn("cfg", found.parts)


class Playing(unittest.TestCase):
    def test_the_command_drops_the_extension_cs2_adds_back(self):
        self.assertEqual(demos.play_command("thing.dem"), 'playdemo "replays/thing"')

    def test_it_takes_a_name_with_or_without_the_extension(self):
        self.assertEqual(demos.play_command("thing"), demos.play_command("thing.dem"))

    def test_a_path_is_reduced_to_its_name(self):
        """Whatever is passed, the command stays inside the replay folder."""
        self.assertEqual(demos.play_command("/etc/passwd.dem"),
                         'playdemo "replays/passwd"')

    def test_the_config_binds_rather_than_plays(self):
        """Exec'd from the autoexec, a bare playdemo runs too early to work."""
        body = demos.render_cfg("faceit_abc.dem", key="F9")
        self.assertIn('bind "F9"', body)
        self.assertIn("playdemo", body)
        self.assertNotRegex(body, r"(?m)^\s*playdemo")

    def test_the_config_names_the_demo_it_is_for(self):
        self.assertIn("faceit_abc.dem", demos.render_cfg("faceit_abc.dem"))


if __name__ == "__main__":
    unittest.main()


class NotSendingPeopleNowhere(unittest.TestCase):
    """FACEIT publishes demo addresses on hosts that do not exist -- the same
    dead host for matches that definitely downloaded through their site. So
    the address is checked before a browser is pointed at it."""

    def test_a_host_that_does_not_exist_is_not_reachable(self):
        self.assertFalse(demos.reachable(
            "https://demos-europe-central.backblaze.faceit-cdn.net/cs2/x.dem.zst"))

    def test_a_host_that_does_exist_is(self):
        self.assertTrue(demos.reachable("https://www.faceit.com/whatever"))

    def test_nonsense_is_not_reachable(self):
        for bad in ["", None, "not a url", "/just/a/path"]:
            self.assertFalse(demos.reachable(bad), bad)


class TheBindMustParse(unittest.TestCase):
    """A bind is itself a quoted string. A second pair of quotes inside it
    closes the bind early and the key silently does nothing -- which is
    exactly what shipped before this test existed."""

    def test_the_bind_line_has_balanced_quotes(self):
        line = next(l for l in demos.render_cfg("faceit_abc_demirage.dem", "F9")
                    .splitlines() if l.startswith("bind"))
        self.assertEqual(line.count('"') % 2, 0)
        self.assertEqual(line.count('"'), 4, f"nested quotes in: {line}")

    def test_the_bind_is_exactly_what_cs2_expects(self):
        line = next(l for l in demos.render_cfg("faceit_abc_demirage.dem", "F9")
                    .splitlines() if l.startswith("bind"))
        self.assertEqual(line, 'bind "F9" "playdemo replays/faceit_abc_demirage"')

    def test_the_console_form_keeps_its_quotes(self):
        """Typed at the console the path is quoted; only the bind drops them."""
        self.assertEqual(demos.play_command("x.dem"), 'playdemo "replays/x"')
        self.assertEqual(demos.play_command("x.dem", quoted=False),
                         "playdemo replays/x")

    def test_both_forms_name_the_same_demo(self):
        for name in ["a.dem", "a", "/tmp/a.dem"]:
            self.assertEqual(demos.demo_path(name), "replays/a")
