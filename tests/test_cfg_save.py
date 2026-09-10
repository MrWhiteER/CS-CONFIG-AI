"""Saving an edited config file.

This is the one place in the application that writes to a file the user wrote
by hand, so the things worth pinning are: the line endings survive, the
encoding survives, a backup exists, and a path outside the scan is refused.

Everything runs on copies in a temp directory.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import backup, cfglang, cfgscan, webui  # noqa: E402

CRLF = "\r\n"


class TestRestoreNewlines(unittest.TestCase):
    """The helper the save path leans on."""

    def test_browser_newlines_become_the_files_own(self):
        self.assertEqual(cfglang.restore_newlines("a\nb\n", CRLF), "a\r\nb\r\n")

    def test_a_lf_file_stays_lf(self):
        self.assertEqual(cfglang.restore_newlines("a\r\nb\r\n", "\n"), "a\nb\n")

    def test_mixed_endings_come_out_consistent(self):
        self.assertEqual(cfglang.restore_newlines("a\r\nb\nc\rd", CRLF),
                         "a\r\nb\r\nc\r\nd\r\n")

    def test_a_file_without_a_trailing_newline_keeps_none(self):
        self.assertEqual(cfglang.restore_newlines("a\nb", CRLF, trailing=False),
                         "a\r\nb")

    def test_empty_text_does_not_gain_a_newline(self):
        self.assertEqual(cfglang.restore_newlines("", CRLF, trailing=True), "")


class SaveCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cs2cfg-save-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        # Backups must not land in the real store while testing.
        store = self.tmp / "backups"
        patcher = mock.patch.object(backup, "backups_root", lambda: store)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.cfg_root = self.tmp / "cfg"
        self.collection = self.cfg_root / "mine"
        self.collection.mkdir(parents=True)
        # Deliberately CRLF: that is what a Windows editor produces, and what
        # a careless save would silently convert.
        (self.collection / "autoexec.vcfg").write_bytes(
            ('// header' + CRLF + 'fps_max "400"' + CRLF +
             'alias "!x" "say hi"' + CRLF).encode("utf-8"))

        self.state = mock.Mock()
        self.state.cfg_scan = cfgscan.scan(self.collection, cfg_root=self.cfg_root)

    def save(self, path, text, force=False):
        return webui._cfg_save(self.state, {"path": path, "text": text, "force": force})

    def read(self):
        return (self.collection / "autoexec.vcfg").read_bytes()


class TestSaving(SaveCase):
    def test_a_normal_edit_is_written(self):
        r = self.save("mine/autoexec.vcfg",
                      '// header\nfps_max "500"\nalias "!x" "say hi"\n')
        self.assertTrue(r["written"])
        self.assertIn(b'fps_max "500"', self.read())

    def test_crlf_survives_an_edit_made_in_a_browser(self):
        """The textarea hands back plain newlines. Writing those would change
        every line in the file, not the one that was edited."""
        self.save("mine/autoexec.vcfg",
                  '// header\nfps_max "500"\nalias "!x" "say hi"\n')
        data = self.read()
        self.assertEqual(data.count(b"\r\n"), 3)
        self.assertNotIn(b"\r\r\n", data)
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))

    def test_a_backup_is_taken_before_writing(self):
        r = self.save("mine/autoexec.vcfg", 'fps_max "500"\n')
        self.assertTrue(r["backup"])
        saved = backup.find_set(r["backup"])
        self.assertIsNotNone(saved)
        stored = next(iter(saved.files.values()))
        kept = (saved.path / stored).read_bytes()
        self.assertIn(b'fps_max "400"', kept)

    def test_saving_identical_text_writes_nothing(self):
        before = self.read()
        r = self.save("mine/autoexec.vcfg",
                      '// header\nfps_max "400"\nalias "!x" "say hi"\n')
        self.assertFalse(r["written"])
        self.assertEqual(self.read(), before)

    def test_a_path_outside_the_scan_is_refused(self):
        for attempt in ("../../outside.cfg", "C:/Windows/system.ini",
                        "mine/does-not-exist.vcfg"):
            r = self.save(attempt, "anything")
            self.assertFalse(r["ok"], attempt)
            self.assertIn("not part of the scan", r["error"])

    def test_an_edit_that_breaks_the_syntax_asks_first(self):
        r = self.save("mine/autoexec.vcfg", 'alias "!x" "never closed\n')
        self.assertFalse(r["ok"])
        self.assertTrue(r["needs_confirm"])
        self.assertGreater(r["errors"], 0)
        self.assertIn(b'fps_max "400"', self.read(), "the file was written anyway")

    def test_the_same_edit_goes_through_when_insisted_on(self):
        """It is the user's config; refusing to save half-finished work would
        be worse than telling them what is wrong with it."""
        r = self.save("mine/autoexec.vcfg", 'alias "!x" "never closed\n', force=True)
        self.assertTrue(r["written"])
        self.assertGreater(r["errors"], 0)
        self.assertIn(b"never closed", self.read())

    def test_the_scan_is_refreshed_so_later_reads_see_the_edit(self):
        self.save("mine/autoexec.vcfg", '// header\nfps_max "500"\n')
        found = self.state.cfg_scan.effective_setting("fps_max")
        self.assertIsNotNone(found)
        self.assertEqual(found.value, "500")

    def test_saving_without_a_scan_is_refused(self):
        self.state.cfg_scan = None
        r = self.save("mine/autoexec.vcfg", "x")
        self.assertFalse(r["ok"])
        self.assertIn("scan a configuration folder first", r["error"])


if __name__ == "__main__":
    unittest.main()
