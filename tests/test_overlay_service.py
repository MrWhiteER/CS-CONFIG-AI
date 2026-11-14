"""Bounded data and lifecycle tests; no game, ETW session or HUD is created."""

import types
import unittest
from unittest import mock

from cs2cfg.overlay import settings
from cs2cfg.overlay.hud import display_lines
from cs2cfg.overlay.presentmon import Aggregator, Frame
from cs2cfg.overlay.service import OverlayService, hud_allowed, hud_position


def interval(values):
    aggregator = Aggregator()
    for value in values:
        aggregator.add(Frame(value, "Hardware: Independent Flip"))
    return aggregator.snapshot()


class ServiceData(unittest.TestCase):
    def test_ring_keeps_latest_600_seconds(self):
        service = OverlayService()
        for at in range(800):
            service.ingest(interval([4]), at=at)
        with mock.patch("cs2cfg.overlay.service.time.time", return_value=800):
            rows = service.snapshot()["history"]
        self.assertEqual(len(rows), 600)
        self.assertEqual((rows[0]["at"], rows[-1]["at"]), (200, 799))
        self.assertNotIn("frame_time_histogram_ms", rows[-1])

    def test_ring_expires_old_intervals_after_a_gap(self):
        service = OverlayService()
        service.ingest(interval([4]), at=1)
        service.ingest(interval([5]), at=1000)
        with mock.patch("cs2cfg.overlay.service.time.time", return_value=1000):
            self.assertEqual([r["at"] for r in service.snapshot()["history"]], [1000])
            self.assertEqual(len(service.snapshot(120)["history"]), 1)

    def test_snapshot_is_detached(self):
        service = OverlayService()
        service.ingest(interval([4]))
        first = service.snapshot()
        first["history"][0]["present_modes"].clear()
        first["settings"]["overlay_fields"].clear()
        self.assertTrue(service.snapshot()["history"][0]["present_modes"])
        self.assertEqual(service.snapshot()["settings"]["overlay_fields"], list(settings.FIELDS))

    def test_session_summary_weights_frames_and_merges_distribution(self):
        service = OverlayService()
        service.ingest(interval([4] * 98))
        service.ingest(interval([10, 100]))
        summary = service.summary()
        self.assertAlmostEqual(summary["avg_fps"], 100000 / 502)
        self.assertEqual(summary["one_percent_low"], 100)
        self.assertEqual(summary["worst_frame_ms"], 100)
        self.assertEqual(summary["frame_count"], 100)
        self.assertIsNone(OverlayService().summary()["avg_fps"])

    def test_missing_interval_does_not_dilute_summary(self):
        service = OverlayService()
        service.ingest(interval([4]))
        service.ingest(interval([]))
        self.assertEqual(service.summary()["avg_fps"], 250)
        self.assertIsNone(service.snapshot()["history"][-1]["fps"])

    def test_presentmon_and_telemetry_events_merge_on_a_shared_clock(self):
        service = OverlayService()
        recorder = types.SimpleNamespace(started=100, record=types.SimpleNamespace(overlay=None))
        service._recorder = recorder
        sample = interval([4, 12])
        sample["events"][0]["at"] = 101.1
        service.ingest(sample, at=102)
        stall = types.SimpleNamespace(at=1.2, seconds=.35, focused=True)
        service._stall(recorder, stall)
        events = service.snapshot()["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "not_responding")
        self.assertEqual(events[0]["sources"], ["frame_spike", "not_responding"])
        self.assertAlmostEqual(events[0]["duration_ms"], 350)
        self.assertEqual(service.summary()["stutter_count"], 1)
        self.assertAlmostEqual(service.summary()["worst_freeze_ms"], 350)

    def test_consecutive_stall_probes_form_one_freeze(self):
        service = OverlayService()
        service.add_event({"type": "not_responding", "at": 10, "duration_ms": 350})
        service.add_event({"type": "not_responding", "at": 10.5, "duration_ms": 350})
        self.assertEqual(len(service.snapshot()["events"]), 1)
        self.assertAlmostEqual(service.summary()["worst_freeze_ms"], 850)
        service.add_event({"type": "not_responding", "at": 15, "duration_ms": 350})
        self.assertEqual(len(service.snapshot()["events"]), 2)

    def test_separate_spikes_remain_separate_newest_first_and_bounded(self):
        service = OverlayService()
        for at in range(250):
            service.add_event({"type": "frame_spike", "at": at, "duration_ms": 12})
        service.add_event({"type": "frame_spike", "at": -1, "duration_ms": 12})
        events = service.snapshot()["events"]
        self.assertEqual(len(events), 200)
        self.assertEqual((events[0]["at"], events[-1]["at"]), (249, 50))

    def test_event_eviction_does_not_lose_session_worst_freeze_or_stutter_count(self):
        aggregator = Aggregator()
        aggregator.add(Frame(4))
        aggregator.add(Frame(1000))
        for _ in range(201):
            for value in (4, 4, 4, 12):
                aggregator.add(Frame(value))
        sample = aggregator.snapshot()
        self.assertEqual(len(sample["events"]), 200)
        self.assertEqual(sample["max_spike_ms"], 1000)
        service = OverlayService()
        service.ingest(sample)
        self.assertEqual(service.summary()["worst_freeze_ms"], 1000)
        self.assertEqual(service.summary()["stutter_count"], 202)

    def test_stalls_from_another_recorder_are_ignored(self):
        service = OverlayService()
        service._stall(object(), types.SimpleNamespace(at=1, seconds=1))
        self.assertEqual(service.snapshot()["events"], [])

    def test_finalising_drains_last_frames_into_session_record(self):
        service = OverlayService()
        service._aggregator = Aggregator()
        service._aggregator.add(Frame(5))
        record = types.SimpleNamespace(overlay=None)
        recorder = types.SimpleNamespace(record=record)
        service._recorder = recorder
        service._finalising(recorder)
        self.assertEqual(record.overlay["avg_fps"], 200)
        service._finalising(recorder)
        self.assertEqual(record.overlay["frame_count"], 1)

    def test_finalising_flushes_capture_before_writing_summary(self):
        service = OverlayService()
        service._aggregator = Aggregator()
        recorder = types.SimpleNamespace(record=types.SimpleNamespace(overlay=None))
        service._recorder = recorder
        service._capture = mock.Mock()
        service._capture.stop.side_effect = lambda: service._aggregator.add(Frame(20))
        service._finalising(recorder)
        service._capture.stop.assert_called_once()
        self.assertEqual(recorder.record.overlay["worst_frame_ms"], 20)
        self.assertEqual(recorder.record.overlay["avg_fps"], 50)


class ServiceLifecycle(unittest.TestCase):
    def test_disabled_construct_configure_snapshot_and_stop_create_no_worker(self):
        with (mock.patch("cs2cfg.overlay.service.threading.Thread") as thread,
              mock.patch("cs2cfg.overlay.service.PresentMon") as capture):
            service = OverlayService()
            service.configure(settings.read())
            self.assertEqual(service.snapshot()["status"], "disabled")
            service.stop()
        thread.assert_not_called()
        capture.assert_not_called()

    def test_idle_loop_only_waits_five_seconds_and_never_starts_capture(self):
        service = OverlayService()
        service._stop = mock.Mock()
        service._stop.is_set.side_effect = [False, False, True]
        with (mock.patch("cs2cfg.window.find_game_window", return_value=None) as find,
              mock.patch.object(service, "_end_game"),
              mock.patch("cs2cfg.overlay.service.PresentMon") as capture):
            service._run()
        self.assertEqual(find.call_count, 2)
        self.assertEqual(service._stop.wait.call_args_list, [mock.call(5), mock.call(5)])
        capture.assert_not_called()

    def test_enable_is_idempotent_disable_joins_and_unsubscribes(self):
        service = OverlayService()
        thread = mock.Mock()
        thread.is_alive.side_effect = [True, False]
        unsubscribe = mock.Mock()
        with (mock.patch("cs2cfg.overlay.service.threading.Thread", return_value=thread) as make,
              mock.patch("cs2cfg.telemetry.subscribe", return_value=unsubscribe)):
            service.configure(settings.read({"overlay_enabled": True}))
            service.configure(settings.read({"overlay_enabled": True}))
            service.configure(settings.read())
        make.assert_called_once()
        thread.start.assert_called_once()
        thread.join.assert_called_once()
        unsubscribe.assert_called_once()
        self.assertIsNone(service._thread)

    def run_game(self, *, ready=True, capture_status="waiting", stall=False):
        service = OverlayService()
        service._settings = settings.read({"overlay_enabled": True})
        service._stop = mock.Mock()
        service._stop.is_set.side_effect = [False, True]
        service._stop.wait.return_value = False
        found = types.SimpleNamespace(hwnd=123, size=(1920, 1080), rect=(0, 0, 1920, 1080))
        recorder = types.SimpleNamespace(started=0, record=types.SimpleNamespace(overlay=None))
        with (mock.patch("cs2cfg.window.find_game_window", return_value=found),
              mock.patch("cs2cfg.window.is_borderless", return_value=True),
              mock.patch("cs2cfg.window.foreground_hwnd", return_value=123),
              mock.patch("cs2cfg.telemetry.acquire_recorder", return_value=recorder),
              mock.patch("cs2cfg.telemetry.release_recorder") as release,
              mock.patch("cs2cfg.monitor.Monitor") as cpu,
              mock.patch("cs2cfg.overlay.metrics.Nvml") as gpu,
              mock.patch("cs2cfg.overlay.hud.Hud") as hud,
              mock.patch("cs2cfg.overlay.permissions.frame_capture_ready", return_value=ready),
              mock.patch("cs2cfg.overlay.service.PresentMon") as capture):
            cpu.return_value.cpu_percent.return_value = 10
            gpu.return_value.sample.return_value = {"gpu_percent": 20, "gpu_temp_c": 60}
            capture.return_value.status.return_value = capture_status
            if stall:
                def sample():
                    service._stall(recorder, types.SimpleNamespace(at=1, seconds=.5, focused=True))
                    return {"gpu_percent": 20, "gpu_temp_c": 60}

                gpu.return_value.sample.side_effect = sample
            service._run()
        return service, capture, hud, gpu, release, recorder

    def test_game_capture_and_native_resources_clean_up_on_exit(self):
        service, capture, hud, gpu, release, recorder = self.run_game()
        capture.return_value.start.assert_called_once()
        capture.return_value.stop.assert_called_once()
        hud.return_value.stop.assert_called_once()
        gpu.return_value.close.assert_called_once()
        release.assert_called_once_with(recorder)
        self.assertIsNone(service._hwnd)

    def test_without_permissions_resources_and_telemetry_continue_without_capture(self):
        service, capture, hud, gpu, release, recorder = self.run_game(ready=False, stall=True)
        capture.assert_not_called()
        sample = service.snapshot()["history"][-1]
        for field in settings.FIELDS[:3]:
            self.assertIsNone(sample[field])
        self.assertFalse(sample["frame_capture_ready"])
        self.assertEqual(sample["cpu_percent"], 10)
        self.assertEqual(sample["gpu_percent"], 20)
        self.assertEqual(sample["gpu_temp_c"], 60)
        self.assertEqual(service.summary()["worst_freeze_ms"], 500)
        self.assertEqual(service.snapshot()["events"][0]["type"], "not_responding")
        hud.return_value.set_allowed.assert_any_call(True)
        text = " ".join(display_lines(hud.return_value.update.call_args.args[0]))
        self.assertIn("FPS \u2014", text)
        self.assertIn("Frame \u2014", text)
        self.assertIn("CPU 10.0%", text)
        hud.return_value.stop.assert_called_once()
        gpu.return_value.close.assert_called_once()
        release.assert_called_once_with(recorder)
        self.assertNotEqual(service.snapshot()["status"], "error")

    def test_real_capture_denial_overrides_token_and_stops_capture(self):
        service, capture, hud, gpu, release, recorder = self.run_game(capture_status="access_denied",
                                                                   stall=True)
        with (mock.patch("cs2cfg.overlay.permissions.frame_capture_ready", return_value=True),
              mock.patch("cs2cfg.overlay.permissions.frame_capture_hint", return_value="")):
            result = service.snapshot()
        self.assertFalse(result["frame_capture_ready"])
        self.assertEqual(result["status"], "access_denied")
        self.assertEqual(result["display"]["fps"], "\u2014")
        self.assertEqual(result["history"][-1]["cpu_percent"], 10)
        self.assertEqual(result["events"][0]["type"], "not_responding")
        capture.return_value.start.assert_called_once()
        capture.return_value.stop.assert_called_once()
        hud.return_value.set_allowed.assert_any_call(True)

    def test_hud_preference_edits_preserve_capture_history(self):
        service = OverlayService()
        service.ingest(interval([4]))
        service._thread = mock.Mock()
        service._thread.is_alive.return_value = True
        service._hud = mock.Mock()
        with mock.patch("cs2cfg.overlay.service.PresentMon") as capture:
            service.configure(settings.read({"overlay_enabled": True, "overlay_hotkey": "Alt+F12"}))
        service._hud.configure.assert_called_once_with(fields=list(settings.FIELDS), hotkey="Alt+F12",
                                                       panel_hotkey="Ctrl+Alt+P")
        self.assertEqual(service.summary()["frame_count"], 1)
        service._thread.join.assert_not_called()
        capture.assert_not_called()


class HudSettings(unittest.TestCase):
    def test_overlay_is_off_by_default_and_defaults_are_detached(self):
        self.assertFalse(settings.read()["overlay_enabled"])
        self.assertEqual(settings.read()["overlay_hotkey"], "Ctrl+Alt+O")
        self.assertEqual(settings.read()["overlay_corner"], "top_left")
        self.assertFalse(settings.read()["overlay_sign_out_hint_dismissed"])
        settings.read()["overlay_fields"].clear()
        self.assertEqual(settings.read()["overlay_fields"], list(settings.FIELDS))

    def test_corrupt_saved_preferences_cannot_enable_overlay(self):
        self.assertFalse(settings.read({"overlay_enabled": "false"})["overlay_enabled"])
        for value in ("O", "Ctrl+Ctrl+O", "Ctrl+F25", "Win+O", "Ctrl++"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                settings.read({"overlay_hotkey": value}, strict=True)
        with self.assertRaises(ValueError):
            settings.read({"overlay_fields": []}, strict=True)
        with self.assertRaises(ValueError):
            settings.read({"overlay_sign_out_hint_dismissed": "yes"}, strict=True)

    def test_hotkey_parse_and_selected_fields(self):
        self.assertEqual(settings.hotkey("Ctrl+Alt+O"), (0x4003, ord("O")))
        self.assertEqual(settings.hotkey("Alt+F12"), (0x4001, 0x7b))
        text = " ".join(display_lines({"fps": 200}, ["fps"], "Alt+F12"))
        self.assertIn("FPS 200.0", text)
        self.assertNotIn("CPU", text)
        self.assertIn("Alt+F12", text)

    def test_unready_hud_masks_frame_values_and_keeps_resources(self):
        text = " ".join(display_lines({"fps": 200, "one_percent_low": 150, "frame_time_ms": 5,
                                       "cpu_percent": 10, "gpu_percent": 20, "gpu_temp_c": 60,
                                       "frame_capture_ready": False}))
        for label in ("FPS", "1% low", "Frame"):
            self.assertIn(label + " \u2014", text)
        self.assertIn("CPU 10.0%", text)
        self.assertIn("GPU 20.0%", text)
        self.assertIn("Temp 60.0 C", text)

    def test_window_and_present_mode_both_gate_hud(self):
        self.assertTrue(hud_allowed(True, {"Hardware: Independent Flip": 10}))
        self.assertTrue(hud_allowed(True, {"Composed: Flip": 10}))
        self.assertFalse(hud_allowed(False, {"Composed: Flip": 10}))
        self.assertFalse(hud_allowed(True, {"Hardware: Legacy Flip": 10}))
        self.assertFalse(hud_allowed(True, {}))
        self.assertFalse(hud_allowed(True, {"Unknown": 10}))
        self.assertTrue(hud_allowed(True, {}, frame_capture_ready=False))
        self.assertFalse(hud_allowed(False, {}, frame_capture_ready=False))
        self.assertFalse(hud_allowed(True, {"Hardware: Legacy Flip": 10}, frame_capture_ready=False))

    def test_corners_follow_game_monitor_including_negative_coordinates(self):
        self.assertEqual(hud_position((-1920, 0, 0, 1080), "top_left"), (-1900, 20))
        self.assertEqual(hud_position((-1920, 0, 0, 1080), "bottom_right"), (-660, 940))

    def test_settings_are_shared_between_steam_accounts(self):
        from cs2cfg import profiles

        prefs = {}
        profiles.remember(prefs, "one", settings.read({"overlay_enabled": True}))
        profiles.migrate(prefs, "two")
        self.assertTrue(profiles.ui_for(prefs, "two")["overlay_enabled"])
        self.assertNotIn("overlay_enabled", prefs["accounts"]["one"])


if __name__ == "__main__":
    unittest.main()
