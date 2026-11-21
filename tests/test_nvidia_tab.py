"""Settings -> NVIDIA (Edy, Nov 21): CS2's NVIDIA profile, the GPU/CPU lean, the helper job."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg import elevated, nvidia, pcstate
from cs2cfg.hardware import Cpu, Display, Gpu, Machine
from cs2cfg.kb import KnowledgeBase
from cs2cfg.profile import LEAN_CPU_KEYS, LEAN_GPU_KEYS, build_profile

ROOT = Path(__file__).resolve().parents[1]


class FakeSession:
    """Stands in for the driver: one CS2 profile held in a dict."""

    def __init__(self, held=None, admin_only=False):
        self.held = dict(held or {})
        self.saved = False
        self.admin_only = admin_only
        self.created = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cs2_profile(self, create=False):
        if create:
            self.created = True
        return "cs2"

    def profile_state(self, handle, setting_id):
        return self.held.get(setting_id)

    def change(self, handle, setting_id, value):
        assert handle == "cs2", "only CS2's profile is ever written"
        if value is None:
            self.held.pop(setting_id, None)
        else:
            self.held[setting_id] = value

    def save(self):
        if self.admin_only:
            raise nvidia.NeedsAdministrator("admin")
        self.saved = True


class TestWriteCs2(unittest.TestCase):
    def test_writes_only_what_differs_and_reports_plain_words(self):
        session = FakeSession({nvidia.POWER: 0x5, nvidia.VSYNC: 0x60925292})
        with mock.patch.object(nvidia, "_Session", return_value=session), \
             mock.patch.object(pcstate, "note") as note:
            result = nvidia.apply_intent("competitive")
        self.assertTrue(result["ok"], result)
        self.assertTrue(session.saved)
        names = {c["name"]: (c["before"], c["after"]) for c in result["changed"]}
        self.assertEqual(names["Power management mode"], ("Normal", "Prefer maximum performance"))
        self.assertNotIn("Vertical sync", names, "already right, so not rewritten")
        self.assertEqual(names["Texture filtering - Quality"][1], "High performance")
        self.assertEqual(session.held[nvidia.TEX_QUALITY], 0x14)
        noted = {c.args[1]: (c.args[2], c.args[3]) for c in note.call_args_list}
        self.assertEqual(noted["0x1057EB71"], (0x5, 0x1))
        for call in note.call_args_list:
            self.assertEqual(call.args[0], "nvidia_3d")

    def test_players_own_value_wins_over_the_mode(self):
        session = FakeSession()
        with mock.patch.object(nvidia, "_Session", return_value=session), \
             mock.patch.object(pcstate, "note"):
            nvidia.apply_intent("competitive", {"0x1057EB71": 0x5})
        self.assertEqual(session.held[nvidia.POWER], 0x5)

    def test_admin_only_driver_goes_through_the_helper_never_a_prompt(self):
        session = FakeSession(admin_only=True)
        answer = {"ok": True, "before": [{"id": nvidia.POWER, "value": "default"}]}
        with mock.patch.object(nvidia, "_Session", return_value=session), \
             mock.patch.object(elevated, "run", return_value=answer) as run, \
             mock.patch.object(pcstate, "note") as note:
            result = nvidia.write_cs2({nvidia.POWER: 1})
        self.assertTrue(result["ok"])
        run.assert_called_once_with("nvidia.set", {"changes": [{"id": nvidia.POWER, "value": 1}]})
        note.assert_called_once_with("nvidia_3d", "0x1057EB71", "default", 1)
        self.assertEqual(result["changed"][0]["before"], "NVIDIA's own setting for CS2")

    def test_no_helper_is_a_plain_message(self):
        session = FakeSession(admin_only=True)
        with mock.patch.object(nvidia, "_Session", return_value=session), \
             mock.patch.object(elevated, "run", return_value={"ok": False, "needs_setup": True}):
            result = nvidia.write_cs2({nvidia.POWER: 1})
        self.assertFalse(result["ok"])
        self.assertTrue(result["needs_setup"])
        self.assertIn("Allow it once", result["error"])

    def test_bad_values_never_reach_the_driver(self):
        with mock.patch.object(nvidia, "_Session") as session:
            self.assertFalse(nvidia.write_cs2({nvidia.POWER: -1})["ok"])
            self.assertFalse(nvidia.write_cs2({0: 1})["ok"])
            self.assertFalse(nvidia.write_cs2({i: 0 for i in range(1, 70)})["ok"])
        session.assert_not_called()


class TestPutBack(unittest.TestCase):
    def test_pcstate_reads_and_writes_cs2s_profile(self):
        with mock.patch.object(nvidia, "read_cs2", return_value={nvidia.POWER: 1}):
            self.assertEqual(pcstate._read("nvidia_3d", "0x1057EB71"), 1)
        with mock.patch.object(nvidia, "write_cs2", return_value={"ok": True}) as write, \
             mock.patch("cs2cfg.steam.cs2_running", return_value=False):
            pcstate._write("nvidia_3d", "0x1057EB71", "default", live_ok=False, persist=True)
        write.assert_called_once_with({nvidia.POWER: "default"}, record=False)

    def test_put_back_waits_for_cs2_to_close(self):
        with mock.patch("cs2cfg.steam.cs2_running", return_value=True):
            with self.assertRaises(pcstate.Waiting):
                pcstate._write("nvidia_3d", "0x1057EB71", 5, live_ok=False, persist=True)

    def test_has_a_plain_label(self):
        self.assertEqual(pcstate.label({"kind": "nvidia_3d"}), "NVIDIA graphics settings for CS2")


class TestHelperJob(unittest.TestCase):
    def test_validated_before_it_is_sent(self):
        ok = elevated.validate("nvidia.set", {"changes": [{"id": 0x1057EB71, "value": 1},
                                                          {"id": 5, "value": None},
                                                          {"id": 6, "value": "default"}]})
        self.assertEqual(len(ok["changes"]), 3)
        for bad in ({"changes": []}, {"changes": [{"id": 0, "value": 1}]},
                    {"changes": [{"id": 1, "value": "rm -rf"}]},
                    {"changes": [{"id": 1, "value": True}]},
                    {"changes": [{"id": 1, "value": 2 ** 32}]}):
            with self.assertRaises(elevated.HelperError):
                elevated.validate("nvidia.set", bad)

    def test_broker_job_is_fixed_code_for_cs2s_profile_only(self):
        broker = (ROOT / "cs2cfg" / "helper" / "broker.ps1").read_text(encoding="utf-8")
        job = broker[broker.index("$NvSource = @'"):broker.index("function Invoke-HelperUninstall")]
        self.assertIn("'nvidia.set'       = { param($a) Invoke-NvidiaSet $a }", broker)
        self.assertIn('"cs2.exe"', job)
        self.assertNotIn("0xDA8466A0", job, "never opens the global (base) profile")
        self.assertNotIn("0x617BFF9F", job, "never opens the current global profile")
        self.assertNotIn("Invoke-Expression", job)
        self.assertIn("-notmatch '^\\d{1,10}$'", job)


class TestLean(unittest.TestCase):
    def setUp(self):
        self.kb = KnowledgeBase()
        self.machine = Machine(
            cpu=Cpu("AMD Ryzen 7 7800X3D 8-Core Processor", 8, 16, 5000, "amd"),
            gpu=Gpu("NVIDIA GeForce RTX 4070", 12, "nvidia"), all_gpus=[],
            displays=[Display(1920, 1080, 240, True)], ram_gb=32, ram_speed_mts=6000,
            os_caption="", os_build="", power_plan=None, display_source="")

    def video(self, intent, bias):
        return build_profile(self.machine, self.kb, intent=intent, load_bias=bias).video

    def test_lean_moves_real_picture_settings(self):
        """Until Nov 21 "Lean on GPU" changed nothing on this machine."""
        for intent in ("competitive", "balanced", "quality"):
            auto, gpu, cpu = (self.video(intent, b) for b in ("auto", "gpu", "cpu"))
            real = set(LEAN_GPU_KEYS) | set(LEAN_CPU_KEYS)
            self.assertTrue({k for k in real if gpu[k] != auto[k]}, intent + ": GPU lean moved nothing")
            self.assertTrue({k for k in real if cpu[k] != auto[k]}, intent + ": CPU lean moved nothing")
            for key in LEAN_GPU_KEYS:
                self.assertGreaterEqual(gpu[key], auto[key])
                self.assertLessEqual(cpu[key], auto[key])
            for key in LEAN_CPU_KEYS:
                self.assertLessEqual(gpu[key], auto[key])
                self.assertGreaterEqual(cpu[key], auto[key])
            self.assertEqual(gpu["setting.videocfg_dynamic_shadows"], auto["setting.videocfg_dynamic_shadows"])

    def test_values_stay_ones_cs2_accepts(self):
        for bias in ("gpu", "cpu"):
            self.assertIn(self.video("balanced", bias)["setting.msaa_samples"], (0, 2, 4, 8))


class TestKnownSettings(unittest.TestCase):
    def test_names_and_choices_read_as_plain_words(self):
        table = nvidia.known_settings()
        self.assertGreater(len(table), 100)
        for setting_id in nvidia.MANAGED["balanced"]:
            entry = table[nvidia.hex_id(setting_id)]
            for label in entry["choices"].values():
                self.assertNotRegex(label, r"^[A-Z0-9_]+$", "no raw driver names")
        self.assertEqual(nvidia.label_for(nvidia.VSYNC, 0x60925292), "Use the game's setting")


class TestPage(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "cs2cfg" / "web" / "index.html").read_text(encoding="utf-8")

    def test_apply_tab_is_now_nvidia(self):
        self.assertIn('data-sub="nvidia" role="tab"', self.page)
        self.assertNotIn('data-sub="apply"', self.page)
        for gone in ('id="w-video"', 'id="p-video"', 'id="w-cfg"', 'id="w-autoexec"',
                     'id="w-scaling"', 'id="preview"', 'id="apply"', 'id="revert"'):
            self.assertNotIn(gone, self.page)
        self.assertIn("Managed by CS CONFIG", self.page)
        self.assertIn('id="nv-show-all"', self.page)

    def test_switching_never_asks_first(self):
        start = self.page.index("async function applyProfile(")
        body = self.page[start:self.page.index("/* Profile Rail:", start)]
        self.assertNotIn("appAsk", body)
        self.assertNotIn("confirm(", body)


if __name__ == "__main__":
    unittest.main()
