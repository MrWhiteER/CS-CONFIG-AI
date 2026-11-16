"""Read-back compares intended values, never a writer's success flag."""
import tempfile
import ctypes
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg import elevated, nvidia, verification, webui, steam, wingraphics


class ReadBack(unittest.TestCase):
    def setUp(self):
        for name in ("ready", "run"):
            patcher = mock.patch.object(elevated, name, side_effect=AssertionError("helper must not run"))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "config.cfg"
        self.path.write_text('fps_max "0"\n', encoding="utf-8")

    def run_check(self, **changes):
        spec = dict(label="Config", kind="text", path=str(self.path), expected='fps_max "0"\n')
        if changes.get("kind") == "scaling":
            spec.pop("expected")
        spec.update(changes)
        return verification.check(dict(checks=[spec], applied_at=1, account="42"))

    def test_matches_expected_text(self):
        self.assertEqual(self.run_check()["verified"], 1)

    def test_overwritten_value_is_amber(self):
        self.path.write_text('fps_max "60"\n', encoding="utf-8")
        out = self.run_check()
        self.assertEqual(out["verified"], 0)
        self.assertEqual(out["items"][0]["status"], "changed")

    def test_missing_file_is_changed(self):
        self.path.unlink()
        self.assertEqual(self.run_check()["items"][0]["status"], "changed")

    def test_no_writes_or_repairs_while_checking(self):
        before = self.path.read_bytes()
        with mock.patch.object(Path, "write_text", side_effect=AssertionError("write")), \
             mock.patch.object(Path, "mkdir", side_effect=AssertionError("mkdir")), \
             mock.patch.object(verification, "save", side_effect=AssertionError("save")), \
             mock.patch.object(verification.scaling, "ensure_fill", side_effect=AssertionError("repair")):
            self.assertEqual(self.run_check()["verified"], 1)
        self.assertEqual(self.path.read_bytes(), before)

    def test_permission_failure_is_not_checked(self):
        with mock.patch.object(Path, "read_text", side_effect=PermissionError):
            out = self.run_check()
        self.assertEqual(out["items"][0]["status"], "not_checked")
        self.assertEqual(out["total"], 1)
        self.assertEqual(out["verified"], 0)

    def test_failed_write_stays_red_even_if_old_file_matches(self):
        self.assertEqual(self.run_check(failed="Write failed")["items"][0]["status"], "failed")

    def test_unwritten_settings_are_not_in_denominator(self):
        out = self.run_check(kind="unavailable", counted=False, detail="Not written")
        self.assertEqual((out["verified"], out["total"]), (0, 0))
        self.assertEqual(out["items"][0]["status"], "not_checked")

    def test_skipped_settings_stay_in_denominator(self):
        out = self.run_check(kind="unavailable", detail="CS2 running")
        self.assertEqual((out["verified"], out["total"]), (0, 1))

    def test_autoexec_comment_does_not_count_as_exec(self):
        self.path.write_text('// exec "folder/generated.cfg"\n', encoding="utf-8")
        self.assertEqual(self.run_check(kind="exec", expected="folder/generated.cfg")["verified"], 0)
        self.path.write_text('exec "folder/generated.cfg"\n', encoding="utf-8")
        self.assertEqual(self.run_check(kind="exec", expected="folder/generated.cfg")["verified"], 1)

    def test_video_values_are_compared_individually(self):
        user = steam.SteamUser("42", Path(self.tmp.name))
        user.video_cfg.parent.mkdir(parents=True)
        user.video_cfg.write_text('"video.cfg" { "setting.gpu_level" "2" }', encoding="utf-8")
        out = self.run_check(kind="video", user=str(user.path), key="setting.gpu_level", expected="3")
        self.assertEqual(out["items"][0]["status"], "changed")
        self.assertEqual(self.run_check(kind="video", user=str(user.path), key="setting.gpu_level", expected="2")["verified"], 1)

    def test_launch_options_read_real_vdf(self):
        user = steam.SteamUser("42", Path(self.tmp.name))
        user.localconfig.parent.mkdir(parents=True)
        user.localconfig.write_text('"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { "730" { "LaunchOptions" "-novid" } } } } } }', encoding="utf-8")
        self.assertEqual(self.run_check(kind="launch", user=str(user.path), expected="-novid")["verified"], 1)
        self.assertEqual(self.run_check(kind="launch", user=str(user.path), expected="-other")["verified"], 0)

    def test_scaling_checks_primary_only(self):
        primary = types.SimpleNamespace(display_id=1, fills=True)
        report = types.SimpleNamespace(available=True, screens=[primary], primary=primary)
        with mock.patch.object(verification.scaling, "read", return_value=report):
            self.assertEqual(self.run_check(kind="scaling")["verified"], 1)

    def test_scaling_unavailable_does_not_try_to_set_it(self):
        report = types.SimpleNamespace(available=False, screens=[], reason="Access unavailable")
        with mock.patch.object(verification.scaling, "read", return_value=report), \
             mock.patch.object(verification.scaling, "ensure_fill", side_effect=AssertionError("write")):
            self.assertEqual(self.run_check(kind="scaling")["items"][0]["status"], "not_checked")

    def test_receipt_survives_reload_and_is_rechecked(self):
        path = Path(self.tmp.name) / "receipt.json"
        receipt = dict(checks=[dict(label="Config", kind="text", path=str(self.path), expected='fps_max "0"\n')], applied_at=1)
        verification.save(path, receipt)
        self.assertEqual(verification.load(path), receipt)
        self.path.write_text("changed", encoding="utf-8")
        self.assertEqual(verification.check(verification.load(path))["verified"], 0)

    def test_invalid_receipt_is_not_a_success(self):
        self.path.write_text("{}", encoding="utf-8")
        self.assertIsNone(verification.load(self.path))
        self.assertEqual(verification.check(None)["total"], 0)

    def test_recording_uses_requested_video_not_current_file(self):
        state = types.SimpleNamespace(kb=types.SimpleNamespace(ui_name=lambda key:key),
            verification_path=Path(self.tmp.name) / "receipt.json", cs2_install=None)
        user = steam.SteamUser("42", Path(self.tmp.name))
        profile = types.SimpleNamespace(video={"setting.gpu_level": 3}, intent="balanced")
        with mock.patch.object(verification, "check", return_value={}):
            webui._record_verification(state, user, profile, None,
                dict(write_cfg=False, write_launch=False, fix_scaling=False),
                [dict(what="cs2_video.txt", ok=True)])
        self.assertEqual(state.verification_receipt["checks"][0]["expected"], "3")
        self.assertEqual([s["kind"] for s in state.verification_receipt["checks"][-3:]],
                         ["nvidia", "power", "wingraphics"])

    def test_generated_expectation_is_exact_text_passed_to_writer(self):
        state = types.SimpleNamespace(kb=object(), cfg_folder="folder", cfg_name="generated.cfg",
            verification_path=Path(self.tmp.name) / "receipt.json", cs2_install=Path(self.tmp.name))
        user = steam.SteamUser("42", Path(self.tmp.name))
        profile = types.SimpleNamespace(video={}, intent="balanced")
        generated = {"generated.cfg": "// Generated at the original minute\nfps_max 0",
                     "launch_options_generated.txt": "original launch notes"}
        with mock.patch.object(verification, "check", return_value={}), \
             mock.patch.object(webui.emit, "render_cfg", side_effect=AssertionError("must not regenerate")), \
             mock.patch.object(webui.emit, "render_launch_notes", side_effect=AssertionError("must not regenerate")):
            webui._record_verification(state, user, profile, None,
                dict(write_video=False, write_cfg=True, write_launch=False, fix_scaling=False), [], generated)
        self.assertEqual(state.verification_receipt["checks"][0]["expected"], generated["generated.cfg"])


