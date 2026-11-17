"""Settings following a Steam account between PCs, with no button pressed.

The cloud is a stand-in object holding one document, the way the Worker does,
so two "PCs" (two temporary cfg folders and two preference files) can be
synced through it and checked against each other. No network is touched.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import autosync  # noqa: E402
from sandbox import redirect_backups  # noqa: E402

ACCOUNT = "244173392"
STEAM64 = str(autosync.STEAM64_BASE + int(ACCOUNT))


class FakeCloud:
    class CloudError(RuntimeError):
        pass

    def __init__(self, steam_id=STEAM64, signed=True):
        self.document = None
        self.steam_id = steam_id
        self.signed = signed
        self.pushes = 0

    def signed_in(self):
        return self.signed

    def load_session(self):
        return {"token": "t", "steam_id": self.steam_id}

    def pull_settings(self):
        if self.document is None:
            return {"ok": True, "found": False, "settings": None}
        return {"ok": True, "found": True, "settings": json.loads(json.dumps(self.document))}

    def push_settings(self, settings):
        # Same limit the Worker enforces.
        if len(json.dumps(settings)) > 256 * 1024:
            raise self.CloudError("settings are limited to 262144 bytes")
        self.pushes += 1
        self.document = json.loads(json.dumps(settings))
        return {"ok": True}


class PC:
    """One machine: a CS2 cfg folder, a preferences dict, a sync-state file."""

    def __init__(self, root: Path, name: str):
        self.home = root / name
        self.cfg = self.home / "game" / "csgo" / "cfg"
        self.cfg.mkdir(parents=True)
        self.data = self.home / "data"
        self.data.mkdir()
        self.prefs = {"ui": {}, "accounts": {}}

    def load(self):
        return json.loads(json.dumps(self.prefs))

    def save(self, prefs):
        self.prefs = json.loads(json.dumps(prefs))

    def ui(self):
        return self.prefs["accounts"].setdefault(ACCOUNT, {})

    def sync(self, cloud, **kw):
        with mock.patch.object(autosync, "_state_path",
                               return_value=self.data / autosync.STATE_FILE):
            return autosync.run(ACCOUNT, self.cfg, "mrwhiteer",
                                load_prefs=self.load, save_prefs=self.save,
                                cloud_module=cloud, **kw)


class SyncCase(unittest.TestCase):
    def setUp(self):
        redirect_backups(self)
        self.root = Path(tempfile.mkdtemp(prefix="cs2cfg-autosync-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.cloud = FakeCloud()

        self.home = PC(self.root, "home")
        (self.home.cfg / "autoexec.cfg").write_text("exec mrwhiteer/autoexec\n", encoding="utf-8")
        mine = self.home.cfg / "mrwhiteer"
        (mine / "tools").mkdir(parents=True)
        (mine / "autoexec.vcfg").write_text('exec "mrwhiteer/tools/alias.vcfg"\n', encoding="utf-8")
        (mine / "tools" / "alias.vcfg").write_text('alias "+jt" "+jump"\n', encoding="utf-8")
        (mine / "console.log").write_text("not a setting\n", encoding="utf-8")
        self.home.ui().update({"intent": "competitive", "theme": "ember",
                               "cfg_folder": str(mine), "target_fps": "400"})
        self.home.prefs["ui"]["audio_output"] = "{home-headset}"
        self.home.prefs["ui"]["cfg_write_ok"] = True

        self.work = PC(self.root, "work")
        self.work.prefs["ui"]["cfg_write_ok"] = True


class TheNewPC(SyncCase):
    def test_home_pushes_then_the_new_pc_gets_everything(self):
        first = self.home.sync(self.cloud)
        self.assertEqual(first["action"], "push", first)
        self.assertEqual(first["files"], 3)

        second = self.work.sync(self.cloud)
        self.assertEqual(second["action"], "pull", second)
        self.assertEqual((self.work.cfg / "mrwhiteer" / "tools" / "alias.vcfg")
                         .read_text(encoding="utf-8"), 'alias "+jt" "+jump"\n')
        self.assertTrue((self.work.cfg / "autoexec.cfg").is_file())
        ui = self.work.prefs["accounts"][ACCOUNT]
        self.assertEqual(ui["intent"], "competitive")
        self.assertEqual(ui["theme"], "ember")
        # The collection is re-pointed at this PC's own cfg folder.
        self.assertEqual(Path(ui["cfg_folder"]), (self.work.cfg / "mrwhiteer").resolve())

    def test_logs_and_this_pcs_devices_stay_home(self):
        self.home.sync(self.cloud)
        self.work.sync(self.cloud)
        self.assertFalse((self.work.cfg / "mrwhiteer" / "console.log").exists())
        self.assertNotIn("audio_output", self.work.prefs["ui"])
        self.assertNotIn("audio_output", self.work.prefs["accounts"][ACCOUNT])

    def test_once_in_step_nothing_moves(self):
        self.home.sync(self.cloud)
        self.work.sync(self.cloud)
        self.assertEqual(self.work.sync(self.cloud)["action"], "none")
        self.assertEqual(self.home.sync(self.cloud)["action"], "none")

    def test_a_change_on_one_pc_reaches_the_other(self):
        self.home.sync(self.cloud)
        self.work.sync(self.cloud)

        alias = self.work.cfg / "mrwhiteer" / "tools" / "alias.vcfg"
        alias.write_text('alias "+jt" "+jump;-attack"\n', encoding="utf-8")
        self.assertEqual(self.work.sync(self.cloud)["action"], "push")

        self.assertEqual(self.home.sync(self.cloud)["action"], "pull")
        self.assertIn("-attack", (self.home.cfg / "mrwhiteer" / "tools" / "alias.vcfg")
                      .read_text(encoding="utf-8"))

    def test_a_pull_is_backed_up_first(self):
        self.home.sync(self.cloud)
        (self.work.cfg / "autoexec.cfg").write_text("old\n", encoding="utf-8")
        with mock.patch("cs2cfg.backup.BackupSession.add") as add:
            self.work.sync(self.cloud)
        backed = {Path(c.args[0]).name for c in add.call_args_list}
        self.assertIn("autoexec.cfg", backed)


class Permission(SyncCase):
    def test_files_wait_until_the_app_may_write(self):
        self.home.sync(self.cloud)
        self.work.prefs["ui"]["cfg_write_ok"] = False
        out = self.work.sync(self.cloud)
        self.assertEqual(out["waiting"], 3)
        self.assertFalse((self.work.cfg / "autoexec.cfg").exists())
        # Preferences still came across.
        self.assertEqual(self.work.prefs["accounts"][ACCOUNT]["intent"], "competitive")

        self.work.prefs["ui"]["cfg_write_ok"] = True
        self.assertEqual(self.work.sync(self.cloud)["action"], "pull")
        self.assertTrue((self.work.cfg / "autoexec.cfg").exists())


class WhoseSettings(SyncCase):
    def test_not_signed_in_does_nothing(self):
        self.cloud.signed = False
        out = self.home.sync(self.cloud)
        self.assertFalse(out["ok"])
        self.assertEqual(self.cloud.pushes, 0)

    def test_another_steam_account_is_never_written_to(self):
        self.cloud.steam_id = str(autosync.STEAM64_BASE + 1)
        out = self.home.sync(self.cloud)
        self.assertFalse(out["ok"])
        self.assertIn("different Steam account", out["reason"])
        self.assertEqual(self.cloud.pushes, 0)

    def test_turned_off_stays_off_unless_asked(self):
        self.home.prefs["ui"]["sync_auto"] = False
        self.assertFalse(self.home.sync(self.cloud)["ok"])
        self.assertEqual(self.home.sync(self.cloud, force=True)["action"], "push")

    def test_other_cloud_contents_survive_a_push(self):
        self.cloud.document = {"schema": 1, "collections": {"mrwhiteer": {"files": {}}}}
        self.home.sync(self.cloud)
        self.assertIn("collections", self.cloud.document)
        self.assertIn(ACCOUNT, self.cloud.document["autosync"])


class Hostile(SyncCase):
    def test_paths_from_the_cloud_cannot_escape_the_cfg_folder(self):
        bundle = {"prefs": {"intent": "balanced", "audio_output": "{evil}"},
                  "collection": "../../outside",
                  "files": {"../../evil.cfg": "x", "C:/evil.cfg": "x",
                            "/etc/evil.cfg": "x", "ok/fine.cfg": "fine",
                            "notes.txt": "x"}}
        packed = autosync.pack(bundle)
        self.cloud.document = {"autosync": {ACCOUNT: packed}}
        out = self.work.sync(self.cloud)
        self.assertEqual(out["written"], ["ok/fine.cfg"])
        self.assertFalse((self.root / "work" / "game" / "evil.cfg").exists())
        ui = self.work.prefs["accounts"][ACCOUNT]
        self.assertNotIn("audio_output", ui)
        self.assertNotIn("cfg_folder", ui)

    def test_damaged_cloud_copy_is_reported_not_raised(self):
        self.cloud.document = {"autosync": {ACCOUNT: {"hash": "x", "data": "!!!"}}}
        out = self.work.sync(self.cloud)
        self.assertFalse(out["ok"])

    def test_too_big_is_refused_before_it_is_sent(self):
        import os

        for n in (1, 2):
            (self.home.cfg / "mrwhiteer" / f"huge{n}.cfg").write_bytes(
                os.urandom(200 * 1024).hex()[:250 * 1024].encode())
        out = self.home.sync(self.cloud)
        self.assertFalse(out["ok"])
        self.assertIn("too large", out["reason"])


class Deciding(unittest.TestCase):
    def test_the_three_way_table(self):
        d = autosync.decide
        self.assertEqual(d("a", None, None), "push")
        self.assertEqual(d("a", None, None, local_empty=True), "none")
        self.assertEqual(d("a", "a", None), "none")
        self.assertEqual(d("a", "b", "a"), "pull")
        self.assertEqual(d("a", "b", "b"), "push")
        self.assertEqual(d("a", "b", None, local_empty=True), "pull")
        # A PC that has never synced takes the cloud's copy first, even with
        # newer files of its own -- they are backed up, and any it alone has
        # go up on the next round.
        self.assertEqual(d("a", "b", None, local_time=30, remote_time=20), "pull")
        self.assertEqual(d("a", "b", "c", local_time=10, remote_time=20), "pull")
        self.assertEqual(d("a", "b", "c", local_time=30, remote_time=20), "push")

    def test_steam_ids(self):
        self.assertEqual(autosync.account_from_steam64(STEAM64), ACCOUNT)
        self.assertEqual(autosync.account_from_steam64(ACCOUNT), ACCOUNT)
        self.assertEqual(autosync.account_from_steam64(None), "")


if __name__ == "__main__":
    unittest.main()
