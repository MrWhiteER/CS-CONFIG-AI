"""One telemetry recorder shared by launcher and overlay, with event delivery."""

import types
import unittest
from unittest import mock

from cs2cfg import telemetry
from cs2cfg.overlay.service import OverlayService


class SharedRecorder(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.dict(telemetry._recorders, {}, clear=True)
        patch.start()
        self.addCleanup(patch.stop)

    def test_two_owners_use_one_detector_and_last_release_stops_it(self):
        recorder = mock.Mock(hwnd=123, meta={})
        with mock.patch.object(telemetry, "SessionRecorder", return_value=recorder) as create:
            first = telemetry.acquire_recorder(123)
            second = telemetry.acquire_recorder(123, {"borderless": True})
            self.assertIs(first, second)
            telemetry.release_recorder(first)
            recorder.stop.assert_not_called()
            telemetry.release_recorder(second)
        create.assert_called_once_with(123, None)
        recorder.start.assert_called_once()
        recorder.stop.assert_called_once()
        self.assertTrue(recorder.meta["borderless"])
        self.assertEqual(telemetry._recorders, {})

    def test_launcher_finish_finalises_even_with_overlay_lease(self):
        recorder = mock.Mock(hwnd=123, meta={})
        with mock.patch.object(telemetry, "SessionRecorder", return_value=recorder):
            telemetry.acquire_recorder(123)
            telemetry.acquire_recorder(123)
            telemetry.release_recorder(recorder, finish=True)
            telemetry.release_recorder(recorder)
        recorder.stop.assert_called_once()

    def test_event_delivery_final_summary_and_unsubscribe(self):
        with mock.patch.object(telemetry, "_listeners", []):
            service = OverlayService()
            recorder = types.SimpleNamespace(started=100, record=types.SimpleNamespace(overlay=None))
            service._recorder = recorder
            unsubscribe = telemetry.subscribe(service._stall, service._finalising)
            telemetry._publish(0, recorder, telemetry.Stall(at=2, seconds=.35, focused=True))
            telemetry._publish(1, recorder)
            self.assertEqual(len(service.snapshot()["events"]), 1)
            self.assertAlmostEqual(recorder.record.overlay["worst_freeze_ms"], 350)
            unsubscribe()
            unsubscribe()
            telemetry._publish(0, recorder, telemetry.Stall(at=10, seconds=1, focused=True))
            self.assertEqual(len(service.snapshot()["events"]), 1)

    def test_optional_consumer_failure_does_not_stop_other_consumers(self):
        with mock.patch.object(telemetry, "_listeners", []):
            telemetry.subscribe(mock.Mock(side_effect=ValueError), mock.Mock())
            delivered = mock.Mock()
            telemetry.subscribe(delivered, mock.Mock())
            telemetry._publish(0, "recorder", "stall")
            delivered.assert_called_once_with("recorder", "stall")

    def test_summary_written_with_existing_session_and_old_history_loads(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as folder, mock.patch.object(
                telemetry, "sessions_dir", return_value=Path(folder)):
            summary = {"avg_fps": 200, "one_percent_low": 100, "worst_frame_ms": 30,
                       "stutter_count": 2, "worst_freeze_ms": 500}
            record = telemetry.SessionRecord(stamp="20261114-123456", started="now", overlay=summary)
            telemetry._write(record)
            (Path(folder) / "20261113-123456.json").write_text(
                json.dumps({"stamp": "old", "started": "before", "duration": 1}), encoding="utf-8")
            sessions = telemetry.load_sessions()
        self.assertEqual(sessions[0]["overlay"], summary)
        self.assertNotIn("overlay", sessions[1])

    def test_existing_detector_times_one_continuous_not_responding_interval(self):
        import threading

        recorder = object.__new__(telemetry.SessionRecorder)
        recorder.started = 100
        recorder._lock = threading.Lock()
        recorder._stalls = []
        recorder._open_stall = recorder._stall_since = None
        with mock.patch.object(telemetry, "_publish") as publish:
            recorder._sample_stall(True, 100, 10, True)
            publish.assert_not_called()
            recorder._sample_stall(False, 101, 11, True)
            recorder._sample_stall(False, 101.5, 11.5, True)
            recorder._sample_stall(True, 102, 12, False)
        self.assertEqual(len(recorder._stalls), 1)
        self.assertEqual(recorder._stalls[0].seconds, 1)
        self.assertEqual(recorder._stalls[0].at, 2)
        self.assertIsNone(recorder._open_stall)
        self.assertEqual(publish.call_count, 3)

    def test_unavailable_responsiveness_query_does_not_invent_a_stall(self):
        recorder = object.__new__(telemetry.SessionRecorder)
        with mock.patch.object(telemetry, "_publish") as publish:
            recorder._sample_stall(None, 100, 10, True)
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
