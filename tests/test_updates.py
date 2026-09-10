"""Tests for the GitHub update client.

Nothing here touches the network. The release JSON is a fixture, the archive
is built in a temporary directory, and the staging directory is redirected
there too -- so no test can reach the real data directory, the real repository,
or the CS2 configuration folder.

The install step is only ever asked for its refusals. Actually running it
would spawn a script whose entire purpose is to overwrite the application, so
the tests stop at the point where it would.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import updates  # noqa: E402

RELEASE_JSON = {
    "tag_name": "v1.4.0",
    "name": "1.4.0 — keyboard canvas",
    "body": "Drag and resize the models.",
    "html_url": "https://github.com/someone/cs2-autoconfig/releases/tag/v1.4.0",
    "published_at": "2026-09-10T12:00:00Z",
    "assets": [
        {"name": "notes.txt", "browser_download_url": "https://x/notes.txt",
         "size": 12},
        {"name": "cs2-autoconfig-1.4.0-win64.zip",
         "browser_download_url": "https://x/app.zip",
         "size": 2048,
         "digest": "sha256:" + "ab" * 32},
    ],
}


class Versions(unittest.TestCase):
    def test_parses_tags_with_and_without_a_v(self):
        self.assertEqual(updates.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(updates.parse_version("1.2.3"), (1, 2, 3))

    def test_pads_short_versions(self):
        self.assertEqual(updates.parse_version("2"), (2, 0, 0))
        self.assertEqual(updates.parse_version("2.1"), (2, 1, 0))

    def test_compares_numerically_not_as_text(self):
        # The bug this guards: "1.10.0" sorts before "1.9.9" as a string.
        self.assertTrue(updates.is_newer("1.10.0", "1.9.9"))
        self.assertFalse(updates.is_newer("1.9.9", "1.10.0"))

    def test_same_version_is_not_newer(self):
        self.assertFalse(updates.is_newer("1.0.0", "1.0.0"))

    def test_junk_does_not_raise(self):
        self.assertEqual(updates.parse_version(""), (0, 0, 0))
        self.assertEqual(updates.parse_version("not-a-version"), (0, 0, 0))


class ParsingReleases(unittest.TestCase):
    def test_reads_the_fields_the_panel_shows(self):
        release = updates.parse_release(RELEASE_JSON)
        self.assertEqual(release.version, "1.4.0")
        self.assertEqual(release.name, "1.4.0 — keyboard canvas")
        self.assertEqual(release.notes, "Drag and resize the models.")
        self.assertTrue(release.page.endswith("/v1.4.0"))

    def test_picks_the_zip_and_ignores_other_attachments(self):
        release = updates.parse_release(RELEASE_JSON)
        self.assertEqual(release.asset_name, "cs2-autoconfig-1.4.0-win64.zip")
        self.assertEqual(release.asset_size, 2048)
        self.assertEqual(release.asset_sha256, "ab" * 32)

    def test_survives_a_release_with_no_assets(self):
        release = updates.parse_release({"tag_name": "v2.0.0", "assets": []})
        self.assertEqual(release.version, "2.0.0")
        self.assertEqual(release.asset_url, "")


class Staging(unittest.TestCase):
    """Downloading, verifying and unpacking, with the network stubbed out."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        patcher = mock.patch.object(updates, "staging_dir",
                                    lambda: self.root / "updates")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def _zip_bytes(self, names=("CS2 Launcher.exe", "cs2cfg.exe")) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            for name in names:
                bundle.writestr(name, "binary would go here")
        return buffer.getvalue()

    def _serve(self, payload: bytes):
        """Stand in for urlopen, returning payload as one response."""
        response = mock.MagicMock()
        response.read.side_effect = [payload, b""]
        response.headers = {"Content-Length": str(len(payload))}
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        return response

    def test_downloads_unpacks_and_marks_it_ready(self):
        payload = self._zip_bytes()
        release = updates.Release(version="1.4.0", asset_name="app.zip",
                                  asset_url="https://x/app.zip",
                                  asset_size=len(payload))
        self.assertFalse(updates.is_ready(release))
        with mock.patch.object(updates.urllib.request, "urlopen",
                               return_value=self._serve(payload)):
            updates.download(release)

        self.assertTrue(updates.is_ready(release))
        ready = updates.ready_dir(release)
        self.assertTrue((ready / "CS2 Launcher.exe").is_file())
        self.assertTrue((ready / "cs2cfg.exe").is_file())

    def test_reports_progress_as_it_goes(self):
        payload = self._zip_bytes()
        release = updates.Release(version="1.4.0", asset_url="https://x/app.zip",
                                  asset_size=len(payload))
        seen = []
        with mock.patch.object(updates.urllib.request, "urlopen",
                               return_value=self._serve(payload)):
            updates.download(release, progress=lambda d, t: seen.append((d, t)))
        self.assertTrue(seen)
        self.assertEqual(seen[-1], (len(payload), len(payload)))

    def test_a_short_download_is_rejected_and_leaves_nothing_behind(self):
        payload = self._zip_bytes()
        release = updates.Release(version="1.4.0", asset_url="https://x/app.zip",
                                  asset_size=len(payload) + 500)
        with mock.patch.object(updates.urllib.request, "urlopen",
                               return_value=self._serve(payload)):
            with self.assertRaises(RuntimeError):
                updates.download(release)
        self.assertFalse(updates.is_ready(release))

    def test_a_wrong_checksum_is_rejected(self):
        payload = self._zip_bytes()
        release = updates.Release(version="1.4.0", asset_url="https://x/app.zip",
                                  asset_size=len(payload),
                                  asset_sha256="00" * 32)
        with mock.patch.object(updates.urllib.request, "urlopen",
                               return_value=self._serve(payload)):
            with self.assertRaisesRegex(RuntimeError, "checksum"):
                updates.download(release)
        self.assertFalse(updates.is_ready(release))

    def test_a_release_with_no_archive_is_refused(self):
        with self.assertRaises(RuntimeError):
            updates.download(updates.Release(version="1.4.0"))

    def test_an_archive_escaping_the_folder_is_refused(self):
        """A zip naming ..\\.. must not be allowed to write outside staging."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr("../../escaped.txt", "no")
        archive = self.root / "evil.zip"
        archive.write_bytes(buffer.getvalue())

        release = updates.Release(version="1.4.0")
        with self.assertRaisesRegex(RuntimeError, "outside"):
            updates.unpack(archive, release)
        self.assertFalse((self.root.parent / "escaped.txt").exists())

    def test_old_versions_are_cleaned_up_but_the_kept_one_stays(self):
        for version in ("1.1.0", "1.2.0", "1.4.0"):
            staged = updates.ready_dir(updates.Release(version=version))
            staged.mkdir(parents=True, exist_ok=True)
            (staged / ".complete").write_text(version, encoding="utf-8")
        updates.clean_old(keep="1.4.0")
        base = updates.staging_dir() / "ready"
        self.assertEqual([p.name for p in base.iterdir()], ["1.4.0"])


class Installing(unittest.TestCase):
    def test_refuses_when_running_from_source(self):
        """There is no exe to replace, and git is the right answer instead."""
        with mock.patch.object(updates, "is_frozen", lambda: False):
            with self.assertRaisesRegex(RuntimeError, "from source"):
                updates.install(updates.Release(version="1.4.0"))

    def test_refuses_a_version_that_was_never_downloaded(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch.object(updates, "is_frozen", lambda: True), \
             mock.patch.object(updates, "staging_dir",
                               lambda: Path(tmp.name) / "updates"):
            with self.assertRaisesRegex(RuntimeError, "finished downloading"):
                updates.install(updates.Release(version="9.9.9"))

    def test_the_swap_script_waits_before_it_copies(self):
        """Copying over a running exe fails on Windows, so order matters."""
        script = updates._fill(pid=4321, ready=r"C:\ready", target=r"C:\app",
                               relaunch=r"C:\app\CS2 Launcher.exe")
        order = [script.index(":waitpid"), script.index(":waitlocks"),
                 script.index("\n:copyfiles")]
        self.assertEqual(order, sorted(order),
                         "it must wait for the window, then for any other "
                         "lock holder, and only then copy")
        self.assertIn("tasklist", script)
        # A failed copy must leave the working version alone.
        self.assertIn("leaving the old version in place", script)

    def test_the_swap_script_waits_for_other_copies_too(self):
        """A console cs2cfg.exe left open locks a file the copy needs."""
        script = updates._fill(pid=1, ready=r"C:\ready", target=r"C:\app",
                               relaunch="")
        self.assertIn("StartsWith", script, "it should look for processes by path")
        self.assertNotIn("taskkill", script.lower(),
                         "a window the user opened is theirs; wait, do not kill")

    def test_every_token_in_the_swap_script_is_filled(self):
        """A leftover token would run as a literal and do the wrong thing."""
        script = updates._fill(pid=7, ready=r"C:\r", target=r"C:\t", relaunch="")
        self.assertNotIn("@@", script)

    def test_both_waits_are_bounded(self):
        """Something that never lets go must not hang the update forever."""
        script = updates._fill(pid=7, ready=r"C:\r", target=r"C:\t", relaunch="")
        self.assertEqual(script.count("GTR"), 2)


class TheTimer(unittest.TestCase):
    """The checker's state machine, without starting its thread."""

    def _checker(self, latest=None, current="1.0.0", **kw):
        checker = updates.Checker(current=current, **kw)
        if latest is not None:
            checker._latest = latest
        return checker

    def test_a_newer_release_is_offered(self):
        checker = self._checker(updates.Release(version="1.4.0"))
        checker._state = updates.AVAILABLE
        summary = checker.summary()
        self.assertTrue(summary["available"])
        self.assertTrue(summary["notify"])

    def test_the_same_version_is_not_offered(self):
        checker = self._checker(updates.Release(version="1.0.0"))
        summary = checker.summary()
        self.assertFalse(summary["available"])
        self.assertFalse(summary["notify"])

    def test_a_skipped_version_stops_the_popup_but_stays_visible(self):
        checker = self._checker(updates.Release(version="1.4.0"))
        checker._state = updates.AVAILABLE
        checker.skip_version("1.4.0")
        summary = checker.summary()
        self.assertFalse(summary["notify"], "should not pop up again")
        self.assertTrue(summary["available"], "but the panel still lists it")

    def test_skipping_one_version_does_not_skip_the_next(self):
        checker = self._checker(updates.Release(version="1.4.0"))
        checker._state = updates.AVAILABLE
        checker.skip_version("1.4.0")
        checker._latest = updates.Release(version="1.5.0")
        self.assertTrue(checker.summary()["notify"])

    def test_a_failed_check_records_the_error_and_carries_on(self):
        checker = self._checker()
        with mock.patch.object(updates, "configured", lambda: True), \
             mock.patch.object(updates, "fetch_latest",
                               side_effect=OSError("network is down")):
            checker.check_once()
        summary = checker.summary()
        self.assertEqual(summary["state"], updates.ERROR)
        self.assertIn("network is down", summary["error"])

    def test_an_unchanged_feed_keeps_what_it_already_knew(self):
        """GitHub answers 304 with no body; the known release must survive."""
        checker = self._checker(updates.Release(version="1.4.0"))
        checker._state = updates.AVAILABLE
        with mock.patch.object(updates, "configured", lambda: True), \
             mock.patch.object(updates, "fetch_latest",
                               return_value=(None, "etag-2", updates.Rate(60, 55, 0))):
            checker.check_once()
        summary = checker.summary()
        self.assertEqual(summary["latest"]["version"], "1.4.0")
        self.assertEqual(summary["error"], "", "a 304 is not a failure")
        self.assertNotEqual(summary["state"], updates.ERROR)

    def test_auto_download_is_off_unless_asked_for(self):
        self.assertFalse(updates.Checker().summary()["auto_download"])
        self.assertTrue(
            updates.Checker(auto_download=True).summary()["auto_download"])

    def test_a_full_check_records_what_is_left_of_the_budget(self):
        checker = self._checker()
        with mock.patch.object(updates, "configured", lambda: True), \
             mock.patch.object(updates, "fetch_latest",
                               return_value=(updates.Release(version="1.4.0"),
                                             "e", updates.Rate(60, 41, 0))):
            checker.check_once()
        self.assertEqual(checker.summary()["rate"]["remaining"], 41)

    def test_it_never_installs_on_its_own(self):
        """The whole point: downloading may be automatic, installing is not."""
        source = Path(updates.__file__).read_text(encoding="utf-8")
        loop = source[source.index("def _run(self)"):source.index("def start(self)")]
        self.assertNotIn("install", loop)


