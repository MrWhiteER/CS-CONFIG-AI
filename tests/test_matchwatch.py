"""Noticing a found match, from what Windows' shell hook reports.

The FACEIT cases replay the sequence captured live on the player's PC on
2026-11-14 (window titles in Russian, the client's language there).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import matchwatch as mw  # noqa: E402

FOUND_RED = "\U0001F534 Матч найден"
FOUND_BLACK = "⚫ Матч найден"
ROOM = "Соревновательный матч FACEIT - FACEIT.com"
QUEUE = "Matchmaking - Middle East 5v5 Queue - FACEIT.com"


class FaceitTitles(unittest.TestCase):
    def test_the_dot_prefix_is_match_found_in_any_language(self):
        self.assertTrue(mw.faceit_title_says_found(FOUND_RED))
        self.assertTrue(mw.faceit_title_says_found(FOUND_BLACK))
        self.assertTrue(mw.faceit_title_says_found("\U0001F534 Match found"))

    def test_ordinary_titles_are_not(self):
        for title in (ROOM, QUEUE, "FACEIT.com", "FACEIT | Challenge your Game", ""):
            self.assertFalse(mw.faceit_title_says_found(title), title)


class FaceitPop(unittest.TestCase):
    def replay(self, tracker, rows):
        out = []
        for t, title in rows:
            out.append(tracker.title("faceit.exe", title, 42, t))
        return out

    def test_the_captured_pop_starts_one_alert(self):
        tr = mw.Tracker()
        # 19:21:56.124 onward, as recorded: blinking, back to the room title
        # between blinks.
        rows = [(0.0, FOUND_RED), (0.1, FOUND_RED), (0.3, ROOM),
                (1.0, FOUND_RED), (1.1, FOUND_BLACK), (1.6, ROOM),
                (2.0, FOUND_RED), (3.0, FOUND_BLACK), (4.0, FOUND_RED),
                (6.0, FOUND_RED), (7.0, FOUND_BLACK), (7.8, ROOM)]
        events = self.replay(tr, rows)
        self.assertEqual(events.count("start"), 1)
        self.assertEqual(tr.alert.source, mw.FACEIT)
        # Still blinking: no end.
        self.assertIsNone(tr.tick(7.5))

    def test_it_ends_once_the_blinking_stops(self):
        tr = mw.Tracker()
        tr.title("faceit.exe", FOUND_RED, 42, 0.0)
        tr.title("faceit.exe", FOUND_BLACK, 42, 7.0)
        tr.title("faceit.exe", QUEUE, 42, 7.8)       # accepted
        self.assertIsNone(tr.tick(9.0))
        self.assertEqual(tr.tick(10.5), "end")
        self.assertIsNone(tr.alert)

    def test_it_never_outlives_the_accept_window(self):
        tr = mw.Tracker()
        for second in range(0, 60):
            tr.title("faceit.exe", FOUND_RED, 42, float(second))
            if tr.tick(float(second) + 0.5) == "end":
                break
        self.assertIsNone(tr.alert)
        self.assertLessEqual(second, int(mw.FACEIT_MAX) + 1)

    def test_other_programs_titles_are_ignored(self):
        tr = mw.Tracker()
        self.assertIsNone(tr.title("chrome.exe", FOUND_RED, 1, 0.0))
        self.assertIsNone(tr.alert)

    def test_dismiss_ignores_the_rest_of_that_pop(self):
        tr = mw.Tracker()
        tr.title("faceit.exe", FOUND_RED, 42, 0.0)
        self.assertEqual(tr.dismiss(1.0), "end")
        self.assertIsNone(tr.title("faceit.exe", FOUND_RED, 42, 2.0))
        # ...but the next match, after that one's window, alerts again.
        self.assertEqual(tr.title("faceit.exe", FOUND_RED, 42, 100.0), "start")


class Cs2Flash(unittest.TestCase):
    def test_startup_flashes_are_ignored(self):
        tr = mw.Tracker()
        tr.created("cs2.exe", 0.0)
        self.assertIsNone(tr.flash("cs2.exe", 7, 3.0))
        self.assertIsNone(tr.flash("cs2.exe", 7, 5.0))

    def test_a_later_flash_while_away_is_a_match(self):
        tr = mw.Tracker()
        tr.created("cs2.exe", 0.0)
        self.assertEqual(tr.flash("cs2.exe", 7, 600.0, "explorer.exe"), "start")
        self.assertEqual(tr.alert.source, mw.CS2)

    def test_cs2_already_running_when_the_app_started_still_alerts(self):
        tr = mw.Tracker()
        self.assertEqual(tr.flash("cs2.exe", 7, 5.0, "explorer.exe"), "start")

    def test_no_alert_when_already_in_the_game(self):
        tr = mw.Tracker()
        tr.created("cs2.exe", 0.0)
        self.assertIsNone(tr.flash("cs2.exe", 7, 600.0, "cs2.exe"))

    def test_going_to_the_game_ends_it(self):
        tr = mw.Tracker()
        tr.created("cs2.exe", 0.0)
        tr.flash("cs2.exe", 7, 600.0, "explorer.exe")
        self.assertEqual(tr.activated("cs2.exe", 603.0), "end")

    def test_cs2_alert_times_out(self):
        tr = mw.Tracker()
        tr.created("cs2.exe", 0.0)
        tr.flash("cs2.exe", 7, 600.0)
        self.assertEqual(tr.tick(600.0 + mw.CS2_MAX), "end")


class FindingTheButton(unittest.TestCase):
    def frame(self, w, h, box=None, colour=(54, 178, 76)):
        def pixel(x, y):
            if box and box[0] <= x < box[2] and box[1] <= y < box[3]:
                return colour
            return (30, 32, 36)
        return pixel

    def test_a_green_button_is_found_near_its_centre(self):
        w, h = 1920, 1080
        box = (860, 560, 1060, 620)
        spot = mw.find_green_button(self.frame(w, h, box), w, h)
        self.assertIsNotNone(spot)
        self.assertTrue(box[0] <= spot[0] < box[2] and box[1] <= spot[1] < box[3], spot)

    def test_no_button_means_no_click(self):
        self.assertIsNone(mw.find_green_button(self.frame(1920, 1080), 1920, 1080))

    def test_a_green_screen_is_not_a_button(self):
        w, h = 1280, 960
        everything = (0, 0, w, h)
        self.assertIsNone(mw.find_green_button(self.frame(w, h, everything), w, h))


if __name__ == "__main__":
    unittest.main()
