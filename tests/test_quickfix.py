"""Tests for the repairs, which are mostly tests of when they refuse.

Each of these takes something away and gives it back. That is fine when it
works and unpleasant when it does not: an adapter restarted mid-round loses the
round, and a keyboard disabled without being re-enabled stays disabled across
reboots. So what is pinned here is the refusing -- the cases where the right
behaviour is to do nothing and say why.

Nothing here touches a real device. Every privileged call is stubbed.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import quickfix  # noqa: E402


class WhileTheGameIsUp(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(quickfix, "_run_elevated",
                                  side_effect=AssertionError("should not have run"))
        patch.start()
        self.addCleanup(patch.stop)

    def _run(self, fix_id, running=True, **body):
        with mock.patch.object(quickfix, "_game_running", return_value=running):
            return quickfix.run(fix_id, body)

    def test_restarting_the_connection_is_refused_mid_match(self):
        """Not a fix -- it is the problem. A dropped adapter is a dropped round."""
        result = self._run("net.restart", adapter="Ethernet")
        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])
        self.assertIn("CS2 is running", result["error"])

    def test_restarting_audio_is_refused_mid_match(self):
        result = self._run("sound.restart")
        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])

    def test_restarting_the_graphics_driver_is_allowed_mid_match(self):
        """The one repair whose whole purpose is a game that has frozen.
        Refusing it while the game is up withholds it exactly when it is
        wanted, and Windows closes nothing when it resets the driver."""
        with mock.patch.object(quickfix, "_game_running", return_value=True), \
             mock.patch.object(quickfix, "_send_keys", return_value=0) as keys:
            result = quickfix.run("gpu.restart", {})
        self.assertTrue(result["ok"])
        keys.assert_called_once()

    def test_with_the_game_closed_the_repair_goes_through(self):
        with mock.patch.object(quickfix, "_game_running", return_value=False), \
             mock.patch.object(quickfix, "_run_elevated",
                               return_value={"ok": True, "detail": "done"}):
            result = quickfix.run("net.restart", {"adapter": "Ethernet"})
        self.assertTrue(result["ok"])


class NotTakingTheLastOne(unittest.TestCase):
    """Disable-PnpDevice persists across reboots.

    Taking away the only mouse is an annoyance. Taking away the only keyboard
    leaves somebody unable to answer the dialog explaining what happened, and a
    reboot does not give it back.
    """

    LISTING = ('[{"FriendlyName":"Only Keyboard","Class":"Keyboard","InstanceId":"HID\\\\K1"},'
               '{"FriendlyName":"Mouse A","Class":"Mouse","InstanceId":"HID\\\\M1"},'
               '{"FriendlyName":"Mouse B","Class":"Mouse","InstanceId":"HID\\\\M2"}]')

    def setUp(self):
        patch = mock.patch.object(quickfix, "_powershell", return_value=self.LISTING)
        patch.start()
        self.addCleanup(patch.stop)

    def test_the_only_keyboard_is_not_offered(self):
        found = {d["name"]: d for d in quickfix.devices()}
        self.assertFalse(found["Only Keyboard"]["restartable"])
        self.assertIn("only keyboard", found["Only Keyboard"]["why_not"].lower())

    def test_one_of_two_mice_is_offered(self):
        found = {d["name"]: d for d in quickfix.devices()}
        self.assertTrue(found["Mouse A"]["restartable"])
        self.assertTrue(found["Mouse B"]["restartable"])

    def test_asking_for_it_anyway_is_refused(self):
        """The list is a courtesy; the refusal is the guard. A caller that
        sends the id regardless must still be turned away."""
        with mock.patch.object(quickfix, "_run_elevated",
                               side_effect=AssertionError("should not have run")):
            result = quickfix._fix_restart_device("HID\\K1")
        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])

    def test_a_device_that_is_not_there_is_refused(self):
        with mock.patch.object(quickfix, "_run_elevated",
                               side_effect=AssertionError("should not have run")):
            result = quickfix._fix_restart_device("HID\\NOPE")
        self.assertFalse(result["ok"])
        self.assertIn("not connected", result["error"])

    def test_nothing_chosen_is_refused(self):
        result = quickfix._fix_restart_device("")
        self.assertFalse(result["ok"])


class TheDeviceScript(unittest.TestCase):
    def test_the_enable_is_in_a_finally(self):
        """If the disable succeeds and the script then fails, the device has
        to come back anyway. Checked on the script text because the failure it
        guards against is one that cannot be provoked from here safely."""
        listing = ('[{"FriendlyName":"Mouse A","Class":"Mouse","InstanceId":"HID\\\\M1"},'
                   '{"FriendlyName":"Mouse B","Class":"Mouse","InstanceId":"HID\\\\M2"}]')
        seen = {}
        with mock.patch.object(quickfix, "_powershell", return_value=listing), \
             mock.patch.object(quickfix, "_run_elevated",
                               side_effect=lambda body, **kw: seen.update(body=body) or {"ok": True}):
            quickfix._fix_restart_device("HID\\M1")
        script = seen["body"]
        self.assertIn("Disable-PnpDevice", script)
        self.assertIn("Enable-PnpDevice", script)
        self.assertLess(script.index("} finally {"), script.index("Enable-PnpDevice"),
                        "the enable must sit in the finally, not after the disable")


class Sound(unittest.TestCase):
    def test_a_mixer_on_the_machine_is_noticed(self):
        listing = ('[{"Name":"TC-HELICON GoXLR","Status":"OK"},'
                   '{"Name":"Realtek USB Audio","Status":"OK"}]')
        with mock.patch.object(quickfix, "_powershell", return_value=listing):
            found = quickfix.sound_devices()
        self.assertIn("TC-HELICON GoXLR", found["special"])
        self.assertNotIn("Realtek USB Audio", found["special"])

    def test_an_ordinary_machine_flags_nothing(self):
        listing = '[{"Name":"Realtek High Definition Audio","Status":"OK"}]'
        with mock.patch.object(quickfix, "_powershell", return_value=listing):
            self.assertEqual(quickfix.sound_devices()["special"], [])

    def test_routing_is_never_written(self):
        """The interface behind per-app routing is undocumented and the
        registry it lands in is an opaque blob. Guessing at it on a machine
        somebody streams through is not a small mistake, so the repair opens
        the page and writes nothing."""
        with mock.patch.object(quickfix.os, "startfile") as opened:
            result = quickfix._fix_open_app_volume()
        self.assertTrue(result["ok"])
        opened.assert_called_once_with("ms-settings:apps-volume")


class Plumbing(unittest.TestCase):
    def test_an_unknown_repair_is_refused_rather_than_guessed_at(self):
        result = quickfix.run("something.else", {})
        self.assertFalse(result["ok"])

    def test_a_repair_that_throws_does_not_take_the_app_down(self):
        with mock.patch.object(quickfix, "_game_running", return_value=False), \
             mock.patch.object(quickfix, "_fix_flush_dns",
                               side_effect=OSError("powershell missing")):
            result = quickfix.run("net.flush", {})
        self.assertFalse(result["ok"])
        self.assertIn("powershell missing", result["error"])

    def test_every_catalogue_entry_has_something_that_runs_it(self):
        for fix in quickfix.CATALOGUE:
            self.assertIn(fix.id, quickfix._RUNNERS, f"{fix.id} has no runner")

    def test_every_runner_is_described_to_the_user(self):
        described = {f.id for f in quickfix.CATALOGUE}
        for fix_id in quickfix._RUNNERS:
            self.assertIn(fix_id, described, f"{fix_id} would appear with no explanation")

    def test_anything_needing_admin_says_so_before_it_runs(self):
        """The badge is what tells somebody a prompt is coming. A repair that
        raises one without warning reads as the app misbehaving."""
        for fix in quickfix.CATALOGUE:
            if fix.id in ("net.flush", "net.restart", "device.restart", "sound.restart"):
                self.assertTrue(fix.needs_admin, f"{fix.id} prompts without saying so")

    def test_input_struct_is_the_size_windows_demands(self):
        """SendInput rejects the whole call unless cbSize is exactly
        sizeof(INPUT) -- it does not round, and it does not tell you why.

        This shipped wrong: the union was padded by hand to 24 bytes, which
        made INPUT 32 instead of 40 on x64, and every attempt to reset the
        display driver came back as error 87 the instant it was pressed. The
        size is set by the union's largest arm, which is MOUSEINPUT, not the
        keyboard one being used.
        """
        import ctypes

        sixty_four = ctypes.sizeof(ctypes.c_void_p) == 8
        self.assertEqual(quickfix.EXPECTED_INPUT_SIZE, 40 if sixty_four else 28)
        self.assertEqual(ctypes.sizeof(quickfix._Input),
                         quickfix.EXPECTED_INPUT_SIZE)
        # The mouse arm is the one that sets it; if it ever stops being the
        # largest, the number above stops being right.
        self.assertGreaterEqual(ctypes.sizeof(quickfix._MouseInput),
                                ctypes.sizeof(quickfix._KeyInput))

    def test_a_wrong_sized_struct_is_refused_rather_than_sent(self):
        """Better a clear complaint than a keystroke Windows silently drops."""
        with mock.patch.object(quickfix, "INPUT_SIZE", 32), \
             mock.patch.object(quickfix, "sys") as fake_sys, \
             mock.patch.object(quickfix, "_send_keys") as never:
            fake_sys.platform = "win32"
            result = quickfix._fix_restart_gpu()
        self.assertFalse(result["ok"])
        self.assertIn("32 bytes", result["error"])
        never.assert_not_called()

    def test_a_blocked_keystroke_says_what_to_do_about_it(self):
        """Error 5 here means a window running as administrator is in front,
        which the user can fix in one click if they are told so."""
        with mock.patch.object(quickfix, "sys") as fake_sys, \
             mock.patch.object(quickfix, "_send_keys", return_value=5):
            fake_sys.platform = "win32"
            result = quickfix._fix_restart_gpu()
        self.assertFalse(result["ok"])
        self.assertIn("administrator", result["error"])


class PowerPlan(unittest.TestCase):
    """Found live: powercfg refusing was read as "did not switch" rather
    than as a refusal, because only stdout was ever kept. A plan that ran,
    exited non-zero and said why on stderr looked identical to one that
    quietly did nothing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.object(quickfix, "_power_record_path",
                                  return_value=Path(self.tmp.name) / "power.json")
        patch.start()
        self.addCleanup(patch.stop)

    def _proc(self, returncode=0, stdout="", stderr=""):
        return mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)

    def test_powercfg_reports_failure_rather_than_assuming_success(self):
        with mock.patch.object(quickfix.subprocess, "run",
                               return_value=self._proc(1, "", "Access is denied.")):
            result = quickfix._powercfg(["/setactive", "SCHEME_MIN"])
        self.assertFalse(result["ok"])
        self.assertIn("Access is denied", result["error"])

    def test_a_missing_powercfg_is_a_failure_not_an_empty_string(self):
        with mock.patch.object(quickfix.subprocess, "run",
                               side_effect=OSError("not found")):
            result = quickfix._powercfg(["/getactivescheme"])
        self.assertFalse(result["ok"])

    def test_setactive_does_not_escalate_when_the_plain_call_works(self):
        with mock.patch.object(quickfix.subprocess, "run",
                               return_value=self._proc(0, "ok")), \
             mock.patch.object(quickfix, "_run_elevated",
                               side_effect=AssertionError("should not have run")):
            result = quickfix._powercfg_setactive("SCHEME_MIN")
        self.assertTrue(result["ok"])

    def test_a_refusal_is_retried_elevated(self):
        with mock.patch.object(quickfix.subprocess, "run",
                               return_value=self._proc(1, "", "Access is denied.")), \
             mock.patch.object(quickfix, "_run_elevated",
                               return_value={"ok": True}) as elevated:
            result = quickfix._powercfg_setactive("SCHEME_MIN")
        self.assertTrue(result["ok"])
        elevated.assert_called_once()

    def test_the_real_reason_survives_an_elevated_failure(self):
        """The wrapper that runs an elevated script reports a caught
        exception under "detail", not "error" -- this is the case that was
        read as "Windows did not switch the power plan" with nothing to go
        on."""
        with mock.patch.object(quickfix.subprocess, "run",
                               return_value=self._proc(1, "", "")), \
             mock.patch.object(quickfix, "_run_elevated",
                               return_value={"ok": False,
                                            "detail": "powercfg exited with code 5"}):
            result = quickfix._powercfg_setactive("SCHEME_MIN")
        self.assertFalse(result["ok"])
        self.assertIn("exited with code 5", result["error"])

    def test_a_declined_prompt_is_reported_as_declined(self):
        with mock.patch.object(quickfix.subprocess, "run",
                               return_value=self._proc(1, "", "denied")), \
             mock.patch.object(quickfix, "_run_elevated",
                               return_value={"ok": False, "declined": True,
                                            "error": "the administrator prompt was declined"}):
            result = quickfix._powercfg_setactive("SCHEME_MIN")
        self.assertTrue(result.get("declined"))

    def test_switching_raises_with_the_real_message_rather_than_a_generic_one(self):
        with mock.patch.object(quickfix, "_active_scheme_guid", return_value="guid-a"), \
             mock.patch.object(quickfix, "_find_or_create_ultimate_scheme",
                               return_value="ultimate-guid"), \
             mock.patch.object(quickfix, "_powercfg_setactive",
                               return_value={"ok": False,
                                            "error": "Access is denied."}):
            with self.assertRaises(quickfix.FixError) as caught:
                quickfix._fix_toggle_power({})
        self.assertIn("Access is denied", str(caught.exception))

    def test_switching_successfully_remembers_what_to_restore(self):
        guids = iter(["before-guid", "after-guid"])
        with mock.patch.object(quickfix, "_active_scheme_guid",
                               side_effect=lambda: next(guids)), \
             mock.patch.object(quickfix, "_find_or_create_ultimate_scheme",
                               return_value="ultimate-guid"), \
             mock.patch.object(quickfix, "_powercfg_setactive",
                               return_value={"ok": True}):
            result = quickfix._fix_toggle_power({})
        self.assertTrue(result["ok"])
        self.assertTrue(result["boosted"])
        self.assertEqual(result["plan"], "Ultimate Performance")
        record = quickfix._power_record_path()
        self.assertTrue(record.is_file())

    def test_already_being_on_the_target_plan_is_success_not_a_refusal(self):
        """Found live: the machine this was tested on already had Ultimate
        Performance active. The old code read "nothing changed" as a
        failure in every case, which made an already-correct machine report
        an error for a repair that had nothing to repair."""
        with mock.patch.object(quickfix, "_active_scheme_guid",
                               return_value="same-guid"), \
             mock.patch.object(quickfix, "_find_or_create_ultimate_scheme",
                               return_value="same-guid"), \
             mock.patch.object(quickfix, "_powercfg_setactive",
                               return_value={"ok": True}):
            result = quickfix._fix_toggle_power({})
        self.assertTrue(result["ok"])
        self.assertTrue(result["boosted"])
        self.assertIn("Already on", result["detail"])
        self.assertFalse(quickfix._power_record_path().is_file(),
                         "nothing changed, so there is nothing to put back")

    def test_falling_back_to_high_performance_when_ultimate_cannot_be_made(self):
        """Rare: duplicating the template itself failed. The switch still
        goes through, just onto the plan every edition already ships with."""
        guids = iter(["before-guid", "after-guid"])
        with mock.patch.object(quickfix, "_active_scheme_guid",
                               side_effect=lambda: next(guids)), \
             mock.patch.object(quickfix, "_find_or_create_ultimate_scheme",
                               return_value=None), \
             mock.patch.object(quickfix, "_powercfg_setactive",
                               return_value={"ok": True}) as setactive:
            result = quickfix._fix_toggle_power({})
        self.assertEqual(result["plan"], "High performance")
        setactive.assert_called_once_with("SCHEME_MIN")

    def test_schemes_are_parsed_from_a_real_shaped_listing(self):
        listing = (
            "Existing Power Schemes (* Active)\n"
            "-----------------------------------\n"
            "Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)\n"
            "Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  "
            "(High performance) *\n"
            "Power Scheme GUID: eee9dd6d-34f7-4662-b9a9-b69497e6568d  "
            "(Ultimate Performance)\n")
        with mock.patch.object(quickfix, "_powercfg",
                               return_value={"ok": True, "out": listing}):
            found = quickfix._schemes()
        self.assertIn(("eee9dd6d-34f7-4662-b9a9-b69497e6568d",
                       "Ultimate Performance"), found)
        self.assertEqual(len(found), 3)

    def test_an_existing_ultimate_scheme_is_reused_not_duplicated_again(self):
        with mock.patch.object(quickfix, "_schemes",
                               return_value=[("abc-guid", "Ultimate Performance")]), \
             mock.patch.object(quickfix, "_powercfg",
                               side_effect=AssertionError("should not duplicate again")):
            found = quickfix._find_or_create_ultimate_scheme()
        self.assertEqual(found, "abc-guid")

    def test_a_missing_ultimate_scheme_is_duplicated_in(self):
        new_guid = "11111111-2222-3333-4444-555555555555"
        created = {"ok": True,
                  "out": f"Power Scheme GUID: {new_guid}  (Ultimate Performance)"}
        with mock.patch.object(quickfix, "_schemes", return_value=[]), \
             mock.patch.object(quickfix, "_powercfg",
                               return_value=created) as powercfg:
            found = quickfix._find_or_create_ultimate_scheme()
        self.assertEqual(found, new_guid)
        powercfg.assert_called_once_with(
            ["-duplicatescheme", quickfix.ULTIMATE_TEMPLATE_GUID])

    def test_a_refused_duplication_falls_back_cleanly(self):
        with mock.patch.object(quickfix, "_schemes", return_value=[]), \
             mock.patch.object(quickfix, "_powercfg",
                               return_value={"ok": False, "out": "", "error": "no"}):
            found = quickfix._find_or_create_ultimate_scheme()
        self.assertIsNone(found)

    def test_putting_it_back_also_surfaces_a_real_refusal(self):
        quickfix._power_record_path().write_text(
            '{"before": "before-guid", "changed_to": "after-guid", "active": true}',
            encoding="utf-8")
        with mock.patch.object(quickfix, "_active_scheme_guid", return_value="after-guid"), \
             mock.patch.object(quickfix, "_powercfg_setactive",
                               return_value={"ok": False,
                                            "error": "Access is denied."}):
            with self.assertRaises(quickfix.FixError) as caught:
                quickfix._fix_toggle_power({})
        self.assertIn("Access is denied", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
