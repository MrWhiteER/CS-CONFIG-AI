"""PC settings go back to the player's own whenever the app is not running."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg import pcstate, steam


class FakePC:
    """Stands in for the registry, Steam and the driver: one dict of values."""

    def __init__(self) -> None:
        self.values = {}
        self.blocked = {}
        self.writes = []

    def read(self, kind, ident):
        return self.values.get((kind, ident))

    def write(self, kind, ident, value, *, live_ok, persist):
        why = self.blocked.get(kind)
        if why and not live_ok:
            raise pcstate.Waiting(why)
        self.writes.append((kind, ident, value))
        self.values[(kind, ident)] = value


class Base(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="cs2cfg-pcstate-")
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.pc = FakePC()
        for target, value in (
            ("store_path", mock.Mock(return_value=self.dir / pcstate.STORE)),
            ("_read", self.pc.read),
            ("_write", self.pc.write),
            ("arm_next_sign_in", mock.Mock()),
            ("disarm_next_sign_in", mock.Mock()),
        ):
            patch = mock.patch.object(pcstate, target, value)
            patch.start()
            self.addCleanup(patch.stop)
        pcstate.enable(True)
        self.addCleanup(pcstate.enable, False)
        # No desktop-mode record in a test.
        patch = mock.patch("cs2cfg.deskmode.outstanding", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def parts(self):
        return json.loads((self.dir / pcstate.STORE).read_text())["parts"]


class Recording(Base):
    def test_first_change_keeps_the_original(self):
        pcstate.note("power_plan", "active", "balanced", "ultimate")
        pcstate.note("power_plan", "active", "ultimate", "high")
        part = self.parts()["power_plan|active"]
        self.assertEqual(part["original"], "balanced")
        self.assertEqual(part["ours"], "high")
        self.assertEqual(part["state"], "ours")

    def test_change_back_to_original_drops_the_record(self):
        pcstate.note("power_plan", "active", "balanced", "ultimate")
        pcstate.note("power_plan", "active", "ultimate", "balanced")
        self.assertEqual(self.parts(), {})

    def test_off_by_default_and_silent_while_putting_back(self):
        pcstate.enable(False)
        pcstate.note("power_plan", "active", "a", "b")
        self.assertFalse((self.dir / pcstate.STORE).exists())
        pcstate.enable(True)
        with pcstate.restoring():
            pcstate.note("power_plan", "active", "a", "b")
        self.assertFalse((self.dir / pcstate.STORE).exists())


class PuttingBack(Base):
    def test_puts_back_what_still_holds_the_apps_value(self):
        self.pc.values[("win_graphics", "cs2.exe")] = "GpuPreference=2;"
        pcstate.note("win_graphics", "cs2.exe", None, "GpuPreference=2;")
        result = pcstate.restore_all()
        self.assertIsNone(self.pc.values[("win_graphics", "cs2.exe")])
        self.assertEqual(result["items"][0]["result"], "restored")
        self.assertEqual(self.parts()["win_graphics|cs2.exe"]["state"], "original")

    def test_leaves_a_setting_the_player_changed_themselves(self):
        pcstate.note("power_plan", "active", "balanced", "ultimate")
        self.pc.values[("power_plan", "active")] = "power saver"
        result = pcstate.restore_all()
        self.assertEqual(self.pc.writes, [])
        self.assertEqual(result["items"][0]["result"], "left")
        self.assertEqual(self.parts(), {})

    def test_steam_files_wait_for_steam_to_close(self):
        self.pc.blocked["launch_options"] = "waiting for Steam to close"
        self.pc.values[("launch_options", "u")] = "-novid -high"
        pcstate.note("launch_options", "u", "-novid", "-novid -high")
        result = pcstate.restore_all()
        self.assertTrue(result["waiting"])
        self.assertEqual(result["items"][0]["text"], "Waiting for Steam to close")
        self.assertEqual(self.parts()["launch_options|u"]["state"], "ours")

    def test_one_game_changes_are_put_back_but_never_set_again(self):
        self.pc.values[("scaling", "7")] = 2
        pcstate.note("scaling", "7", 5, 2, reapply=False)
        pcstate.restore_all()
        self.assertEqual(self.pc.values[("scaling", "7")], 5)
        self.assertEqual(self.parts(), {})

    def test_uninstall_does_not_wait_for_the_game(self):
        self.pc.blocked["scaling"] = "waiting for CS2 to close"
        self.pc.values[("scaling", "7")] = 2
        pcstate.note("scaling", "7", 5, 2)
        self.assertEqual(pcstate.restore_all()["items"][0]["result"], "waiting")
        self.assertEqual(pcstate.restore_all(live_ok=True)["items"][0]["result"], "restored")


class SettingAgain(Base):
    def test_app_start_sets_its_value_again(self):
        self.pc.values[("fullscreen_opt", "cs2.exe")] = "~ X"
        pcstate.note("fullscreen_opt", "cs2.exe", None, "~ X")
        pcstate.restore_all()
        result = pcstate.reapply_all()
        self.assertEqual(self.pc.values[("fullscreen_opt", "cs2.exe")], "~ X")
        self.assertEqual(result["items"][0]["result"], "applied")

    def test_player_change_while_closed_wins(self):
        self.pc.values[("power_plan", "active")] = "ultimate"
        pcstate.note("power_plan", "active", "balanced", "ultimate")
        pcstate.restore_all()
        self.pc.values[("power_plan", "active")] = "power saver"
        result = pcstate.reapply_all()
        self.assertEqual(self.pc.values[("power_plan", "active")], "power saver")
        self.assertEqual(result["items"][0]["result"], "left")

    def test_file_put_back_by_the_waiter_is_set_again(self):
        # The waiter changed Steam's file after the app was gone, so the
        # record still says "ours"; the file says original.
        self.pc.values[("launch_options", "u")] = "-novid"
        pcstate.note("launch_options", "u", "-novid", "-novid -high")
        pcstate.reapply_all()
        self.assertEqual(self.pc.values[("launch_options", "u")], "-novid -high")


class LaunchOptions(unittest.TestCase):
    def test_region_lock_ping_limit_stays_while_app_is_closed(self):
        part = {"kind": "launch_options", "original": "-novid",
                "ours": "-novid -high +mm_dedicated_search_maxping 95"}
        self.assertEqual(pcstate.restore_target(part),
                         "-novid +mm_dedicated_search_maxping 95")
        self.assertEqual(pcstate.restore_target(part, uninstalling=True), "-novid")

    def test_options_handed_to_one_launch_keep_their_values(self):
        user = mock.Mock(path=Path("u"))
        stored = {"parts": {"launch_options|u": {
            "kind": "launch_options", "state": "original", "reapply": True,
            "original": "-novid -refresh 60", "ours": "-novid -refresh 144 -high"}}}
        with mock.patch.object(pcstate, "_load", return_value=stored):
            self.assertEqual(pcstate.for_launch(user), "-refresh 144 -high")


class SteamHook(unittest.TestCase):
    def test_writing_launch_options_is_recorded(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        user_dir = root / "userdata" / "123"
        (user_dir / "config").mkdir(parents=True)
        (user_dir / "config" / "localconfig.vdf").write_text(
            '"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n'
            '\t\t\t\t"apps"\n\t\t\t\t{\n\t\t\t\t\t"730"\n\t\t\t\t\t{\n'
            '\t\t\t\t\t\t"LaunchOptions"\t\t"-novid"\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n',
            encoding="utf-8")
        user = steam.SteamUser(account_id="123", path=user_dir)
        with mock.patch.object(pcstate, "note") as note, \
                mock.patch.object(steam, "steam_running", return_value=False):
            steam.write_launch_options(user, "-novid -high")
        note.assert_called_once_with("launch_options", str(user_dir), "-novid", "-novid -high")


class Waiter(Base):
    def test_waiter_gets_only_lines_the_app_set(self):
        with mock.patch.object(pcstate, "waiter_dir", return_value=self.dir / "w"), \
                mock.patch.object(pcstate.sys, "platform", "linux"):
            pcstate.note("launch_options", str(self.dir / "123"), "-novid", '-novid +exec "a b"')
            pcstate.note("window_mode", f"{self.dir / '123'}|setting.fullscreen", "1", "0")
            pcstate.note("power_plan", "active", "a", "b")
            script = pcstate._write_file_waiter()
        jobs = json.loads((self.dir / "w" / "jobs.json").read_text())["jobs"]
        self.assertEqual(sorted(j["type"] for j in jobs), ["launch", "video"])
        launch = next(j for j in jobs if j["type"] == "launch")
        self.assertTrue(launch["path"].endswith("localconfig.vdf"))
        self.assertEqual(launch["ours"], '-novid +exec "a b"')
        self.assertIn("Remove-Item -LiteralPath $MyInvocation.MyCommand.Path", script.read_text())
        self.assertNotIn("Invoke-Expression", script.read_text())
        self.assertTrue(script.read_text().isascii())


class Lifecycle(Base):
    def test_update_skips_the_put_back(self):
        with mock.patch("cs2cfg.paths.user_data_dir", return_value=self.dir), \
                mock.patch.object(pcstate, "_wait_for_pid"), \
                mock.patch.object(pcstate, "put_back") as put_back:
            pcstate.mark_updating()
            self.assertEqual(pcstate.guard(1)["skipped"], "update")
            put_back.assert_not_called()

    def test_guard_stands_down_if_the_app_is_open_again(self):
        with mock.patch.object(pcstate, "_wait_for_pid"), \
                mock.patch.object(pcstate, "_take_updating_mark", return_value=False), \
                mock.patch.object(pcstate, "app_running", return_value=True), \
                mock.patch.object(pcstate, "put_back") as put_back:
            pcstate.guard(1, sleep=lambda s: None)
            put_back.assert_not_called()

    def test_status_reads_as_plain_words(self):
        pcstate.note("window_mode", "u|setting.fullscreen", "1", "0")
        pcstate.note("scaling", "7", 5, 2)
        labels = [i["label"] for i in pcstate.status()["items"]]
        self.assertEqual(labels, ["NVIDIA screen scaling", "CS2 fullscreen or window"])
        for label in labels:
            self.assertNotIn("_", label)
            self.assertNotIn("setting.", label)


class Cli(unittest.TestCase):
    def test_commands_exist(self):
        from cs2cfg import cli

        parser = cli.build_parser()
        self.assertEqual(parser.parse_args(["pc-guard", "--pid", "5"]).pid, 5)
        self.assertEqual(parser.parse_args(["pc-restore"]).command, "pc-restore")


if __name__ == "__main__":
    unittest.main()