class TheRateLimit(unittest.TestCase):
    """GitHub allows 60 an hour per address, and a 304 costs one of them.

    That was measured against the live rate_limit endpoint rather than assumed:
    a full request took it 59 -> 58, and a conditional request answered 304 took
    it 58 -> 57. Several copies behind one router therefore share one budget,
    which is what the backing-off below exists for.
    """

    def test_headers_are_read_into_a_budget(self):
        rate = updates._rate_from({
            "X-RateLimit-Limit": "60", "X-RateLimit-Remaining": "37",
            "X-RateLimit-Reset": "1789050000"})
        self.assertEqual((rate.limit, rate.remaining), (60, 37))
        self.assertTrue(rate.known)

    def test_missing_headers_mean_nothing_is_known(self):
        self.assertFalse(updates._rate_from({}).known)

    def test_a_healthy_budget_keeps_the_asked_for_interval(self):
        checker = updates.Checker(interval=300.0)
        checker._rate = updates.Rate(60, 55, time.time() + 3000)
        self.assertEqual(checker._delay(), 300.0)

    def test_a_thin_budget_stretches_the_interval(self):
        """Five left and half an hour to go: slow to fit, not to fail."""
        checker = updates.Checker(interval=300.0)
        checker._rate = updates.Rate(60, 5, time.time() + 1800)
        delay = checker._delay()
        self.assertGreater(delay, 300.0)
        self.assertLessEqual(delay, 1800.0)

    def test_an_exhausted_budget_waits_for_the_window(self):
        checker = updates.Checker(interval=300.0)
        checker._rate = updates.Rate(60, 0, time.time() + 900)
        self.assertGreaterEqual(checker._delay(), 900.0)

    def test_the_interval_is_a_floor_never_a_ceiling(self):
        """A generous budget must not make it poll faster than asked."""
        checker = updates.Checker(interval=300.0)
        checker._rate = updates.Rate(60, 59, time.time() + 10)
        self.assertEqual(checker._delay(), 300.0)

    def test_being_rate_limited_is_not_an_error_state(self):
        """The network is fine and so is the app; there is just nothing to ask."""
        checker = updates.Checker()
        limited = updates.RateLimited(updates.Rate(60, 0, time.time() + 600))
        with mock.patch.object(updates, "configured", lambda: True), \
             mock.patch.object(updates, "fetch_latest", side_effect=limited):
            checker.check_once()
        summary = checker.summary()
        self.assertNotEqual(summary["state"], updates.ERROR)
        self.assertIn("limit", summary["error"])

    def test_a_known_release_survives_being_rate_limited(self):
        checker = updates.Checker(current="1.0.0")
        checker._latest = updates.Release(version="1.4.0")
        checker._state = updates.AVAILABLE
        limited = updates.RateLimited(updates.Rate(60, 0, time.time() + 600))
        with mock.patch.object(updates, "configured", lambda: True), \
             mock.patch.object(updates, "fetch_latest", side_effect=limited):
            checker.check_once()
        self.assertEqual(checker.summary()["latest"]["version"], "1.4.0")
        self.assertTrue(checker.summary()["available"])

    def test_nothing_published_yet_is_not_an_error(self):
        """Before the first release, and every user's first launch after it."""
        checker = updates.Checker()
        with mock.patch.object(updates, "configured", lambda: True), \
             mock.patch.object(updates, "fetch_latest",
                               side_effect=updates.NoReleasesYet()):
            checker.check_once()
        summary = checker.summary()
        self.assertEqual(summary["state"], updates.IDLE)
        self.assertNotIn("404", summary["error"],
                         "a bare status code tells the reader nothing")
        self.assertIn("no releases", summary["error"])

    def test_summary_does_not_deadlock(self):
        """summary() holds the lock and calls _delay(); the lock is not reentrant."""
        checker = updates.Checker()
        checker._rate = updates.Rate(60, 3, time.time() + 600)
        done = []
        worker = threading.Thread(target=lambda: done.append(checker.summary()))
        worker.start()
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive(), "summary() deadlocked")
        self.assertEqual(len(done), 1)


if __name__ == "__main__":
    unittest.main()
