"""A new profile starts as an empty keyboard, or as CS2's defaults.

Profiles only change the keys they bind, so a blank profile file switched to
left every key on the old binds: it looked like a copy of what was there.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cfgscan, starter, webui  # noqa: E402
from sandbox import redirect_backups  # noqa: E402


class _State:
    def __init__(self, scan, table):
        self.cfg_scan = scan
        self.cs2_install = None
        self._table = table

    def refresh(self):
        pass


class NewProfile(unittest.TestCase):
    def setUp(self):
        redirect_backups(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cfg = Path(tmp.name) / "cfg"
        cfg.mkdir(parents=True)
        starter.create(cfg, "cs2config")
        self.root = cfg / "cs2config"
        self.cfg = cfg
        self.state = _State(cfgscan.scan(self.root), {})
        for key, command in (("scancode26", "+forward"), ("mouse4", "say hi"),
                             ("scancode58", "exec cs2config/lan/warmup")):
            r = webui._cfg_bind(self.state, {"binding": key, "command": command})
            self.assertTrue(r["ok"], r.get("error"))
            self.state.cfg_scan = cfgscan.scan(self.root)
        self.table = {"scancode26": "+forward", "mouse1": "+attack"}
        self._orig = webui._defaults_table
        webui._defaults_table = lambda state: dict(state._table)
        self.addCleanup(setattr, webui, "_defaults_table", self._orig)

    def create(self, start, table=None):
        self.state._table = table or {}
        r = webui._cfg_layouts_create(self.state, {"name": "Fresh", "start": start})
        self.assertTrue(r["ok"], r.get("error"))
        return r["file"], cfgscan.scan(self.root)

    def own(self, scan, file):
        return {k: d.body for k, ds in scan.binds.items() for d in ds if d.file == file}

    def test_empty_profile_clears_every_bound_key(self):
        file, scan = self.create("empty")
        own = self.own(scan, file)
        self.assertEqual(own["scancode26"], "")
        self.assertEqual(own["mouse4"], "")

    def test_a_key_that_execs_a_config_is_kept(self):
        file, scan = self.create("empty")
        self.assertNotIn("scancode58", self.own(scan, file))

    def test_switching_to_an_empty_profile_frees_the_keys(self):
        file, scan = self.create("empty")
        applied, _, texts = cfgscan.apply_profile_overrides(scan, file)
        self.assertIn("mouse4", applied)
        for rel, text in texts.items():
            (self.cfg / rel).write_text(text, encoding="utf-8")
        after = cfgscan.scan(self.root)
        winner = max(after.binds["mouse4"], key=lambda b: b.order)
        self.assertEqual(winner.body, "")

    def test_defaults_profile_uses_cs2_stock_binds(self):
        file, scan = self.create("defaults", self.table)
        own = self.own(scan, file)
        self.assertEqual(own["scancode26"], "+forward")
        self.assertEqual(own["mouse4"], "")
        self.assertEqual(own["mouse1"], "+attack")

    def test_defaults_missing_falls_back_to_empty_with_a_note(self):
        r = webui._cfg_layouts_create(self.state, {"name": "X", "start": "defaults"})
        self.assertTrue(r["ok"])
        self.assertIn("could not be found", r["note"])

    def test_a_cleared_key_can_be_bound_without_a_warning(self):
        file, scan = self.create("empty")
        applied, _, texts = cfgscan.apply_profile_overrides(scan, file)
        for rel, text in texts.items():
            (self.cfg / rel).write_text(text, encoding="utf-8")
        self.state.cfg_scan = cfgscan.scan(self.root)
        r = webui._cfg_bind(self.state, {"binding": "mouse4", "command": "+jump"})
        self.assertTrue(r["ok"], r.get("error"))


if __name__ == "__main__":
    unittest.main()
