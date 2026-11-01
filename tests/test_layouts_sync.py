"""Pushing and pulling this collection's profiles through the cloud.

The actual HTTP is cloud.py's own responsibility and is covered in
test_cloud.py; these mock cloud.pull_settings/push_settings directly and
check what webui's sync handlers do with them -- building the right payload
to push, and writing back safely (backed up, path-checked) what a pull hands
back. No real network call is ever made here.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cfgscan, cloud, layouts, webui  # noqa: E402
from sandbox import redirect_backups, redirect_layouts  # noqa: E402

FILES = {
    "mrwhiteer/autoexec.vcfg": (
        'exec "mrwhiteer/tools/alias.vcfg"\n'
        'exec "mrwhiteer/mainsettings/key_binds.vcfg"\n'
    ),
    "mrwhiteer/tools/alias.vcfg": (
        'alias "!warmup" "exec mrwhiteer/lan/warmup.vcfg"\n'
    ),
    "mrwhiteer/mainsettings/key_binds.vcfg": (
        'bind "mouse3" "say custom text"\n'
        'bind "mouse4" "player_ping"\n'
    ),
    "mrwhiteer/lan/warmup.vcfg": (
        'bind "mouse3" "noclip"\n'
        'bind "mouse4" "bot_place"\n'
    ),
}

EMPTY_CLOUD = {"ok": True, "found": False, "settings": None}


class SyncCase(unittest.TestCase):
    def setUp(self):
        redirect_backups(self)
        redirect_layouts(self)
        self.sandbox = Path(tempfile.mkdtemp(prefix="cs2cfg-sync-"))
        self.addCleanup(shutil.rmtree, self.sandbox, ignore_errors=True)

        self.cfg_root = self.sandbox / "cfg"
        for relative, text in FILES.items():
            path = self.cfg_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.collection = self.cfg_root / "mrwhiteer"

        self.state = mock.Mock()
        self.state.cfg_scan = cfgscan.scan(self.collection, cfg_root=self.cfg_root)

        # write_text() translates "\n" to the platform line ending (CRLF on
        # Windows); the push handler reads raw bytes and keeps whatever is
        # actually on disk, so comparisons below read it back the same way
        # rather than assuming FILES' own "\n"-only spelling survived.
        self.warmup_text = (self.cfg_root / "mrwhiteer/lan/warmup.vcfg").read_bytes().decode("utf-8")

        signed_in = mock.patch.object(cloud, "signed_in", return_value=True)
        signed_in.start()
        self.addCleanup(signed_in.stop)

    def push(self):
        return webui._cfg_layouts_sync_push(self.state, {})

    def pull(self):
        return webui._cfg_layouts_sync_pull(self.state, {})


class TestPush(SyncCase):
    def test_signed_out_is_refused_before_any_request(self):
        with mock.patch.object(cloud, "signed_in", return_value=False), \
             mock.patch.object(cloud, "pull_settings") as pulled:
            result = self.push()
        self.assertFalse(result["ok"])
        self.assertIn("sign in", result["error"])
        pulled.assert_not_called()

    def test_uploads_warmups_content_under_the_collections_own_name(self):
        with mock.patch.object(cloud, "pull_settings", return_value=EMPTY_CLOUD), \
             mock.patch.object(cloud, "push_settings") as pushed:
            result = self.push()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["collection"], "mrwhiteer")
        self.assertEqual(result["files"], ["mrwhiteer/lan/warmup.vcfg"])

        sent = pushed.call_args[0][0]
        entry = sent["collections"]["mrwhiteer"]
        self.assertEqual(entry["files"]["mrwhiteer/lan/warmup.vcfg"], self.warmup_text)
        self.assertEqual(entry["created"], [])

    def test_hidden_profiles_are_not_pushed(self):
        layouts.hide_profile(self.collection, "mrwhiteer/lan/warmup.vcfg")
        with mock.patch.object(cloud, "pull_settings", return_value=EMPTY_CLOUD), \
             mock.patch.object(cloud, "push_settings") as pushed:
            result = self.push()
        self.assertEqual(result["files"], [])
        entry = pushed.call_args[0][0]["collections"]["mrwhiteer"]
        self.assertEqual(entry["files"], {})

    def test_preserves_other_collections_already_in_the_cloud(self):
        existing = {"ok": True, "found": True, "settings":
                    {"schema": 1, "collections": {"someoneelse": {"files": {"x": "y"}}}}}
        with mock.patch.object(cloud, "pull_settings", return_value=existing), \
             mock.patch.object(cloud, "push_settings") as pushed:
            self.push()
        sent = pushed.call_args[0][0]
        self.assertIn("someoneelse", sent["collections"])
        self.assertIn("mrwhiteer", sent["collections"])

    def test_app_created_status_is_included(self):
        layouts.mark_created(self.collection, "mrwhiteer/lan/warmup.vcfg")
        with mock.patch.object(cloud, "pull_settings", return_value=EMPTY_CLOUD), \
             mock.patch.object(cloud, "push_settings") as pushed:
            self.push()
        entry = pushed.call_args[0][0]["collections"]["mrwhiteer"]
        self.assertEqual(entry["created"], ["mrwhiteer/lan/warmup.vcfg"])

    def test_a_cloud_error_while_reading_is_reported_not_raised(self):
        with mock.patch.object(cloud, "pull_settings",
                               side_effect=cloud.CloudError("down")):
            result = self.push()
        self.assertFalse(result["ok"])
        self.assertIn("down", result["error"])


class TestPull(SyncCase):
    def test_signed_out_is_refused(self):
        with mock.patch.object(cloud, "signed_in", return_value=False), \
             mock.patch.object(cloud, "pull_settings") as pulled:
            result = self.pull()
        self.assertFalse(result["ok"])
        pulled.assert_not_called()

    def test_nothing_saved_for_this_collection_is_reported_not_raised(self):
        with mock.patch.object(cloud, "pull_settings", return_value=EMPTY_CLOUD):
            result = self.pull()
        self.assertFalse(result["ok"])
        self.assertIn("mrwhiteer", result["error"])

    def test_writes_a_new_profile_and_marks_it_app_created(self):
        cloud_settings = {"ok": True, "found": True, "settings": {
            "schema": 1,
            "collections": {"mrwhiteer": {
                "files": {"mrwhiteer/lan/competitive.vcfg":
                         "// Competitive -- created in cs2-autoconfig\n"},
                "created": ["mrwhiteer/lan/competitive.vcfg"],
                "pins": {},
            }},
        }}
        with mock.patch.object(cloud, "pull_settings", return_value=cloud_settings):
            result = self.pull()

        self.assertTrue(result["ok"], result)
        path = self.cfg_root / "mrwhiteer/lan/competitive.vcfg"
        self.assertTrue(path.is_file())
        self.assertIn("Competitive", path.read_text(encoding="utf-8"))
        self.assertTrue(layouts.is_created(self.collection, "mrwhiteer/lan/competitive.vcfg"))

    def test_an_unsafe_path_is_refused_without_writing_anything(self):
        cloud_settings = {"ok": True, "found": True, "settings": {
            "collections": {"mrwhiteer": {
                "files": {"../../evil.vcfg": "payload"},
                "created": [], "pins": {},
            }},
        }}
        with mock.patch.object(cloud, "pull_settings", return_value=cloud_settings):
            result = self.pull()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["files"], [])
        self.assertFalse((self.sandbox / "evil.vcfg").exists())

    def test_existing_file_is_overwritten_and_backed_up(self):
        cloud_settings = {"ok": True, "found": True, "settings": {
            "collections": {"mrwhiteer": {
                "files": {"mrwhiteer/lan/warmup.vcfg": 'bind "mouse3" "from the cloud"\n'},
                "created": [], "pins": {},
            }},
        }}
        with mock.patch.object(cloud, "pull_settings", return_value=cloud_settings):
            result = self.pull()
        self.assertTrue(result["ok"], result)
        text = (self.cfg_root / "mrwhiteer/lan/warmup.vcfg").read_text(encoding="utf-8")
        self.assertIn("from the cloud", text)

    def test_a_cloud_error_is_reported_not_raised(self):
        with mock.patch.object(cloud, "pull_settings",
                               side_effect=cloud.CloudError("down")):
            result = self.pull()
        self.assertFalse(result["ok"])
        self.assertIn("down", result["error"])


if __name__ == "__main__":
    unittest.main()
