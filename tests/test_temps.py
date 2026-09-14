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
        """83 is hot for a GPU and unremarkable for a CPU, so one shared
        threshold would either cry wolf or say nothing."""
        self.assertEqual(temps.Reading("gpu", "GPU", celsius=84).state, "warm")
        self.assertEqual(temps.Reading("cpu", "CPU", celsius=84).state, "fine")

    def test_past_the_limit_is_hot(self):
        self.assertEqual(temps.Reading("cpu", "CPU", celsius=97).state, "hot")
        self.assertEqual(temps.Reading("gpu", "GPU", celsius=88).state, "hot")

    def test_a_missing_reading_is_unknown_not_zero(self):
        found = temps.Reading("cpu", "CPU", unavailable="needs administrator")
        self.assertFalse(found.known)
        self.assertEqual(found.state, "unknown")
        self.assertIsNone(found.celsius)


class NotInventingNumbers(unittest.TestCase):
    def test_the_cpu_says_why_it_cannot_be_read_without_admin(self):
        with mock.patch.object(temps, "_elevated", return_value=False):
            found = temps._cpu()
        self.assertFalse(found.known)
        self.assertIn("administrator", found.unavailable)

    def test_a_machine_with_no_thermal_zone_says_so(self):
        with mock.patch.object(temps, "_elevated", return_value=True), \
             mock.patch.object(temps, "_powershell", return_value=""):
            found = temps._cpu()
        self.assertFalse(found.known)
        self.assertIn("no thermal zone", found.unavailable)

    def test_deci_kelvin_is_converted(self):
        # 3151 tenths of a kelvin is 42.0 C.
        with mock.patch.object(temps, "_elevated", return_value=True), \
             mock.patch.object(temps, "_powershell", return_value="3151"):
            found = temps._cpu()
        self.assertAlmostEqual(found.celsius, 42.0, places=1)

    def test_a_firmware_constant_is_rejected_rather_than_shown(self):
        """Some firmware fills this field with a fixed value. 2732 tenths is
        exactly 0 C, which is not a temperature any running CPU is at, and it
        looks like a working sensor."""
        with mock.patch.object(temps, "_elevated", return_value=True), \
             mock.patch.object(temps, "_powershell", return_value="2732"):
            found = temps._cpu()
        self.assertFalse(found.known)

    def test_the_warmest_zone_wins(self):
        with mock.patch.object(temps, "_elevated", return_value=True), \
             mock.patch.object(temps, "_powershell",
                               return_value="3151\n3451\n3251"):
            found = temps._cpu()
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
        self.assertEqual([f.label for f in found], ["Samsung 980 PRO"])
        self.assertEqual(found[0].celsius, 41.0)

    def test_unparseable_output_yields_nothing_rather_than_raising(self):
        with mock.patch.object(temps, "_elevated", return_value=True), \
             mock.patch.object(temps, "_powershell", return_value="not json"):
            self.assertEqual(temps._drives(), [])


class TheReadout(unittest.TestCase):
    def test_the_hottest_known_part_is_the_one_reported(self):
        found = temps.Readings(parts=[
            temps.Reading("gpu", "GPU", celsius=54),
            temps.Reading("cpu", "CPU", unavailable="needs administrator"),
            temps.Reading("drive", "980 PRO", celsius=61),
        ])
        self.assertEqual(found.hottest.label, "980 PRO")

    def test_nothing_known_reports_no_hottest_rather_than_zero(self):
        found = temps.Readings(parts=[temps.Reading("cpu", "CPU", unavailable="x")])
        self.assertIsNone(found.hottest)

    def test_the_payload_carries_the_reason_a_part_is_missing(self):
        found = temps.Readings(parts=[
            temps.Reading("cpu", "CPU", unavailable="needs administrator")])
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


if __name__ == "__main__":
    unittest.main()
