"""Script Builder: plain-word steps become config lines that cannot get stuck
and never use a combination CS2 refuses."""

from __future__ import annotations

import re
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
        'bind "mouse5" "+voicerecord"\n'
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

    def test_mouse1_keeps_firing_when_config_leaves_it_alone(self):
        built = self.shift("next", "mouse1")
        self.assertTrue(built.ok, self.blocks(built))
        self.assertIn("bind mouse1 +attack", built.lines[0])
        self.assertNotIn("unbind mouse1", "".join(built.lines))

    def test_mouse2_as_shift_key(self):
        body = spec("Alt one", "shift", {"id": "say_team", "text": "alt"}, binding="mouse2")
        body.update(target="scancode30", style="hold")
        built = scriptgen.build(body, self.scan)
        self.assertTrue(built.ok, self.blocks(built))
        self.assertEqual(built.entry, "+alt_one")

    def test_stock_from_the_game_wins(self):
        body = spec("Alt one", "shift", {"id": "say_team", "text": "alt"}, binding="scancode226")
        body.update(target="mouse5", style="next", target_stock="+voicerecord")
        built = scriptgen.build(body, self.scan)
        self.assertIn("bind mouse5 +voicerecord", built.lines[0])

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


class ReleaseAndOwnCase(Base):
    def blocks(self, built):
        return [c.text for c in built.checks if c.level == "block"]

    def test_fire_on_press_knife_on_release(self):
        body = spec("Shoot then knife", "hold", {"id": "cmd:+attack"})
        body["release_steps"] = [{"id": "cmd:slot3"}, {"id": "say_team", "text": "knife"}]
        built = scriptgen.build(body, self.scan)
        self.assertTrue(built.ok, self.blocks(built))
        self.assertEqual(built.lines, [
            'alias "+shoot_then_knife" "+attack"',
            'alias "-shoot_then_knife" "-attack; slot3; say_team knife"'])
        self.assertEqual(built.spec["release_steps"][0]["id"], "cmd:slot3")

    def test_held_let_go_step_refused(self):
        body = spec("x", "hold", {"id": "cmd:slot1"})
        body["release_steps"] = [{"id": "cmd:+duck"}]
        self.assertFalse(scriptgen.build(body, self.scan).ok)

    def shift(self, style, keep=True):
        body = spec("Talk alt", "shift", {"id": "say_team", "text": "alt"}, binding="mouse5")
        body.update(target="scancode30", style=style, keep_own=keep)
        return scriptgen.build(body, self.scan)

    def test_shift_key_keeps_voice_chat_next_press(self):
        built = self.shift("next")
        self.assertTrue(built.ok, self.blocks(built))
        self.assertEqual(built.entry, "+talk_alt")
        self.assertIn('alias "+talk_alt" "+voicerecord; talk_alt_next"', built.lines)
        self.assertIn('alias "-talk_alt" "-voicerecord"', built.lines)
        self.assertTrue(built.target["own"])

    def test_shift_key_keeps_voice_chat_while_held(self):
        built = self.shift("hold")
        self.assertTrue(built.ok, self.blocks(built))
        self.assertIn('alias "+talk_alt" "+voicerecord; bind scancode30 talk_alt_do"', built.lines)
        self.assertIn('alias "-talk_alt" "-voicerecord; bind scancode30 slot1"', built.lines)

    def test_shift_key_own_job_can_be_turned_off(self):
        built = self.shift("next", keep=False)
        self.assertTrue(built.ok, self.blocks(built))
        self.assertEqual(built.entry, "talk_alt")
        self.assertFalse(any("voicerecord" in l for l in built.lines))

    def test_saved_without_asking_when_kept(self):
        state = mock.Mock(); state.cfg_scan = self.scan
        body = spec("Talk alt", "shift", {"id": "say_team", "text": "alt"}, binding="mouse5")
        body.update(target="scancode30", style="next")
        reply = webui._scriptgen_save(state, {"spec": body, "binding": "mouse5"})
        self.assertTrue(reply["ok"], reply)


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

    def test_mouse1_counts_as_taken(self):
        reply = self.save({"spec": spec("Drop it", "press", {"id": "drop_bomb"}),
                           "binding": "mouse1"})
        self.assertTrue(reply.get("needs_confirm"), reply)

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


