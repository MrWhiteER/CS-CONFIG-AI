"""Tests for the two published editions and how each updates itself.

A portable copy owns its folder and updates by copying files over it. An
installed copy is a registered Windows installation and updates by running the
next Setup.exe -- copying files over it would leave its Add/Remove Programs
entry, its shortcuts and its uninstaller describing a version that is no
longer there.

Nothing here runs an installer or a swap script. The scripts are generated and
read; actually running one would replace the application.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import paths, updates  # noqa: E402

BOTH_ASSETS = {
    "tag_name": "v1.4.0",
    "name": "1.4.0",
    "body": "notes",
    "assets": [
        {"name": "cs2-autoconfig-1.4.0-win64.zip",
         "browser_download_url": "https://x/app.zip", "size": 100},
        {"name": "cs2-autoconfig-1.4.0-Setup.exe",
         "browser_download_url": "https://x/Setup.exe", "size": 200},
    ],
}


class WhichEdition(unittest.TestCase):
    def test_running_from_source_is_neither(self):
        with mock.patch.object(paths, "is_frozen", lambda: False):
            self.assertEqual(paths.install_kind(), paths.SOURCE)

    def test_an_unpacked_copy_is_portable(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch.object(paths, "is_frozen", lambda: True), \
             mock.patch.object(paths, "app_dir", lambda: Path(tmp.name)), \
             mock.patch.object(paths, "_registered_install", lambda: None):
            self.assertEqual(paths.install_kind(), paths.PORTABLE)

    def test_the_registry_saying_this_folder_means_installed(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        here = Path(tmp.name)
        with mock.patch.object(paths, "is_frozen", lambda: True), \
             mock.patch.object(paths, "app_dir", lambda: here), \
             mock.patch.object(paths, "_registered_install", lambda: here):
            self.assertEqual(paths.install_kind(), paths.INSTALLED)

    def test_an_installation_somewhere_else_does_not_claim_this_copy(self):
        """A portable copy on a stick, on a machine that also has it installed."""
        tmp = tempfile.TemporaryDirectory()
        other = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(other.cleanup)
        with mock.patch.object(paths, "is_frozen", lambda: True), \
             mock.patch.object(paths, "app_dir", lambda: Path(tmp.name)), \
             mock.patch.object(paths, "_registered_install",
                               lambda: Path(other.name)):
            self.assertEqual(paths.install_kind(), paths.PORTABLE)

    def test_the_uninstaller_beside_it_is_a_second_opinion(self):
        """For when the registry entry has been cleaned away but it is still installed."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        here = Path(tmp.name)
        (here / "unins000.exe").write_text("", encoding="utf-8")
        with mock.patch.object(paths, "is_frozen", lambda: True), \
             mock.patch.object(paths, "app_dir", lambda: here), \
             mock.patch.object(paths, "_registered_install", lambda: None):
            self.assertEqual(paths.install_kind(), paths.INSTALLED)

    def test_a_missing_registry_is_not_an_error(self):
        """Reading it must never raise; "not installed" is the safe answer."""
        self.assertIn(paths._registered_install(), (None,) + tuple(
            [paths._registered_install()]))


class PickingTheRightAsset(unittest.TestCase):
    def test_portable_takes_the_zip(self):
        release = updates.parse_release(BOTH_ASSETS, paths.PORTABLE)
        self.assertEqual(release.asset_name, "cs2-autoconfig-1.4.0-win64.zip")
        self.assertFalse(updates.is_installer(release))

    def test_installed_takes_the_installer(self):
        release = updates.parse_release(BOTH_ASSETS, paths.INSTALLED)
        self.assertEqual(release.asset_name, "cs2-autoconfig-1.4.0-Setup.exe")
        self.assertTrue(updates.is_installer(release))

    def test_a_release_missing_this_edition_offers_no_download(self):
        """Better an empty download than the wrong edition's file."""
        zip_only = dict(BOTH_ASSETS, assets=BOTH_ASSETS["assets"][:1])
        release = updates.parse_release(zip_only, paths.INSTALLED)
        self.assertEqual(release.asset_url, "")
        self.assertEqual(release.version, "1.4.0", "the release is still known")


