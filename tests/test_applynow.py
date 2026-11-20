"""The in-game apply key: one config file holding the full current setup,
rewritten after every change, and one key in the autoexec that runs it.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import applynow, cfgscan, emit, webui  # noqa: E402
from sandbox import redirect_backups, redirect_layouts  # noqa: E402

FILES = {
    "mrwhiteer/autoexec.vcfg": (
        'exec "mrwhiteer/tools/alias.vcfg"\n'
        'exec "mrwhiteer/mainsettings/key_binds.vcfg"\n'
        'exec "mrwhiteer/mainsettings/settings.vcfg"\n'
    ),
    "mrwhiteer/tools/alias.vcfg": (
        'alias "!warmup" "exec mrwhiteer/lan/warmup.vcfg"\n'
        'alias "+jt" "+jump; -attack"\n'
    ),
    "mrwhiteer/mainsettings/key_binds.vcfg": (
        'bind "mouse3" "say custom text"\n'
        'bind "mouse4" "player_ping"\n'
        'bind "scancode9" "+lookatweapon"\n'
    ),
    "mrwhiteer/mainsettings/settings.vcfg": (
        'sensitivity "1.1"\n'
        'cl_crosshairsize "2"\n'
        'echo "settings loaded"\n'
        'connect "1.2.3.4"\n'
    ),
    "mrwhiteer/lan/warmup.vcfg": (
        'bind "mouse3" "noclip"\n'
        'bind "mouse4" "bot_place"\n'
    ),
}


class ApplyNowCase(unittest.TestCase):
    def setUp(self):
        redirect_backups(self)
        redirect_layouts(self)
        self.sandbox = Path(tempfile.mkdtemp(prefix="cs2cfg-applynow-"))
        self.addCleanup(shutil.rmtree, self.sandbox, ignore_errors=True)
        self.cfg_root = self.sandbox / "cfg"
        for relative, text in FILES.items():
            path = self.cfg_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.collection = self.cfg_root / "mrwhiteer"
        self.state = mock.Mock()
        self.state.cfg_scan = cfgscan.scan(self.collection, cfg_root=self.cfg_root)
        self.state.cs2_install = None

    @property
    def apply_file(self) -> Path:
        return self.cfg_root / applynow.FILE_NAME

    @property
    def autoexec(self) -> Path:
        return self.cfg_root / "mrwhiteer/autoexec.vcfg"

    def set_key(self, code, force=False):
        return webui._apply_now_key(self.state, {"code": code, "force": force})


class TestRender(ApplyNowCase):
    def test_holds_full_state_of_startup_configs(self):
        text = applynow.render(self.state.cfg_scan)
        self.assertIn('alias "!warmup" "exec mrwhiteer/lan/warmup.vcfg"', text)
        self.assertIn('alias "+jt" "+jump; -attack"', text)
        self.assertIn('bind "mouse3" "say custom text"', text)
        self.assertIn('bind "scancode9" "+lookatweapon"', text)
        self.assertIn('sensitivity "1.1"', text)
        self.assertIn('cl_crosshairsize "2"', text)

    def test_never_copies_commands_that_do_something(self):
        text = applynow.render(self.state.cfg_scan)
        self.assertNotIn("connect", text)
        self.assertNotIn("settings loaded", text)
        self.assertNotIn("exec mrwhiteer/tools", text)

    def test_files_outside_startup_are_left_out(self):
        # warmup.vcfg only loads from a key, not at launch.
        self.assertNotIn('"noclip"', applynow.render(self.state.cfg_scan))

    def test_cleared_keys_are_unbound(self):
        previous = 'bind "mouse5" "+voicerecord"\nbind "mouse3" "x"\n'
        text = applynow.render(self.state.cfg_scan, previous)
        self.assertIn('unbind "mouse5"', text)
        self.assertNotIn('unbind "mouse3"', text)

    def test_skipped_by_the_scanner(self):
        self.apply_file.write_text('bind "mouse3" "stale"\n', encoding="utf-8")
        scan = cfgscan.scan(self.cfg_root, cfg_root=self.cfg_root)
        self.assertNotIn(applynow.FILE_NAME, [c.name for c in scan.files.values()])


class TestKey(ApplyNowCase):
    def test_no_file_until_a_key_is_set(self):
        self.assertIsNone(applynow.refresh(self.state.cfg_scan))
        self.assertFalse(self.apply_file.exists())
        self.assertFalse(webui._apply_now_status(self.state, {})["ready"])

    def test_setting_a_key_binds_it_and_writes_the_file(self):
        r = self.set_key("F8")
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["ready"])
        self.assertEqual(r["key_label"], "F8")
        self.assertIn('bind "scancode65" "exec cs2cfg_apply_now"',
                      self.autoexec.read_text(encoding="utf-8"))
        text = self.apply_file.read_text(encoding="utf-8")
        self.assertIn('bind "scancode65" "exec cs2cfg_apply_now"', text)
        self.assertIn('bind "mouse4" "player_ping"', text)

    def test_bind_is_a_single_exec(self):
        # Valve's Aug 2024 rule: no multi-action binds. Ours runs one exec.
        self.set_key("F8")
        line = [l for l in self.autoexec.read_text(encoding="utf-8").splitlines()
                if "cs2cfg_apply_now" in l][0]
        self.assertEqual(line, 'bind "scancode65" "exec cs2cfg_apply_now"')

    def test_changing_the_key_swaps_it_and_clears_the_old_one(self):
        self.set_key("F8")
        r = self.set_key("F7")
        self.assertEqual(r["key_label"], "F7")
        text = self.autoexec.read_text(encoding="utf-8")
        self.assertEqual(text.count("cs2cfg_apply_now"), 1)
        self.assertIn('bind "scancode64" "exec cs2cfg_apply_now"', text)
        applied = self.apply_file.read_text(encoding="utf-8")
        self.assertIn('unbind "scancode65"', applied)
        self.assertIn('bind "scancode64" "exec cs2cfg_apply_now"', applied)

    def test_a_used_key_needs_confirming(self):
        r = self.set_key("KeyF")
        self.assertFalse(r["ok"])
        self.assertTrue(r["needs_confirm"])
        self.assertIn("+lookatweapon", r["error"])
        self.assertTrue(self.set_key("KeyF", force=True)["ok"])

    def test_revert_removes_the_key_block(self):
        self.set_key("F8")
        self.assertTrue(emit.strip_generated_block(self.autoexec))
        self.assertNotIn("cs2cfg_apply_now", self.autoexec.read_text(encoding="utf-8"))


class TestFollowsChanges(ApplyNowCase):
    def test_profile_switch_lands_in_the_file(self):
        self.set_key("F8")
        r = webui._cfg_layouts_apply(self.state, {"file": "mrwhiteer/lan/warmup.vcfg"})
        self.assertTrue(r["changed"], r)
        self.assertEqual(r["apply_keys"], ["F8"])
        webui._refresh_apply_now(self.state)
        text = self.apply_file.read_text(encoding="utf-8")
        self.assertIn('bind "mouse3" "noclip"', text)
        self.assertIn('bind "mouse4" "bot_place"', text)
        self.assertNotIn("say custom text", text)

    def test_config_writers_trigger_a_refresh(self):
        for handler in (webui._cfg_bind, webui._cfg_layouts_apply,
                        webui._cfg_settings_apply, webui._cfg_plugin_bind,
                        webui._cfg_save, webui._apply, webui._revert):
            self.assertIn(handler, webui._CONFIG_WRITERS)

    def test_refresh_never_raises(self):
        self.state.cfg_scan = mock.Mock(root=self.sandbox / "gone",
                                        cfg_root=self.sandbox / "gone")
        with mock.patch.object(applynow, "refresh", side_effect=RuntimeError):
            webui._refresh_apply_now(self.state)


if __name__ == "__main__":
    unittest.main()


class TestOnlyChangesWhileRunning(ApplyNowCase):
    """While CS2 runs, the key sends only what changed since it started, not
    the whole config: hundreds of commands at once can read as a flood."""

    def setUp(self):
        super().setUp()
        self.set_key("F8")
        # CS2 closed: full setup written, remembered as what launch loads.
        applynow.refresh(self.state.cfg_scan, running=False)

    def commands(self):
        return [l for l in self.apply_file.read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.startswith("//")]

    def test_nothing_changed_sends_only_the_message(self):
        applynow.refresh(self.state.cfg_scan, running=True)
        self.assertEqual(self.commands(),
                         ['echo "CS CONFIG AI: your latest changes are now applied"'])

    def test_a_changed_key_is_the_only_bind_sent(self):
        r = webui._cfg_bind(self.state, {"code": "mouse4", "command": "+jump", "force": True})
        self.assertTrue(r["ok"], r)
        applynow.refresh(self.state.cfg_scan, running=True)
        sent = self.commands()
        self.assertIn('bind "mouse4" "+jump"', sent)
        self.assertEqual(len(sent), 2, sent)

    def test_a_cleared_key_is_unbound(self):
        r = webui._cfg_bind(self.state, {"code": "mouse4", "unbind": True, "force": True})
        self.assertTrue(r["ok"], r)
        applynow.refresh(self.state.cfg_scan, running=True)
        self.assertIn('unbind "mouse4"', self.commands())

    def test_closing_the_game_goes_back_to_the_full_setup(self):
        webui._cfg_bind(self.state, {"code": "mouse4", "command": "+jump", "force": True})
        applynow.refresh(self.state.cfg_scan, running=True)
        applynow.refresh(self.state.cfg_scan, running=False)
        self.assertIn('bind "mouse3" "say custom text"', self.commands())
        # and the next running session compares against the new setup
        applynow.refresh(self.state.cfg_scan, running=True)
        self.assertEqual(len(self.commands()), 1)


class TestAutomaticKey(ApplyNowCase):
    """Every player gets an apply key without picking one (Edy, Nov 20)."""

    def test_f12_is_set_up_when_free(self):
        self.assertEqual(webui._apply_now_auto(self.state), "scancode69")
        self.assertIn('bind "scancode69" "exec cs2cfg_apply_now"',
                      self.autoexec.read_text(encoding="utf-8"))
        self.assertEqual(applynow.current_key(self.state.cfg_scan), "scancode69")

    def test_a_taken_f12_is_left_alone(self):
        binds = self.cfg_root / "mrwhiteer/mainsettings/key_binds.vcfg"
        binds.write_text(binds.read_text(encoding="utf-8") + 'bind "scancode69" "+jump"\n',
                         encoding="utf-8")
        self.state.cfg_scan = cfgscan.scan(self.collection, cfg_root=self.cfg_root)
        self.assertEqual(webui._apply_now_auto(self.state), "scancode68")

    def test_an_old_reload_key_is_replaced(self):
        binds = self.cfg_root / "mrwhiteer/mainsettings/key_binds.vcfg"
        binds.write_text(binds.read_text(encoding="utf-8") + 'bind "scancode69" "!autoexec"\n',
                         encoding="utf-8")
        self.state.cfg_scan = cfgscan.scan(self.collection, cfg_root=self.cfg_root)
        self.assertEqual(webui._apply_now_auto(self.state), "scancode69")

    def test_only_once_so_the_players_choice_stands(self):
        webui._apply_now_auto(self.state)
        self.autoexec.write_text(FILES["mrwhiteer/autoexec.vcfg"], encoding="utf-8")
        self.state.cfg_scan = cfgscan.scan(self.collection, cfg_root=self.cfg_root)
        self.assertIsNone(webui._apply_now_auto(self.state))

    def test_an_existing_key_is_kept(self):
        self.set_key("F8")
        self.assertIsNone(webui._apply_now_auto(self.state))