class LetGoCase(Base):
    """Edy, Nov 22: Mouse 5 (held) changes Mouse 2. Mouse 2 was scoping when
    it got rebound, so CS2 never ran -attack2 and the knife kept stabbing."""

    def built(self, style, steps=({"id": "cmd:slot3"},)):
        body = spec("Insta fire", "shift", *steps, binding="mouse5")
        body.update(target="mouse2", style=style)
        built = scriptgen.build(body, self.scan)
        self.assertTrue(built.ok, [c.text for c in built.checks if c.level == "block"])
        return built

    def test_hold_style_lets_go_of_right_click_before_rebinding(self):
        built = self.built("hold")
        self.assertIn('alias "+insta_fire" "+voicerecord; -attack2; bind mouse2 insta_fire_do"',
                      built.lines)
        self.assertIn('alias "-insta_fire" "-voicerecord; bind mouse2 +attack2"', built.lines)

    def test_next_press_style_lets_go_too(self):
        built = self.built("next")
        arm = [l for l in built.lines if l.startswith('alias "insta_fire_arm"')][0]
        self.assertIn('"-attack2; bind mouse2 insta_fire_do;', arm)

    def test_every_plus_has_its_minus(self):
        for style in ("hold", "next"):
            text = " ".join(self.built(style).lines)
            for word in set(re.findall(r"(?<![\w-])\+(\w+)", text)):
                if word.startswith("insta_fire"):
                    continue
                self.assertIn("-" + word, text, (style, word))

    def test_edited_lines_without_let_go_are_refused(self):
        built = self.built("hold")
        body = spec("Insta fire", "shift", {"id": "cmd:slot3"}, binding="mouse5")
        body.update(target="mouse2", style="hold",
                    lines_text="\n".join(l.replace("-attack2; ", "") for l in built.lines))
        again = scriptgen.build(body, self.scan)
        self.assertFalse(again.ok)
        self.assertTrue(any("-attack2" in c.text for c in again.checks))


