"""The Keyboard tab's own key coloring: whether a bound key is still doing
exactly what CS2 ships by default, or something this collection chose on
purpose.

Runs the real _cfg_keys handler (not cfgscan or defaults.py directly), since
it is the handler that cross-references a bound key's resolved command
against the game's own default table and marks the result -- the one place
that comparison actually happens.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cfgscan, defaults, webui  # noqa: E402
from sandbox import redirect_backups, redirect_layouts  # noqa: E402

DEFAULTS_VCFG = '''"config"
{
\t"bindings"
\t{
\t\t"f"\t\t"+lookatweapon"
\t\t"SPACE"\t\t"+jump"
\t}
}
'''

FILES = {
    "mrwhiteer/autoexec.vcfg": 'exec "mrwhiteer/mainsettings/key_binds.vcfg"\n',
    "mrwhiteer/mainsettings/key_binds.vcfg": (
        'bind "f" "+lookatweapon"\n'
        'bind "space" "say hi"\n'
        'bind "q" "lastinv"\n'
    ),
}


class KeysWebCase(unittest.TestCase):
    def setUp(self):
        redirect_backups(self)
        redirect_layouts(self)
        self.sandbox = Path(tempfile.mkdtemp(prefix="cs2cfg-keys-web-"))
        self.addCleanup(shutil.rmtree, self.sandbox, ignore_errors=True)

        self.cfg_root = self.sandbox / "cfg"
        for relative, text in FILES.items():
            path = self.cfg_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.collection = self.cfg_root / "mrwhiteer"

        self.install = self.sandbox / "cs2"
        cfg = self.install / "game" / "csgo" / "cfg"
        cfg.mkdir(parents=True)
        (cfg / defaults.DEFAULTS_FILE).write_text(DEFAULTS_VCFG, encoding="utf-8")

        self.state = mock.Mock()
        self.state.cfg_scan = cfgscan.scan(self.collection, cfg_root=self.cfg_root)
        self.state.cs2_install = self.install

    def keys(self):
        return webui._cfg_keys(self.state, {})


class TestDefaultVsCustom(KeysWebCase):
    def test_a_key_rebound_to_the_same_command_reads_as_default(self):
        bound = self.keys()["bound"]
        self.assertTrue(bound["f"]["is_default"])

    def test_a_key_rebound_to_something_else_reads_as_custom(self):
        bound = self.keys()["bound"]
        self.assertFalse(bound["space"]["is_default"])

    def test_a_key_the_game_has_no_default_for_is_left_unmarked(self):
        """Nothing known either way -- the client falls back to its
        ordinary "bound" color rather than asserting a default that was
        never actually confirmed."""
        bound = self.keys()["bound"]
        self.assertNotIn("is_default", bound["q"])

    def test_with_no_cs2_install_nothing_is_marked(self):
        self.state.cs2_install = None
        bound = self.keys()["bound"]
        for entry in bound.values():
            self.assertNotIn("is_default", entry)


if __name__ == "__main__":
    unittest.main()
