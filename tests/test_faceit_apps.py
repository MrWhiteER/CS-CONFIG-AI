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

        def running(_name):
            up["n"] += 1
            # Not running when first checked, up after 30 "seconds": longer
            # than the ordinary companion wait, inside the anti-cheat one.
            return up["n"] > 30

        said = []
        with mock.patch.object(launcher, "COMPANION_WAIT", 5.0), \
             mock.patch.object(companions, "running", side_effect=running), \
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


if __name__ == "__main__":
    unittest.main()
