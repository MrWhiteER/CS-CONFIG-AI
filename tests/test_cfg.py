"""Tests for the config scanner, formatter and editor.

Everything runs on fixtures built in a temp directory. No real collection is
read or written, no config is executed, and CS2 and Steam are never touched.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cfgedit, cfgformat, cfglang, cfgscan, layouts  # noqa: E402
from cs2cfg.cfglang import Severity, parse, tokenize_line  # noqa: E402
from sandbox import redirect_layouts  # noqa: E402


class TestTokenising(unittest.TestCase):
    def test_semicolon_inside_quotes_is_not_a_separator(self):
        line = tokenize_line('say "one; two"')
        self.assertEqual(len(line.commands), 1)
        self.assertEqual(line.commands[0].arg_text(0), "one; two")

    def test_comment_marker_inside_quotes_is_not_a_comment(self):
        line = tokenize_line('say "100// not a comment"')
        self.assertIsNone(line.comment)
        self.assertEqual(line.commands[0].arg_text(0), "100// not a comment")

    def test_comment_outside_quotes_is_a_comment(self):
        line = tokenize_line('fps_max "0"   // uncapped')
        self.assertEqual(line.comment, " uncapped")
        self.assertEqual(line.commands[0].arg_text(0), "0")

    def test_semicolon_outside_quotes_separates(self):
        line = tokenize_line("slot3; slot7")
        self.assertEqual([c.name for c in line.commands], ["slot3", "slot7"])

    def test_backslash_is_literal_not_an_escape(self):
        line = tokenize_line('play "buttons\\\\button11"')
        self.assertEqual(line.commands[0].arg_text(0), "buttons\\\\button11")

    def test_unterminated_quote_runs_to_end_of_line_and_is_reported(self):
        line = tokenize_line('alias "+x" "+use; host_timescale 20   // note')
        codes = [i.code for i in line.issues]
        self.assertIn("unterminated-quote", codes)
        # The engine swallows the rest, comment included. Reproduced faithfully.
        self.assertIn("// note", line.commands[0].arg_text(1))

    def test_unicode_survives_tokenising(self):
        text = 'say "☼ GG Everyone! ღ 𝔾𝕆𝕆𝔻"'
        line = tokenize_line(text)
        self.assertEqual(line.commands[0].arg_text(0), "☼ GG Everyone! ღ 𝔾𝕆𝕆𝔻")

    def test_empty_quoted_argument_is_preserved(self):
        line = tokenize_line('say ""')
        self.assertEqual(line.commands[0].arg_text(0), "")
        self.assertTrue(line.commands[0].arg(0).quoted)

    def test_signature_ignores_quoting_and_spacing(self):
        a = parse('bind "x"    "+jump"').signature()
        b = parse("bind x +jump").signature()
        self.assertEqual(a, b)


class TestClassification(unittest.TestCase):
    def test_comment_braces_do_not_make_it_keyvalues(self):
        """Regression: '// JUMP {BUTTON - SPACE}' is a comment, not structure.

        Counting braces in raw text classified a whole binds file as KeyValues
        and skipped it silently.
        """
        text = "\n".join(
            f'bind "key{i}" "+jump"   // JUMP {{BUTTON - SPACE}}' for i in range(30)
        )
        self.assertTrue(cfglang.looks_like_commands(text))

    def test_real_keyvalues_is_detected(self):
        text = '"video.cfg"\n{\n\t"setting.fullscreen"\t\t"1"\n}\n'
        self.assertFalse(cfglang.looks_like_commands(text))

    def test_exec_path_normalisation_keeps_extension(self):
        self.assertEqual(cfglang.normalise_exec_path("A\\B\\C.VCFG"), "a/b/c.vcfg")
        self.assertNotEqual(
            cfglang.normalise_exec_path("x/y.cfg"), cfglang.normalise_exec_path("x/y.vcfg")
        )

    def test_leading_dot_in_a_path_is_not_eaten(self):
        # lstrip('./') would strip characters, not a prefix.
        self.assertEqual(cfglang.normalise_exec_path(".hidden/a.cfg"), ".hidden/a.cfg")
        self.assertEqual(cfglang.normalise_exec_path("./a.cfg"), "a.cfg")


class FixtureCase(unittest.TestCase):
    """Builds a small collection mirroring the reference structure."""

    FILES = {
        "mrwhiteer/autoexec.vcfg": (
            "// =============================================\n"
            "// ENTRY - autoexec.vcfg\n"
            "// =============================================\n"
            "unbindall\n"
            'exec "mrwhiteer/tools/alias.vcfg"\n'
            'exec "mrwhiteer/tools/scripts.vcfg"\n'
            'exec "mrwhiteer/mainsettings/gamesettings.vcfg"\n'
            'exec "mrwhiteer/autoperf.vcfg"\n'
        ),
        "mrwhiteer/tools/alias.vcfg": (
            "// --------------------------\n"
            "// GENERAL\n"
            "// --------------------------\n"
            'alias "!dc"  "disconnect"           // Exit server\n'
            'alias "!5v5" "exec mrwhiteer/lan/lan.vcfg"\n'
            'alias "!gg"  "say ☼ GG Everyone! ღ"  // custom text\n'
        ),
        "mrwhiteer/tools/scripts.vcfg": (
            'alias "!afk_on"  "+forward; alias !afk !afk_ff"\n'
            'alias "!afk_off" "-forward; alias !afk !afk_on"\n'
            'alias "!afk"     "!afk_on"\n'
            'alias "+qsw" "slot3"\n'
            'alias "-qsw" "lastinv"\n'
            'alias "!wallhack_on"  "r_drawworld 0; alias !wallhack !wallhack_off"\n'
            'alias "!wallhack_off" "r_drawworld 1; alias !wallhack !wallhack_on"\n'
            'alias "!wallhack" "!wallhack_on"\n'
            'alias "!mic_on"  "toggle voice_loopback; alias !voicechat !voicechat_on"\n'
            'alias "1GM" "!5v5; alias GM 2GM"\n'
            'alias "2GM" "!warmup; alias GM 1GM"\n'
            'alias "GM" "1GM"\n'
            "ECHO \"---Script---!wallhack ready. Press (\\)\"\n"
        ),
        "mrwhiteer/mainsettings/gamesettings.vcfg": (
            'fps_max_ui "0"        // menus\n'
            'bind "scancode74" "!wallhack"     // WALLHACK {BUTTON - \\}\n'
            'bind "scancode20" "+qsw"          // QUICK SWITCH {BUTTON - Q}\n'
            'bind "scancode58" "autobuy"       // {BUTTON - F1}\n'
            'bind "scancode58" "autobuy"       // {BUTTON - F1}\n'
        ),
        "mrwhiteer/autoperf.vcfg": (
            "// GENERATED BY cs2-autoconfig -- DO NOT EDIT BY HAND\n"
            'fps_max_ui "300"      // menus\n'
        ),
        "mrwhiteer/lan/lan.vcfg": 'sv_cheats 0\nmp_maxmoney 16000\n',
        "mrwhiteer/lan/warmup.vcfg": (
            "sv_cheats 1\n"
            "mp_maxmoney 60000\n"
            "sv_infinite_ammo 1\n"
            'bind "mouse3" "noclip"\n'
            'alias "+invsmoke" "+use; host_timescale 20   // broken\n'
        ),
    }

    def setUp(self):
        self.sandbox = Path(tempfile.mkdtemp(prefix="cs2cfg-test-"))
        self.cfg_root = self.sandbox / "cfg"
        for relative, text in self.FILES.items():
            path = self.cfg_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.collection = self.cfg_root / "mrwhiteer"
        self.result = cfgscan.scan(self.collection, cfg_root=self.cfg_root)

    def tearDown(self):
        shutil.rmtree(self.sandbox, ignore_errors=True)

    def codes(self):
        return [i.code for i in self.result.issues]


class TestScanning(FixtureCase):
    def test_entry_point_is_the_autoexec(self):
        self.assertEqual(self.result.entry_points[0], "mrwhiteer/autoexec.vcfg")

    def test_exec_chain_follows_declared_order(self):
        order = [f for f, _ in self.result.exec_chain]
        self.assertEqual(order[0], "mrwhiteer/autoexec.vcfg")
        self.assertLess(order.index("mrwhiteer/tools/alias.vcfg"),
                        order.index("mrwhiteer/tools/scripts.vcfg"))
        self.assertLess(order.index("mrwhiteer/mainsettings/gamesettings.vcfg"),
                        order.index("mrwhiteer/autoperf.vcfg"))

    def test_exec_resolves_from_cfg_root_not_the_containing_file(self):
        """'mrwhiteer/lan/lan.vcfg' inside tools/ still resolves."""
        self.assertNotIn("missing-exec-target", self.codes())

    def test_aliases_and_binds_are_collected(self):
        self.assertIn("!wallhack", self.result.aliases)
        self.assertIn("scancode74", self.result.binds)

    def test_deferred_body_is_not_treated_as_immediate(self):
        """'r_drawworld 0' lives inside an alias, so it is not a setting."""
        self.assertIsNone(self.result.effective_setting("r_drawworld"))

    def test_last_definition_wins(self):
        winner = self.result.effective_setting("fps_max_ui")
        self.assertEqual(winner.value, "300")
        self.assertEqual(winner.file, "mrwhiteer/autoperf.vcfg")

    def test_cross_file_override_is_reported(self):
        names = [name for name, _ in self.result.overridden_settings()]
        self.assertIn("fps_max_ui", names)
        self.assertIn("sv_cheats", names)

    def test_duplicate_identical_bind_is_reported(self):
        keys = [k for k, _ in self.result.duplicate_binds()]
        self.assertIn("scancode58", keys)

    def test_nested_alias_typo_is_caught(self):
        """'alias !afk !afk_ff' names a target that does not exist."""
        messages = [i.message for i in self.result.issues]
        self.assertTrue(any("!afk_ff" in m for m in messages), messages)

    def test_state_alias_redefining_something_else_is_flagged(self):
        hits = [i for i in self.result.issues if i.code == "state-redefines-other"]
        self.assertTrue(any("!mic_on" in i.message for i in hits), self.codes())

    def test_stateful_cycle_is_not_called_recursion(self):
        """GM -> 1GM -> redefines GM is a toggle, not infinite recursion."""
        recursion = [i for i in self.result.issues if i.code == "alias-recursion"]
        self.assertFalse(any("GM" in i.message for i in recursion),
                         [i.message for i in recursion])

    def test_wallhack_toggle_is_not_called_recursion(self):
        recursion = [i.message for i in self.result.issues if i.code == "alias-recursion"]
        self.assertFalse(any("wallhack" in m for m in recursion), recursion)

    def test_engine_plus_commands_are_not_unresolved(self):
        unresolved = [i.message for i in self.result.issues
                      if i.code == "unresolved-custom-reference"]
        self.assertFalse(any("+forward" in m for m in unresolved), unresolved)

    def test_unknown_command_is_a_note_not_an_error(self):
        notes = [i for i in self.result.issues if i.code == "unverified-command"]
        for issue in notes:
            self.assertEqual(issue.severity, Severity.INFO)

    def test_generated_file_provenance_is_recorded(self):
        config = self.result.files["mrwhiteer/autoperf.vcfg"]
        self.assertIsNotNone(config.generated_by)
        self.assertEqual(config.role, "generated")

    def test_malformed_quote_is_reported_with_a_location(self):
        errors = [i for i in self.result.issues if i.code == "unterminated-quote"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].file, "mrwhiteer/lan/warmup.vcfg")
        self.assertEqual(errors[0].line, 5)

    def test_profile_switch_reports_what_is_not_restored(self):
        delta = cfgscan.compare_profiles(
            self.result, "mrwhiteer/lan/warmup.vcfg", "mrwhiteer/lan/lan.vcfg"
        )
        names = [n for n, _ in delta.unrestored_settings]
        self.assertIn("sv_infinite_ammo", names)
        self.assertNotIn("sv_cheats", names)      # lan does set this one back
        self.assertTrue(delta.unrestored_binds)


class TestFormatting(FixtureCase):
    def _text(self, relative):
        return (self.cfg_root / relative).read_text(encoding="utf-8")

    def test_formatting_preserves_the_token_sequence(self):
        for relative in self.FILES:
            text = self._text(relative)
            outcome = cfgformat.polish(text, relative)
            if not outcome.safe:
                continue
            self.assertEqual(
                parse(text, relative).signature(),
                parse(outcome.formatted, relative).signature(),
                f"{relative} changed what it executes",
            )

    def test_formatting_is_idempotent(self):
        for relative in self.FILES:
            self.assertTrue(
                cfgformat.is_idempotent(self._text(relative), relative), relative
            )

    def test_malformed_file_is_skipped_and_left_alone(self):
        relative = "mrwhiteer/lan/warmup.vcfg"
        text = self._text(relative)
        outcome = cfgformat.polish(text, relative)
        self.assertFalse(outcome.safe)
        self.assertEqual(outcome.formatted, text)
        self.assertIn("unterminated quote", outcome.skipped_reason)

    def test_unicode_and_quoted_content_survive(self):
        relative = "mrwhiteer/tools/alias.vcfg"
        outcome = cfgformat.polish(self._text(relative), relative)
        self.assertTrue(outcome.safe)
        self.assertIn("☼ GG Everyone! ღ", outcome.formatted)

    def test_trailing_whitespace_inside_quotes_is_kept(self):
        text = 'say "hello   "   \n'
        outcome = cfgformat.polish(text, "x.cfg")
        self.assertTrue(outcome.safe)
        self.assertIn('"hello   "', outcome.formatted)
        self.assertFalse(outcome.formatted.rstrip("\n").endswith(" "))

    def test_commands_are_never_reordered(self):
        text = 'zzz_last "1"\naaa_first "2"\n'
        outcome = cfgformat.polish(text, "x.cfg")
        self.assertLess(outcome.formatted.index("zzz_last"), outcome.formatted.index("aaa_first"))

    def test_duplicates_are_not_removed(self):
        text = 'bind "k" "a"\nbind "k" "a"\n'
        outcome = cfgformat.polish(text, "x.cfg")
        self.assertEqual(outcome.formatted.count('bind "k" "a"'), 2)

    def test_generated_header_is_preserved(self):
        relative = "mrwhiteer/autoperf.vcfg"
        outcome = cfgformat.polish(self._text(relative), relative)
        self.assertIn("GENERATED BY cs2-autoconfig", outcome.formatted)

    def test_semicolon_inside_a_message_is_not_split(self):
        text = 'say "one; two"   // note\n'
        outcome = cfgformat.polish(text, "x.cfg")
        self.assertTrue(outcome.safe)
        self.assertEqual(parse(outcome.formatted).signature(), parse(text).signature())


class TestRenaming(FixtureCase):
    def test_rename_updates_definition_call_and_bind(self):
        plan = cfgedit.plan_rename(self.result, "!wallhack", "!xray")
        files = plan.files_touched()
        self.assertIn("mrwhiteer/tools/scripts.vcfg", files)
        self.assertIn("mrwhiteer/mainsettings/gamesettings.vcfg", files)

    def test_rename_carries_the_on_off_family(self):
        plan = cfgedit.plan_rename(self.result, "!wallhack", "!xray")
        moved = dict(plan.family)
        self.assertEqual(moved.get("!wallhack_on"), "!xray_on")
        self.assertEqual(moved.get("!wallhack_off"), "!xray_off")

    def test_rename_carries_the_press_release_pair(self):
        plan = cfgedit.plan_rename(self.result, "+qsw", "+swap")
        self.assertEqual(dict(plan.family).get("-qsw"), "-swap")

    def test_rename_does_not_change_behaviour(self):
        plan = cfgedit.plan_rename(self.result, "!wallhack", "!xray")
        updates = cfgedit.apply_edits(self.result, plan.edits)
        for relative, text in updates.items():
            self.assertIn("r_drawworld", text) if "scripts" in relative else None
        scripts = updates["mrwhiteer/tools/scripts.vcfg"]
        self.assertIn("r_drawworld 0", scripts)
        self.assertIn("r_drawworld 1", scripts)

    def test_rename_is_surgical_not_a_text_replace(self):
        """'!afk' must not corrupt '!afk_on' when the family is excluded."""
        plan = cfgedit.plan_rename(self.result, "!afk", "!idle", include_family=False)
        updates = cfgedit.apply_edits(self.result, plan.edits)
        scripts = updates["mrwhiteer/tools/scripts.vcfg"]
        self.assertIn('alias "!afk_on"', scripts)
        self.assertIn('alias "!afk_off"', scripts)
        self.assertIn('alias "!idle"', scripts)

    def test_rename_changes_only_the_identifier(self):
        """The code is a pure identifier swap; nothing else in it moves."""
        plan = cfgedit.plan_rename(self.result, "!wallhack", "!xray")
        checked = 0
        for edit in plan.edits:
            before_code = edit.before.split("//")[0]
            after_code = edit.after.split("//")[0]
            self.assertEqual(
                after_code.rstrip(), before_code.rstrip().replace("!wallhack", "!xray"),
                edit.before,
            )
            checked += 1
        self.assertGreater(checked, 0)

    def test_rename_holds_the_comment_at_its_original_column(self):
        """A shorter name must not drag the aligned comment left."""
        plan = cfgedit.plan_rename(self.result, "!wallhack", "!xray")
        commented = [e for e in plan.edits if "//" in e.before]
        self.assertTrue(commented)
        for edit in commented:
            self.assertEqual(edit.after.index("//"), edit.before.index("//"), edit.before)
            # And the comment text itself is untouched.
            self.assertEqual(edit.after.split("//", 1)[1], edit.before.split("//", 1)[1])

    def test_wording_is_separate_and_not_selected_by_default(self):
        plan = cfgedit.plan_rename(self.result, "!wallhack", "!xray")
        self.assertTrue(plan.wording_edits)
        self.assertTrue(all(not e.selected for e in plan.wording_edits))
        # The ECHO text is not touched by the code edits.
        for edit in plan.edits:
            self.assertNotIn("---Script---", edit.after)

    def test_collision_is_blocking(self):
        plan = cfgedit.plan_rename(self.result, "!afk", "!wallhack", include_family=False)
        self.assertTrue(any(i.severity == Severity.ERROR for i in plan.issues))

    def test_illegal_name_is_rejected(self):
        for bad in ("has space", 'has"quote', "has;semicolon"):
            with self.assertRaises(cfgedit.EditError):
                cfgedit.plan_rename(self.result, "!afk", bad)

    def test_rename_is_not_blocked_by_what_a_name_says(self):
        """A name is a label. It does not gate the operation."""
        plan = cfgedit.plan_rename(self.result, "!wallhack", "!my_view_toggle")
        self.assertTrue(plan.edits)
        self.assertFalse(any(i.severity == Severity.ERROR for i in plan.issues))

    def test_apply_refuses_if_the_file_moved_since_the_scan(self):
        plan = cfgedit.plan_rename(self.result, "!wallhack", "!xray")
        target = self.cfg_root / "mrwhiteer/tools/scripts.vcfg"
        target.write_text("// changed underneath\n", encoding="utf-8")
        with self.assertRaises(cfgedit.EditError):
            cfgedit.apply_edits(self.result, plan.edits)


class TestBehaviourEditing(FixtureCase):
    def test_added_and_removed_commands_are_described(self):
        change = cfgedit.plan_behaviour_change(
            self.result, "+qsw", "slot3; cl_showfps 1"
        )
        self.assertIn("cl_showfps 1", change.added)
        self.assertEqual(change.removed, [])
        self.assertTrue(any("Will now run" in line for line in change.explain()))

    def test_reordering_is_recognised_as_such(self):
        change = cfgedit.plan_behaviour_change(
            self.result, "!wallhack_on", "alias !wallhack !wallhack_off; r_drawworld 0"
        )
        self.assertTrue(any("different order" in line for line in change.explain()))

    def test_unbalanced_quotes_are_rejected(self):
        change = cfgedit.plan_behaviour_change(self.result, "+qsw", 'say "oops')
        self.assertFalse(change.valid)

    def test_breaking_a_toggle_is_flagged(self):
        change = cfgedit.plan_behaviour_change(self.result, "!wallhack_on", "r_drawworld 0")
        codes = [i.code for i in change.issues]
        self.assertIn("toggle-broken", codes)

    def test_missing_press_release_partner_is_flagged(self):
        change = cfgedit.plan_behaviour_change(self.result, "+invsmoke", "+use")
        codes = [i.code for i in change.issues]
        self.assertIn("missing-partner", codes)

    def test_unknown_reference_is_a_warning_not_a_rejection(self):
        change = cfgedit.plan_behaviour_change(self.result, "+qsw", "totally_made_up_thing")
        self.assertTrue(change.valid)
        self.assertIn("unknown-reference", [i.code for i in change.issues])

    def test_editing_an_unknown_alias_raises(self):
        with self.assertRaises(cfgedit.EditError):
            cfgedit.plan_behaviour_change(self.result, "!not_here", "slot1")


class TestLineEndings(unittest.TestCase):
    """CRLF files must survive a round trip.

    Regression: writers used Path.write_text, which opens in text mode with
    newline=None and rewrites every '\\n' to os.linesep. Text already holding
    '\\r\\n' came out as '\\r\\r\\n', doubling every line ending. Every real
    config written by a Windows editor is CRLF, so this corrupted all of them.
    """

    def setUp(self):
        self.sandbox = Path(tempfile.mkdtemp(prefix="cs2cfg-crlf-"))

    def tearDown(self):
        shutil.rmtree(self.sandbox, ignore_errors=True)

    def test_write_config_text_does_not_translate(self):
        target = self.sandbox / "crlf.vcfg"
        cfglang.write_config_text(target, 'volume "1"\r\nfps_max "0"\r\n')
        self.assertEqual(target.read_bytes(), b'volume "1"\r\nfps_max "0"\r\n')
        self.assertNotIn(b"\r\r\n", target.read_bytes())

    def test_lf_stays_lf(self):
        target = self.sandbox / "lf.vcfg"
        cfglang.write_config_text(target, 'volume "1"\nfps_max "0"\n')
        self.assertEqual(target.read_bytes(), b'volume "1"\nfps_max "0"\n')

    def test_setting_write_preserves_crlf(self):
        root = self.sandbox / "cfg"
        collection = root / "coll"
        collection.mkdir(parents=True)
        source = 'volume "1"       // master\r\nfps_max "0"      // cap\r\n'
        (collection / "a.vcfg").write_bytes(source.encode("utf-8"))

        result = cfgscan.scan(collection, cfg_root=root)
        self.assertEqual(result.files["coll/a.vcfg"].document.newline, "\r\n")

        _, text = cfgscan.write_setting(result, "volume", "0.5")
        cfglang.write_config_text(collection / "a.vcfg", text)

        data = (collection / "a.vcfg").read_bytes()
        self.assertNotIn(b"\r\r\n", data)
        self.assertEqual(data.count(b"\r\n"), 2)
        self.assertIn(b'volume "0.5"', data)

    def test_polish_preserves_crlf(self):
        source = '// =====\r\nvolume    "1"    // master\r\n'
        outcome = cfgformat.polish(source, "a.vcfg")
        self.assertTrue(outcome.safe)
        self.assertNotIn("\r\r\n", outcome.formatted)
        self.assertIn("\r\n", outcome.formatted)

    def test_rename_preserves_crlf(self):
        root = self.sandbox / "cfg"
        collection = root / "coll"
        collection.mkdir(parents=True)
        (collection / "a.vcfg").write_bytes(
            b'alias "!x" "slot1"\r\nbind "k" "!x"\r\n'
        )
        result = cfgscan.scan(collection, cfg_root=root)
        plan = cfgedit.plan_rename(result, "!x", "!y")
        updates = cfgedit.apply_edits(result, plan.edits)
        cfglang.write_config_text(collection / "a.vcfg", updates["coll/a.vcfg"])

        data = (collection / "a.vcfg").read_bytes()
        self.assertNotIn(b"\r\r\n", data)
        self.assertIn(b'alias "!y"', data)
        self.assertEqual(data.count(b"\r\n"), 2)


class TestSettingControls(FixtureCase):
    """Controls derived from a scan."""

    def test_only_known_settings_get_controls(self):
        views, _ = cfgscan.settings_view(self.result)
        names = {v.name.lower() for v in views}
        self.assertIn("fps_max_ui", names)
        self.assertNotIn("sv_infinite_ammo", names)   # no spec, so no control

    def test_a_slider_only_where_the_engine_clamps(self):
        views, _ = cfgscan.settings_view(self.result)
        for view in views:
            if view.control == "slider":
                self.assertEqual(view.spec.get("range_source"), "clamp", view.name)
                self.assertIn("min", view.spec)
                self.assertIn("max", view.spec)

    def test_unbounded_settings_never_get_a_slider(self):
        views, _ = cfgscan.settings_view(self.result)
        for view in views:
            if view.spec.get("range_source") == "convention":
                self.assertNotEqual(view.control, "slider", view.name)

    def test_override_is_reported_with_every_source(self):
        views, _ = cfgscan.settings_view(self.result)
        fps = next(v for v in views if v.name.lower() == "fps_max_ui")
        self.assertTrue(fps.overridden)
        self.assertEqual(len(fps.sources), 2)
        self.assertEqual(fps.value, "300")
        self.assertTrue(any(s["wins"] for s in fps.sources))

    def test_effective_value_comes_from_the_startup_chain(self):
        views, _ = cfgscan.settings_view(self.result)
        fps = next(v for v in views if v.name.lower() == "fps_max_ui")
        self.assertEqual(fps.file, "mrwhiteer/autoperf.vcfg")

    def test_profile_only_settings_are_flagged_not_guessed(self):
        views, _ = cfgscan.settings_view(self.result)
        profile_only = [v for v in views if v.profile_only]
        for view in profile_only:
            self.assertTrue(view.note, view.name)

    def test_writing_an_unknown_setting_raises(self):
        with self.assertRaises(ValueError):
            cfgscan.write_setting(self.result, "not_a_real_setting", "1")

    def test_settings_not_in_any_file_are_still_listed(self):
        """The catalogue is the game's settings, not just what is written down."""
        views, _ = cfgscan.settings_view(self.result)
        unset = [v for v in views if v.unset]
        self.assertTrue(unset)
        for view in unset:
            self.assertEqual(view.file, "")
            self.assertTrue(view.note)

    def test_a_profile_only_file_is_not_part_of_startup(self):
        """Regression: lan.vcfg is exec'd from an alias, not at load.

        It has no file exec'ing it at startup, so the walker treats it as its
        own root. Counting every root as "startup" made a match profile look
        live from launch and the busiest startup file.
        """
        chain = cfgscan.startup_chain(self.result)
        self.assertIn("mrwhiteer/autoexec.vcfg", chain)
        self.assertIn("mrwhiteer/mainsettings/gamesettings.vcfg", chain)
        self.assertNotIn("mrwhiteer/lan/lan.vcfg", chain)
        self.assertNotIn("mrwhiteer/lan/warmup.vcfg", chain)

    def test_new_settings_go_to_a_startup_file_not_a_match_profile(self):
        target = cfgscan.default_target(self.result)
        self.assertIn(target, cfgscan.startup_chain(self.result))
        self.assertNotIn("lan", target)

    def test_new_settings_never_target_a_generated_file(self):
        target = cfgscan.default_target(self.result)
        generated = {c.relative for c in self.result.files.values() if c.generated_by}
        self.assertTrue(generated, "fixture should contain a generated file")
        self.assertNotIn(target, generated)

    def test_appending_preserves_everything_before_it(self):
        relative, text = cfgscan.append_setting(self.result, "cl_righthand", "1")
        config = next(c for c in self.result.files.values() if c.relative == relative)
        before = parse(config.path.read_bytes().decode("utf-8"), relative).signature()
        after = parse(text, relative).signature()
        self.assertEqual(after[:len(before)], before)
        self.assertEqual(len(after) - len(before), 1)
        self.assertEqual(after[-1], ("cl_righthand", "1"))

    def test_appending_twice_reuses_one_block(self):
        _, text = cfgscan.append_setting(self.result, "cl_righthand", "1")
        config = next(c for c in self.result.files.values()
                      if c.relative == cfgscan.default_target(self.result))
        cfglang.write_config_text(config.path, text)
        again = cfgscan.scan(self.collection, cfg_root=self.cfg_root)
        _, text2 = cfgscan.append_setting(again, "cl_showpos", "1")
        self.assertEqual(text2.count("// ADDED SETTINGS"), 1)

    def test_appending_to_a_file_outside_the_scan_raises(self):
        with self.assertRaises(ValueError):
            cfgscan.append_setting(self.result, "cl_righthand", "1", "nope/missing.cfg")

    def test_appending_a_setting_that_already_exists_raises(self):
        """The whole point of the guard: two lines would shadow each other."""
        with self.assertRaises(ValueError) as caught:
            cfgscan.append_setting(self.result, "fps_max_ui", "300")
        self.assertIn("already set", str(caught.exception))

    def test_appending_then_changing_leaves_exactly_one_line(self):
        """Changing an added setting must edit its line, not add another.

        This is the bug that made a saved change look like it did nothing: the
        last line won, but the page still showed the setting as unset and every
        save stacked one more copy.
        """
        relative, text = cfgscan.append_setting(self.result, "cl_righthand", "0")
        config = next(c for c in self.result.files.values() if c.relative == relative)
        cfglang.write_config_text(config.path, text)

        for value in ("1", "0", "1"):
            again = cfgscan.scan(self.collection, cfg_root=self.cfg_root)
            self.assertTrue(again.settings.get("cl_righthand"))
            _, text = cfgscan.write_setting(again, "cl_righthand", value)
            cfglang.write_config_text(config.path, text)

        final = config.path.read_text(encoding="utf-8")
        lines = [ln for ln in final.splitlines() if ln.strip().startswith("cl_righthand")]
        self.assertEqual(len(lines), 1, final)
        self.assertIn('"1"', lines[0])

    def test_the_added_block_never_holds_the_same_name_twice(self):
        target = cfgscan.default_target(self.result)
        config = next(c for c in self.result.files.values() if c.relative == target)
        for name, value in (("cl_righthand", "1"), ("cl_showpos", "1"),
                            ("cl_showfps", "2")):
            scan = cfgscan.scan(self.collection, cfg_root=self.cfg_root)
            _, text = cfgscan.append_setting(scan, name, value)
            cfglang.write_config_text(config.path, text)

        body = config.path.read_text(encoding="utf-8")
        added = body.split("// ADDED SETTINGS", 1)[1]
        names = [ln.split()[0] for ln in added.splitlines()
                 if ln.strip() and not ln.strip().startswith("//")]
        self.assertEqual(sorted(names), sorted(set(names)), added)

    def test_a_stale_line_number_still_edits_the_right_line(self):
        """A page loaded before the last save holds an old line number."""
        _, text = cfgscan.write_setting(self.result, "fps_max_ui", "144",
                                        "mrwhiteer/autoperf.vcfg", 9999)
        self.assertIn('fps_max_ui "144"', text)
        self.assertEqual(text.count("fps_max_ui"), 1)


