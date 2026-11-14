"""Pure CSV/aggregation and lifecycle tests: no ETW, GPU, admin or display."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg.overlay.hud import display_lines
from cs2cfg.overlay.presentmon import (
    Aggregator, Frame, PresentMon, classify_status, locate_executable, parse_csv,
)


FIXTURE = Path(__file__).parent / "fixtures" / "overlay_presentmon.csv"


class CsvAndAggregation(unittest.TestCase):
    def fixture(self):
        with FIXTURE.open(encoding="utf-8") as stream:
            return list(parse_csv(stream))

    def test_fixture_ignores_other_processes_unknown_columns_and_missing_metrics(self):
        frames = self.fixture()
        self.assertEqual(len(frames), 6)
        self.assertEqual([frame.frame_time_ms for frame in frames], [4, 4, 4, 12, None, None])
        self.assertIsNone(frames[-1].present_mode)
        self.assertEqual(frames[0].latency_ms,
                         {"display_latency": 10, "click_to_photon": None, "all_input_to_photon": None})

    def test_fixture_one_second_metrics(self):
        aggregator = Aggregator()
        for frame in self.fixture():
            aggregator.add(frame)
        result = aggregator.snapshot()
        self.assertEqual(result["frame_count"], 4)
        self.assertAlmostEqual(result["fps"], 1000 * 4 / 24)
        self.assertAlmostEqual(result["one_percent_low"], 1000 / 12)
        self.assertEqual(result["frame_time_ms"], 6)
        self.assertEqual(result["max_frame_time_ms"], 12)
        self.assertEqual(result["spikes"], 1)
        self.assertEqual(result["present_modes"], {"Hardware: Independent Flip": 3, "Composed: Flip": 2})
        self.assertEqual(result["latency_ms"],
                         {"display_latency": 12, "click_to_photon": 21, "all_input_to_photon": 31})
        self.assertEqual(result["frame_time_histogram_ms"], {"4.0000": 3, "12.0000": 1})

    def test_header_aliases_bom_case_and_column_order(self):
        for header in ("MsBetweenPresents", "msBetweenPresents", "FrameTime"):
            with self.subTest(header=header):
                frames = list(parse_csv(io.StringIO(
                    f"\ufeffPresentMode,Unknown,{header},MsUntilDisplayed\nHardware: Independent Flip,x,5,9\n")))
                self.assertEqual(len(frames), 1)
                self.assertEqual(frames[0].frame_time_ms, 5)
                self.assertEqual(frames[0].latency_ms, {"until_displayed": 9})

    def test_repeated_headers_banners_and_short_rows(self):
        frames = list(parse_csv(io.StringIO(
            "PresentMon 2.6.0\nFrameTime,PresentMode\n4,mode\nbad\n"
            "MsBetweenPresents,PresentMode\n5,mode\n")))
        self.assertEqual([frame.frame_time_ms for frame in frames], [4, 5])

    def test_missing_na_invalid_and_non_finite_values_stay_missing(self):
        for value in ("", "NA", "na", "NaN", "inf", "-1", "0", "broken"):
            with self.subTest(value=value):
                frame = next(iter(parse_csv(io.StringIO(f"FrameTime,DisplayLatency\n{value},NA\n"))))
                self.assertIsNone(frame.frame_time_ms)
                self.assertIsNone(frame.latency_ms["display_latency"])

    def test_p99_is_nearest_rank_not_the_maximum_for_100_frames(self):
        aggregator = Aggregator()
        for value in [4] * 98 + [10, 100]:
            aggregator.add(Frame(value))
        result = aggregator.snapshot()
        self.assertEqual(result["p99_frame_time_ms"], 10)
        self.assertEqual(result["one_percent_low"], 100)
        self.assertEqual(result["max_frame_time_ms"], 100)

    def test_empty_second_resets_metrics_not_rolling_baseline(self):
        aggregator = Aggregator()
        aggregator.add(Frame(4))
        aggregator.snapshot()
        empty = aggregator.snapshot()
        self.assertIsNone(empty["fps"])
        self.assertIsNone(empty["one_percent_low"])
        self.assertEqual(empty["spikes"], 0)
        self.assertEqual(empty["present_modes"], {})
        aggregator.add(Frame(11))
        self.assertEqual(aggregator.snapshot()["spikes"], 1)

    def test_spike_rule_is_strict_on_both_thresholds(self):
        for baseline, value, expected in ((4, 10, 0), (4, 10.001, 1), (2, 8, 0), (2, 8.001, 1)):
            with self.subTest(baseline=baseline, value=value):
                aggregator = Aggregator()
                for _ in range(10):
                    aggregator.add(Frame(baseline))
                aggregator.add(Frame(value))
                self.assertEqual(aggregator.snapshot()["spikes"], expected)

    def test_rolling_median_expires_after_120_frames(self):
        aggregator = Aggregator()
        for _ in range(120):
            aggregator.add(Frame(4))
        for _ in range(120):
            aggregator.add(Frame(10))
        aggregator.snapshot()
        aggregator.add(Frame(24))
        self.assertEqual(aggregator.snapshot()["spikes"], 0)
        aggregator.add(Frame(26))
        self.assertEqual(aggregator.snapshot()["spikes"], 1)

    def test_swapchains_have_independent_baselines(self):
        aggregator = Aggregator()
        aggregator.add(Frame(2, stream="a"))
        aggregator.add(Frame(20, stream="b"))
        self.assertEqual(aggregator.snapshot()["spikes"], 0)


class StatusAndDiscovery(unittest.TestCase):
    def test_access_denied_stderr_takes_precedence_over_missing_game(self):
        self.assertEqual(classify_status("error: failed to start trace session: access denied.",
                                         None, game_running=False), "access_denied")

    def test_access_denied_exit_codes(self):
        for code in (5, 6, 0x80070005, -2147024891):
            self.assertEqual(classify_status("", code, game_running=False), "access_denied")

    def test_game_absent_while_child_is_still_running(self):
        self.assertEqual(classify_status("", None, game_running=False), "not_found")

    def test_target_process_not_found_message(self):
        self.assertEqual(classify_status("Target process cs2.exe not found", 1, game_running=True), "not_found")

    def test_other_failure_does_not_get_misreported_as_missing_game(self):
        self.assertEqual(classify_status("bad argument", 2, game_running=False), "error")

    def test_waiting_ok_and_clean_exit(self):
        self.assertEqual(classify_status("", None, game_running=True), "waiting")
        self.assertEqual(classify_status("", None, game_running=True, has_frames=True), "ok")
        self.assertEqual(classify_status("", 0, game_running=True), "stopped")

    def test_newest_version_wins_numeric_not_lexical(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict("os.environ", {}, clear=True):
            root = Path(directory)
            for name in ("PresentMon-2.9.0-x64.exe", "PresentMon-2.10.0-x64.exe", "PresentMon-1.0.exe"):
                (root / name).touch()
            self.assertEqual(locate_executable(root).name, "PresentMon-2.10.0-x64.exe")

    def test_override_and_missing_override(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "custom.exe"
            executable.touch()
            with mock.patch.dict("os.environ", {"CS2CFG_PRESENTMON": str(executable)}):
                self.assertEqual(locate_executable(), executable.resolve())
            with mock.patch.dict("os.environ", {"CS2CFG_PRESENTMON": str(executable) + "missing"}):
                self.assertIsNone(locate_executable())

    def test_hud_has_dashes_and_status_without_data(self):
        lines = display_lines({"status": "cs2.exe not found"})
        self.assertIn("FPS --", lines[0])
        self.assertIn("CPU --", lines[1])
        self.assertEqual(lines[2], "cs2.exe not found")


class ChildLifecycle(unittest.TestCase):
    @mock.patch("cs2cfg.overlay.presentmon.locate_executable", return_value=Path("PresentMon.exe"))
    def test_capture_and_stop_are_scoped_to_unique_session(self, _):
        first, second = PresentMon(Aggregator()), PresentMon(Aggregator())
        self.assertNotEqual(first.session, second.session)
        self.assertIn("--output_stdout", first.command)
        self.assertIn("--terminate_on_proc_exit", first.command)
        self.assertIn("--no_console_stats", first.command)
        child = mock.Mock()
        first.process = child
        with mock.patch("cs2cfg.overlay.presentmon.subprocess.run") as run:
            first.stop()
        self.assertEqual(run.call_args.args[0],
                         ["PresentMon.exe", "--session_name", first.session, "--terminate_existing_session"])
        child.wait.assert_called_once()
        child.stdout.close.assert_called_once()
        child.stderr.close.assert_called_once()

    @mock.patch("cs2cfg.overlay.presentmon.locate_executable", return_value=None)
    def test_missing_binary_start_and_stop_are_harmless(self, _):
        capture = PresentMon(Aggregator())
        capture.start()
        self.assertEqual(capture.status(False, False), "missing")
        capture.stop()


if __name__ == "__main__":
    unittest.main()
