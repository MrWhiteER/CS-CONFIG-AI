"""Every PresentMon launch is gated by the pinned byte hash."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg.overlay import presentmon


class BinaryIntegrity(unittest.TestCase):
    def test_hash_accepts_known_bytes_rejects_modified_and_missing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "renamed.exe"
            exe.write_bytes(b"known release bytes")
            digest = hashlib.sha256(exe.read_bytes()).hexdigest()
            with mock.patch.object(presentmon, "EXECUTABLE_SHA256", digest):
                self.assertTrue(presentmon.verify_executable(exe))
                exe.write_bytes(b"changed bytes")
                self.assertFalse(presentmon.verify_executable(exe))
                self.assertFalse(presentmon.verify_executable(exe.with_name("absent.exe")))

    def test_rejected_binary_never_launches_a_child(self):
        with (mock.patch.object(presentmon, "locate_executable", return_value=Path("unknown.exe")),
              mock.patch.object(presentmon, "verify_executable", return_value=False),
              mock.patch.object(presentmon.subprocess, "Popen") as popen):
            capture = presentmon.PresentMon(presentmon.Aggregator())
            capture.start()
            self.assertEqual(capture.status(True, False), "untrusted")
            capture.stop()
        popen.assert_not_called()

    def test_stop_does_not_execute_a_binary_changed_after_capture_started(self):
        with mock.patch.object(presentmon, "locate_executable", return_value=Path("release.exe")):
            capture = presentmon.PresentMon(presentmon.Aggregator())
        child = mock.Mock()
        capture.process = child
        with (mock.patch.object(presentmon, "verify_executable", return_value=False),
              mock.patch.object(presentmon.subprocess, "run") as run):
            capture.stop()
        run.assert_not_called()
        child.wait.assert_called_once()
        self.assertIsNone(capture.process)

    def test_verified_binary_launches_without_elevation(self):
        with (mock.patch.object(presentmon, "locate_executable", return_value=Path("release.exe")),
              mock.patch.object(presentmon, "verify_executable", return_value=True) as verify,
              mock.patch.object(presentmon.subprocess, "Popen") as popen,
              mock.patch.object(presentmon.threading, "Thread")):
            capture = presentmon.PresentMon(presentmon.Aggregator())
            capture.start()
        verify.assert_called_once_with(Path("release.exe"))
        self.assertEqual(popen.call_args.args[0][0], "release.exe")
        self.assertIn("--process_name", popen.call_args.args[0])

    def test_frozen_binary_uses_bundled_data_location(self):
        with (tempfile.TemporaryDirectory() as folder,
              mock.patch.dict("os.environ", {}, clear=True),
              mock.patch("cs2cfg.paths.is_frozen", return_value=True),
              mock.patch("sys._MEIPASS", folder, create=True)):
            exe = Path(folder) / "tools" / "presentmon" / presentmon.EXECUTABLE_NAME
            exe.parent.mkdir(parents=True)
            exe.touch()
            self.assertEqual(presentmon.locate_executable(), exe)


if __name__ == "__main__":
    unittest.main()