class TestRecommendedSettings(unittest.TestCase):
    """The curated subset surfaced under its own tab -- not a separate set
    of cvars, just a list of which existing ones to group together."""

    def test_cl_color_is_recommended(self):
        self.assertIn("cl_color", cfgscan.recommended_settings())

    def test_every_recommended_name_is_a_real_setting(self):
        """Recommending a cvar that is not in "settings" at all would be a
        row the rest of the page can never actually render."""
        specs = cfgscan._load_setting_specs().get("settings", {})
        for name in cfgscan.recommended_settings():
            self.assertIn(name, specs, f"{name!r} is recommended but has no spec")

    def test_cl_color_labels_match_what_the_game_draws(self):
        """Checked in-game one value at a time on 2026-11-03. The labels the
        game used to ship (0 Yellow, 1 Purple, 2 Green, 3 Blue, 4 Orange) no
        longer match, and a picker built from them silently writes the wrong
        number for the colour the player asked for."""
        spec = cfgscan._load_setting_specs()["settings"]["cl_color"]
        self.assertEqual(spec["control"], "select")
        self.assertEqual(spec["options"], {
            "0": "Cyan / Blue",
            "1": "Green",
            "2": "Yellow",
            "3": "Orange",
            "4": "Purple",
        })

    def test_an_empty_knowledge_base_recommends_nothing(self):
        with mock.patch.object(cfgscan, "_load_setting_specs", return_value={}):
            self.assertEqual(cfgscan.recommended_settings(), [])


