"""Notification dock production JS in a deterministic Node DOM/timer harness."""
from pathlib import Path
import os
import shutil
import subprocess
import unittest


class StatusBarWeb(unittest.TestCase):
    def test_notification_lifetimes_and_friendly_errors(self):
        node = shutil.which("node")
        if not node:
            candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "nodejs/node.exe"
            if candidate.is_file():
                node = str(candidate)
        if not node:
            self.skipTest("Node is required for the notification harness")
        result = subprocess.run(
            [node, str(Path(__file__).with_name("status_bar_harness.cjs"))],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