class SyncCase(Base):
    """Scripts tab, Keyboard tab and Script Builder agree, and switching a
    script off reaches a running game through the apply-now file."""

    def setUp(self):
        super().setUp()
        self.state = mock.Mock()
        self.state.cfg_scan = self.scan
        self.state.cs2_install = None

    def save_shift(self):
        body = spec("Talk alt", "shift", {"id": "say_team", "text": "alt"}, binding="mouse5")
        body.update(target="scancode30", style="next")
        reply = webui._scriptgen_save(self.state, {"spec": body, "binding": "mouse5"})
        self.assertTrue(reply["ok"], reply)
        return body

    def bind_of(self, key):
        scan = self.state.cfg_scan
        chain = cfgscan.startup_chain(scan)
        winner = cfgscan._effective_bind(scan, chain, key)
        return (winner.body or "").strip('"') if winner else ""

    def saved(self):
        return webui._scriptgen_saved(self.state, {})["scripts"]

    def toggle(self, enable):
        item = self.saved()[0]
        reply = webui._cfg_plugin_toggle(self.state, {"id": item["id"], "enable": enable})
        self.assertTrue(reply.get("changed"), reply)
        return reply

    def test_saving_again_keeps_voice_chat(self):
        body = self.save_shift()
        reply = webui._scriptgen_save(self.state, {"spec": body, "binding": "mouse5"})
        self.assertTrue(reply["ok"], reply)
        text = "".join(p.read_text() for p in (self.cfg_root / "me").rglob("*.vcfg"))
        self.assertIn('alias "+talk_alt" "+voicerecord; talk_alt_next"', text)

    def test_switch_off_gives_key_back_and_empties_names(self):
        from cs2cfg import applynow

        self.save_shift()
        self.assertEqual(self.bind_of("mouse5"), "+talk_alt")
        on_file = applynow.render(self.state.cfg_scan)
        self.assertIn("// Script Builder: talk_alt on", on_file)

        self.toggle(False)
        self.assertEqual(self.bind_of("mouse5"), "+voicerecord")
        item = self.saved()[0]
        self.assertFalse(item["enabled"])
        off_file = applynow.render(self.state.cfg_scan)
        self.assertIn('alias "+talk_alt" ""', off_file)
        self.assertIn('alias "talk_alt_do" ""', off_file)
        self.assertIn('bind "scancode30" "slot1"', off_file)
        self.assertIn('bind "mouse5" "+voicerecord"', off_file)

        # Mid-match: only changes are sent, and the script's lines are among them.
        baseline = applynow._entries(on_file)
        changes = applynow.render_changes(off_file, baseline)
        self.assertIn('alias "+talk_alt" ""', changes)
        self.assertIn('bind "mouse5" "+voicerecord"', changes)

        # Back on, still in the same match: the real lines go out again even
        # though they match what CS2 loaded at the start.
        self.toggle(True)
        self.assertEqual(self.bind_of("mouse5"), "+talk_alt")
        again = applynow.render_changes(applynow.render(self.state.cfg_scan), baseline, changes)
        self.assertIn('alias "+talk_alt" "+voicerecord; talk_alt_next"', again)
        self.assertIn('bind "mouse5" "+talk_alt"', again)

    def test_profile_resave_on_other_keys_shows_new_keys(self):
        from cs2cfg import keys, layouts

        prof = self.cfg_root / "me/lan/training.vcfg"
        prof.parent.mkdir(parents=True, exist_ok=True)
        prof.write_text('bind "mouse5" "+voicerecord"\nbind "mouse4" "player_ping"\n'
                        'bind "scancode30" "slot1"\nbind "scancode31" "slot2"\n', encoding="utf-8")
        alias = self.cfg_root / "me/tools/alias.vcfg"
        alias.write_text(alias.read_text() + 'alias "!train" "exec me/lan/training.vcfg"\n')
        self.state.cfg_scan = cfgscan.scan(self.cfg_root / "me", cfg_root=self.cfg_root)
        self.assertTrue(cfgscan.is_match_profile(self.state.cfg_scan, "me/lan/training.vcfg"))
        layouts.save_current(self.state.cfg_scan.root, "me/lan/training.vcfg")

        def save(key, target):
            body = spec("Insta fire", "shift", {"id": "cmd:slot3"}, binding=key)
            body.update(target=target, style="hold")
            reply = webui._scriptgen_save(self.state, {"spec": body, "binding": key})
            self.assertTrue(reply["ok"], reply)

        save("mouse5", "scancode30")
        save("mouse4", "scancode31")
        card = [c for c in webui._cfg_plugins(self.state, {})["plugins"] if c.get("made")][0]
        self.assertEqual(card["bound_labels"], ["Mouse 4"])
        self.assertEqual(card["made_keys"], "Hold Mouse 4, press " + keys.label("scancode31"))
        self.assertEqual(self.saved()[0]["keys"], ["Mouse 4"])
        live = webui._live_binds(self.state.cfg_scan)
        self.assertEqual(live["mouse5"].body.strip('"'), "+voicerecord")

    def test_scripts_tab_marks_builder_scripts(self):
        self.save_shift()
        cards = webui._cfg_plugins(self.state, {})["plugins"]
        made = [c for c in cards if c.get("made")]
        self.assertEqual([c["made"]["alias"] for c in made], ["talk_alt"])
        self.assertFalse(made[0]["suspect"])

    def test_off_script_without_earlier_job_is_cleared(self):
        reply = webui._scriptgen_save(self.state, {
            "spec": spec("Drop it", "press", {"id": "drop_bomb"}), "binding": "scancode27"})
        self.assertTrue(reply["ok"], reply)
        self.toggle(False)
        self.assertEqual(self.bind_of("scancode27"), "")

    def test_key_changed_on_keyboard_shows_in_builder(self):
        webui._scriptgen_save(self.state, {
            "spec": spec("Drop it", "press", {"id": "drop_bomb"}), "binding": "scancode27"})
        webui._cfg_bind(self.state, {"binding": "scancode27", "unbind": True})
        webui._cfg_bind(self.state, {"binding": "scancode28", "command": "drop_it", "force": True})
        item = self.saved()[0]
        self.assertEqual(item["keys"], [webui_label("scancode28")])

    def test_moving_to_another_key_frees_the_old_one(self):
        webui._scriptgen_save(self.state, {
            "spec": spec("Drop it", "press", {"id": "drop_bomb"}), "binding": "scancode27"})
        reply = webui._scriptgen_save(self.state, {
            "spec": spec("Drop it", "press", {"id": "drop_bomb"}, binding="scancode28"),
            "binding": "scancode28"})
        self.assertTrue(reply["ok"], reply)
        self.assertEqual(self.bind_of("scancode27"), "")
        self.assertEqual(self.bind_of("scancode28"), "drop_it")