class TestApplyScript(FixtureCase):
    """The key-triggered 'reload my configs' alias -- the one thing this app
    writes that is not a value the user asked to change, so it gets its own
    checks: right file, right exec target, and readable back as a script."""

    def test_targets_the_real_entry_point(self):
        _, text = cfgscan.append_apply_script(self.result)
        self.assertIn('alias "cs2cfg_apply" "exec mrwhiteer/autoexec.vcfg"', text)

    def test_lands_in_the_same_file_new_settings_would(self):
        relative, _ = cfgscan.append_apply_script(self.result)
        self.assertEqual(relative, cfgscan.default_target(self.result))

    def test_installing_twice_raises(self):
        relative, text = cfgscan.append_apply_script(self.result)
        config = next(c for c in self.result.files.values() if c.relative == relative)
        cfglang.write_config_text(config.path, text)
        again = cfgscan.scan(self.collection, cfg_root=self.cfg_root)
        with self.assertRaises(ValueError) as caught:
            cfgscan.append_apply_script(again)
        self.assertIn("already installed", str(caught.exception))

    def test_reads_back_as_a_script(self):
        """The whole point of the banner shape: plugins.py has to recognise
        this as a feature, or it never shows up in the Scripts tab."""
        from cs2cfg import plugins

        relative, text = cfgscan.append_apply_script(self.result)
        config = next(c for c in self.result.files.values() if c.relative == relative)
        cfglang.write_config_text(config.path, text)
        again = cfgscan.scan(self.collection, cfg_root=self.cfg_root)

        found = plugins.find(again)
        match = next((p for p in found if p.entry == "cs2cfg_apply"), None)
        self.assertIsNotNone(match, [p.entry for p in found])
        self.assertEqual(match.name, "Apply Saved Settings")
        self.assertFalse(match.missing, "exec target should resolve to a real file")
        self.assertEqual(match.bound_to, [])


