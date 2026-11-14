"""Exercise timed/Ctrl+C cleanup using fake clocks and fake data providers."""

import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg.overlay import probe


class ProbeLifecycle(unittest.TestCase):
    def run_probe(self, *, interrupt=False, no_hud=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        metrics = mock.Mock()
        metrics.game.find.return_value = None
        metrics.sample.return_value = {"overlay_cpu_percent": 0.1, "working_set_mb": 20}
        module = types.ModuleType("cs2cfg.overlay.metrics")
        module.Metrics = mock.Mock(return_value=metrics)
        capture = mock.Mock(process=None, stderr="access denied", session="unique-session")
        capture.status.return_value = "access_denied"
        hud = mock.Mock(visible=True, warning="", error="")
        clock = [0.0]

        def wait(seconds):
            if interrupt:
                raise KeyboardInterrupt
            clock[0] += seconds

        with (mock.patch.dict(sys.modules, {module.__name__: module}),
              mock.patch.dict("os.environ", {"LOCALAPPDATA": temporary.name}),
              mock.patch.object(probe, "PresentMon", return_value=capture),
              mock.patch("cs2cfg.overlay.hud.Hud", return_value=hud),
              mock.patch.object(probe.time, "monotonic", side_effect=lambda: clock[0]),
              mock.patch.object(probe.threading, "Event") as event,
              contextlib.redirect_stdout(io.StringIO()) as output):
            event.return_value.wait.side_effect = wait
            code = probe.run(seconds=2, no_hud=no_hud)
        files = list((Path(temporary.name) / "cs2cfg" / "overlay-probe").glob("*.jsonl"))
        self.assertEqual(len(files), 1)
        self.assertIn(str(files[0]), output.getvalue())
        rows = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
        capture.stop.assert_called_once()
        metrics.close.assert_called_once()
        return code, rows, hud

    def test_seconds_produces_one_line_per_second_and_stops_everything(self):
        code, rows, hud = self.run_probe()
        self.assertEqual(code, 0)
        self.assertEqual([row["elapsed_seconds"] for row in rows], [1, 2])
        self.assertTrue(all(row["fps"] is None for row in rows))
        self.assertTrue(all(row["game_status"] == "not_found" for row in rows))
        self.assertTrue(all(row["presentmon_status"] == "access_denied" for row in rows))
        self.assertIn("cs2.exe not found", rows[0]["status"])
        self.assertIn("access denied", rows[0]["status"])
        hud.stop.assert_called_once()

    def test_ctrl_c_stops_child_and_hud(self):
        code, rows, hud = self.run_probe(interrupt=True)
        self.assertEqual(code, 130)
        self.assertEqual(rows, [])
        hud.stop.assert_called_once()

    def test_no_hud_still_writes_samples(self):
        code, rows, hud = self.run_probe(no_hud=True)
        self.assertEqual(code, 0)
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0]["hud_visible"])
        self.assertEqual(rows[0]["hud_status"], "disabled")
        hud.start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
