"""The launch handler's crosshair step, against a throwaway game folder.

Exercises _settle_crosshair itself rather than its parts, so the wiring is
covered too: which folder it writes into, what it links, and that it never
takes the launch down with it.
"""

import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg import crosshairx, webui


class Settling(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.install = Path(self.tmp.name) / "Counter-Strike Global Offensive"
        self.cfg = self.install / "game" / "csgo" / "cfg" / "mrwhiteer"
        self.cfg.mkdir(parents=True)
        (self.cfg / "autoexec.vcfg").write_text("// the player's own\n", encoding="utf-8")
        self.state = types.SimpleNamespace(
            steam_root=Path(self.tmp.name) / "Steam",
            cs2_install=self.install,
            cfg_folder="mrwhiteer",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _settle(self, body, installed=True, up=True):
        found = {"installed": True} if installed else None
        with mock.patch.object(crosshairx, "find", return_value=found), \
             mock.patch.object(crosshairx, "running", return_value=up), \
             mock.patch.object(webui.steam, "find_libraries", return_value=[]):
            return webui._settle_crosshair(self.state, body)

    def _written(self):
        return (self.cfg / crosshairx.CFG_NAME).read_text(encoding="utf-8")

    def test_switch_on_writes_the_crosshair_off(self):
        out = self._settle({"hide_crosshair": True})
        self.assertTrue(out["hidden"])
        self.assertFalse(out["error"])
        self.assertIn('crosshair "0"', self._written())

    def test_switch_off_writes_the_crosshair_back_on(self):
        self._settle({"hide_crosshair": True})
        out = self._settle({"hide_crosshair": False})
        self.assertFalse(out["hidden"])
        self.assertIn('crosshair "1"', self._written())
        self.assertNotIn('crosshair "0"', self._written())

    def test_the_overlay_being_down_keeps_the_crosshair(self):
        out = self._settle({"hide_crosshair": True}, up=False)
        self.assertIn('crosshair "1"', self._written())
        self.assertIn("not running", out["warning"])

    def test_starting_the_overlay_this_launch_counts(self):
        out = self._settle({"hide_crosshair": True, "crosshairx_launch": True}, up=False)
        self.assertTrue(out["hidden"])
        self.assertIn('crosshair "0"', self._written())

    def test_it_writes_into_the_configured_folder(self):
        self._settle({"hide_crosshair": True})
        self.assertTrue((self.cfg / crosshairx.CFG_NAME).is_file())

    def test_it_links_the_file_from_the_autoexec(self):
        self._settle({"hide_crosshair": True})
        text = (self.cfg / "autoexec.vcfg").read_text(encoding="utf-8")
        self.assertIn(crosshairx.CFG_NAME, text)
        self.assertIn("// the player's own", text)

    def test_relaunching_does_not_stack_exec_lines(self):
        for _ in range(4):
            self._settle({"hide_crosshair": True})
        text = (self.cfg / "autoexec.vcfg").read_text(encoding="utf-8")
        self.assertEqual(text.count(crosshairx.CFG_NAME), 1)

    def test_it_leaves_the_generated_performance_config_alone(self):
        perf = self.cfg / "autoperf.vcfg"
        perf.write_text("// applied earlier\nfps_max \"0\"\n", encoding="utf-8")
        self._settle({"hide_crosshair": True})
        self.assertEqual(perf.read_text(encoding="utf-8"),
                         "// applied earlier\nfps_max \"0\"\n")

    def test_a_failure_is_reported_and_not_raised(self):
        """A crosshair that could not be written must not stop the game."""
        self.state.cs2_install = None
        out = self._settle({"hide_crosshair": True})
        self.assertTrue(out["error"])

    def test_an_unwritable_folder_does_not_raise(self):
        with mock.patch.object(webui.emit, "write_text_file",
                               side_effect=OSError("read-only")):
            out = self._settle({"hide_crosshair": True})
        self.assertIn("read-only", out["error"])


if __name__ == "__main__":
    unittest.main()
