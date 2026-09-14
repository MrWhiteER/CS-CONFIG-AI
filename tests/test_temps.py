"""Tests for the temperature read-out.

Heat is why a machine that benchmarks well plays badly: nothing reports an
error, the part simply stops boosting and the frame rate sags. So it is worth
showing -- but only where the number is real. A wrong temperature is worse than
none, because it is the one somebody takes their side panel off for.

What these pin is mostly that: no invented numbers, no plausible-looking
reading from the wrong sensor, and a clear reason when there is nothing to
show.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import temps  # noqa: E402


class Thresholds(unittest.TestCase):
    def test_a_cool_part_is_fine(self):
        self.assertEqual(temps.Reading("gpu", "GPU", celsius=54).state, "fine")

    def test_each_part_has_its_own_limit(self):
        """83 is hot for a GPU and unremarkable for a board sensor, so one
        shared threshold would either cry wolf or say nothing."""
        self.assertEqual(temps.Reading("gpu", "GPU", celsius=84).state, "warm")
        self.assertEqual(temps.Reading("system", "System", celsius=50).state, "fine")

    def test_past_the_limit_is_hot(self):
        self.assertEqual(temps.Reading("system", "System", celsius=75).state, "hot")
        self.assertEqual(temps.Reading("gpu", "GPU", celsius=88).state, "hot")

    def test_a_missing_reading_is_unknown_not_zero(self):
        found = temps.Reading("system", "System", unavailable="needs administrator")
        self.assertFalse(found.known)
        self.assertEqual(found.state, "unknown")
        self.assertIsNone(found.celsius)


class NotInventingNumbers(unittest.TestCase):
    def test_the_zone_says_why_it_cannot_be_read_without_admin(self):
        with mock.patch.object(temps, "_elevated", return_value=False):
            found = temps._system_zone()
        self.assertFalse(found.known)
        self.assertIn("administrator", found.unavailable)

    def test_a_machine_with_no_thermal_zone_says_so(self):
        with mock.patch.object(temps, "_elevated", return_value=True), \
             mock.patch.object(temps, "_powershell", return_value=""):
            found = temps._system_zone()
        self.assertFalse(found.known)
        self.assertIn("no thermal zone", found.unavailable)

    def test_deci_kelvin_is_converted(self):
        # 3151 tenths of a kelvin is 42.0 C.
        with mock.patch.object(temps, "_elevated", return_value=True), \
             mock.patch.object(temps, "_powershell", return_value="3151"):
            found = temps._system_zone()
        self.assertAlmostEqual(found.celsius, 42.0, places=1)

    def test_a_firmware_constant_is_rejected_rather_than_shown(self):
        """Some firmware answers this field with a constant. 2732 tenths is
        exactly 0 C, which nothing in a running machine is at, and a fixed
        value looks exactly like a working sensor."""
        with mock.patch.object(temps, "_elevated", return_value=True), \
             mock.patch.object(temps, "_powershell", return_value="2732"):
            found = temps._system_zone()
        self.assertFalse(found.known)

    def test_the_warmest_zone_wins(self):
        with mock.patch.object(temps, "_elevated", return_value=True), \
             mock.patch.object(temps, "_powershell",
                               return_value="3151\n3451\n3251"):
            found = temps._system_zone()
        self.assertAlmostEqual(found.celsius, 72.0, places=1)

    def test_drives_need_admin_and_say_so(self):
        with mock.patch.object(temps, "_elevated", return_value=False):
            found = temps._drives()
        self.assertEqual(len(found), 1)
        self.assertIn("administrator", found[0].unavailable)

    def test_a_drive_reporting_nothing_is_left_out_entirely(self):
        """Every disk answers the query; only some carry a temperature. A row
        of dashes for four drives is noise, not information."""
        payload = ('[{"Name":"Samsung 980 PRO","Temp":41},'
                   '{"Name":"ST1000DM010","Temp":null}]')
        with mock.patch.object(temps, "_elevated", return_value=True), \
             mock.patch.object(temps, "_powershell", return_value=payload):
            found = temps._drives()
        self.assertEqual([f.label for f in found], ["980 PRO"])
        self.assertEqual(found[0].celsius, 41.0)

    def test_unparseable_output_yields_nothing_rather_than_raising(self):
        with mock.patch.object(temps, "_elevated", return_value=True), \
             mock.patch.object(temps, "_powershell", return_value="not json"):
            self.assertEqual(temps._drives(), [])


class TheReadout(unittest.TestCase):
    def test_the_hottest_known_part_is_the_one_reported(self):
        found = temps.Readings(parts=[
            temps.Reading("gpu", "GPU", celsius=54),
            temps.Reading("system", "System", unavailable="needs administrator"),
            temps.Reading("drive", "980 PRO", celsius=61),
        ])
        self.assertEqual(found.hottest.label, "980 PRO")

    def test_nothing_known_reports_no_hottest_rather_than_zero(self):
        found = temps.Readings(parts=[temps.Reading("system", "System", unavailable="x")])
        self.assertIsNone(found.hottest)

    def test_the_payload_carries_the_reason_a_part_is_missing(self):
        found = temps.Readings(parts=[
            temps.Reading("system", "System", unavailable="needs administrator")])
        shape = temps.as_dict(found)
        self.assertFalse(shape["parts"][0]["known"])
        self.assertEqual(shape["parts"][0]["unavailable"], "needs administrator")
        self.assertIsNone(shape["hottest"])


class ReadingIsCheap(unittest.TestCase):
    def test_read_never_blocks_on_the_first_call(self):
        """The gauges poll about once a second and each source costs a
        PowerShell start. A read that collected in line would make the whole
        readout stutter."""
        watcher = temps.Watcher()
        with mock.patch.object(watcher, "_collect",
                               side_effect=AssertionError("collected inline")):
            found = watcher.read()
        self.assertEqual(found.parts, [])



class TheElevatedHelper(unittest.TestCase):
    """Only the reader is elevated, never the application.

    The app launches CS2 through the steam:// protocol, and a protocol handler
    invoked from an elevated process starts Steam elevated too. Steam then
    writes its library as administrator, which Valve advises against and which
    is unpleasant to unpick. A UAC prompt on every launch to read a
    thermometer is a poor trade by itself; one that can leave the game library
    owned by the wrong user is not a trade at all.
    """

    def setUp(self):
        import tempfile as tf
        tmp = tf.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "temps_elevated.json"
        patch = mock.patch.object(temps, "helper_path", return_value=self.path)
        patch.start()
        self.addCleanup(patch.stop)

    def publish(self, parts, age=0.0):
        import json
        import time as clock
        self.path.write_text(json.dumps({
            "at": clock.time() - age, "parts": parts}), encoding="utf-8")

    def test_published_readings_are_used_when_fresh(self):
        self.publish([{"part": "drive", "label": "980 PRO", "celsius": 49}])
        found = temps._published()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].celsius, 49)

    def test_a_dead_helper_stops_being_believed(self):
        """The file outlives the process that wrote it. Trusting it forever
        would freeze a temperature on screen while the part actually heats."""
        self.publish([{"part": "drive", "label": "980 PRO", "celsius": 49}],
                     age=temps.HELPER_STALE + 5)
        self.assertEqual(temps._published(), [])

    def test_no_helper_falls_back_to_saying_why(self):
        with mock.patch.object(temps, "_elevated", return_value=False):
            found = temps.Watcher()._collect()
        by_part = {p.part: p for p in found.parts}
        self.assertIn("administrator", by_part["system"].unavailable)
        self.assertFalse(found.assisted)

    def test_a_running_helper_supplies_the_privileged_parts(self):
        self.publish([
            {"part": "system", "label": "System", "celsius": 28},
            {"part": "drive", "label": "980 PRO", "celsius": 49},
        ])
        with mock.patch.object(temps, "_gpu",
                               return_value=temps.Reading("gpu", "GPU", celsius=54)), \
             mock.patch.object(temps, "_elevated", return_value=False):
            found = temps.Watcher()._collect()
        self.assertTrue(found.assisted)
        self.assertEqual({p.label for p in found.parts}, {"GPU", "System", "980 PRO"})

    def test_a_corrupt_file_is_ignored_rather_than_raising(self):
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(temps._published(), [])

    def test_the_helper_stops_when_the_app_it_serves_is_gone(self):
        """It holds administrator rights, so it must not outlive the thing
        that asked for them -- including when that thing crashes."""
        with mock.patch.object(temps, "_parent_alive", return_value=False):
            self.assertEqual(temps.run_helper(4242), 0)
        self.assertFalse(self.path.exists(), "it should clean up after itself")

    def test_a_dead_parent_id_is_never_alive(self):
        self.assertFalse(temps._parent_alive(0))

    def test_this_process_is_alive(self):
        import os as _os
        self.assertTrue(temps._parent_alive(_os.getpid()))

class DriveNames(unittest.TestCase):
    """Four drives stacked in a row are told apart by model, not by maker."""

    def test_the_maker_and_the_size_come_off(self):
        self.assertEqual(temps._short_drive("Samsung SSD 980 PRO 1TB"), "980 PRO")
        self.assertEqual(temps._short_drive("WD Blue SN570 500GB"), "Blue SN570")

    def test_a_name_it_does_not_recognise_is_left_alone(self):
        """An unfamiliar naming scheme should read oddly, not vanish."""
        self.assertEqual(temps._short_drive("ST1000DM010-2EP102"),
                         "ST1000DM010-2EP102")
        self.assertEqual(temps._short_drive("Some Odd Device"), "Some Odd Device")

    def test_a_name_that_is_only_maker_and_size_keeps_something(self):
        self.assertTrue(temps._short_drive("Samsung 1TB"))

    def test_the_capacity_pattern_actually_matches(self):
        """It did not, once: a stray escape left a literal control character in
        the pattern, so every name kept its size and nothing looked wrong."""
        self.assertTrue(temps._CAPACITY.search("1TB"))
        self.assertTrue(temps._CAPACITY.search("500 GB"))
        self.assertFalse(temps._CAPACITY.search("SN570"))


if __name__ == "__main__":
    unittest.main()