class SystemReadBack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.install = Path(self.tmp.name)
        self.exe = self.install.joinpath(*wingraphics.EXE_REL)
        self.exe.parent.mkdir(parents=True)
        self.exe.write_bytes(b"fixture")
        self.record = self.install / "power_plan.json"
        self.registry = mock.MagicMock()
        self.registry.QueryValueEx.return_value = (
            "GpuPreference=2;SwapEffectUpgradeEnable=1;AppStatus=4;", 1)
        for patcher in (
            mock.patch.object(sys, "platform", "win32"),
            mock.patch.dict(sys.modules, {"winreg": self.registry}),
            mock.patch.object(elevated, "ready", side_effect=AssertionError("live helper")),
            mock.patch.object(elevated, "run", side_effect=AssertionError("live helper")),
            mock.patch.object(verification.quickfix, "_helper", side_effect=AssertionError("helper")),
            mock.patch.object(verification.quickfix, "_run_elevated", side_effect=AssertionError("UAC")),
            mock.patch.object(verification.quickfix, "_powercfg_setactive", side_effect=AssertionError("write")),
            mock.patch.object(verification.quickfix, "_find_or_create_ultimate_scheme", side_effect=AssertionError("write")),
            mock.patch.object(wingraphics, "apply", side_effect=AssertionError("write")),
            mock.patch.object(verification.quickfix, "_power_record_path", side_effect=AssertionError("storage resolver")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.power = self.patch(verification.quickfix.subprocess, "run", return_value=
                               types.SimpleNamespace(returncode=0, stdout=self.scheme(
                                   "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"), stderr=""))
        self.nv = self.patch(nvidia, "read_recommended", return_value=
                             {"available": True, "matches": True, "detail": ""})

    def patch(self, target, name, **kwargs):
        patcher = mock.patch.object(target, name, **kwargs)
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    @staticmethod
    def scheme(guid, name="High performance"):
        return f"Power Scheme GUID: {guid}  ({name})"

    def check(self, kind=None):
        checks = verification.system_checks(self.install, self.install)
        if kind:
            checks = [s for s in checks if s["kind"] == kind]
        out = verification.check({"checks": checks, "applied_at": 1})
        self.registry.SetValueEx.assert_not_called()
        self.registry.CreateKey.assert_not_called()
        self.registry.DeleteValue.assert_not_called()
        for call in self.power.call_args_list:
            self.assertIn(call.args[0], (["powercfg", "/getactivescheme"], ["powercfg", "/list"]))
        return out

    def test_three_recommendations_count_without_prior_system_apply(self):
        out = self.check()
        self.assertEqual((out["verified"], out["total"]), (3, 3))
        self.assertTrue(all(i["counted"] for i in out["items"]))
        self.registry.QueryValueEx.assert_called_once_with(
            self.registry.OpenKey.return_value.__enter__.return_value, str(self.exe))
        self.registry.OpenKey.assert_called_once_with(self.registry.HKEY_CURRENT_USER, wingraphics.KEY)

    def test_no_driver_excludes_only_nvidia(self):
        self.nv.return_value = {"available": False, "not_applicable": True}
        out = self.check()
        self.assertEqual((out["verified"], out["total"]), (2, 2))
        self.assertEqual(out["items"][0]["status"], "not_applicable")

    def test_nvidia_read_failure_stays_counted(self):
        self.nv.return_value = {"available": False, "reason": "Access denied"}
        out = self.check("nvidia")
        self.assertEqual((out["verified"], out["total"]), (0, 1))
        self.assertEqual(out["items"][0]["status"], "not_checked")

    def test_nvidia_mismatch_is_amber_with_review_action(self):
        self.nv.return_value = {"available": True, "matches": False, "detail": "Power management"}
        item = self.check("nvidia")["items"][0]
        self.assertEqual((item["status"], item["action"]), ("not_set", "nvidia"))
        self.assertIn("NVIDIA Control Panel", item["detail"])

    def test_ultimate_template_matches(self):
        self.power.return_value.stdout = self.scheme(verification.quickfix.ULTIMATE_TEMPLATE_GUID)
        self.assertEqual(self.check("power")["verified"], 1)

    def test_duplicated_ultimate_matches_the_fix_discovery_rule(self):
        self.power.return_value.stdout = self.scheme("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "Ultimate Performance")
        self.assertEqual(self.check("power")["verified"], 1)
        self.assertEqual(len(self.power.call_args_list), 2)

    def test_renamed_app_created_ultimate_matches_recorded_guid(self):
        guid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        self.record.write_text('{"active":true,"changed_to":"' + guid.upper() + '"}', encoding="utf-8")
        self.power.return_value.stdout = self.scheme(guid, "My renamed plan")
        self.assertEqual(self.check("power")["verified"], 1)
        self.assertEqual(len(self.power.call_args_list), 1)

    def test_balanced_is_not_set_with_power_action(self):
        self.power.return_value.stdout = self.scheme("381b4222-f694-41f0-9685-ff5bb260df2e", "Balanced")
        item = self.check("power")["items"][0]
        self.assertEqual((item["status"], item["action"]), ("not_set", "power"))

    def test_power_command_failure_does_not_trust_stdout(self):
        self.power.return_value.returncode = 1
        self.assertEqual(self.check("power")["items"][0]["status"], "not_checked")

    def test_power_timeout_is_not_checked_without_retrying_elevated(self):
        self.power.side_effect = subprocess.TimeoutExpired("powercfg", 5)
        out = self.check("power")
        self.assertEqual((out["verified"], out["total"]), (0, 1))
        self.assertEqual(out["items"][0]["status"], "not_checked")

    def test_unparseable_power_output_is_not_checked(self):
        self.power.return_value.stdout = "unrecognised output"
        self.assertEqual(self.check("power")["items"][0]["status"], "not_checked")

    def test_graphics_mismatch_checks_both_wanted_values(self):
        for value in ("GpuPreference=2;", "SwapEffectUpgradeEnable=1;", "GpuPreference=1;SwapEffectUpgradeEnable=1;"):
            with self.subTest(value=value):
                self.registry.QueryValueEx.return_value = (value, 1)
                item = self.check("wingraphics")["items"][0]
                self.assertEqual((item["status"], item["action"]), ("not_set", "wingraphics"))

    def test_missing_registry_value_is_not_set(self):
        self.registry.QueryValueEx.side_effect = FileNotFoundError
        self.assertEqual(self.check("wingraphics")["items"][0]["status"], "not_set")

    def test_denied_registry_is_not_checked_not_a_mismatch(self):
        self.registry.OpenKey.side_effect = PermissionError
        out = self.check("wingraphics")
        self.assertEqual((out["verified"], out["total"]), (0, 1))
        self.assertEqual(out["items"][0]["status"], "not_checked")

    def test_missing_cs2_executable_is_counted_but_not_checked(self):
        self.exe.unlink()
        self.assertEqual(self.check("wingraphics")["items"][0]["status"], "not_checked")
        self.registry.OpenKey.assert_not_called()

    def test_old_receipt_is_upgraded_on_get_without_saving_or_mutating(self):
        receipt = {"applied_at": 1, "checks": [
            {"label": label, "kind": "unavailable", "counted": False}
            for label in ("NVIDIA profile", "Windows power", "Windows graphics")]}
        state = types.SimpleNamespace(verification_receipt=receipt, cs2_install=self.install,
                                      verification_path=self.install / "applied-verification.json")
        with mock.patch.object(verification, "save", side_effect=AssertionError("GET saved")), \
             mock.patch.object(Path, "write_text", side_effect=AssertionError("GET wrote")), \
             mock.patch.object(Path, "mkdir", side_effect=AssertionError("GET created")):
            out = webui._verification(state)
        self.assertEqual((out["verified"], out["total"]), (3, 3))
        self.assertTrue(all(s["kind"] == "unavailable" for s in receipt["checks"]))
        upgraded = verification.with_system_checks(receipt, self.install)
        self.assertEqual(verification.with_system_checks(upgraded, self.install), upgraded)


class NvidiaReadPath(unittest.TestCase):
    """Exercise real ctypes read plumbing with a fake NVAPI function table."""
    def setUp(self):
        for name in ("ready", "run"):
            patcher = mock.patch.object(elevated, name, side_effect=AssertionError("live helper"))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.session = nvidia._Session.__new__(nvidia._Session)
        self.session._session = ctypes.c_void_p(1)
        self.values = {0x1057EB71: 1, 0x00A879CF: 0x60925292}
        self.profile_values = {2: self.values, 3: {}, 4: {}}
        self.profile_codes = {}
        self.global_codes = {}
        self.find_code = 0
        self.setting_code = 0
        self.setting_type = nvidia._DWORD
        self.called = []
        self.reads = []

        def function(name, *types_):
            self.called.append(name)
            if name == "DRS_FindApplicationByName":
                def find(_session, executable, pointer, app):
                    self.assertEqual(nvidia._text(executable), "cs2.exe")
                    ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p)).contents.value = 2
                    return self.find_code
                return find
            if name in ("DRS_GetCurrentGlobalProfile", "DRS_GetBaseProfile"):
                def global_profile(_session, pointer):
                    handle = 3 if name == "DRS_GetCurrentGlobalProfile" else 4
                    ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p)).contents.value = handle
                    return self.global_codes.get(name, 0)
                return global_profile
            if name == "DRS_GetSetting":
                def get(_session, _profile, setting_id, pointer):
                    profile = _profile.value
                    self.reads.append((profile, setting_id))
                    entry = ctypes.cast(pointer, ctypes.POINTER(nvidia._Setting)).contents
                    self.assertEqual(entry.version, nvidia._stamp(nvidia._Setting, 1))
                    code = self.setting_code or self.profile_codes.get(profile, 0)
                    if code:
                        return code
                    if setting_id not in self.profile_values[profile]:
                        return -160  # NVAPI_SETTING_NOT_FOUND
                    entry.settingType = self.setting_type
                    entry.current.u32 = self.profile_values[profile][setting_id]
                    return 0
                return get
            raise AssertionError("Unexpected NVAPI function: " + name)

        self.session._fn = function
        self.session._explain = lambda code: str(code)
        patcher = mock.patch.object(nvidia, "_Session")
        factory = patcher.start()
        factory.return_value.__enter__.return_value = self.session
        self.addCleanup(patcher.stop)

    def test_explicit_app_values_take_precedence_over_global(self):
        self.profile_values[3] = {0x1057EB71: 5, 0x00A879CF: 0x47814940}
        self.assertTrue(nvidia.read_recommended()["matches"])
        self.assertEqual(self.reads, [(2, setting_id) for setting_id in self.values])
        self.assertNotIn("DRS_GetCurrentGlobalProfile", self.called)
        self.assertNotIn("DRS_GetBaseProfile", self.called)

    def test_unset_app_settings_inherit_current_global_values(self):
        self.profile_values[2] = {}
        self.profile_values[3] = dict(self.values)
        self.profile_values[4] = {0x1057EB71: 5, 0x00A879CF: 0x47814940}
        self.assertTrue(nvidia.read_recommended()["matches"])
        self.assertEqual(self.reads, [(profile, setting_id) for setting_id in self.values
                                      for profile in (2, 3)])
        self.assertEqual(self.called.count("DRS_GetCurrentGlobalProfile"), 1)
        self.assertNotIn("DRS_GetBaseProfile", self.called)

    def test_inheritance_is_resolved_per_setting(self):
        del self.values[0x00A879CF]
        self.profile_values[3] = {0x1057EB71: 5, 0x00A879CF: 0x08416747}
        self.assertTrue(nvidia.read_recommended()["matches"])
        self.assertEqual(self.reads, [(2, 0x1057EB71), (2, 0x00A879CF), (3, 0x00A879CF)])

    def test_inherited_global_mismatch_is_readable(self):
        self.profile_values[2] = {}
        self.profile_values[3] = {0x1057EB71: 0, 0x00A879CF: 0x47814940}
        self.profile_values[4] = dict(self.values)
        report = nvidia.read_recommended()
        self.assertTrue(report["available"])
        self.assertFalse(report["matches"])
        self.assertEqual(report["detail"], "; ".join(
            label for label, _allowed in nvidia.VERIFICATION_TARGETS.values()))
        self.assertNotIn("DRS_GetBaseProfile", self.called)

    def test_unset_global_settings_inherit_base_values(self):
        self.profile_values[2] = {}
        self.profile_values[4] = dict(self.values)
        self.assertTrue(nvidia.read_recommended()["matches"])
        self.assertEqual(self.reads, [(profile, setting_id) for setting_id in self.values
                                      for profile in (2, 3, 4)])
        self.assertEqual(self.called.count("DRS_GetBaseProfile"), 1)

    def test_unset_profiles_use_documented_driver_defaults(self):
        self.profile_values[2] = {}
        values = self.session.effective_settings("cs2.exe", nvidia.VERIFICATION_TARGETS)
        self.assertEqual(values, {0x1057EB71: 5, 0x00A879CF: 0x60925292})
        report = nvidia.read_recommended()
        self.assertTrue(report["available"])
        self.assertFalse(report["matches"])
        self.assertEqual(report["detail"], nvidia.VERIFICATION_TARGETS[0x1057EB71][0])

    def test_missing_app_profile_reads_global_inheritance(self):
        for code in (-166, -163):
            with self.subTest(code=code):
                self.find_code = code
                self.profile_values[3] = dict(self.values)
                self.reads.clear()
                self.assertTrue(nvidia.read_recommended()["matches"])
                self.assertEqual(self.reads, [(3, setting_id) for setting_id in self.values])

    def test_missing_cs2_and_global_profiles_use_driver_defaults(self):
        self.find_code = -163
        self.global_codes = {"DRS_GetCurrentGlobalProfile": -163, "DRS_GetBaseProfile": -163}
        report = nvidia.read_recommended()
        self.assertTrue(report["available"])
        self.assertFalse(report["matches"])
        self.assertEqual(report["detail"], nvidia.VERIFICATION_TARGETS[0x1057EB71][0])
        self.assertEqual(self.reads, [])

    def test_missing_profile_during_setting_read_uses_inheritance(self):
        for code in (-163, -166):
            with self.subTest(code=code):
                self.profile_codes[2] = code
                self.profile_values[3] = dict(self.values)
                self.assertTrue(nvidia.read_recommended()["matches"])

    def test_missing_current_global_profile_reads_base(self):
        self.profile_values[2] = {}
        self.global_codes["DRS_GetCurrentGlobalProfile"] = -163
        self.profile_values[4] = dict(self.values)
        self.assertTrue(nvidia.read_recommended()["matches"])
        self.assertEqual(self.reads, [(profile, setting_id) for setting_id in self.values
                                      for profile in (2, 4)])

    def test_forced_vsync_off_also_matches(self):
        self.values[0x00A879CF] = 0x08416747
        self.assertTrue(nvidia.read_recommended()["matches"])

    def test_any_recommended_value_mismatch_prevents_green(self):
        for setting_id, value in ((0x1057EB71, 5), (0x00A879CF, 0x47814940)):
            with self.subTest(setting_id=setting_id):
                original = self.values[setting_id]
                self.values[setting_id] = value
                self.assertFalse(nvidia.read_recommended()["matches"])
                self.values[setting_id] = original

    def test_access_denied_is_not_mistaken_for_missing_profile(self):
        self.find_code = -175
        report = nvidia.read_recommended()
        self.assertFalse(report["available"])
        self.assertFalse(report.get("not_applicable", False))
        self.assertNotIn("DRS_GetCurrentGlobalProfile", self.called)

    def test_unreadable_setting_is_not_checked(self):
        for code in (-175, -1, -9):
            with self.subTest(code=code):
                self.setting_code = code
                self.assertFalse(nvidia.read_recommended()["available"])
        self.assertNotIn("DRS_GetCurrentGlobalProfile", self.called)

    def test_global_access_denied_does_not_use_driver_defaults(self):
        self.profile_values[2] = {}
        self.profile_codes[3] = -175
        self.assertFalse(nvidia.read_recommended()["available"])
        self.assertNotIn("DRS_GetBaseProfile", self.called)

    def test_global_profile_open_failure_is_not_checked(self):
        self.profile_values[2] = {}
        self.global_codes["DRS_GetCurrentGlobalProfile"] = -175
        self.assertFalse(nvidia.read_recommended()["available"])
        self.assertNotIn("DRS_GetBaseProfile", self.called)

    def test_unexpected_setting_type_is_not_checked(self):
        self.setting_type = nvidia._STRING
        self.assertFalse(nvidia.read_recommended()["available"])
        self.assertNotIn("DRS_GetCurrentGlobalProfile", self.called)

    def test_missing_nvidia_gpu_is_not_applicable(self):
        self.find_code = -6
        self.assertTrue(nvidia.read_recommended()["not_applicable"])

    def test_missing_dll_is_not_applicable_but_other_errors_are_not_checked(self):
        for error, excluded in ((nvidia.NoNvidiaDriver("no driver"), True),
                                (PermissionError("denied"), False),
                                (nvidia.NvApiError("old driver"), False)):
            with self.subTest(error=error), mock.patch.object(nvidia, "_Session", side_effect=error):
                self.assertEqual(nvidia.read_recommended().get("not_applicable", False), excluded)


if __name__ == "__main__":
    unittest.main()
