"""Mouse buttons take binds the same way keyboard keys do.

The Keyboard tab names a key by its browser code ("KeyW") and a mouse button
by its CS2 name ("mouse4"). Only the first was understood, so picking any
mouse button showed "no key given" instead of the command picker, and neither
a command nor a script could be put on it.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cfgscan, keys, starter, webui  # noqa: E402
from sandbox import redirect_backups  # noqa: E402


class FromCode(unittest.TestCase):
    def test_keyboard_codes_still_map_to_scancodes(self):
        self.assertEqual(keys.from_code("KeyW"), "scancode26")

    def test_mouse_buttons_and_wheel_map_to_their_cs2_names(self):
        for name in ("mouse1", "mouse2", "mouse3", "mouse4", "mouse5",
                     "mwheelup", "mwheeldown"):
            self.assertEqual(keys.from_code(name), name)
        self.assertEqual(keys.from_code("Mouse4"), "mouse4")

    def test_buttons_cs2_cannot_bind_are_still_refused(self):
        self.assertIsNone(keys.from_code("mouse6"))
        self.assertIsNone(keys.from_code("nonsense"))


class _State:
    def __init__(self, scan):
        self.cfg_scan = scan
        self.cs2_install = None

    def refresh(self):
        pass


class BindingAMouseButton(unittest.TestCase):
    def setUp(self):
        redirect_backups(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cfg = Path(tmp.name) / "cfg"
        cfg.mkdir(parents=True)
        starter.create(cfg, "cs2config")
        self.root = cfg / "cs2config"
        self.state = _State(cfgscan.scan(self.root))

    def test_a_mouse_button_opens_the_command_picker(self):
        result = webui._cfg_key_options(self.state, {"code": "mouse4"})
        self.assertTrue(result["ok"], result.get("error"))
        self.assertTrue(result.get("groups"))

    def test_a_command_can_be_put_on_a_mouse_button(self):
        result = webui._cfg_bind(self.state, {"code": "mouse4", "command": "+jump"})
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(cfgscan.scan(self.root).binds["mouse4"][0].body, "+jump")

    def test_mouse_6_says_why_it_cannot_be_bound(self):
        result = webui._cfg_key_options(self.state, {"code": "mouse6"})
        self.assertFalse(result["ok"])
        self.assertIn("Mouse 6", result["error"])
        self.assertNotIn("no key given", result["error"])


if __name__ == "__main__":
    unittest.main()
