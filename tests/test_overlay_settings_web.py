"""Unittest wrapper for the optional, dependency-free Settings renderer check."""

import shutil
import subprocess
import unittest
from pathlib import Path


class OverlaySettingsWeb(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "optional Node runtime for browser-script checks")
    def test_settings_states_and_preview_without_requests_or_timers(self):
        result = subprocess.run([shutil.which("node"), "tests/overlay_settings_harness.js"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
