"""Read-back compares intended values, never a writer's success flag."""
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg import verification, webui, steam


class ReadBack(unittest.TestCase):
    def setUp(self):
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


if __name__ == "__main__":
    unittest.main()
