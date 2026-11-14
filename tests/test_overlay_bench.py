"""Comparison math is independent of Windows and any live capture."""

import unittest

from tools.overlay_bench import compare, percent_difference, summarise


class ComparisonMath(unittest.TestCase):
    def test_relative_percent_difference(self):
        self.assertAlmostEqual(percent_difference(200, 198), -1)
        self.assertAlmostEqual(percent_difference(0.2, 0.3), 50)
        for before, after in ((0, 1), (None, 1), (1, None)):
            self.assertIsNone(percent_difference(before, after))

    def test_run_metrics_use_frames_and_distribution_not_mean_of_second_percentiles(self):
        rows = [
            {"frame_count": 99, "frame_time_sum_ms": 396, "frame_time_histogram_ms": {"4": 99},
             "present_modes": {"Hardware: Independent Flip": 99},
             "overlay_cpu_percent": 0.2, "working_set_mb": 20, "status": "ok"},
            {"frame_count": 1, "frame_time_sum_ms": 100, "frame_time_histogram_ms": {"100": 1},
             "present_modes": {"Composed: Flip": 1},
             "overlay_cpu_percent": 0.4, "working_set_mb": 30, "status": "ok"},
        ]
        result = summarise(rows)
        self.assertAlmostEqual(result["fps"], 1000 * 100 / 496)
        self.assertEqual(result["one_percent_low"], 250)
        self.assertEqual(result["present_mode_share"], {"Hardware: Independent Flip": 99, "Composed: Flip": 1})
        self.assertAlmostEqual(result["overlay_cpu_percent"], 0.3)
        self.assertEqual(result["working_set_mb"], 25)
        self.assertEqual(result["peak_working_set_mb"], 30)

    def test_no_data_is_missing_and_resource_metrics_still_compare(self):
        before = summarise([{"overlay_cpu_percent": 0.1, "working_set_mb": 20}])
        after = summarise([{"overlay_cpu_percent": 0.2, "working_set_mb": 21}])
        changes = compare(before, after)
        self.assertIsNone(changes["fps"])
        self.assertIsNone(changes["one_percent_low"])
        self.assertEqual(changes["overlay_cpu_percent"], 100)
        self.assertEqual(changes["working_set_mb"], 5)
        self.assertEqual(before["present_mode_share"], {})

    def test_empty_capture(self):
        result = summarise([])
        self.assertEqual(result["samples"], 0)
        self.assertIsNone(result["fps"])
        self.assertIsNone(result["working_set_mb"])


if __name__ == "__main__":
    unittest.main()