class TestDispatcherState(FixtureCase):
    """Jumping a toggle/cycle's dispatcher (GM -> 1GM -> 2GM -> ...) straight
    to a chosen state, instead of pressing its key through every step
    between wherever it is now and the one that is actually wanted."""

    def test_points_gm_at_the_chosen_state_with_the_files_own_casing(self):
        """plugins.py only ever knows state names in lowercase; the file's
        own casing is what should actually land on disk."""
        _, text = cfgscan.set_dispatcher_state(self.result, "GM", "2gm")
        self.assertIn('alias "GM" "2GM"', text)

    def test_an_unknown_state_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            cfgscan.set_dispatcher_state(self.result, "GM", "3GM")
        self.assertIn("not a defined alias", str(caught.exception))

    def test_an_unknown_dispatcher_is_refused(self):
        with self.assertRaises(ValueError):
            cfgscan.set_dispatcher_state(self.result, "NoSuchDispatcher", "2GM")

    def test_refuses_when_the_dispatcher_does_more_than_name_a_state(self):
        """A hand-edit that added a second command to GM's own line would
        have that command silently dropped by a plain text substitution --
        refused instead of risked."""
        scripts = self.cfg_root / "mrwhiteer/tools/scripts.vcfg"
        text = scripts.read_text(encoding="utf-8").replace(
            'alias "GM" "1GM"', 'alias "GM" "1GM; echo hi"')
        scripts.write_text(text, encoding="utf-8")
        again = cfgscan.scan(self.collection, cfg_root=self.cfg_root)

        with self.assertRaises(ValueError) as caught:
            cfgscan.set_dispatcher_state(again, "GM", "2GM")
        self.assertIn("not safe to retarget", str(caught.exception))