class HowEachInstalls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = mock.patch.object(updates, "staging_dir",
                                    lambda: self.root / "updates")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _ready(self, release, with_setup=False):
        ready = updates.ready_dir(release)
        ready.mkdir(parents=True, exist_ok=True)
        (ready / ".complete").write_text(release.version, encoding="utf-8")
        if with_setup:
            path = updates.archive_path(release)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("not really an installer", encoding="utf-8")

    def test_the_installer_script_runs_setup_and_never_copies(self):
        release = updates.Release(version="1.4.0",
                                  asset_name="cs2-autoconfig-1.4.0-Setup.exe")
        self._ready(release, with_setup=True)
        with mock.patch.object(updates, "is_frozen", lambda: True), \
             mock.patch.object(updates, "_spawn") as spawn:
            script = updates.install(release)
        spawn.assert_called_once()

        body = script.read_text(encoding="utf-8")
        # The flags on the command itself, not the comment above it that
        # explains which one was chosen.
        command = next(l for l in body.splitlines()
                       if l.startswith("start ") and "/wait" in l)
        self.assertIn("/SILENT", command)
        self.assertNotIn("/VERYSILENT", command,
                         "a large copy with nothing on screen reads as a hang")
        self.assertIn("/DIR=", command, "the target must be pinned, not looked up")
        self.assertNotIn("robocopy", body)
        self.assertNotIn("@@", body, "a token was left unfilled")

    def test_the_installer_script_waits_before_it_runs_anything(self):
        release = updates.Release(version="1.4.0",
                                  asset_name="cs2-autoconfig-1.4.0-Setup.exe")
        self._ready(release, with_setup=True)
        with mock.patch.object(updates, "is_frozen", lambda: True), \
             mock.patch.object(updates, "_spawn"):
            body = updates.install(release).read_text(encoding="utf-8")
        order = [body.index(":waitpid"), body.index(":waitlocks"),
                 body.index("\n:runsetup")]
        self.assertEqual(order, sorted(order))

    def test_a_failed_install_says_the_old_version_is_still_there(self):
        release = updates.Release(version="1.4.0",
                                  asset_name="cs2-autoconfig-1.4.0-Setup.exe")
        self._ready(release, with_setup=True)
        with mock.patch.object(updates, "is_frozen", lambda: True), \
             mock.patch.object(updates, "_spawn"):
            body = updates.install(release).read_text(encoding="utf-8")
        self.assertIn("still installed", body)

    def test_portable_still_copies_files(self):
        release = updates.Release(version="1.4.0",
                                  asset_name="cs2-autoconfig-1.4.0-win64.zip")
        self._ready(release)
        with mock.patch.object(updates, "is_frozen", lambda: True), \
             mock.patch.object(updates, "_spawn"):
            body = updates.install(release).read_text(encoding="utf-8")
        self.assertIn("robocopy", body)
        self.assertNotIn("/SILENT", body)

    def test_a_missing_installer_on_disk_is_refused(self):
        release = updates.Release(version="1.4.0",
                                  asset_name="cs2-autoconfig-1.4.0-Setup.exe")
        self._ready(release, with_setup=False)
        with mock.patch.object(updates, "is_frozen", lambda: True):
            with self.assertRaisesRegex(RuntimeError, "not on disk"):
                updates.install(release)


class TheInstallerScript(unittest.TestCase):
    """The Inno script itself, read as text."""

    def setUp(self):
        self.iss = (Path(__file__).resolve().parents[1] / "installer.iss") \
            .read_text(encoding="utf-8")

    def test_the_app_id_matches_the_one_the_program_looks_for(self):
        """They are how Windows recognises an update to the same install."""
        guid = paths.APP_ID.strip("{}")
        self.assertIn(guid, self.iss)

    def test_it_installs_per_user_so_nothing_needs_elevating(self):
        self.assertIn("PrivilegesRequired=lowest", self.iss)
        self.assertIn("{localappdata}", self.iss)

    def test_the_version_comes_from_outside(self):
        """So it can only ever come from the same place as everything else."""
        self.assertIn("#ifndef AppVersion", self.iss)

    def test_uninstalling_keeps_the_users_own_data(self):
        removed = self.iss.split("[UninstallDelete]")[1]
        self.assertIn("cs2cfg-data\\updates", removed)
        self.assertNotIn('Name: "{app}\\cs2cfg-data"', removed,
                         "preferences and backups must survive an uninstall")


if __name__ == "__main__":
    unittest.main()
