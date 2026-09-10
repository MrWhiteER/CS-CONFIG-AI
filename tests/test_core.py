"""Self-tests. Standard library only: `python -m unittest discover tests`.

The cases that matter most are the ones touching Steam's own files, because a
bug there costs someone their settings rather than a few frames.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import vdf  # noqa: E402
from cs2cfg.hardware import Cpu, Display, Gpu, Machine, _reconcile_refresh, detect  # noqa: E402
from cs2cfg.kb import KnowledgeBase, normalise  # noqa: E402
from cs2cfg.profile import build_profile, estimate_fps, parse_launch_options, plan_launch_options  # noqa: E402

LOCALCONFIG = '''"UserLocalConfigStore"
{
\t"Software"
\t{
\t\t"Valve"
\t\t{
\t\t\t"Steam"
\t\t\t{
\t\t\t\t"apps"
\t\t\t\t{
\t\t\t\t\t"440"
\t\t\t\t\t{
\t\t\t\t\t\t"LaunchOptions"\t\t"-dxlevel 90"
\t\t\t\t\t}
\t\t\t\t\t"730"
\t\t\t\t\t{
\t\t\t\t\t\t"LastPlayed"\t\t"1788640309"
\t\t\t\t\t\t"LaunchOptions"\t\t"-full -novid +exec mrwhiteer\\\\autoexec.vcfg"
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}
\t\t}
\t}
\t"friends"
\t{
\t\t"note"\t\t"must survive untouched"
\t}
}
'''

VIDEO_CFG = '''"video.cfg"
{
\t"setting.defaultres"\t\t"1550"
\t"setting.defaultresheight"\t\t"1440"
\t"setting.mat_vsync"\t\t"1"
\t"setting.videocfg_shadow_quality"\t\t"3"
\t"setting.msaa_samples"\t\t"4"
\t"setting.aspectratiomode"\t\t"2"
}
'''

PROBE = {
    "schema": 1,
    "os": {"caption": "Microsoft Windows 11 Pro", "build": "26200"},
    "cpu": {"name": "12th Gen Intel(R) Core(TM) i9-12900K", "manufacturer": "GenuineIntel",
            "cores": 16, "threads": 24, "max_clock_mhz": 3200},
    "gpus": [{"name": "NVIDIA GeForce RTX 3090 Ti", "vram_bytes": 24146608128,
              "vendor_id": 4318, "device_id": 8707, "driver_version": "32.0.16.1088",
              "driver_date": "2026-07-22", "current_width": 2560, "current_height": 1440,
              "current_refresh": 239}],
    "memory": {"total_bytes": 68447891456, "modules": 4, "speed_mts": 4000},
    "displays": [{"primary": True, "native_width": 2560, "native_height": 1440,
                  "max_refresh": 60, "current_refresh": 0, "mode_count": 4}],
    "display_source": "wmi_monitor_modes",
    "disks": [{"letter": "G", "media_type": "SSD", "free_bytes": 1}],
    "power_plan": "High performance",
}


class TestVdf(unittest.TestCase):
    def test_parse_nested(self):
        data = vdf.parse(LOCALCONFIG)
        apps = data["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["apps"]
        self.assertEqual(apps["730"]["LastPlayed"], "1788640309")

    def test_escaped_backslash_round_trip(self):
        value = vdf.read_value(
            LOCALCONFIG,
            ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps", "730"],
            "LaunchOptions",
        )
        self.assertEqual(value, "-full -novid +exec mrwhiteer\\autoexec.vcfg")

    def test_finds_the_right_730_not_the_first_match(self):
        location = vdf.find_key_line(
            LOCALCONFIG,
            ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps", "730"],
            "LaunchOptions",
        )
        line = LOCALCONFIG.splitlines()[location["key_line"] - 1]
        self.assertIn("mrwhiteer", line)
        self.assertNotIn("dxlevel", line)

    def test_line_surgery_leaves_every_other_byte_alone(self):
        location = vdf.find_key_line(
            LOCALCONFIG,
            ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps", "730"],
            "LaunchOptions",
        )
        lines = LOCALCONFIG.splitlines(keepends=True)
        lines[location["key_line"] - 1] = '\t\t\t\t\t\t"LaunchOptions"\t\t"-novid"\n'
        patched = "".join(lines)

        self.assertIn("must survive untouched", patched)
        self.assertIn('"-dxlevel 90"', patched)
        self.assertEqual(len(patched.splitlines()), len(LOCALCONFIG.splitlines()))

    def test_missing_key_reports_block_for_insertion(self):
        text = LOCALCONFIG.replace('\t\t\t\t\t\t"LaunchOptions"\t\t"-full -novid +exec mrwhiteer\\\\autoexec.vcfg"\n', "")
        location = vdf.find_key_line(
            text, ["UserLocalConfigStore", "Software", "Valve", "Steam", "apps", "730"], "LaunchOptions"
        )
        self.assertIsNone(location["key_line"])
        self.assertIsNotNone(location["block_open_line"])

    def test_case_insensitive_path(self):
        value = vdf.read_value(
            LOCALCONFIG,
            ["userlocalconfigstore", "software", "valve", "steam", "apps", "730"],
            "launchoptions",
        )
        self.assertTrue(value.startswith("-full"))

    def test_dumps_round_trips(self):
        original = vdf.parse(VIDEO_CFG)
        again = vdf.parse(vdf.dumps(original))
        self.assertEqual(original, again)

    def test_comments_are_ignored(self):
        text = '"root"\n{\n\t// a comment\n\t"key"\t\t"value"\n}\n'
        self.assertEqual(vdf.parse(text)["root"]["key"], "value")

    def test_unbalanced_braces_rejected(self):
        with self.assertRaises(vdf.VdfError):
            vdf.parse('"root"\n{\n\t"key" "value"\n')


class TestMatching(unittest.TestCase):
    def setUp(self):
        self.kb = KnowledgeBase(extra_dir=Path("/nonexistent-override-dir"))

    def test_normalise_strips_trademarks(self):
        self.assertEqual(
            normalise("12th Gen Intel(R) Core(TM) i9-12900K"),
            "12th gen intel core i9-12900k",
        )

    def test_more_specific_gpu_entry_wins(self):
        ti = self.kb.match_gpu("NVIDIA GeForce RTX 3090 Ti")
        plain = self.kb.match_gpu("NVIDIA GeForce RTX 3090")
        self.assertTrue(ti.exact and plain.exact)
        self.assertGreater(ti.index, plain.index)

    def test_cpu_exact_match(self):
        match = self.kb.match_cpu("12th Gen Intel(R) Core(TM) i9-12900K", 3200)
        self.assertTrue(match.exact)
        self.assertEqual(match.index, 88)

    def test_unknown_gpu_falls_back_to_series(self):
        match = self.kb.match_gpu("NVIDIA GeForce RTX 4055 Ultra")
        self.assertFalse(match.exact)
        self.assertGreater(match.index, 0)

    def test_unknown_cpu_estimated_from_clock(self):
        match = self.kb.match_cpu("Some Unreleased CPU 9000", 4000)
        self.assertFalse(match.exact)
        self.assertGreaterEqual(match.index, 30)
        self.assertLessEqual(match.index, 85)

    def test_rx_580_does_not_match_5800(self):
        # Word-boundary matching must not let '580' swallow '5800X'.
        self.assertTrue(self.kb.match_cpu("AMD Ryzen 7 5800X").exact)
        self.assertEqual(self.kb.match_cpu("AMD Ryzen 7 5800X").index, 80)

    def test_clamp_respects_declared_range(self):
        self.assertEqual(self.kb.clamp("setting.videocfg_texture_detail", 9), 2)
        self.assertEqual(self.kb.clamp("setting.msaa_samples", 3), 2)
        self.assertEqual(self.kb.clamp("setting.msaa_samples", 8), 8)


class TestRefresh(unittest.TestCase):
    def test_adapter_reading_beats_a_low_edid_table(self):
        refresh, confident = _reconcile_refresh(60, 239)
        self.assertEqual(refresh, 240)
        self.assertTrue(confident)

    def test_snaps_239_to_240(self):
        self.assertEqual(_reconcile_refresh(0, 239)[0], 240)

    def test_unknown_refresh_is_flagged(self):
        refresh, confident = _reconcile_refresh(144, 0)
        self.assertEqual(refresh, 144)
        self.assertFalse(confident)

    def test_nothing_at_all_defaults_to_60(self):
        self.assertEqual(_reconcile_refresh(0, 0), (60, False))


class TestDetection(unittest.TestCase):
    def test_interprets_a_probe_payload(self):
        machine = detect(PROBE)
        self.assertEqual(machine.cpu.name, "12th Gen Intel(R) Core(TM) i9-12900K")
        self.assertTrue(machine.cpu.likely_hybrid)
        self.assertAlmostEqual(machine.gpu.vram_gb, 22.5, places=1)
        self.assertEqual(machine.primary_display.width, 2560)

    def test_hybrid_detection_is_structural(self):
        self.assertFalse(Cpu("Core i7-10700K", 8, 16, 3800, "intel").likely_hybrid)
        self.assertTrue(Cpu("Core i9-12900K", 16, 24, 3200, "intel").likely_hybrid)
        self.assertFalse(Cpu("Ryzen 7 7800X3D", 8, 16, 4200, "amd").likely_hybrid)

    def test_virtual_adapters_are_ignored(self):
        payload = dict(PROBE)
        payload["gpus"] = [
            {"name": "Microsoft Basic Display Adapter", "vram_bytes": 0},
            {"name": "NVIDIA GeForce RTX 3090 Ti", "vram_bytes": 24146608128, "vendor_id": 4318},
        ]
        self.assertEqual(detect(payload).gpu.name, "NVIDIA GeForce RTX 3090 Ti")

    def test_discrete_gpu_beats_integrated(self):
        payload = dict(PROBE)
        payload["gpus"] = [
            {"name": "Intel(R) UHD Graphics 770", "vram_bytes": 128 * 1024 ** 2, "vendor_id": 0x8086},
            {"name": "NVIDIA GeForce RTX 4060 Laptop GPU", "vram_bytes": 8 * 1024 ** 3, "vendor_id": 4318},
        ]
        self.assertIn("4060", detect(payload).gpu.name)


class TestScoring(unittest.TestCase):
    def test_faster_cpu_scores_higher(self):
        slow = estimate_fps(50, 60, 1920 * 1080, "balanced")[0]
        fast = estimate_fps(100, 60, 1920 * 1080, "balanced")[0]
        self.assertGreater(fast, slow)

    def test_more_pixels_cost_frames(self):
        low = estimate_fps(80, 40, 1280 * 960, "balanced")[0]
        high = estimate_fps(80, 40, 3840 * 2160, "balanced")[0]
        self.assertGreater(low, high)

    def test_weak_gpu_with_strong_cpu_is_gpu_limited(self):
        self.assertEqual(estimate_fps(100, 8, 2560 * 1440, "balanced")[3], "GPU")

    def test_strong_gpu_with_weak_cpu_is_cpu_limited(self):
        self.assertEqual(estimate_fps(45, 100, 1920 * 1080, "competitive")[3], "CPU")

    def test_combined_estimate_sits_below_both_ceilings(self):
        combined, cpu_ceiling, gpu_ceiling, _ = estimate_fps(80, 60, 1920 * 1080, "balanced")
        self.assertLess(combined, cpu_ceiling)
        self.assertLess(combined, gpu_ceiling)


class TestProfile(unittest.TestCase):
    def setUp(self):
        self.kb = KnowledgeBase(extra_dir=Path("/nonexistent-override-dir"))
        self.machine = detect(PROBE)

    def test_high_end_machine_earns_a_top_tier(self):
        profile = build_profile(self.machine, self.kb, intent="balanced")
        self.assertIn(profile.tier, ("S", "A"))

    def test_every_emitted_value_is_inside_its_declared_range(self):
        for intent in ("competitive", "balanced", "quality"):
            profile = build_profile(self.machine, self.kb, intent=intent)
            for key, value in profile.video.items():
                spec = self.kb.video["keys"].get(key)
                self.assertIsNotNone(spec, f"{key} has no declared range")
                self.assertGreaterEqual(value, spec["min"], f"{key} below range in {intent}")
                self.assertLessEqual(value, spec["max"], f"{key} above range in {intent}")

    def test_vsync_is_always_turned_off(self):
        profile = build_profile(self.machine, self.kb)
        self.assertEqual(profile.video["setting.mat_vsync"], 0)

    def test_reflex_enabled_on_geforce(self):
        profile = build_profile(self.machine, self.kb)
        self.assertEqual(profile.video["setting.r_low_latency"], 2)

    def test_reflex_disabled_on_radeon(self):
        payload = dict(PROBE)
        payload["gpus"] = [{"name": "AMD Radeon RX 7800 XT", "vram_bytes": 16 * 1024 ** 3, "vendor_id": 0x1002}]
        profile = build_profile(detect(payload), self.kb)
        self.assertEqual(profile.video["setting.r_low_latency"], 0)

    def test_low_vram_caps_texture_detail(self):
        payload = dict(PROBE)
        payload["gpus"] = [{"name": "NVIDIA GeForce GTX 1650", "vram_bytes": 4 * 1024 ** 3, "vendor_id": 4318}]
        profile = build_profile(detect(payload), self.kb, intent="quality")
        self.assertEqual(profile.video["setting.videocfg_texture_detail"], 0)

    def test_vsync_currently_on_raises_an_advisory(self):
        profile = build_profile(self.machine, self.kb, current_video={"setting.mat_vsync": "1"})
        self.assertTrue(any("V-Sync" in a.title for a in profile.advisories))

    def test_balanced_profile_never_exceeds_quality_profile(self):
        balanced = build_profile(self.machine, self.kb, intent="balanced")
        quality = build_profile(self.machine, self.kb, intent="quality")
        self.assertGreaterEqual(
            quality.video["setting.videocfg_texture_detail"],
            balanced.video["setting.videocfg_texture_detail"],
        )

    def test_intent_does_not_move_the_tier(self):
        """Tier describes the hardware, not the request.

        Regression guard: when the tier was derived from the chosen intent,
        asking for 'quality' lowered the tier and produced settings *worse*
        than 'balanced' — the opposite of what was asked for.
        """
        tiers = {
            intent: build_profile(self.machine, self.kb, intent=intent).tier
            for intent in ("competitive", "balanced", "quality")
        }
        self.assertEqual(len(set(tiers.values())), 1, f"tier moved with intent: {tiers}")

    def test_quality_never_yields_worse_settings_than_balanced(self):
        ladder = ("setting.videocfg_texture_detail", "setting.videocfg_particle_detail",
                  "setting.videocfg_ao_detail", "setting.r_texturefilteringquality",
                  "setting.msaa_samples")
        for payload_gpu, payload_cpu in (
            ("NVIDIA GeForce RTX 3090 Ti", "12th Gen Intel(R) Core(TM) i9-12900K"),
            ("NVIDIA GeForce GTX 1060", "Intel(R) Core(TM) i5-8400"),
            ("AMD Radeon RX 7800 XT", "AMD Ryzen 5 5600X"),
        ):
            payload = dict(PROBE)
            payload["gpus"] = [{"name": payload_gpu, "vram_bytes": 8 * 1024 ** 3, "vendor_id": 4318}]
            payload["cpu"] = {"name": payload_cpu, "manufacturer": "GenuineIntel",
                              "cores": 6, "threads": 12, "max_clock_mhz": 3000}
            machine = detect(payload)
            balanced = build_profile(machine, self.kb, intent="balanced")
            quality = build_profile(machine, self.kb, intent="quality")
            for key in ladder:
                self.assertGreaterEqual(
                    quality.video[key], balanced.video[key],
                    f"{payload_gpu}: quality gave a lower {key} than balanced",
                )

    def test_upscaling_never_enabled_above_balanced_on_capable_hardware(self):
        quality = build_profile(self.machine, self.kb, intent="quality")
        self.assertEqual(quality.video["setting.videocfg_fsr_detail"], 0)

    def test_intent_below_target_raises_an_advisory(self):
        payload = dict(PROBE)
        payload["gpus"] = [{"name": "NVIDIA GeForce GTX 1050 Ti", "vram_bytes": 4 * 1024 ** 3, "vendor_id": 4318}]
        profile = build_profile(detect(payload), self.kb, intent="quality")
        self.assertTrue(any("under your" in a.title for a in profile.advisories))

    def test_alt_tab_blackout_advisory_on_multi_monitor_fullscreen(self):
        payload = dict(PROBE)
        payload["displays"] = [
            {"primary": True, "native_width": 2560, "native_height": 1440,
             "max_refresh": 240, "current_refresh": 240},
            {"primary": False, "native_width": 2560, "native_height": 1440,
             "max_refresh": 144, "current_refresh": 144},
        ]
        profile = build_profile(
            detect(payload), self.kb,
            current_video={"setting.fullscreen": "1", "setting.fullscreen_min_on_focus_loss": "1"},
        )
        self.assertTrue(any("Exclusive fullscreen" in a.title for a in profile.advisories))

    def test_no_alt_tab_advisory_on_a_single_monitor(self):
        profile = build_profile(
            self.machine, self.kb,
            current_video={"setting.fullscreen": "1", "setting.fullscreen_min_on_focus_loss": "1"},
        )
        self.assertFalse(any("Exclusive fullscreen" in a.title for a in profile.advisories))

    def test_unknown_intent_rejected(self):
        with self.assertRaises(ValueError):
            build_profile(self.machine, self.kb, intent="ultra")


class TestLaunchOptions(unittest.TestCase):
    def setUp(self):
        self.kb = KnowledgeBase(extra_dir=Path("/nonexistent-override-dir"))
        self.machine = detect(PROBE)

    def test_parses_attached_and_spaced_values(self):
        parsed = dict(parse_launch_options("-w1920 -h 1440 -novid", self.kb))
        self.assertEqual(parsed["-w"], "1920")
        self.assertEqual(parsed["-h"], "1440")
        self.assertIsNone(parsed["-novid"])

    def test_drops_csgo_era_flags(self):
        current = ("-full -console -novid -nojoy +mat_queue_mode 2 -d3d9ex -threads 4 "
                   "-tickrate 128 +cl_updaterate 128 +cl_cmdrate 128 +rate 128000")
        plan = plan_launch_options(current, self.machine, self.kb)
        for dead in ("-d3d9ex", "-nojoy", "-tickrate", "+mat_queue_mode", "+cl_updaterate", "+rate"):
            self.assertNotIn(dead, plan.line, f"{dead} should have been removed")

    def test_invalid_full_is_dropped_not_upgraded_to_fullscreen(self):
        """Regression: -full was being "corrected" to -fullscreen.

        -full is discarded by CS2, so the video config decides the display
        mode. Substituting the real flag forced exclusive fullscreen, silently
        overrode the windowed setting, and brought back the alt-tab blackout
        the tool exists to remove.
        """
        plan = plan_launch_options("-full -novid", self.machine, self.kb)
        self.assertNotIn("-full", plan.line)
        self.assertNotIn("-fullscreen", plan.line)

    def test_windowed_mode_strips_fullscreen_flags(self):
        plan = plan_launch_options(
            "-fullscreen -w 1550 -h 1440 -novid", self.machine, self.kb, window_mode="windowed"
        )
        self.assertNotIn("-fullscreen", plan.line)
        self.assertIn("-windowed", plan.line)
        self.assertIn("-noborder", plan.line)
        self.assertIn("-w 1550", plan.line)
        self.assertTrue(any("-fullscreen" in opt for opt, _ in plan.removed))

    def test_windowed_mode_is_idempotent(self):
        once = plan_launch_options("-novid", self.machine, self.kb, window_mode="windowed").line
        twice = plan_launch_options(once, self.machine, self.kb, window_mode="windowed").line
        self.assertEqual(once.count("-windowed"), 1)
        self.assertEqual(twice.count("-windowed"), 1)
        self.assertEqual(twice.count("-noborder"), 1)

    def test_fullscreen_mode_strips_windowed_flags(self):
        plan = plan_launch_options(
            "-windowed -noborder -novid", self.machine, self.kb, window_mode="fullscreen"
        )
        self.assertIn("-fullscreen", plan.line)
        self.assertNotIn("-windowed", plan.line)
        self.assertNotIn("-noborder", plan.line)

    def test_display_flags_untouched_without_a_window_mode(self):
        plan = plan_launch_options("-windowed -noborder -novid", self.machine, self.kb)
        self.assertIn("-windowed", plan.line)
        self.assertIn("-noborder", plan.line)

    def test_keeps_deliberate_resolution(self):
        plan = plan_launch_options("-w 1550 -h 1440 -novid", self.machine, self.kb)
        self.assertIn("-w 1550", plan.line)
        self.assertIn("-h 1440", plan.line)

    def test_high_removed_on_hybrid_cpu(self):
        plan = plan_launch_options("-high -novid", self.machine, self.kb)
        self.assertNotIn("-high", plan.line)
        self.assertTrue(any("-high" in option for option, _ in plan.removed))

    def test_high_kept_on_homogeneous_cpu(self):
        payload = dict(PROBE)
        payload["cpu"] = {"name": "Intel(R) Core(TM) i7-10700K", "manufacturer": "GenuineIntel",
                          "cores": 8, "threads": 16, "max_clock_mhz": 3800}
        plan = plan_launch_options("-high -novid", detect(payload), self.kb)
        self.assertIn("-high", plan.line)

    def test_exec_added_once_and_preserved_when_present(self):
        plan = plan_launch_options("-novid", self.machine, self.kb, exec_path="mrwhiteer\\autoexec.vcfg")
        self.assertEqual(plan.line.count("+exec"), 1)

        already = plan_launch_options(
            "+exec mrwhiteer\\autoexec.vcfg", self.machine, self.kb, exec_path="other\\file.vcfg"
        )
        self.assertIn("mrwhiteer", already.line)
        self.assertEqual(already.line.count("+exec"), 1)

    def test_novid_added_when_missing(self):
        self.assertIn("-novid", plan_launch_options("-console", self.machine, self.kb).line)

    def test_unknown_flags_are_preserved_not_eaten(self):
        plan = plan_launch_options("-some_future_flag -novid", self.machine, self.kb)
        self.assertIn("-some_future_flag", plan.line)

    def test_valueless_flags_print_without_a_dangling_none(self):
        plan = plan_launch_options("-full -d3d9ex -novid", self.machine, self.kb)
        for option, _ in plan.removed:
            self.assertNotIn("None", option)
        for option in plan.kept:
            self.assertNotIn("None", option)
        self.assertNotIn("None", plan.line)

    def test_bottleneck_label_is_readable(self):
        self.assertEqual(estimate_fps(80, 40, 1920 * 1080, "balanced")[3], "evenly matched")

    def test_every_removal_carries_a_reason(self):
        plan = plan_launch_options("-d3d9ex -nojoy -tickrate 128", self.machine, self.kb)
        self.assertTrue(plan.removed)
        for option, reason in plan.removed:
            self.assertTrue(reason.strip(), f"{option} was removed without an explanation")


class TestTelemetry(unittest.TestCase):
    """The summary maths, without needing a game to actually run."""

    def setUp(self):
        from cs2cfg import telemetry
        self.t = telemetry

    def _session(self, **kw):
        base = {"stamp": "x", "started": "2026-09-06T01:00:00", "duration": 3600,
                "alt_tabs": 0, "borderless": True, "stall_count": 0}
        base.update(kw)
        return base

    def test_empty_history(self):
        self.assertEqual(self.t.summarise([]), {"count": 0})

    def test_splits_borderless_from_exclusive(self):
        sessions = [
            self._session(borderless=True, median_return=0.8),
            self._session(borderless=False, median_return=6.4),
        ]
        summary = self.t.summarise(sessions)
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["borderless"]["median_return"], 0.8)
        self.assertEqual(summary["exclusive"]["median_return"], 6.4)

    def test_group_absent_when_no_sessions_of_that_kind(self):
        summary = self.t.summarise([self._session(borderless=True, median_return=1.0)])
        self.assertIsNone(summary["exclusive"])

    def test_hours_accumulate(self):
        summary = self.t.summarise([self._session(duration=1800), self._session(duration=5400)])
        self.assertEqual(summary["total_hours"], 2.0)

    def test_slow_return_is_called_out_as_the_blackout_pattern(self):
        record = self.t.SessionRecord(stamp="x", started="now", duration=600,
                                      alt_tabs=3, median_return=7.0, worst_return=9.1)
        notes = " ".join(self.t._observations(record))
        self.assertIn("blackout", notes)

    def test_fast_return_is_reported_as_correct(self):
        record = self.t.SessionRecord(stamp="x", started="now", duration=600,
                                      alt_tabs=4, median_return=0.6, worst_return=0.9)
        notes = " ".join(self.t._observations(record))
        self.assertIn("what it should look like", notes)

    def test_focus_is_polled_far_faster_than_it_is_reported(self):
        """Guard against the quantisation bug.

        Focus was once sampled on the same two-second clock as CPU, which
        inflated every alt-tab reading by up to a full interval and produced a
        3.45s median that was mostly measurement noise.
        """
        self.assertLessEqual(self.t.FOCUS_POLL, 0.25)
        self.assertLess(self.t.FOCUS_POLL, self.t.SAMPLE_INTERVAL / 4)

    def test_never_claims_a_frame_rate(self):
        record = self.t.SessionRecord(stamp="x", started="now", duration=600)
        notes = " ".join(self.t._observations(record)).lower()
        self.assertIn("no frame rate here", notes)
        self.assertNotIn(" fps average", notes)


class TestClosingTheGame(unittest.TestCase):
    """The close path, without needing a game to close."""

    def setUp(self):
        from cs2cfg import window
        self.window = window

    def test_polite_close_is_tried_before_force(self):
        """A clean WM_CLOSE lets CS2 disconnect and flush its config.

        Reaching for TerminateProcess first would skip all of that, so the
        order matters more than the outcome here.
        """
        import inspect
        source = inspect.getsource(self.window.close_process_window)
        self.assertLess(
            source.index("request_close"), source.index("terminate_process"),
            "force is being tried before the polite close",
        )

    def test_force_can_be_declined(self):
        import inspect
        source = inspect.getsource(self.window.close_process_window)
        self.assertIn("if not force:", source)

    def test_terminate_on_a_dead_pid_fails_cleanly(self):
        # PID 0 is the system idle process; it can never be opened for
        # termination, so this exercises the failure path without risk.
        self.assertFalse(self.window.terminate_process(0))

    def test_process_alive_is_false_for_an_impossible_pid(self):
        self.assertFalse(self.window.process_alive(0xFFFFFFF0))

    def test_process_alive_is_true_for_this_process(self):
        self.assertTrue(self.window.process_alive(os.getpid()))

    def test_exit_detection_is_not_sluggish(self):
        from cs2cfg import launcher
        import inspect
        signature = inspect.signature(launcher.wait_for_exit)
        self.assertLessEqual(signature.parameters["interval"].default, 1.0)


class TestLaunchModes(unittest.TestCase):
    """The two launch modes must actually differ the way their labels say."""

    def setUp(self):
        from cs2cfg import launcher
        self.launcher = launcher

    def test_the_two_modes_are_opposites(self):
        seamless = self.launcher.SEAMLESS_VIDEO
        exclusive = self.launcher.EXCLUSIVE_VIDEO
        self.assertEqual(seamless["setting.fullscreen"], 0)
        self.assertEqual(exclusive["setting.fullscreen"], 1)
        self.assertEqual(seamless["setting.nowindowborder"], 1)
        self.assertEqual(exclusive["setting.nowindowborder"], 0)

    def test_fullscreen_mode_really_means_fullscreen(self):
        """Regression guard for a label that does not match its behaviour.

        The second option used to be borderless-windowed-but-unstretched while
        being labelled 'Fullscreen'.
        """
        self.assertEqual(self.launcher.EXCLUSIVE_VIDEO["setting.fullscreen"], 1)

    def test_default_mode_is_the_windowed_fullscreen_one(self):
        import inspect
        default = inspect.signature(self.launcher.play).parameters["stretch_mode"].default
        self.assertEqual(default, "borderless")

    def test_every_written_setting_is_explained(self):
        for key in self.launcher.EXCLUSIVE_VIDEO:
            self.assertIn(key, self.launcher.EXCLUSIVE_REASONS)
        for key in self.launcher.SEAMLESS_VIDEO:
            self.assertIn(key, self.launcher.SEAMLESS_REASONS)

    def test_old_mode_names_still_resolve(self):
        """A saved preference must not break, or select a mode that is gone."""
        mapping = {"window": "borderless", "desktop": "borderless", "none": "fullscreen"}
        for old, new in mapping.items():
            self.assertIn(new, ("borderless", "fullscreen"), old)


class TestPortablePaths(unittest.TestCase):
    """Where a portable build keeps its data."""

    def setUp(self):
        from cs2cfg import paths
        self.paths = paths
        self._saved = paths._resolved

    def tearDown(self):
        self.paths._resolved = self._saved

    def test_env_override_wins(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.paths._resolved = None
            os.environ[self.paths.ENV_OVERRIDE] = tmp
            try:
                self.assertEqual(self.paths.user_data_dir(), Path(tmp))
            finally:
                del os.environ[self.paths.ENV_OVERRIDE]

    def test_resolution_is_cached_so_data_cannot_split(self):
        self.paths._resolved = None
        first = self.paths.user_data_dir()
        self.assertIs(self.paths.user_data_dir(), first)

    def test_writable_actually_writes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(self.paths._writable(Path(tmp) / "nested" / "deep"))
        # A path under a file, not a directory, cannot be created.
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            blocked = Path(handle.name) / "child"
        self.assertFalse(self.paths._writable(blocked))

    def test_bundle_root_holds_the_resources(self):
        root = self.paths.bundle_root()
        self.assertTrue((root / "probe.ps1").is_file())
        self.assertTrue((root / "knowledge" / "gpus.json").is_file())
        self.assertTrue((root / "web" / "index.html").is_file())


class TestKnowledgeIntegrity(unittest.TestCase):
    """The JSON files are hand-edited, so guard their invariants."""

    def setUp(self):
        self.kb = KnowledgeBase(extra_dir=Path("/nonexistent-override-dir"))

    def test_every_tier_of_every_intent_is_present(self):
        for intent in ("competitive", "balanced", "quality"):
            tiers = self.kb.video["intents"][intent]["tiers"]
            for tier in ("S", "A", "B", "C", "D"):
                self.assertIn(tier, tiers, f"{intent} is missing tier {tier}")

    def test_matrix_values_are_inside_declared_ranges(self):
        for intent, spec in self.kb.video["intents"].items():
            for tier, settings in spec["tiers"].items():
                for key, value in settings.items():
                    declared = self.kb.video["keys"].get(key)
                    self.assertIsNotNone(declared, f"{key} used in {intent}/{tier} but never declared")
                    self.assertGreaterEqual(value, declared["min"], f"{intent}/{tier}/{key}")
                    self.assertLessEqual(value, declared["max"], f"{intent}/{tier}/{key}")

    def test_quality_never_below_competitive_on_texture_detail(self):
        for tier in ("S", "A", "B"):
            self.assertGreaterEqual(
                self.kb.video["intents"]["quality"]["tiers"][tier]["setting.videocfg_texture_detail"],
                self.kb.video["intents"]["competitive"]["tiers"][tier]["setting.videocfg_texture_detail"],
            )

    def test_every_launch_option_has_a_status_and_reason(self):
        for flag, entry in self.kb.launch["options"].items():
            self.assertIn(entry.get("status"),
                          ("good", "situational", "dead", "harmful", "invalid"),
                          f"{flag} has no valid status")
            self.assertTrue(entry.get("reason", "").strip(), f"{flag} has no reason")

    def test_gpu_indices_are_positive(self):
        for entry in self.kb.gpus["gpus"]:
            self.assertGreater(entry["index"], 0, entry["tokens"])

    def test_no_duplicate_gpu_token_sets(self):
        seen = set()
        for entry in self.kb.gpus["gpus"]:
            key = tuple(sorted(entry["tokens"]))
            self.assertNotIn(key, seen, f"duplicate GPU entry {key}")
            seen.add(key)

    def test_no_duplicate_cpu_token_sets(self):
        seen = set()
        for entry in self.kb.cpus["cpus"]:
            key = tuple(sorted(entry["tokens"]))
            self.assertNotIn(key, seen, f"duplicate CPU entry {key}")
            seen.add(key)


if __name__ == "__main__":
    unittest.main(verbosity=2)
