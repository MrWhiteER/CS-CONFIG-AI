"""R3-8: disposable config snapshots, backups and consent/running-game guards.

No real Steam paths, server, hardware probe or elevated helper is used.
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cs2cfg import backup, cfglang, cfgscan, configbundle as bundle, webui
from sandbox import redirect_backups, redirect_layouts


class Sandbox(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.backups = redirect_backups(self)
        redirect_layouts(self)
        for patch in [mock.patch.object(bundle, "user_data_dir", return_value=self.root / "data"),
                      mock.patch("cs2cfg.elevated.ready", return_value=True),
                      mock.patch("cs2cfg.elevated.run", side_effect=AssertionError("No helper")),
                      mock.patch("cs2cfg.elevated.install", side_effect=AssertionError("No UAC"))]:
            patch.start()
            self.addCleanup(patch.stop)

    def prepare(self, performance="fps_max 300\n"):
        return bundle.prepare("account-a", "custom", "autoperf.vcfg", performance, "launch notes\n")


class Preparation(Sandbox):
    def test_no_game_is_needed_to_build_all_standard_files(self):
        out = self.prepare()
        root = Path(out["root"])
        self.assertTrue(root.is_relative_to(self.root / "data"))
        self.assertEqual(len(out["files"]), 6)
        result = cfgscan.scan(root)
        self.assertEqual(result.effective_setting("fps_max").value, "300")
        self.assertEqual(result.binds, {})
        self.assertNotIn("unbindall", [c.lname for f in result.files.values() for c in f.document.commands()])

    def test_identical_starts_do_not_write_or_make_more_backups(self):
        self.prepare()
        count = len(backup.list_sets())
        out = self.prepare()
        self.assertEqual(out["changed"], 0)
        self.assertEqual(len(backup.list_sets()), count)

    def test_accounts_have_different_app_copies(self):
        self.assertNotEqual(bundle.storage("a"), bundle.storage("b"))

    def test_starter_edits_survive_preparation(self):
        root = Path(self.prepare()["root"])
        path = root / "mainsettings/key_binds.vcfg"
        path.write_text('bind "mouse1" "+attack"\n', encoding="utf-8")
        self.prepare()
        self.assertIn('"+attack"', path.read_text())

    def test_imported_commands_load_after_the_preset(self):
        root = Path(self.prepare()["root"])
        bundle.write_changed(root, {bundle.IMPORTED: "fps_max 144\n"}, "test import")
        self.prepare()
        self.assertEqual(cfgscan.scan(root).effective_setting("fps_max").value, "144")

    def test_replaced_performance_has_an_original_backup(self):
        root = Path(self.prepare()["root"])
        self.prepare("fps_max 144\n")
        path = root / "autoperf.vcfg"
        copies = [s.path / s.files[str(path)] for s in backup.list_sets() if s.files.get(str(path))]
        self.assertTrue(any(p.read_text() == "fps_max 300\n" for p in copies))

    def test_all_backups_complete_before_any_write(self):
        root = self.root / "files"
        root.mkdir()
        (root / "a.cfg").write_text("old a")
        (root / "b.cfg").write_text("old b")
        with mock.patch.object(backup.BackupSession, "add", side_effect=[None, OSError("backup full")]):
            with self.assertRaises(OSError):
                bundle.write_changed(root, {"a.cfg": "new a", "b.cfg": "new b"}, "test")
        self.assertEqual((root / "a.cfg").read_text(), "old a")
        self.assertEqual((root / "b.cfg").read_text(), "old b")

    def test_same_second_backups_keep_both_manifests(self):
        a, b = backup.BackupSession("first"), backup.BackupSession("second")
        b.stamp, b.dir = a.stamp, a.dir
        path = self.root / "file.cfg"
        path.write_text("first")
        a.add(path)
        path.write_text("second")
        b.add(path)
        self.assertNotEqual(a.stamp, b.stamp)
        self.assertEqual(len(backup.list_sets()), 2)
        self.assertEqual((a.dir / a.files[str(path)]).read_text(), "first")
        self.assertEqual((b.dir / b.files[str(path)]).read_text(), "second")

    def test_unsafe_relative_paths_are_rejected(self):
        for value in ("../cfg", "C:/cfg", "/cfg", "a//b", 'a";quit', "a\nb"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bundle.safe_relative(value)


class Installation(Sandbox):
    def setUp(self):
        super().setUp()
        self.app = Path(self.prepare()["root"])
        self.cfg = self.root / "game" / "cfg"
        self.dest = self.cfg / "custom"

    def install(self):
        return bundle.install(self.app, self.cfg, "custom")

    def test_fresh_destination_scans_and_repeated_install_is_idle(self):
        self.install()
        self.assertEqual(cfgscan.scan(self.dest).effective_setting("fps_max").value, "300")
        self.assertEqual(self.install()["changed"], 0)

    def test_existing_personal_files_survive(self):
        (self.dest / "mainsettings").mkdir(parents=True)
        path = self.dest / "mainsettings/key_binds.vcfg"
        path.write_text('bind "mouse1" "+attack"\n')
        entry = self.dest / "autoexec.vcfg"
        entry.write_text("sensitivity 2\n")
        self.install()
        self.assertEqual(path.read_text(), 'bind "mouse1" "+attack"\n')
        self.assertTrue(entry.read_text().startswith("sensitivity 2\n"))
        self.assertIn('exec "custom/autoperf.vcfg"', entry.read_text())

    def test_import_originals_in_destination_are_never_edited(self):
        self.dest.mkdir(parents=True)
        entry = self.dest / "autoexec.vcfg"
        entry.write_text("sensitivity 2\n")
        (self.app / "_import_sources.json").write_text(json.dumps([str(entry.resolve()).casefold()]))
        with self.assertRaisesRegex(ValueError, "Original files"):
            self.install()
        self.assertEqual(entry.read_text(), "sensitivity 2\n")
        self.assertFalse((self.dest / "autoperf.vcfg").exists())

    def test_source_metadata_is_not_installed_into_cs2(self):
        (self.app / "_import_sources.json").write_text("[]")
        self.install()
        self.assertFalse((self.dest / "_import_sources.json").exists())

    def test_keyboard_edits_to_installed_import_survive_next_start(self):
        (self.app / bundle.IMPORTED).write_text("volume 1\n")
        self.install()
        path = self.dest / bundle.IMPORTED
        path.write_text("volume 0.25\n")
        result = self.install()
        self.assertEqual(path.read_text(), "volume 0.25\n")
        self.assertEqual(result["preserved"], [bundle.IMPORTED])

    def test_a_new_accepted_import_replaces_old_copy_with_backup(self):
        (self.app / bundle.IMPORTED).write_text("volume 1\n")
        self.install()
        path = self.dest / bundle.IMPORTED
        path.write_text("volume 0.25\n")
        (self.app / bundle.IMPORTED).write_text("volume 0.75\n")
        self.install()
        self.assertEqual(path.read_text(), "volume 0.75\n")
        self.assertTrue(any(s.files.get(str(path)) and (s.path / s.files[str(path)]).read_text() == "volume 0.25\n"
                            for s in backup.list_sets()))


class Importing(Sandbox):
    def test_arbitrarily_renamed_cfg_is_kept_and_never_modified(self):
        path = self.root / "my-match-settings.cfg"
        original = b'sensitivity 2\nalias "hello" "say hello"\nbind "mouse1" "+attack"\n'
        path.write_bytes(original)
        snapshot = bundle.snapshot([path])
        result = bundle.rebuild(snapshot, list(snapshot))
        self.assertEqual(result["kept"], 3)
        self.assertEqual(result["dropped"], 0)
        self.assertEqual(path.read_bytes(), original)

    def test_execs_merge_in_place_with_later_overrides_preserved(self):
        result = bundle.rebuild({"my.cfg": 'sensitivity 1\nexec "nested"\nsensitivity 3\n',
                                 "nested.cfg": "sensitivity 2\n"}, ["my.cfg"])
        self.assertEqual([c.arg_text(0) for c in cfglang.parse(result["text"]).commands()], ["1", "2", "3"])
        self.assertEqual((result["kept"], result["merged"], result["dropped"]), (3, 1, 0))

    def test_cfg_relative_paths_and_vcfg_extension_work(self):
        result = bundle.rebuild({"custom/my.cfg": 'exec "custom/tools"\n',
                                 "custom/tools.vcfg": "volume 0.5\n"}, ["custom/my.cfg"])
        self.assertEqual(result["kept"], 1)
        self.assertEqual(result["dropped"], 0)

    def test_collection_tail_resolution_uses_the_existing_scanner(self):
        out = bundle.rebuild({"my.cfg": 'exec "mycollection/tools.vcfg"\n',
                              "tools.vcfg": "volume 0.5\n"}, ["my.cfg"])
        self.assertEqual(out["kept"], 1)
        self.assertEqual(out["dropped"], 0)

    def test_exec_with_unhandled_arguments_is_reported(self):
        out = bundle.rebuild({"my.cfg": 'exec "tools.cfg" unexpected\n',
                              "tools.cfg": "volume 0.5\n"}, ["my.cfg"])
        self.assertEqual(out["kept"], 0)
        self.assertIn("arguments need review", out["details"][0]["reason"])

    def test_duplicate_commands_are_not_removed_or_sorted(self):
        text = "sensitivity 2\nsensitivity 2\nvolume 1\nsensitivity 1\n"
        result = bundle.rebuild({"a.cfg": text}, ["a.cfg"])
        self.assertEqual(cfglang.parse(text).signature(), cfglang.parse(result["text"]).signature())

    def test_deferred_exec_is_reported_instead_of_run_at_start(self):
        out = bundle.rebuild({"a.cfg": 'bind "f1" "exec practice.cfg"\nvolume 1\n'}, ["a.cfg"])
        self.assertEqual(out["kept"], 1)
        self.assertEqual(out["dropped"], 1)
        self.assertIn("Deferred exec", out["details"][0]["reason"])

    def test_missing_exec_and_syntax_have_source_line_details(self):
        out = bundle.rebuild({"a.cfg": 'exec missing.cfg\nsensitivity "2\n'}, ["a.cfg"])
        self.assertEqual(out["dropped"], 2)
        self.assertEqual([d["line"] for d in out["details"]], [1, 2])

    def test_keyvalues_are_not_treated_as_console_commands(self):
        out = bundle.rebuild({"keys.vcfg": '"config"\n{\n"bindings"\n{\n"a" "+left"\n}\n}\n'}, ["keys.vcfg"])
        self.assertEqual(out["kept"], 0)
        self.assertIn("KeyValues", out["details"][0]["reason"])

    def test_exec_loop_is_bounded_and_reported(self):
        out = bundle.rebuild({"a.cfg": "exec a.cfg\nvolume 1\n"}, ["a.cfg"])
        self.assertEqual(out["kept"], 1)
        self.assertEqual(out["dropped"], 1)

    def test_unknown_commands_are_kept(self):
        out = bundle.rebuild({"a.cfg": "some_future_cs2_command 7\n"}, ["a.cfg"])
        self.assertEqual(out["kept"], 1)

    def test_empty_or_unlisted_entries_are_rejected(self):
        for entries in ([], ["outside.cfg"], [{}]):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                bundle.rebuild({"a.cfg": "volume 1"}, entries)

    def test_folder_only_reads_cfg_files_and_names_are_explicit(self):
        (self.root / "renamed.cfg").write_text("volume 1")
        (self.root / "secret.txt").write_text("not a config")
        out = bundle.snapshot([self.root], folder=True)
        self.assertEqual(list(out), ["renamed.cfg"])

    def test_file_and_byte_limits_are_enforced(self):
        path = self.root / "a.cfg"
        path.write_text("volume 1")
        with mock.patch.object(bundle, "MAX_BYTES", 2), self.assertRaises(ValueError):
            bundle.snapshot([path])
        with mock.patch.object(bundle, "MAX_FILES", 0), self.assertRaises(ValueError):
            bundle.snapshot([path])

    def test_legacy_encoding_is_read_without_changing_original_bytes(self):
        path = self.root / "a.cfg"
        original = b'// caf\xe9\nvolume 1\n'
        path.write_bytes(original)
        out = bundle.snapshot([path])
        self.assertIn("café", out["a.cfg"])
        self.assertEqual(path.read_bytes(), original)


class Routes(Sandbox):
    def setUp(self):
        super().setUp()
        self.prefs = {"ui": {}}
        self.game = self.root / "game"
        self.state = SimpleNamespace(refresh=mock.Mock(), users=[], machine=object(), kb=object(),
                                     cs2_install=None, cfg_folder="custom", cfg_name="autoperf.vcfg",
                                     config_import=None, steam_root=None)
        self.running = mock.Mock(return_value=False)
        for patch in [mock.patch("cs2cfg.cli.load_prefs", side_effect=lambda: self.prefs),
                      mock.patch("cs2cfg.cli.save_prefs"),
                      mock.patch.object(webui, "_active_account", return_value="account-a"),
                      mock.patch.object(webui, "build_profile", return_value=object()),
                      mock.patch.object(webui, "plan_launch_options", return_value=SimpleNamespace(line="", removed=[], added=[])),
                      mock.patch("cs2cfg.emit.render_cfg", return_value="fps_max 300\n"),
                      mock.patch("cs2cfg.emit.render_launch_notes", return_value="notes"),
                      mock.patch("cs2cfg.steam.cs2_running", self.running),
                      mock.patch("cs2cfg.steam.cfg_dir", return_value=self.game / "cfg"),
                      mock.patch("cs2cfg.firstrun.known_apps", return_value=[]),
                      mock.patch.object(webui, "_sync_loop", return_value=mock.Mock())]:
            patch.start()
            self.addCleanup(patch.stop)

    def test_no_permission_still_prepares_but_never_touches_game(self):
        self.state.cs2_install = self.game
        out = webui._configs_prepare(self.state, {})
        self.assertTrue(Path(out["root"]).is_dir())
        self.assertFalse(out["installed"])
        self.assertFalse(self.game.exists())

    def test_explicit_false_permission_never_installs(self):
        self.prefs["ui"]["cfg_write_ok"] = False
        self.test_no_permission_still_prepares_but_never_touches_game()

    def test_running_game_defers_every_cs2_write(self):
        self.prefs["ui"]["cfg_write_ok"] = True
        self.state.cs2_install = self.game
        self.running.return_value = True
        out = webui._configs_prepare(self.state, {})
        self.assertEqual(out["state"], "waiting")
        self.assertFalse(self.game.exists())
        self.assertTrue(Path(out["root"]).is_dir())

    def test_allowed_closed_game_installs(self):
        self.prefs["ui"]["cfg_write_ok"] = True
        self.state.cs2_install = self.game
        out = webui._configs_prepare(self.state, {})
        self.assertTrue(out["installed"])
        self.assertTrue((self.game / "cfg/custom/autoperf.vcfg").is_file())

    def test_unwritable_game_keeps_app_ready(self):
        self.prefs["ui"]["cfg_write_ok"] = True
        self.state.cs2_install = self.game
        with mock.patch.object(bundle, "install", side_effect=PermissionError("Read only")):
            out = webui._configs_prepare(self.state, {})
        self.assertEqual(out["state"], "waiting")
        self.assertEqual(out["reason"], "Read only")
        self.assertTrue(Path(out["root"]).is_dir())

    def test_no_game_has_a_clear_state(self):
        self.assertEqual(webui._configs_prepare(self.state, {})["state"], "no_game")

    def test_wizard_folder_listing_can_skip_the_write_probe(self):
        from cs2cfg import firstrun
        self.game.mkdir()
        with mock.patch("tempfile.mkstemp", side_effect=AssertionError("No write probe")):
            out = firstrun.cfg_access(self.game, probe=False)
        self.assertTrue(out["exists"])
        self.assertFalse(out["writable"])

    def test_cancelled_native_picker_does_not_replace_preview(self):
        with mock.patch("cs2cfg.picker.pick_files", return_value=[]):
            self.assertTrue(webui._configs_import_pick(self.state, {})["cancelled"])
        self.assertIsNone(self.state.config_import)

    def test_importing_the_app_output_itself_is_rejected(self):
        root = Path(self.prepare()["root"])
        with mock.patch("cs2cfg.picker.pick_files", return_value=[str(root / "autoexec.vcfg")]), self.assertRaises(ValueError):
            webui._configs_import_pick(self.state, {})

    def pick(self):
        path = self.root / "renamed.cfg"
        path.write_text("sensitivity 2\n")
        with mock.patch("cs2cfg.picker.pick_files", return_value=[str(path)]):
            return webui._configs_import_pick(self.state, {"kind": "files"})

    def test_preview_only_reads_a_snapshot_and_issues_a_distinct_token(self):
        chosen = self.pick()
        (self.root / "renamed.cfg").write_text("sensitivity 99\n")
        out = webui._configs_import_preview(self.state, {"token": chosen["token"], "entries": chosen["files"]})
        self.assertNotEqual(out["token"], chosen["token"])
        self.assertNotIn("text", out)
        self.assertIn("sensitivity 2", self.state.config_import["result"]["text"])
        self.assertFalse(bundle.storage("account-a", "custom").exists())

    def test_expired_and_cross_account_tokens_are_rejected(self):
        chosen = self.pick()
        with self.assertRaises(ValueError):
            webui._configs_import_preview(self.state, {"token": "bad", "entries": chosen["files"]})
        with mock.patch.object(webui, "_active_account", return_value="other"), self.assertRaises(ValueError):
            webui._configs_import_preview(self.state, {"token": chosen["token"], "entries": chosen["files"]})

    def test_finish_commits_only_the_reviewed_copy_without_permission(self):
        chosen = self.pick()
        review = webui._configs_import_preview(self.state, {"token": chosen["token"], "entries": chosen["files"]})
        webui._firstrun_finish(self.state, {"answers": {"import": review["token"]}})
        self.assertTrue((bundle.storage("account-a", "custom") / bundle.IMPORTED).is_file())
        self.assertEqual((self.root / "renamed.cfg").read_text(), "sensitivity 2\n")
        self.assertFalse(self.game.exists())

    def test_import_selects_standard_layout_but_keeps_profile_pins(self):
        from cs2cfg import layouts
        root = bundle.storage("account-a", "custom")
        layouts.save_current(root, "practice.vcfg")
        layouts.save_pins(root, "practice.vcfg", ["mouse1"])
        chosen = self.pick()
        review = webui._configs_import_preview(self.state, {"token": chosen["token"], "entries": chosen["files"]})
        webui._firstrun_finish(self.state, {"answers": {"import": review["token"]}})
        self.assertIsNone(layouts.load_current(root))
        self.assertEqual(layouts.load_pins(root), {"practice.vcfg": ["mouse1"]})
        self.assertTrue(any(str(layouts._current_path(root)) in s.files for s in backup.list_sets()))

    def test_skipping_import_commits_nothing(self):
        self.pick()
        webui._firstrun_finish(self.state, {"answers": {}})
        self.assertFalse(bundle.storage("account-a", "custom").exists())

    def test_stale_import_cannot_complete_wizard(self):
        with self.assertRaises(ValueError):
            webui._firstrun_finish(self.state, {"answers": {"import": "expired"}})

    def test_legacy_starter_create_requires_consent_and_closed_game(self):
        self.state.cs2_install = self.game
        self.assertFalse(webui._cfg_starter(self.state, {"create": True})["ok"])
        self.prefs["ui"]["cfg_write_ok"] = True
        self.running.return_value = True
        self.assertFalse(webui._cfg_starter(self.state, {"create": True})["ok"])
        self.assertFalse(self.game.exists())


class NativePicker(Sandbox):
    def test_multi_file_picker_returns_all_chosen_paths(self):
        from cs2cfg import picker
        with mock.patch.object(picker, "_run", return_value='["C:/a.cfg","C:/renamed.vcfg"]') as run:
            self.assertEqual(picker.pick_files(), ["C:/a.cfg", "C:/renamed.vcfg"])
        self.assertIn("$d.Multiselect = $true", run.call_args.args[0])
        self.assertIn("CS2 configs", run.call_args.args[0])

    def test_cancel_is_an_empty_list(self):
        from cs2cfg import picker
        with mock.patch.object(picker, "_run", return_value=None):
            self.assertEqual(picker.pick_files(), [])
