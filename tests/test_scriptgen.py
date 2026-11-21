"""Script Builder: plain-word steps become config lines that cannot get stuck
and never use a combination CS2 refuses."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cfgscan, plugins, scriptgen, webui  # noqa: E402
from sandbox import redirect_backups, redirect_layouts  # noqa: E402

FILES = {
    "me/autoexec.vcfg": (
        'exec "me/tools/alias.vcfg"\n'
        'exec "me/binds.vcfg"\n'
        'exec "me/settings.vcfg"\n'
    ),
    "me/tools/alias.vcfg": (
        '// --------------------------\n'
        '// Jump throw\n'
        '// --------------------------\n'
        'alias "+jt" "+jump; -attack"\n'
        'alias "-jt" "-jump"\n'
        'alias "hi" "say hi"\n'
    ),
    "me/binds.vcfg": (
        'bind "mouse4" "player_ping"\n'
        'bind "scancode30" "slot1"\n'
        'bind "scancode31" "slot2; say_team pistol"\n'
        'bind "scancode32" "+jump; say hi"\n'
    ),
    "me/settings.vcfg": (
        'sensitivity "1.1"\n'
        'volume "0.8"\n'
    ),
}


def spec(name, mode, *steps, binding="scancode27"):
    return {"name": name, "mode": mode, "steps": list(steps), "binding": binding}


class Base(unittest.TestCase):
    def setUp(self):
        redirect_backups(self)
        redirect_layouts(self)
        self.sandbox = Path(tempfile.mkdtemp(prefix="cs2cfg-scriptgen-"))
        self.addCleanup(shutil.rmtree, self.sandbox, ignore_errors=True)
        self.cfg_root = self.sandbox / "cfg"
        for relative, text in FILES.items():
            path = self.cfg_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.scan = cfgscan.scan(self.cfg_root / "me", cfg_root=self.cfg_root)

    def blocks(self, built):
        return [c.text for c in built.checks if c.level == "block"]


class BuildCase(Base):
    def test_drop_bomb_and_tell_team(self):
        built = scriptgen.build(spec(
            "Drop the bomb and tell my team", "press",
            {"id": "drop_bomb"},
            {"id": "say_team", "text": "Dropping the bomb"},
            {"id": "cmd:lastinv"}), self.scan)
        self.assertTrue(built.ok, self.blocks(built))
        self.assertEqual(built.entry, "drop_the_bomb_and_tell_my_team")
        self.assertEqual(built.lines, [
            'alias "drop_the_bomb_and_tell_my_team" '
            '"use weapon_c4; drop; say_team Dropping the bomb; lastinv"'])

    def test_hold_always_has_matching_release(self):
        built = scriptgen.build(spec(
            "Crouch and talk", "hold",
            {"id": "cmd:+duck"}, {"id": "cmd:+voicerecord"},
            {"id": "volume", "value": 0.2, "back": 1}), self.scan)
        self.assertTrue(built.ok, self.blocks(built))
        self.assertEqual(built.entry, "+crouch_and_talk")
        self.assertEqual(built.lines, [
            'alias "+crouch_and_talk" "+duck; +voicerecord; volume 0.2"',
            'alias "-crouch_and_talk" "-duck; -voicerecord; volume 1"'])

    def test_held_action_on_press_key_is_refused(self):
        # The stuck-crouch bug: +duck with nothing to release it.
        built = scriptgen.build(spec("Crouch", "press", {"id": "cmd:+duck"}), self.scan)
        self.assertFalse(built.ok)
        self.assertTrue(any(c.fix == "mode:hold" for c in built.checks))

    def test_jump_and_crouch_is_blocked_by_valve_rule(self):
        built = scriptgen.build(spec(
            "Jump and crouch", "hold", {"id": "cmd:+jump"}, {"id": "cmd:+duck"}), self.scan)
        self.assertFalse(built.ok)
        self.assertTrue(any(c.fix == "valve" for c in built.checks))

    def test_valve_rule_sees_through_own_scripts(self):
        # +jt already jumps; adding crouch makes two movement actions.
        built = scriptgen.build(spec(
            "Mine", "hold", {"id": "script:+jt"}, {"id": "cmd:+duck"}), self.scan)
        self.assertTrue(any(c.fix == "valve" for c in built.checks))

    def test_one_move_plus_chat_is_fine(self):
        built = scriptgen.build(spec(
            "Jump and shout", "hold", {"id": "cmd:+jump"},
            {"id": "say_team", "text": "jumping"}), self.scan)
        self.assertTrue(built.ok, self.blocks(built))

    def test_toggle_flips_and_undoes(self):
        built = scriptgen.build(spec(
            "Quiet game", "toggle", {"id": "volume", "value": 0.1, "back": 0.8},
            {"id": "echo", "text": "quiet"}), self.scan)
        self.assertTrue(built.ok, self.blocks(built))
        self.assertEqual(built.lines, [
            'alias "quiet_game_on" "volume 0.1; echo quiet; alias quiet_game quiet_game_off"',
            'alias "quiet_game_off" "volume 0.8; alias quiet_game quiet_game_on"',
            'alias "quiet_game" "quiet_game_on"'])

    def test_text_cannot_break_the_line(self):
        built = scriptgen.build(spec(
            "Say it", "press", {"id": "say_team", "text": 'a"b;c//d'}), self.scan)
        self.assertTrue(built.ok)
        self.assertIn("say_team a'b,c/d", built.lines[0])
        self.assertTrue(any(c.level == "warn" for c in built.checks))

    def test_name_clashes(self):
        self.assertFalse(scriptgen.build(spec("hi", "press", {"id": "cmd:slot1"}), self.scan).ok)
        self.assertFalse(scriptgen.build(spec("drop", "press", {"id": "cmd:slot1"}), self.scan).ok)

    def test_needs_back_value_and_range(self):
        built = scriptgen.build(spec("v", "hold", {"id": "volume", "value": 5}), self.scan)
        self.assertFalse(built.ok)

    def test_offers_current_setting_as_back_value(self):
        volume = next(s for s in scriptgen.steps(self.scan) if s["id"] == "volume")
        self.assertEqual(volume["back_default"], 0.8)

    def test_scripts_tab_reads_the_block(self):
        built = scriptgen.build(spec(
            "Drop it", "press", {"id": "drop_bomb"}), self.scan)
        text = scriptgen.write_block("// top\n", "\n", True, built, "X")
        path = self.cfg_root / "me/settings.vcfg"
        path.write_text(path.read_text() + text, encoding="utf-8")
        scan = cfgscan.scan(self.cfg_root / "me", cfg_root=self.cfg_root)
        found = [p for p in plugins.find(scan) if p.name == "Drop it"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].entry, "drop_it")
        self.assertEqual(found[0].key, "X")


class ShiftCase(Base):
    def shift(self, style, target="scancode30", *steps):
        body = spec("Alt one", "shift", *(steps or ({"id": "say_team", "text": "alt"},)),
                    binding="scancode226")
        body.update(target=target, style=style)
        return scriptgen.build(body, self.scan)

    def test_next_press_only_then_back(self):
        built = self.shift("next")
        self.assertTrue(built.ok, self.blocks(built))
        self.assertEqual(built.entry, "alt_one")
        self.assertEqual(built.lines, [
            'alias "alt_one_do" "say_team alt; bind scancode30 slot1; alias alt_one alt_one_arm"',
            'alias "alt_one_arm" "bind scancode30 alt_one_do; alias alt_one alt_one_off"',
            'alias "alt_one_off" "bind scancode30 slot1; alias alt_one alt_one_arm"',
            'alias "alt_one" "alt_one_arm"'])
        self.assertEqual(built.target["normal"], scriptgen.describe("slot1", self.scan))
        self.assertNotEqual(built.target["normal"], "something else")

    def test_while_held(self):
        built = self.shift("hold")
        self.assertTrue(built.ok, self.blocks(built))
        self.assertEqual(built.entry, "+alt_one")
        self.assertEqual(built.lines, [
            'alias "alt_one_do" "say_team alt"',
            'alias "+alt_one" "bind scancode30 alt_one_do"',
            'alias "-alt_one" "bind scancode30 slot1"'])

    def test_multi_command_key_kept_in_alias(self):
        built = self.shift("next", "scancode31")
        self.assertTrue(built.ok, self.blocks(built))
        self.assertEqual(built.lines[0], 'alias "alt_one_normal" "slot2; say_team pistol"')
        self.assertIn("bind scancode31 alt_one_normal", built.lines[1])

    def test_unbound_key_is_unbound_again(self):
        built = self.shift("next", "scancode33")
        self.assertTrue(built.ok, self.blocks(built))
        self.assertIn("unbind scancode33", built.lines[0])

    def test_held_normal_with_extras_refused(self):
        self.assertFalse(self.shift("next", "scancode32").ok)

    def test_held_alt_action_refused(self):
        self.assertFalse(self.shift("next", "scancode30", {"id": "cmd:+duck"}).ok)

    def test_same_key_refused(self):
        self.assertFalse(self.shift("next", "scancode226").ok)


class EditCase(Base):
    def edit(self, mode, text, *steps):
        body = spec("Mine", mode, *(steps or ({"id": "cmd:slot1"},)))
        body["lines_text"] = text
        return scriptgen.build(body, self.scan)

    def blocks(self, built):
        return [c.text for c in built.checks if c.level == "block"]

    def test_explained_in_plain_words(self):
        built = scriptgen.build(spec("Drop it", "press", {"id": "drop_bomb"},
                                     {"id": "say_team", "text": "bomb"}), self.scan)
        rows = built.explained
        self.assertEqual(rows[0]["name"], "drop_it")
        self.assertTrue(rows[0]["role"].startswith("When you press"))
        said = [c["says"] for c in rows[0]["commands"]]
        self.assertEqual(said[0], "Takes out the bomb")
        self.assertEqual(said[2], "Writes \u201cbomb\u201d in team chat")

    def test_good_edit_is_saved_as_written(self):
        built = self.edit("hold", 'alias "+mine" "+duck; say_team down"\nalias "-mine" "-duck"')
        self.assertTrue(built.ok, self.blocks(built))
        self.assertEqual(built.lines, ['alias "+mine" "+duck; say_team down"', 'alias "-mine" "-duck"'])
        self.assertEqual(built.spec["lines"], built.lines)

    def test_edit_that_leaves_crouch_held_is_refused(self):
        built = self.edit("hold", 'alias "+mine" "+duck"\nalias "-mine" "say_team up"')
        self.assertTrue(any("never let go" in t for t in self.blocks(built)))

    def test_edit_missing_release_half(self):
        built = self.edit("hold", 'alias "+mine" "say_team hi"')
        self.assertTrue(any("-mine" in t for t in self.blocks(built)))

    def test_edit_breaking_quotes(self):
        built = self.edit("press", 'alias "mine" "say_team "hi""')
        self.assertTrue(any("Quotes" in t for t in self.blocks(built)))

    def test_edit_cannot_touch_other_names(self):
        built = self.edit("press", 'alias "mine" "slot1"\nalias "hi" "say bye"')
        self.assertTrue(any("start with mine" in t for t in self.blocks(built)))

    def test_edit_double_move(self):
        built = self.edit("hold", 'alias "+mine" "+jump; +duck"\nalias "-mine" "-jump; -duck"')
        self.assertTrue(any("CS2 has only allowed one" in t for t in self.blocks(built)))

    def test_edit_typo_is_a_warning(self):
        built = self.edit("press", 'alias "mine" "slott1"')
        self.assertTrue(built.ok)
        self.assertTrue(any(c.level == "warn" and "slott1" in c.text for c in built.checks))

    def test_edit_bind_line_refused(self):
        built = self.edit("press", 'alias "mine" "slot1"\nbind "x" "mine"')
        self.assertTrue(any("step 4" in t for t in self.blocks(built)))


class SaveCase(Base):
    def setUp(self):
        super().setUp()
        self.state = mock.Mock()
        self.state.cfg_scan = self.scan

    def save(self, body):
        return webui._scriptgen_save(self.state, body)

    def all_text(self):
        return "".join(p.read_text() for p in sorted((self.cfg_root / "me").rglob("*.vcfg")))

    def test_save_writes_and_binds(self):
        reply = self.save({"spec": spec("Drop it", "press", {"id": "drop_bomb"}),
                           "binding": "scancode27"})
        self.assertTrue(reply["ok"], reply)
        text = self.all_text()
        self.assertIn('alias "drop_it" "use weapon_c4; drop"', text)
        self.assertIn('bind "scancode27" "drop_it"', text)

    def test_refused_script_is_never_written(self):
        before = self.all_text()
        reply = self.save({"spec": spec("JC", "hold", {"id": "cmd:+jump"}, {"id": "cmd:+duck"}),
                           "binding": "scancode27"})
        self.assertFalse(reply["ok"])
        self.assertEqual(before, self.all_text())

    def test_taken_key_asks_first(self):
        reply = self.save({"spec": spec("Drop it", "press", {"id": "drop_bomb"}),
                           "binding": "mouse4"})
        self.assertTrue(reply.get("needs_confirm"))
        reply = self.save({"spec": spec("Drop it", "press", {"id": "drop_bomb"}),
                           "binding": "mouse4", "force": True})
        self.assertTrue(reply["ok"], reply)

    def test_saved_list_and_edited_save(self):
        body = spec("Mine", "press", {"id": "cmd:slot1"})
        body["lines_text"] = 'alias "mine" "slot1; say_team switching"'
        reply = self.save({"spec": body, "binding": "scancode27"})
        self.assertTrue(reply["ok"], reply)
        self.assertIn('alias "mine" "slot1; say_team switching"', self.all_text())
        saved = webui._scriptgen_saved(self.state, {})["scripts"]
        self.assertEqual([s["spec"]["name"] for s in saved], ["Mine"])
        self.assertEqual(saved[0]["spec"]["lines"], ['alias "mine" "slot1; say_team switching"'])

    def test_saving_again_replaces_own_script(self):
        self.save({"spec": spec("Drop it", "press", {"id": "drop_bomb"}), "binding": "scancode27"})
        reply = self.save({"spec": spec("Drop it", "press", {"id": "drop_bomb"},
                                        {"id": "say_team", "text": "bomb"}),
                           "binding": "scancode27"})
        self.assertTrue(reply["ok"], reply)
        self.assertTrue(reply["replaced"])
        text = self.all_text()
        self.assertEqual(text.count('alias "drop_it"'), 1)
        self.assertIn("say_team bomb", text)


if __name__ == "__main__":
    unittest.main()