class TestLayoutProfiles(unittest.TestCase):
    """Pinning keys on a match profile like warmup.vcfg so it can't take them
    over, built on a small collection mirroring the real !5v5/!warmup/GM
    toggle: a startup-chain file with standard binds, a profile file outside
    it that overrides some of them, and an alias that execs the profile."""

    FILES = {
        "mrwhiteer/autoexec.vcfg": (
            'exec "mrwhiteer/tools/alias.vcfg"\n'
            'exec "mrwhiteer/mainsettings/key_binds.vcfg"\n'
        ),
        "mrwhiteer/tools/alias.vcfg": (
            'alias "!warmup" "exec mrwhiteer/lan/warmup.vcfg"     // Warmup loader\n'
        ),
        "mrwhiteer/mainsettings/key_binds.vcfg": (
            'bind "mouse3" "say custom text"      // CUSTOM {BUTTON - MOUSE3}\n'
            'bind "mouse4" "player_ping"           // PING {BUTTON - MOUSE4}\n'
        ),
        "mrwhiteer/lan/warmup.vcfg": (
            'bind "mouse3" "noclip"\n'
            'bind "mouse4" "bot_place"\n'
        ),
    }

    def setUp(self):
        self.sandbox = Path(tempfile.mkdtemp(prefix="cs2cfg-test-"))
        self.cfg_root = self.sandbox / "cfg"
        for relative, text in self.FILES.items():
            path = self.cfg_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.collection = self.cfg_root / "mrwhiteer"
        self.result = cfgscan.scan(self.collection, cfg_root=self.cfg_root)
        redirect_layouts(self)

    def tearDown(self):
        shutil.rmtree(self.sandbox, ignore_errors=True)

    def rescan(self):
        return cfgscan.scan(self.collection, cfg_root=self.cfg_root)

    def test_detects_warmup_as_a_profile_with_two_overrides(self):
        profiles = cfgscan.layout_profiles(self.result)
        self.assertEqual(len(profiles), 1)
        profile = profiles[0]
        self.assertEqual(profile["file"], "mrwhiteer/lan/warmup.vcfg")
        keys = {o["key"] for o in profile["overrides"]}
        self.assertEqual(keys, {"mouse3", "mouse4"})

    def test_finds_the_alias_that_switches_to_it(self):
        profile = cfgscan.layout_profiles(self.result)[0]
        self.assertEqual(profile["trigger"]["alias"], "!warmup")
        self.assertEqual(profile["trigger"]["file"], "mrwhiteer/tools/alias.vcfg")

    def test_a_file_the_startup_chain_never_touches_has_nothing_pinnable(self):
        """lan.vcfg-style file with no bind the standard layout also sets."""
        path = self.cfg_root / "mrwhiteer/lan/lan.vcfg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('bind "\\" "matchpause"\n', encoding="utf-8")
        again = self.rescan()
        files = {p["file"] for p in cfgscan.layout_profiles(again)}
        self.assertNotIn("mrwhiteer/lan/lan.vcfg", files)

    def test_switch_path_sits_beside_the_profile_it_wraps(self):
        self.assertEqual(
            cfgscan.layout_switch_path("mrwhiteer/lan/warmup.vcfg"),
            "mrwhiteer/lan/warmup.layout.vcfg")

    def test_switch_text_execs_the_profile_then_reasserts_pins(self):
        text = cfgscan.layout_switch_text(
            "mrwhiteer/lan/warmup.vcfg", {"mouse4": "player_ping"})
        self.assertIn('exec "mrwhiteer/lan/warmup.vcfg"', text)
        self.assertIn('bind "mouse4" "player_ping"', text)
        self.assertNotIn("mouse3", text)

    def test_switch_text_with_no_pins_is_a_plain_passthrough(self):
        text = cfgscan.layout_switch_text("mrwhiteer/lan/warmup.vcfg", {})
        self.assertIn('exec "mrwhiteer/lan/warmup.vcfg"', text)
        self.assertNotIn("bind", text)

    def test_retargets_the_triggering_alias_to_the_generated_file(self):
        profile = cfgscan.layout_profiles(self.result)[0]
        trigger = profile["trigger"]
        _, text = cfgscan.retarget_alias_exec(
            self.result, trigger["file"], trigger["line"],
            trigger["target_text"], "mrwhiteer/lan/warmup.layout.vcfg")
        self.assertIn(
            'alias "!warmup" "exec mrwhiteer/lan/warmup.layout.vcfg"', text)
        self.assertIn("Warmup loader", text, "the comment should survive untouched")

    def test_retarget_refuses_when_the_text_is_not_unique(self):
        config = next(c for c in self.result.files.values()
                     if c.relative == "mrwhiteer/tools/alias.vcfg")
        config.path.write_text(
            'alias "!warmup" "exec mrwhiteer/lan/warmup.vcfg"  '
            '// also mentions mrwhiteer/lan/warmup.vcfg right here\n',
            encoding="utf-8")
        again = self.rescan()
        trigger = cfgscan.layout_profiles(again)[0]["trigger"]
        with self.assertRaises(ValueError):
            cfgscan.retarget_alias_exec(
                again, trigger["file"], trigger["line"],
                "mrwhiteer/lan/warmup.vcfg", "mrwhiteer/lan/warmup.layout.vcfg")

    def test_pins_round_trip_through_storage(self):
        layouts.save_pins(self.collection, "mrwhiteer/lan/warmup.vcfg", ["mouse4"])
        self.assertEqual(
            layouts.load_pins(self.collection),
            {"mrwhiteer/lan/warmup.vcfg": ["mouse4"]})

    def test_clearing_pins_removes_the_entry(self):
        layouts.save_pins(self.collection, "mrwhiteer/lan/warmup.vcfg", ["mouse4"])
        layouts.save_pins(self.collection, "mrwhiteer/lan/warmup.vcfg", [])
        self.assertEqual(layouts.load_pins(self.collection), {})

    def test_match_profiles_includes_one_with_nothing_pinnable(self):
        """Unlike layout_profiles, the broader listing used by the profile
        selector must still show a blank/new profile with zero overrides."""
        path = self.cfg_root / "mrwhiteer/lan/lan.vcfg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('bind "\\" "matchpause"\n', encoding="utf-8")
        again = self.rescan()
        files = {p["file"] for p in cfgscan.match_profiles(again)}
        self.assertIn("mrwhiteer/lan/lan.vcfg", files)
        self.assertIn("mrwhiteer/lan/warmup.vcfg", files)
        self.assertNotIn("mrwhiteer/lan/lan.vcfg",
                         {p["file"] for p in cfgscan.layout_profiles(again)})

    def test_is_match_profile_true_for_a_profile_false_for_startup_files(self):
        self.assertTrue(
            cfgscan.is_match_profile(self.result, "mrwhiteer/lan/warmup.vcfg"))
        self.assertFalse(
            cfgscan.is_match_profile(self.result, "mrwhiteer/autoexec.vcfg"))
        self.assertFalse(
            cfgscan.is_match_profile(self.result, "mrwhiteer/does/not/exist.vcfg"))

    def test_profile_slug_strips_everything_but_letters_and_digits(self):
        self.assertEqual(cfgscan.profile_slug("5v5 Setup!"), "5v5_setup")
        self.assertEqual(cfgscan.profile_slug("../../etc/passwd"), "etc_passwd")
        self.assertEqual(cfgscan.profile_slug("   "), "profile")

    def test_new_profile_path_lands_beside_the_existing_lan_folder(self):
        self.assertEqual(
            cfgscan.new_profile_path(self.result, "Competitive"),
            "mrwhiteer/lan/competitive.vcfg")

    def test_new_profile_path_avoids_a_collision(self):
        self.assertEqual(
            cfgscan.new_profile_path(self.result, "warmup"),
            "mrwhiteer/lan/warmup_2.vcfg")

    def test_blank_profile_text_is_just_a_banner(self):
        text = cfgscan.profile_blank_text("Competitive")
        self.assertIn("Competitive", text)
        self.assertNotIn("GENERATED BY", text)

    def test_disable_line_comments_out_the_triggering_alias(self):
        trigger = cfgscan.layout_profiles(self.result)[0]["trigger"]
        _, text = cfgscan.disable_line(
            self.result, trigger["file"], trigger["line"], "test")
        self.assertIn('// alias "!warmup" "exec mrwhiteer/lan/warmup.vcfg"', text)

    def test_disable_line_refuses_to_disable_twice(self):
        trigger = cfgscan.layout_profiles(self.result)[0]["trigger"]
        _, text = cfgscan.disable_line(
            self.result, trigger["file"], trigger["line"], "test")
        config = next(c for c in self.result.files.values()
                      if c.relative == trigger["file"])
        config.path.write_text(text, encoding="utf-8")
        again = self.rescan()
        with self.assertRaises(ValueError):
            cfgscan.disable_line(again, trigger["file"], trigger["line"], "test again")

    def test_registry_tracks_created_and_hidden_profiles(self):
        layouts.mark_created(self.collection, "mrwhiteer/lan/new.vcfg")
        self.assertTrue(layouts.is_created(self.collection, "mrwhiteer/lan/new.vcfg"))
        self.assertFalse(layouts.is_created(self.collection, "mrwhiteer/lan/warmup.vcfg"))

        layouts.hide_profile(self.collection, "mrwhiteer/lan/warmup.vcfg")
        self.assertIn("mrwhiteer/lan/warmup.vcfg",
                      layouts.load_registry(self.collection)["hidden"])

    def test_forget_profile_clears_pins_and_both_registry_flags(self):
        layouts.mark_created(self.collection, "mrwhiteer/lan/new.vcfg")
        layouts.hide_profile(self.collection, "mrwhiteer/lan/new.vcfg")
        layouts.save_pins(self.collection, "mrwhiteer/lan/new.vcfg", ["mouse4"])

        layouts.forget_profile(self.collection, "mrwhiteer/lan/new.vcfg")

        registry = layouts.load_registry(self.collection)
        self.assertNotIn("mrwhiteer/lan/new.vcfg", registry["created"])
        self.assertNotIn("mrwhiteer/lan/new.vcfg", registry["hidden"])
        self.assertEqual(layouts.load_pins(self.collection), {})

    def test_apply_writes_every_override_onto_the_standard_file(self):
        applied, skipped, texts = cfgscan.apply_profile_overrides(
            self.result, "mrwhiteer/lan/warmup.vcfg")
        self.assertEqual(set(applied), {"mouse3", "mouse4"})
        self.assertEqual(skipped, [])
        text = texts["mrwhiteer/mainsettings/key_binds.vcfg"]
        self.assertIn('bind "mouse3" "noclip"', text)
        self.assertIn('bind "mouse4" "bot_place"', text)
        # The comment beside each bind is untouched -- only the body moved.
        self.assertIn("CUSTOM {BUTTON - MOUSE3}", text)
        self.assertIn("PING {BUTTON - MOUSE4}", text)

    def test_apply_leaves_a_pinned_key_on_its_standard_binding(self):
        applied, skipped, texts = cfgscan.apply_profile_overrides(
            self.result, "mrwhiteer/lan/warmup.vcfg", skip_keys=["mouse4"])
        self.assertEqual(applied, ["mouse3"])
        self.assertEqual(skipped, ["mouse4"])
        text = texts["mrwhiteer/mainsettings/key_binds.vcfg"]
        self.assertIn('bind "mouse3" "noclip"', text)
        self.assertIn('bind "mouse4" "player_ping"', text, "pinned, so unchanged")

    def test_apply_with_every_key_pinned_writes_nothing(self):
        applied, skipped, texts = cfgscan.apply_profile_overrides(
            self.result, "mrwhiteer/lan/warmup.vcfg", skip_keys=["mouse3", "mouse4"])
        self.assertEqual(applied, [])
        self.assertEqual(set(skipped), {"mouse3", "mouse4"})
        self.assertEqual(texts, {})

    def test_apply_refuses_a_file_that_is_not_a_profile(self):
        with self.assertRaises(ValueError):
            cfgscan.apply_profile_overrides(self.result, "mrwhiteer/autoexec.vcfg")

    def test_applying_twice_is_idempotent(self):
        """Writing a profile's own values back onto itself a second time
        changes nothing further -- the whole point of "already switched"."""
        applied, _, texts = cfgscan.apply_profile_overrides(
            self.result, "mrwhiteer/lan/warmup.vcfg")
        config = next(c for c in self.result.files.values()
                      if c.relative == "mrwhiteer/mainsettings/key_binds.vcfg")
        config.path.write_text(texts[config.relative], encoding="utf-8")
        again = self.rescan()

        applied2, _, texts2 = cfgscan.apply_profile_overrides(
            again, "mrwhiteer/lan/warmup.vcfg")
        self.assertEqual(applied2, [])
        self.assertEqual(texts2, {})

    def test_not_active_before_anything_has_been_applied(self):
        self.assertFalse(
            cfgscan.profile_is_active(self.result, "mrwhiteer/lan/warmup.vcfg"))

    def test_active_once_the_standard_layout_matches_it(self):
        _, _, texts = cfgscan.apply_profile_overrides(
            self.result, "mrwhiteer/lan/warmup.vcfg")
        config = next(c for c in self.result.files.values()
                      if c.relative == "mrwhiteer/mainsettings/key_binds.vcfg")
        config.path.write_text(texts[config.relative], encoding="utf-8")
        again = self.rescan()
        self.assertTrue(
            cfgscan.profile_is_active(again, "mrwhiteer/lan/warmup.vcfg"))

    def test_a_profile_with_no_binds_of_its_own_is_never_active(self):
        path = self.cfg_root / "mrwhiteer/lan/blank.vcfg"
        path.write_text("// nothing here yet\n", encoding="utf-8")
        again = self.rescan()
        self.assertFalse(cfgscan.profile_is_active(again, "mrwhiteer/lan/blank.vcfg"))

    def test_active_ignores_a_key_pinned_away(self):
        """Only one of the two keys is applied; the other stays on its
        standard binding, same as a pin already keeps it. Active should
        still read true once the pinned key is excluded from the check."""
        _, _, texts = cfgscan.apply_profile_overrides(
            self.result, "mrwhiteer/lan/warmup.vcfg", skip_keys=["mouse4"])
        config = next(c for c in self.result.files.values()
                      if c.relative == "mrwhiteer/mainsettings/key_binds.vcfg")
        config.path.write_text(texts[config.relative], encoding="utf-8")
        again = self.rescan()
        self.assertFalse(
            cfgscan.profile_is_active(again, "mrwhiteer/lan/warmup.vcfg"),
            "mouse4 still differs, and nothing is pinned here yet")
        self.assertTrue(
            cfgscan.profile_is_active(again, "mrwhiteer/lan/warmup.vcfg",
                                      skip_keys=["mouse4"]))

    def test_default_restorable_is_empty_with_no_baseline(self):
        self.assertEqual(cfgscan.default_restorable(self.result, {}), [])
        self.assertTrue(cfgscan.default_is_active(self.result, {}))

    def test_default_restorable_finds_a_key_that_now_differs(self):
        baseline = {"mrwhiteer/mainsettings/key_binds.vcfg":
                    {"mouse3": "say custom text"}}
        _, _, texts = cfgscan.apply_profile_overrides(
            self.result, "mrwhiteer/lan/warmup.vcfg")
        config = next(c for c in self.result.files.values()
                      if c.relative == "mrwhiteer/mainsettings/key_binds.vcfg")
        config.path.write_text(texts[config.relative], encoding="utf-8")
        again = self.rescan()

        restorable = cfgscan.default_restorable(again, baseline)
        self.assertEqual(len(restorable), 1)
        self.assertEqual(restorable[0]["key"], "mouse3")
        self.assertEqual(restorable[0]["to_body"], "say custom text")
        self.assertFalse(cfgscan.default_is_active(again, baseline))

    def test_apply_default_layout_writes_the_baseline_body_back(self):
        baseline = {"mrwhiteer/mainsettings/key_binds.vcfg":
                    {"mouse3": "say custom text", "mouse4": "player_ping"}}
        _, _, texts = cfgscan.apply_profile_overrides(
            self.result, "mrwhiteer/lan/warmup.vcfg")
        config = next(c for c in self.result.files.values()
                      if c.relative == "mrwhiteer/mainsettings/key_binds.vcfg")
        config.path.write_text(texts[config.relative], encoding="utf-8")
        again = self.rescan()

        applied, restored = cfgscan.apply_default_layout(again, baseline)
        self.assertEqual(set(applied), {"mouse3", "mouse4"})
        self.assertIn('bind "mouse3" "say custom text"',
                      restored["mrwhiteer/mainsettings/key_binds.vcfg"])
        self.assertIn('bind "mouse4" "player_ping"',
                      restored["mrwhiteer/mainsettings/key_binds.vcfg"])

    def test_apply_default_layout_with_nothing_to_restore_writes_nothing(self):
        baseline = {"mrwhiteer/mainsettings/key_binds.vcfg":
                    {"mouse3": "say custom text"}}
        applied, restored = cfgscan.apply_default_layout(self.result, baseline)
        self.assertEqual(applied, [])
        self.assertEqual(restored, {})

    def test_profile_missing_defaults_excludes_what_the_profile_overrides(self):
        table = {"mouse3": "noclip", "mouse4": "bot_place", "w": "+forward"}
        missing = cfgscan.profile_missing_defaults(
            self.result, "mrwhiteer/lan/warmup.vcfg", table)
        self.assertEqual(missing, [{"key": "w", "command": "+forward"}])

    def test_profile_missing_defaults_is_empty_without_a_defaults_table(self):
        self.assertEqual(
            cfgscan.profile_missing_defaults(
                self.result, "mrwhiteer/lan/warmup.vcfg", {}),
            [])

    def test_profile_missing_defaults_lists_everything_for_a_blank_profile(self):
        path = self.cfg_root / "mrwhiteer/lan/blank.vcfg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        again = self.rescan()
        table = {"mouse3": "noclip", "w": "+forward"}
        missing = cfgscan.profile_missing_defaults(
            again, "mrwhiteer/lan/blank.vcfg", table)
        self.assertEqual(
            {(m["key"], m["command"]) for m in missing},
            {("mouse3", "noclip"), ("w", "+forward")})

    def test_profile_missing_defaults_normalises_key_spellings_first(self):
        """A profile may bind "w" where the defaults table -- read from the
        game's own file -- says "scancode26" for the same physical key;
        comparing them as written would report the key as missing twice
        over, once under each spelling."""
        path = self.cfg_root / "mrwhiteer/lan/letters.vcfg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('bind "w" "+forward"\n', encoding="utf-8")
        again = self.rescan()
        missing = cfgscan.profile_missing_defaults(
            again, "mrwhiteer/lan/letters.vcfg", {"scancode26": "+forward"})
        self.assertEqual(missing, [])


