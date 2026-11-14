"""The one-time administrator helper: what it will and will not be asked.

The helper itself is PowerShell and runs only on Windows; these check the
app's half -- what it refuses to send, how it talks to the helper, and that
the old one-off prompt is still used when setup never installed the helper.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import elevated, quickfix  # noqa: E402

CS2 = r"D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\game\bin\win64\cs2.exe"
CFG = r"D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg"
BROKER = Path(elevated.__file__).parent / "helper" / "broker.ps1"


class Refused(unittest.TestCase):
    def bad(self, op, args=None):
        with self.assertRaises(elevated.HelperError):
            elevated.validate(op, args)

    def test_nothing_off_the_list(self):
        for op in ("run", "exec", "cmd", "powershell", "firewall.add", "", "../x"):
            self.bad(op)

    def test_the_lock_only_touches_cs2(self):
        good = [{"name": "Frankfurt", "cidrs": ["155.133.226.0/24"]}]
        self.bad("firewall.lock", {"program": r"C:\Windows\System32\svchost.exe", "regions": good})
        self.bad("firewall.lock", {"program": r"C:\evil\cs2.exe", "regions": good})
        out = elevated.validate("firewall.lock", {"program": CS2, "regions": good, "extra": 1})
        self.assertEqual(out, {"program": CS2, "regions": good})

    def test_addresses_must_be_addresses(self):
        for cidr in ("0.0.0.0/0", "256.1.1.1", "1.2.3.4/33", "1.2.3", "example.com", "1.2.3.4; rm"):
            self.bad("firewall.lock", {"program": CS2,
                                       "regions": [{"name": "X", "cidrs": [cidr]}]})

    def test_region_names_cannot_smuggle_anything(self):
        for name in ("a'; Remove-Item C:\\", "$(calc)", "", "x" * 60):
            self.bad("firewall.lock", {"program": CS2,
                                       "regions": [{"name": name, "cidrs": ["1.2.3.0/24"]}]})

    def test_power_plans_are_guids(self):
        self.bad("power.set", {"guid": "SCHEME_MIN & calc"})
        self.assertEqual(elevated.validate("power.set", {"guid": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"}),
                         {"guid": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"})

    def test_cfg_grant_only_for_a_cs2_cfg_folder(self):
        self.bad("cfg.grant", {"path": r"C:\Windows\System32"})
        self.assertEqual(elevated.validate("cfg.grant", {"path": CFG}), {"path": CFG})


class ListsAgree(unittest.TestCase):
    """The Python list and the broker's own list have to be the same list."""

    def test_same_jobs_and_version(self):
        text = BROKER.read_text(encoding="utf-8")
        jobs = set(re.findall(r"^\s+'([a-z_\.0-9]+)'\s+=\s+\{", text, re.M))
        self.assertEqual(jobs, set(elevated.OPS))
        self.assertIn(f"$Version = {elevated.HELPER_VERSION}", text)

    def test_the_task_runs_without_a_console_window(self):
        # Measured on a real PC: an elevated task running powershell.exe
        # directly flashed a console window on every job.
        text = (BROKER.parent / "install.ps1").read_text(encoding="utf-8")
        action = re.search(r"New-ScheduledTaskAction -Execute (\S+)\s*`\s*-Argument \"([^\n]*)\"", text)
        self.assertIsNotNone(action)
        self.assertEqual(action.group(1), "$conhost")
        self.assertTrue(action.group(2).startswith("--headless "))
        self.assertIn("'conhost.exe'", text)

    def test_the_broker_never_runs_request_text(self):
        text = BROKER.read_text(encoding="utf-8")
        for danger in ("Invoke-Expression", "iex ", "[scriptblock]::Create", "-EncodedCommand"):
            self.assertNotIn(danger, text)


