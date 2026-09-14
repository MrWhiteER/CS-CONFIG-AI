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
             mock.patch.object(quickfix, "_send_keys", return_value=True) as keys:
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


if __name__ == "__main__":
    unittest.main()
