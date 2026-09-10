"""The watcher has to find changes on its own, with nothing pressed.

Everything runs against a temporary folder and a temporary baseline store, so
the real Steam folder is never read and the real baseline is never disturbed.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import gamewatch  # noqa: E402

CONVARS = '''"config"
{
\t"convars"
\t{
\t\t"cl_crosshairsize"\t\t"%s"
\t\t"sensitivity"\t\t"1.15"
\t}
}
'''

KEYS = '"config"\n{\n\t"bindings"\n\t{\n\t\t"q"\t\t"+qsw"\n\t}\n}\n'
VIDEO = '"video.cfg"\n{\n\t"setting.defaultres"\t\t"1550"\n}\n'

ACCOUNT = "test-account"


class WatcherCase(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="cs2cfg-watch-"))
        self.store = Path(tempfile.mkdtemp(prefix="cs2cfg-store-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.store, ignore_errors=True)

        patcher = mock.patch.object(gamewatch, "_store", lambda: self.store)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.write(3)
        (self.folder / "cs2_user_keys_0_slot0.vcfg").write_text(KEYS, encoding="utf-8")
        (self.folder / "cs2_video.txt").write_text(VIDEO, encoding="utf-8")

    def write(self, crosshair):
        (self.folder / "cs2_user_convars_0_slot0.vcfg").write_text(
            CONVARS % crosshair, encoding="utf-8")

    def watcher(self, interval=0.05):
        w = gamewatch.Watcher(self.folder, ACCOUNT, interval=interval)
        self.addCleanup(w.stop)
        return w

    def wait_for(self, predicate, timeout=6.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.05)
        return False


class TestAutoDiscovery(WatcherCase):
    def test_a_change_is_found_without_being_asked(self):
        gamewatch.save_baseline(ACCOUNT, gamewatch.take(self.folder))
        w = self.watcher()
        w.start()

        # Stand in for CS2 saving on exit.
        time.sleep(0.15)
        self.write(2)

        self.assertTrue(self.wait_for(lambda: w.pending is not None),
                        "the watcher never noticed the file changing")
        found = w.pending
        self.assertEqual(found["count"], 1)
        entry = found["sources"]["In-game settings"][0]
        self.assertEqual((entry["was"], entry["now"]), ("3", "2"))

    def test_nothing_is_reported_while_the_files_sit_still(self):
        gamewatch.save_baseline(ACCOUNT, gamewatch.take(self.folder))
        w = self.watcher()
        w.start()
        time.sleep(0.4)
        self.assertIsNone(w.pending)

    def test_a_finding_is_not_reported_twice(self):
        """The baseline moves forward once a session has been accounted for,
        so the next write compares against what was already reported."""
        gamewatch.save_baseline(ACCOUNT, gamewatch.take(self.folder))
        w = self.watcher()
        w.start()
        time.sleep(0.15)
        self.write(2)
        self.assertTrue(self.wait_for(lambda: w.pending is not None))

        w.clear()
        time.sleep(0.3)
        self.assertIsNone(w.pending, "the same change was reported again")

    def test_acknowledging_clears_the_finding(self):
        gamewatch.save_baseline(ACCOUNT, gamewatch.take(self.folder))
        w = self.watcher()
        w.start()
        time.sleep(0.15)
        self.write(2)
        self.assertTrue(self.wait_for(lambda: w.pending is not None))
        w.clear()
        self.assertIsNone(w.pending)
        self.assertEqual(w.summary()["count"], 0)

    def test_the_summary_says_whether_it_is_actually_watching(self):
        w = self.watcher()
        self.assertFalse(w.summary()["watching"])
        w.start()
        self.assertTrue(self.wait_for(lambda: w.summary()["watching"]))
        w.stop()

    def test_a_first_run_records_a_baseline_instead_of_inventing_a_diff(self):
        self.assertIsNone(gamewatch.load_baseline(ACCOUNT))
        w = self.watcher()
        w.start()
        time.sleep(0.15)
        self.write(2)
        self.assertTrue(self.wait_for(
            lambda: gamewatch.load_baseline(ACCOUNT) is not None))
        self.assertIsNone(w.pending, "a first run has nothing to compare against")

    def test_an_unreadable_folder_does_not_kill_the_thread(self):
        """A watcher that dies takes the whole feature with it silently."""
        gamewatch.save_baseline(ACCOUNT, gamewatch.take(self.folder))
        w = self.watcher()
        w.start()
        time.sleep(0.15)
        shutil.rmtree(self.folder, ignore_errors=True)
        time.sleep(0.3)
        self.assertTrue(w.summary()["watching"])


if __name__ == "__main__":
    unittest.main()
