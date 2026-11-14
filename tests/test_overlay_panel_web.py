"""Unittest entry points for the dependency-free browser-script harness."""

import shutil
import subprocess
import unittest
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from cs2cfg import webui
from cs2cfg.overlay import panel, regionlock


class PanelHttp(unittest.TestCase):
    def setUp(self):
        self.state = webui.State("mrwhiteer", "autoperf.vcfg")
        self.module = mock.Mock()
        with mock.patch.object(regionlock, "serverlock", self.module):
            self.state.overlay.panel = panel.Panel(self.state.overlay, mock.Mock())
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), webui.make_handler(self.state))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def test_preview_served_by_existing_handler_without_starting_overlay(self):
        for path in ("/overlay-panel.html?preview=1", "/assets/overlay/panel.js", "/assets/overlay/panel.css"):
            with self.subTest(path=path), urllib.request.urlopen(self.base + path) as response:
                self.assertEqual(response.status, 200)
                content = response.read().decode("utf-8")
                self.assertTrue(content)
                if path.endswith("preview=1"):
                    self.assertNotIn("__CS2CFG_TOKEN__", content)
                    self.assertIn(self.state.token, content)
        self.assertIsNone(self.state.overlay._thread)
        self.assertEqual(self.module.mock_calls, [])

    def test_panel_operations_require_existing_server_token(self):
        request = urllib.request.Request(self.base + "/api/overlay/panel", data=b'{"action":"open"}',
                                         headers={"Content-Type":"application/json"})
        with self.assertRaises(urllib.error.HTTPError) as result:
            urllib.request.urlopen(request)
        self.assertEqual(result.exception.code, 403)
        self.assertEqual(self.module.mock_calls, [])

    def test_authenticated_hidden_panel_still_cannot_query_optional_module(self):
        request = urllib.request.Request(self.base + "/api/overlay/panel", data=b'{"action":"open"}',
                                         headers={"Content-Type":"application/json",
                                                  "X-CS2CFG-Token":self.state.token})
        with urllib.request.urlopen(request) as response:
            self.assertIn(b"Panel hidden", response.read())
        self.assertEqual(self.module.mock_calls, [])


@unittest.skipUnless(shutil.which("node"), "optional Node runtime for browser-script checks")
class PanelScript(unittest.TestCase):
    def check_script(self, scenario):
        result = subprocess.run([shutil.which("node"), "tests/overlay_panel_harness.js", scenario],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_preview_has_sample_data_without_requests_or_timers(self):
        self.check_script("preview")

    def test_busy_region_poll_stops_when_idle_and_on_hide(self):
        self.check_script("busy")

    def test_missing_region_module_has_only_coming_soon(self):
        self.check_script("missing")

    def test_profiles_delegate_and_show_apply_key_or_keyboard_hint(self):
        self.check_script("profiles")

    def test_frame_hints_leave_resource_stats_available(self):
        self.check_script("permissions")

    def test_response_after_hide_cannot_render_or_restart_timers(self):
        self.check_script("late")

    def test_document_hidden_suspends_refreshes(self):
        self.check_script("visibility")

    def test_graph_coalesces_range_changes_with_ten_hz_limit(self):
        self.check_script("graph")
