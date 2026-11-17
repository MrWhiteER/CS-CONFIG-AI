"""Starting the FACEIT client and FACEIT AC.

Only ever starting their executables: nothing here reads or writes a file of
FACEIT's, which is the line that keeps this safe next to their anti-cheat.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import companions, faceit_apps, launcher  # noqa: E402


class Finding(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        local = self.tmp / "local"
        pf = self.tmp / "pf"
        (local / "FACEIT").mkdir(parents=True)
        (pf / "FACEIT AC").mkdir(parents=True)
        self.client = local / "FACEIT" / "FACEIT.exe"
        self.ac = pf / "FACEIT AC" / "faceitclient.exe"
        env = mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local),
                                           "ProgramFiles": str(pf)})
        env.start()
        self.addCleanup(env.stop)

    def test_known_places_are_found(self):
        self.client.write_bytes(b"")
        self.ac.write_bytes(b"")
        self.assertEqual(faceit_apps.find(faceit_apps.CLIENT, []), self.client)
        self.assertEqual(faceit_apps.find(faceit_apps.AC, []), self.ac)

    def test_missing_is_none(self):
        self.assertIsNone(faceit_apps.find(faceit_apps.CLIENT, []))

    def test_uninstall_list_is_the_fallback(self):
        elsewhere = self.tmp / "D" / "FACEIT AC"
        elsewhere.mkdir(parents=True)
        (elsewhere / "faceitclient.exe").write_bytes(b"")
        rows = [
            {"DisplayName": "FACEIT", "InstallLocation": "", "DisplayIcon": ""},
            {"DisplayName": "FACEIT Anti-Cheat", "InstallLocation": str(elsewhere),
             "DisplayIcon": ""},
        ]
        self.assertEqual(faceit_apps.find(faceit_apps.AC, rows),
                         elsewhere / "faceitclient.exe")
        # The anti-cheat's entry is never mistaken for the client.
        self.assertIsNone(faceit_apps.find(faceit_apps.CLIENT, rows))


class Settings(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.exe = self.tmp / "faceitclient.exe"
        self.exe.write_bytes(b"")

    def test_turning_on_adds_a_tagged_companion(self):
        change = faceit_apps.set_with_game({}, faceit_apps.AC, True, str(self.exe))
        [entry] = change["companions"]
        self.assertEqual(entry["integration"], faceit_apps.AC)
        self.assertTrue(entry["with_game"])
        self.assertEqual(companions.listed(change)[0]["integration"], faceit_apps.AC)

    def test_turning_off_keeps_the_path(self):
        ui = faceit_apps.set_with_game({}, faceit_apps.AC, True, str(self.exe))
        off = faceit_apps.set_with_game(ui, faceit_apps.AC, False)
        [entry] = off["companions"]
        self.assertFalse(entry["with_game"])
        self.assertEqual(entry["exe"], str(self.exe))

    def test_not_installed_says_so(self):
        with mock.patch.object(faceit_apps, "find", return_value=None):
            with self.assertRaises(companions.CompanionError):
                faceit_apps.set_with_game({}, faceit_apps.CLIENT, True)

    def test_unknown_program_is_refused(self):
        with self.assertRaises(companions.CompanionError):
            faceit_apps.set_with_game({}, "something-else", True)


class Elevation(unittest.TestCase):
    """FACEIT AC asks for administrator rights. CreateProcess refuses that with
    error 740; the shell shows the UAC prompt instead."""

    def setUp(self):
        self.exe = Path(tempfile.mkdtemp()) / "faceitclient.exe"
        self.exe.write_bytes(b"")
        companions.forget_running()

    def test_740_goes_through_the_shell(self):
        refused = OSError("elevation required")
        refused.winerror = 740
        with mock.patch.object(companions, "running", return_value=False), \
             mock.patch.object(companions.subprocess, "Popen", side_effect=refused), \
             mock.patch.object(companions, "_start_elevated", return_value="") as shell:
            result = companions.start({"name": "FACEIT AC", "exe": str(self.exe)})
        self.assertTrue(result["ok"])
        self.assertTrue(result["elevated"])
        shell.assert_called_once()

    def test_other_errors_are_not_retried_elevated(self):
        with mock.patch.object(companions, "running", return_value=False), \
             mock.patch.object(companions.subprocess, "Popen",
                               side_effect=OSError("nope")), \
             mock.patch.object(companions, "_start_elevated") as shell:
            result = companions.start({"name": "x", "exe": str(self.exe)})
        self.assertFalse(result["ok"])
        shell.assert_not_called()


class LaunchWaitsForTheAntiCheat(unittest.TestCase):
    def test_the_wait_is_stretched_for_faceit_ac(self):
        seen = {}

        def fake_monotonic(_calls=[0.0]):
            _calls[0] += 1.0
            return _calls[0]

        up = {"n": 0}

        def pids(_name):
            up["n"] += 1
            # Not there when first checked, up after 30 "seconds": longer
            # than the ordinary companion wait.
            return [7] if up["n"] > 30 else []

        said = []
        # Every readiness sign is faked: the real FACEIT AC on the machine
        # running the tests must not decide the result.
        with mock.patch.object(launcher, "COMPANION_WAIT", 5.0), \
             mock.patch.object(faceit_apps, "_pids", side_effect=pids), \
             mock.patch.object(faceit_apps, "ac_service_running", return_value=True), \
             mock.patch.object(faceit_apps, "_remote_connections", return_value=1), \
             mock.patch.object(faceit_apps, "_visible_windows", return_value=0), \
             mock.patch.object(companions, "running", return_value=False), \
             mock.patch.object(companions, "start",
                               return_value={"ok": True, "already": False,
                                             "elevated": True}), \
             mock.patch.object(launcher.time, "monotonic", side_effect=fake_monotonic), \
             mock.patch.object(launcher.time, "sleep"):
            launcher._bring_up_companions(
                [{"name": "FACEIT AC", "exe": "C:/x/faceitclient.exe",
                  "integration": "faceit-ac"}],
                False, lambda text, tag="": said.append(text))
        self.assertTrue(any("FACEIT AC is up" in t for t in said), said)
        self.assertTrue(any("administrator" in t for t in said), said)
        seen["ok"] = True


class AntiCheatReadiness(unittest.TestCase):
    """Ready is read from FACEIT AC itself, never from a timer (Edy,
    2026-11-17: on a day FACEIT AC updates, any fixed wait is wrong)."""

    def make(self, **state):
        st = {"pids": [11], "service": True, "online": 1, "windows": 0}
        st.update(state)
        r = faceit_apps.AcReadiness(pids=lambda: st["pids"],
                                    service=lambda: st["service"],
                                    online=lambda p: st["online"],
                                    windows=lambda p: st["windows"])
        return r, st

    def test_the_recorded_good_launch(self):
        r, st = self.make(pids=[], service=False, online=0, windows=0)
        r.started_here = True
        steps = [
            dict(pids=[11]),                       # +0.0 faceitclient starts
            dict(service=True),                    # +1.6 service running
            dict(windows=1),                       # +5.1 "FACEIT AC" opens
            dict(windows=0),                       # +7.4 it closes; client not online yet
        ]
        for step in steps:
            st.update(step)
            self.assertFalse(r(), (step, r.last))
        st["online"] = 1                           # +8.8 client online: ready
        self.assertTrue(r())

    def test_busy_titles(self):
        self.assertTrue(faceit_apps._is_busy_title("FACEIT AC"))
        self.assertTrue(faceit_apps._is_busy_title("Updating FACEIT AC..."))
        # Its main window may be waiting for the game: never waited on.
        self.assertFalse(faceit_apps._is_busy_title("FACEIT Anti-cheat"))

    def test_an_update_keeps_it_not_ready_however_long(self):
        r, st = self.make(windows=1)               # updating: window stays up
        r.started_here = True
        for _ in range(1000):
            self.assertFalse(r())
        self.assertIn("updating", r.last)

    def test_not_ready_until_the_client_is_online(self):
        r, st = self.make(online=0)
        self.assertFalse(r())
        self.assertIn("connecting", r.last)

    def test_service_down_is_not_ready(self):
        r, st = self.make(service=False)
        self.assertFalse(r())

    def test_already_up_with_its_window_open_counts_as_ready(self):
        # The player opened FACEIT AC's window themselves; it is connected.
        r, st = self.make(windows=1)
        self.assertTrue(r.up_now())


class LaunchWaitsForAntiCheatReadiness(unittest.TestCase):
    def test_already_open_but_not_ready_is_waited_for(self):
        said = []
        calls = {"n": 0}

        class FakeReady:
            last = ""
            started_here = False

            def __init__(self):
                pass

            def up_now(self):
                return False

            def __call__(self):
                calls["n"] += 1
                return calls["n"] > 3

        with mock.patch.object(faceit_apps, "AcReadiness", FakeReady), \
             mock.patch.object(companions, "running", return_value=True), \
             mock.patch.object(companions, "start") as start, \
             mock.patch.object(launcher.time, "sleep"):
            launcher._bring_up_companions(
                [{"name": "FACEIT AC", "exe": "C:/x/faceitclient.exe",
                  "integration": "faceit-ac"}],
                False, lambda text, tag="": said.append(text))
        start.assert_not_called()
        self.assertTrue(any("waiting for FACEIT AC" in t for t in said), said)
        self.assertTrue(any("FACEIT AC is up" in t for t in said), said)


class AntiCheatHasNoTimeLimit(unittest.TestCase):
    """Edy, 2026-11-17: keep checking FACEIT AC and only start CS2 once it is
    ready. Never 'did not answer in time, starting anyway' for the AC."""

    def run_wait(self, ready_after, stop_after=None):
        said = []
        clock = {"t": 0.0}
        checks = {"n": 0}

        class FakeReady:
            last = "connecting"
            started_here = False

            def up_now(self):
                return False

            def __call__(self):
                checks["n"] += 1
                return ready_after is not None and checks["n"] >= ready_after

        def sleep(seconds):
            clock["t"] += seconds

        stop = (lambda: stop_after is not None and clock["t"] >= stop_after)
        with mock.patch.object(faceit_apps, "AcReadiness", FakeReady), \
             mock.patch.object(companions, "running", return_value=False), \
             mock.patch.object(companions, "start",
                               return_value={"ok": True, "already": False}), \
             mock.patch.object(launcher.time, "monotonic", side_effect=lambda: clock["t"]), \
             mock.patch.object(launcher.time, "sleep", side_effect=sleep):
            launcher._bring_up_companions(
                [{"name": "FACEIT AC", "exe": "C:/x/faceitclient.exe",
                  "integration": "faceit-ac"}],
                False, lambda text, tag="": said.append(text), stop)
        return said, clock["t"]

    def test_waits_past_any_old_limit_until_ready(self):
        # Ready after ~5 minutes of checks: still waited for.
        said, waited = self.run_wait(ready_after=600)
        self.assertGreater(waited, 200)
        self.assertTrue(any("FACEIT AC is up" in t for t in said))
        self.assertFalse(any("starting CS2 anyway" in t for t in said), said)
        self.assertTrue(any("waiting for FACEIT AC: connecting" in t for t in said), said)

    def test_stop_ends_the_wait(self):
        said, waited = self.run_wait(ready_after=None, stop_after=30.0)
        self.assertLess(waited, 31.0)
        self.assertFalse(any("starting CS2 anyway" in t for t in said), said)


if __name__ == "__main__":
    unittest.main()
