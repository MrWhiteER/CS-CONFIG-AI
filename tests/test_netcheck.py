"""Tests for measuring the connection that sub-tick actually cares about.

The failure worth guarding against is not a crash. It is a check that reports
a clean connection on a link that is dropping packets, because then somebody
goes looking for the problem in their settings and it was never there.

Nothing here touches the network; ping's output is supplied.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import netcheck  # noqa: E402

CLEAN = """
Pinging 1.1.1.1 with 32 bytes of data:
Reply from 1.1.1.1: bytes=32 time=12ms TTL=57
Reply from 1.1.1.1: bytes=32 time=13ms TTL=57
Reply from 1.1.1.1: bytes=32 time=12ms TTL=57
Reply from 1.1.1.1: bytes=32 time=14ms TTL=57
"""

# Two of four answered. The rest timed out, which is the shape of real loss.
LOSSY = """
Pinging 1.1.1.1 with 32 bytes of data:
Reply from 1.1.1.1: bytes=32 time=12ms TTL=57
Request timed out.
Reply from 1.1.1.1: bytes=32 time=13ms TTL=57
Request timed out.
"""

JUMPY = """
Reply from 1.1.1.1: bytes=32 time=10ms TTL=57
Reply from 1.1.1.1: bytes=32 time=48ms TTL=57
Reply from 1.1.1.1: bytes=32 time=11ms TTL=57
Reply from 1.1.1.1: bytes=32 time=52ms TTL=57
"""

# Slowly drifting: a wide spread, but every step is small.
DRIFT = """
Reply from 1.1.1.1: bytes=32 time=20ms TTL=57
Reply from 1.1.1.1: bytes=32 time=23ms TTL=57
Reply from 1.1.1.1: bytes=32 time=26ms TTL=57
Reply from 1.1.1.1: bytes=32 time=29ms TTL=57
"""

# An unreachable host still produces output -- from the router, not the target.
# Counting these as replies is how a check reports 0% loss on a dead link.
UNREACHABLE = """
Pinging 192.0.2.1 with 32 bytes of data:
Reply from 192.168.1.1: Destination host unreachable.
Reply from 192.168.1.1: Destination host unreachable.
"""


def probe_from(text, count=4):
    with mock.patch.object(netcheck, "_run", return_value=text):
        return netcheck.ping("1.1.1.1", "The internet", count)


class Measuring(unittest.TestCase):
    def test_a_clean_link_reads_as_no_loss(self):
        found = probe_from(CLEAN)
        self.assertEqual(found.received, 4)
        self.assertEqual(found.loss, 0.0)
        self.assertTrue(found.reachable)

    def test_lost_packets_are_counted_not_ignored(self):
        """Replies are counted rather than ping's own summary being trusted:
        that summary is localised, and a parser that misses it on a German
        Windows reports a perfect connection."""
        found = probe_from(LOSSY)
        self.assertEqual(found.received, 2)
        self.assertEqual(found.loss, 50.0)

    def test_a_host_that_never_answers_is_total_loss(self):
        found = probe_from("")
        self.assertFalse(found.reachable)
        self.assertEqual(found.sent, 0, "nothing was measured, so claim nothing")

    def test_unreachable_replies_are_not_counted_as_answers(self):
        """The router answers on the target's behalf, and the word is still
        "Reply". What keeps these out is that a reply only counts when it
        carries a round-trip time -- matching on "Reply from" would read a
        dead link as a perfect one."""
        found = probe_from(UNREACHABLE)
        self.assertEqual(found.received, 0)
        self.assertFalse(found.reachable)

    def test_jitter_is_the_step_between_replies(self):
        found = probe_from(JUMPY)
        self.assertGreater(found.jitter, netcheck.JITTER_POOR)

    def test_a_slow_drift_is_not_jitter(self):
        """A wide spread with small steps plays fine. Standard deviation would
        call this bad; what upsets sub-tick is one packet late against the one
        before it."""
        found = probe_from(DRIFT)
        self.assertLess(found.jitter, netcheck.JITTER_FINE)
        self.assertGreater(max(found.times) - min(found.times), 8)

    def test_a_single_reply_has_no_jitter_to_report(self):
        found = probe_from("Reply from 1.1.1.1: bytes=32 time=12ms TTL=57\n", 1)
        self.assertEqual(found.jitter, 0.0)


class Wireless(unittest.TestCase):
    def test_wifi_is_recognised_however_it_is_spelled(self):
        for media, desc in [("Native 802.11", ""), ("", "Intel Wi-Fi 6 AX201"),
                            ("", "Wireless-AC 9560")]:
            self.assertTrue(netcheck.Adapter(description=desc, media=media).wireless,
                            f"{media} {desc}")

    def test_ethernet_is_not_mistaken_for_wireless(self):
        found = netcheck.Adapter(name="Ethernet", media="802.3",
                                 description="Intel(R) Ethernet Controller I225-V")
        self.assertFalse(found.wireless)


class WhatItConcludes(unittest.TestCase):
    def _survey(self, gateway_text, internet_text, adapter=None):
        with mock.patch.object(netcheck, "adapter", return_value=adapter), \
             mock.patch.object(netcheck, "gateway_address", return_value="192.168.1.1"), \
             mock.patch.object(netcheck, "_run",
                               side_effect=[gateway_text, internet_text]), \
             mock.patch.object(sys, "platform", "win32"):
            return netcheck.survey(samples=4)

    def titles(self, found):
        return " | ".join(f.title for f in found.findings)

    def test_a_clean_link_says_so_plainly(self):
        found = self._survey(CLEAN, CLEAN)
        self.assertTrue(found.ok)
        self.assertIn("Nothing wrong", self.titles(found))

    def test_loss_at_the_router_blames_the_local_network(self):
        """The useful half of the answer: this is fixable in the room."""
        found = self._survey(LOSSY, LOSSY)
        self.assertFalse(found.ok)
        self.assertIn("inside your own network", self.titles(found))

    def test_a_clean_router_with_loss_beyond_it_points_at_the_isp(self):
        found = self._survey(CLEAN, LOSSY)
        self.assertIn("past it", self.titles(found))
        self.assertNotIn("inside your own network", self.titles(found))

    def test_wifi_is_raised_before_anything_else_is_measured(self):
        found = self._survey(CLEAN, CLEAN,
                             adapter=netcheck.Adapter(name="Wi-Fi", media="Native 802.11"))
        self.assertIn("Wi-Fi", self.titles(found))

    def test_it_does_not_call_a_lossy_link_healthy(self):
        found = self._survey(CLEAN, LOSSY)
        self.assertFalse(found.ok)
        self.assertNotIn("Nothing wrong", self.titles(found))



class VSyncAndTheFileTheGameOwns(unittest.TestCase):
    """CS2 rewrites cs2_video.txt from memory when it quits.

    A picture setting written while it runs is not merely ignored -- it is
    overwritten on exit, so V-Sync comes back and it looks exactly as though
    the tool turned it on. It never does: every profile writes it off.
    """

    def test_no_profile_on_any_tier_ever_enables_vsync(self):
        from cs2cfg.kb import KnowledgeBase

        kb = KnowledgeBase()
        for intent, spec in kb.video["intents"].items():
            for tier, matrix in spec["tiers"].items():
                self.assertNotEqual(
                    matrix.get("setting.mat_vsync"), 1,
                    f"{intent}/tier {tier} would turn V-Sync on")

    def test_turning_it_off_is_unconditional(self):
        from cs2cfg.kb import KnowledgeBase

        kb = KnowledgeBase()
        rule = next((a for a in kb.video["adjustments"] if a["id"] == "vsync_off"), None)
        self.assertIsNotNone(rule, "the rule that turns V-Sync off is gone")
        self.assertEqual(rule["when"], "always")
        self.assertEqual(rule["set"]["setting.mat_vsync"], 0)

    def test_the_write_is_refused_while_the_game_is_running(self):
        from cs2cfg import steam

        user = mock.Mock()
        user.video_cfg = Path(__file__)          # exists, so we reach the guard
        with mock.patch.object(steam, "cs2_running", return_value=True):
            with self.assertRaises(steam.SteamError) as caught:
                steam.write_video_cfg(user, {"setting.mat_vsync": 0})
        self.assertIn("rewrites", str(caught.exception))

    def test_force_is_there_for_a_caller_that_means_it(self):
        from cs2cfg import steam

        user = mock.Mock()
        user.video_cfg = Path(__file__)
        with mock.patch.object(steam, "cs2_running", return_value=True):
            # Past the guard, so it fails on parsing this file rather than on
            # the game being open -- which is the point being pinned.
            with self.assertRaises(Exception) as caught:
                steam.write_video_cfg(user, {"setting.mat_vsync": 0}, force=True)
        self.assertNotIn("rewrites", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