class TrashCase(Base):
    """Edy, Nov 22: deleting a script puts it in a Trash for seven days."""

    def setUp(self):
        super().setUp()
        self.state = mock.Mock()
        self.state.cfg_scan = self.scan
        self.state.cs2_install = None
        body = spec("Talk alt", "shift", {"id": "say_team", "text": "alt"}, binding="mouse5")
        body.update(target="scancode30", style="next")
        reply = webui._scriptgen_save(self.state, {"spec": body, "binding": "mouse5"})
        self.assertTrue(reply["ok"], reply)

    def text(self):
        return "".join(p.read_text() for p in sorted((self.cfg_root / "me").rglob("*.vcfg")))

    def bind_of(self, key):
        bind = webui._live_binds(self.state.cfg_scan).get(key)
        return (bind.body or "").strip('"') if bind else ""

    def made_id(self):
        return [c for c in webui._cfg_plugins(self.state, {})["plugins"] if c.get("made")][0]["id"]

    def test_delete_moves_to_trash_and_gives_key_back(self):
        from cs2cfg import applynow

        before_file = (self.cfg_root / "me/settings.vcfg").read_text()
        reply = webui._script_delete(self.state, {"id": self.made_id()})
        self.assertTrue(reply["ok"], reply)
        self.assertNotIn("talk_alt", self.text())
        self.assertEqual(self.bind_of("mouse5"), "+voicerecord")
        trash = webui._script_trash(self.state, {})["items"]
        self.assertEqual([t["name"] for t in trash], ["Talk alt"])
        self.assertEqual(trash[0]["keys"], ["Mouse 5"])
        # Still emptied in a running game by the apply key.
        self.assertIn('alias "+talk_alt" ""', applynow.render(self.state.cfg_scan))

        reply = webui._script_restore(self.state, {"id": trash[0]["id"]})
        self.assertTrue(reply["ok"], reply)
        self.assertEqual(reply["keys"], ["Mouse 5"])
        self.assertEqual(self.bind_of("mouse5"), "+talk_alt")
        self.assertIn('alias "+talk_alt" "+voicerecord; talk_alt_next"', self.text())
        self.assertEqual(webui._script_trash(self.state, {})["items"], [])
        self.assertNotIn('alias "+talk_alt" ""', applynow.render(self.state.cfg_scan))
        self.assertEqual(before_file.strip(), (self.cfg_root / "me/settings.vcfg").read_text().strip())

    def test_gone_for_good_after_seven_days(self):
        import time
        from cs2cfg import scripttrash

        webui._script_delete(self.state, {"id": self.made_id()})
        self.assertEqual(len(scripttrash.items()), 1)
        self.assertEqual(len(scripttrash.items(now=time.time() + 6 * 86400)), 1)
        self.assertEqual(scripttrash.items(now=time.time() + 7 * 86400 + 1), [])
        self.assertEqual(scripttrash.items(), [])      # removed from the store too

    def test_restore_leaves_a_key_given_away_since(self):
        webui._script_delete(self.state, {"id": self.made_id()})
        webui._cfg_bind(self.state, {"binding": "mouse5", "command": "slot5", "force": True})
        item = webui._script_trash(self.state, {})["items"][0]
        reply = webui._script_restore(self.state, {"id": item["id"]})
        self.assertTrue(reply["ok"], reply)
        self.assertEqual(reply["left"], ["Mouse 5"])
        self.assertEqual(self.bind_of("mouse5"), "slot5")

    def test_any_script_can_be_deleted(self):
        card = [c for c in webui._cfg_plugins(self.state, {})["plugins"] if c["name"] == "Jump throw"][0]
        reply = webui._script_delete(self.state, {"id": card["id"]})
        self.assertTrue(reply["ok"], reply)
        self.assertNotIn('alias "+jt"', self.text())