class Talking(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="cs2cfg-helper-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for sub in ("requests", "results"):
            (self.root / sub).mkdir()
        for p in (mock.patch.object(elevated, "data_dir", return_value=self.root),
                  mock.patch.object(elevated, "ready", return_value=True)):
            p.start()
            self.addCleanup(p.stop)

    def _answer_like_the_broker(self):
        """Stand in for the scheduled task: read the request, answer it."""
        def work():
            for _ in range(100):
                found = list((self.root / "requests").glob("*.json"))
                if found:
                    request = json.loads(found[0].read_text(encoding="utf-8"))
                    found[0].unlink()
                    (self.root / "results" / found[0].name).write_text(
                        json.dumps({"ok": True, "echo": request["op"]}), encoding="utf-8")
                    return
                time.sleep(0.02)
        threading.Thread(target=work, daemon=True).start()
        return None

    def test_a_job_goes_in_and_the_answer_comes_back(self):
        with mock.patch.object(elevated, "_start_task", side_effect=self._answer_like_the_broker):
            out = elevated.run("dns.flush", timeout=5)
        self.assertEqual(out, {"ok": True, "echo": "dns.flush"})

    def test_a_task_that_will_not_start_leaves_no_request_behind(self):
        with mock.patch.object(elevated, "_start_task", return_value="access denied"):
            out = elevated.run("dns.flush", timeout=1)
        self.assertFalse(out["ok"])
        self.assertEqual(list((self.root / "requests").iterdir()), [])

    def test_a_refused_request_is_never_written(self):
        with mock.patch.object(elevated, "_start_task") as start:
            out = elevated.run("power.set", {"guid": "nope"})
        self.assertFalse(out["ok"])
        start.assert_not_called()


class NotInstalled(unittest.TestCase):
    def test_says_setup_is_needed(self):
        with mock.patch.object(elevated, "ready", return_value=False):
            self.assertTrue(elevated.run("dns.flush")["needs_setup"])

    def test_fixes_use_the_helper_when_it_is_there(self):
        with mock.patch.object(elevated, "ready", return_value=True), \
             mock.patch.object(elevated, "run", return_value={"ok": True, "detail": "x"}) as run, \
             mock.patch.object(quickfix, "_run_elevated") as prompt:
            self.assertTrue(quickfix._fix_flush_dns()["ok"])
            self.assertTrue(quickfix._fix_restart_audio()["ok"])
        prompt.assert_not_called()
        self.assertEqual([c.args[0] for c in run.call_args_list], ["dns.flush", "audio.restart"])

    def test_and_fall_back_to_the_old_prompt_when_it_is_not(self):
        with mock.patch.object(elevated, "ready", return_value=False), \
             mock.patch.object(quickfix, "_run_elevated", return_value={"ok": True}) as prompt:
            quickfix._fix_flush_dns()
        prompt.assert_called_once()

    def test_installed_version_is_read_from_the_installed_broker(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "broker.ps1").write_text("$Version = 1\n", encoding="utf-8")
        with mock.patch.object(elevated, "program_dir", return_value=root):
            self.assertEqual(elevated.installed_version(), 1)
        with mock.patch.object(elevated, "program_dir", return_value=root / "nope"):
            self.assertEqual(elevated.installed_version(), 0)


class Temps(unittest.TestCase):
    def test_helper_readings_are_turned_into_readings(self):
        from cs2cfg import temps

        payload = {"at": time.time(), "zones": [3231, 9999],
                   "drives": [{"Name": "Samsung SSD 980 PRO 1TB", "Temp": 41}]}
        with mock.patch.object(elevated, "temps_published", return_value=payload):
            found = temps._from_setup_helper()
        self.assertEqual(found[0].celsius, 50.0)
        self.assertEqual(found[1].celsius, 41.0)

    def test_stale_helper_readings_are_ignored(self):
        from cs2cfg import temps

        with mock.patch.object(elevated, "temps_published",
                               return_value={"at": 0, "zones": [3231], "drives": []}):
            self.assertEqual(temps._from_setup_helper(), [])


if __name__ == "__main__":
    unittest.main()