class TestFolderPicking(FixtureCase):
    """Choosing a folder should not require typing a path."""

    def test_describe_reports_a_usable_folder(self):
        info = cfgscan.describe_folder(self.collection)
        self.assertTrue(info["is_dir"])
        self.assertEqual(info["file_count"], len(self.FILES))
        self.assertIn("cfg_root", info)

    def test_describe_reports_the_cfg_root_not_the_folder_itself(self):
        info = cfgscan.describe_folder(self.collection)
        self.assertEqual(Path(info["cfg_root"]), self.cfg_root)

    def test_describe_rejects_a_missing_path(self):
        info = cfgscan.describe_folder(self.sandbox / "nope")
        self.assertFalse(info["exists"])
        self.assertEqual(info["file_count"], 0)
        self.assertTrue(info["message"])

    def test_describe_rejects_a_file(self):
        target = self.sandbox / "a-file.txt"
        target.write_text("x", encoding="utf-8")
        info = cfgscan.describe_folder(target)
        self.assertFalse(info["is_dir"])

    def test_describe_reports_an_empty_folder_clearly(self):
        empty = self.sandbox / "empty"
        empty.mkdir()
        info = cfgscan.describe_folder(empty)
        self.assertTrue(info["is_dir"])
        self.assertEqual(info["file_count"], 0)
        self.assertIn("no .cfg", info["message"])

    def test_suggestions_include_an_extra_folder(self):
        found = cfgscan.suggest_folders([self.cfg_root])
        paths = [Path(s.path) for s in found]
        self.assertIn(self.cfg_root, paths)
        self.assertIn(self.collection, paths)

    def test_suggestions_prefer_the_specific_collection_over_the_root(self):
        """Ordering, checked only among this fixture's own entries.

        suggest_folders also finds the real CS2 install on the machine running
        the tests, so an assertion about the very first result overall would
        depend on whoever's PC this is.
        """
        found = cfgscan.suggest_folders([self.cfg_root])
        mine = [s for s in found if Path(s.path) in (self.cfg_root, self.collection)]
        self.assertEqual(len(mine), 2)
        self.assertEqual(Path(mine[0].path), self.collection)
        self.assertTrue(mine[1].is_cfg_root)

    def test_suggestions_skip_folders_with_no_configs(self):
        (self.cfg_root / "screenshots").mkdir()
        (self.cfg_root / "screenshots" / "a.png").write_bytes(b"x")
        found = cfgscan.suggest_folders([self.cfg_root])
        self.assertNotIn("screenshots", [s.label for s in found])

    def test_suggestions_do_not_repeat_a_folder(self):
        found = cfgscan.suggest_folders([self.cfg_root, self.cfg_root])
        paths = [s.path.lower() for s in found]
        self.assertEqual(len(paths), len(set(paths)))


class TestReloadCycles(unittest.TestCase):
    def test_a_file_that_execs_itself_terminates(self):
        sandbox = Path(tempfile.mkdtemp(prefix="cs2cfg-loop-"))
        try:
            root = sandbox / "cfg"
            (root / "p").mkdir(parents=True)
            (root / "p" / "a.vcfg").write_text(
                'alias "!reload" "exec p/a.vcfg"\nexec "p/b.vcfg"\n', encoding="utf-8"
            )
            (root / "p" / "b.vcfg").write_text('exec "p/a.vcfg"\n', encoding="utf-8")
            result = cfgscan.scan(root / "p", cfg_root=root)
            self.assertLess(len(result.exec_chain), 12)
            self.assertNotIn("exec-depth", [i.code for i in result.issues])
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