class SharedShiftKeyCase(Base):
    """Edy, Nov 22: Mouse 5 + 1/2/3 = smoke/molly/HE, all on one Mouse 5,
    and Mouse 5 still talks."""

    def setUp(self):
        super().setUp()
        self.state = mock.Mock()
        self.state.cfg_scan = self.scan
        self.state.cs2_install = None
        for name, target in (("Smoke", "scancode30"), ("Molly", "scancode27"), ("Nade", "scancode28")):
            body = spec(name, "shift", {"id": "cmd:slot3"}, binding="mouse5")
            body.update(target=target, style="hold")
            reply = webui._scriptgen_save(self.state, {"spec": body, "binding": "mouse5"})
            self.assertTrue(reply["ok"], reply)

    def aliases(self):
        scan = self.state.cfg_scan
        return {n: scan.effective_alias(n).body for n in ("+smoke", "+molly", "+nade")
                if scan.effective_alias(n) is not None}

    def key(self):
        return webui._live_binds(self.state.cfg_scan)["mouse5"].body.strip('"')

    def card(self, name):
        return [c for c in webui._cfg_plugins(self.state, {})["plugins"] if c["name"] == name][0]["id"]

    def test_one_key_runs_all_and_still_talks(self):
        self.assertEqual(self.key(), "+nade")
        a = self.aliases()
        self.assertTrue(a["+nade"].startswith("+molly;"))
        self.assertTrue(a["+molly"].startswith("+smoke;"))
        self.assertTrue(a["+smoke"].startswith("+voicerecord;"))

    def test_deleting_the_middle_keeps_the_rest(self):
        self.assertTrue(webui._script_delete(self.state, {"id": self.card("Molly")})["ok"])
        self.assertEqual(self.key(), "+nade")
        self.assertTrue(self.aliases()["+nade"].startswith("+smoke;"))

    def test_switching_the_bottom_off_and_on(self):
        webui._cfg_plugin_toggle(self.state, {"id": self.card("Smoke"), "enable": False})
        self.assertEqual(self.key(), "+nade")
        self.assertTrue(self.aliases()["+molly"].startswith("+voicerecord;"))
        webui._cfg_plugin_toggle(self.state, {"id": self.card("Smoke"), "enable": True})
        self.assertEqual(self.key(), "+smoke")
        self.assertTrue(self.aliases()["+smoke"].startswith("+nade;"))

    def test_saving_the_bottom_again_keeps_the_chain(self):
        body = spec("Smoke", "shift", {"id": "cmd:slot4"}, binding="mouse5")
        body.update(target="scancode30", style="hold")
        self.assertTrue(webui._scriptgen_save(self.state, {"spec": body, "binding": "mouse5"})["ok"])
        self.assertEqual(self.key(), "+nade")
        self.assertTrue(self.aliases()["+smoke"].startswith("+voicerecord;"))

    def test_every_script_shows_the_shared_key(self):
        cards = [c for c in webui._cfg_plugins(self.state, {})["plugins"] if c.get("made")]
        self.assertEqual({c["name"]: c["bound_labels"] for c in cards},
                         {"Smoke": ["Mouse 5"], "Molly": ["Mouse 5"], "Nade": ["Mouse 5"]})

    def test_new_script_without_own_job_still_keeps_the_others(self):
        body = spec("Flash", "shift", {"id": "cmd:slot3"}, binding="mouse5")
        body.update(target="scancode29", style="next", keep_own=False)
        self.assertTrue(webui._scriptgen_save(self.state, {"spec": body, "binding": "mouse5"})["ok"])
        self.assertEqual(self.key(), "+flash")
        flash = self.state.cfg_scan.effective_alias("+flash").body
        self.assertTrue(flash.startswith("+nade;"), flash)

    def test_deleting_the_top_gives_the_key_to_the_next(self):
        self.assertTrue(webui._script_delete(self.state, {"id": self.card("Nade")})["ok"])
        self.assertEqual(self.key(), "+molly")


def webui_label(binding):
    from cs2cfg import keys
    return keys.label(binding)


if __name__ == "__main__":
    unittest.main()
