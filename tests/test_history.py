"""The change history: listing, Keep / Put back, game sessions, NVIDIA.

Everything runs in temporary folders; backups and the history file are
redirected so the player's own data is never touched.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import backup, history, nvwatch, sessionwatch  # noqa: E402
from tests.sandbox import redirect_backups  # noqa: E402


class Case(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="cs2cfg-history-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        redirect_backups(self)
        p = mock.patch.object(history, "_path", lambda: self.root / "history.json")
        p.start()
        self.addCleanup(p.stop)
        self.stamp = 0

    def change(self, path: Path, text: str, note: str) -> str:
        """Do what the app does: back the file up, then write it."""
        self.stamp += 1
        session = backup.BackupSession(note=note)
        session.stamp = f"20261121-1200{self.stamp:02d}"
        session.dir = backup.backups_root() / session.stamp
        session.add(path)
        path.write_text(text, encoding="utf-8")
        return session.stamp


class Wording(Case):
    def test_binds_and_settings_read_as_words(self):
        items = history.describe_diff(
            'bind "e" "+use"\nsensitivity "1.1"\n',
            'bind "e" "+jump"\nsensitivity "1.3"\n')
        self.assertIn({"what": "Key E", "was": "Use", "now": "Jump"}, items)
        sens = [i for i in items if i["was"] == "1.1"]
        self.assertEqual(sens[0]["now"], "1.3")

    def test_titles(self):
        self.assertEqual(history.title_for("bind +jump to Space"), "Key Space: Jump")
        self.assertEqual(history.title_for("cs2 settings (web)"), "Game settings")


class Merge(Case):
    def test_undo_only_that_change(self):
        base = "a\nb\nc\nd\ne\n"
        changed = "a\nB\nc\nd\ne\n"
        later = "a\nB\nc\nd\nE\n"
        self.assertEqual(history.merge(changed, base, later), "a\nb\nc\nd\nE\n")

    def test_same_line_is_a_conflict(self):
        with self.assertRaises(history.Conflict):
            history.merge("a\nB\nc\n", "a\nb\nc\n", "a\nX\nc\n")


class AppChanges(Case):
    def setUp(self):
        super().setUp()
        self.file = self.root / "autoexec.cfg"
        self.file.write_text('bind "e" "+use"\nfps_max "400"\n', encoding="utf-8")

    def test_listed_and_kept_by_default(self):
        self.change(self.file, 'bind "e" "+jump"\nfps_max "400"\n', "bind Jump to E")
        found = history.entries()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["status"], history.KEPT)
        self.assertEqual(found[0]["items"][0]["now"], "Jump")

    def test_put_back_then_keep_again(self):
        stamp = self.change(self.file, 'bind "e" "+jump"\nfps_max "400"\n', "bind Jump to E")
        # A later, unrelated change to the same file survives the put back.
        self.change(self.file, 'bind "e" "+jump"\nfps_max "0"\n', "cs2 settings (web)")
        self.assertTrue(history.swing(stamp, history.BACK)["ok"])
        self.assertEqual(self.file.read_text(), 'bind "e" "+use"\nfps_max "0"\n')
        entry = next(e for e in history.entries() if e["id"] == "app:" + stamp)
        self.assertEqual(entry["status"], history.BACK)
        # The put back itself is not listed as a change of its own.
        self.assertEqual(len(history.entries()), 2)

        self.assertTrue(history.swing(stamp, history.KEPT)["ok"])
        self.assertEqual(self.file.read_text(), 'bind "e" "+jump"\nfps_max "0"\n')

    def test_conflict_then_force(self):
        stamp = self.change(self.file, 'bind "e" "+jump"\nfps_max "400"\n', "bind Jump to E")
        self.change(self.file, 'bind "e" "+duck"\nfps_max "400"\n', "bind Duck to E")
        result = history.swing(stamp, history.BACK)
        self.assertFalse(result["ok"])
        self.assertTrue(result["conflict"])
        self.assertTrue(history.swing(stamp, history.BACK, force=True)["ok"])
        self.assertEqual(self.file.read_text(), 'bind "e" "+use"\nfps_max "400"\n')

    def test_keep_writes_nothing_even_when_later_changes_overlap(self):
        stamp = self.change(self.file, 'bind "e" "+jump"\nfps_max "400"\n', "bind Jump to E")
        self.change(self.file, 'bind "e" "+duck"\nfps_max "400"\n', "bind Duck to E")
        self.assertTrue(history.swing(stamp, history.KEPT)["ok"])
        self.assertEqual(self.file.read_text(), 'bind "e" "+duck"\nfps_max "400"\n')
        entry = next(e for e in history.entries() if e["id"] == "app:" + stamp)
        self.assertEqual(entry["status"], history.KEPT)

    def test_no_code_in_the_list(self):
        items = history.describe_diff(
            '// made 2026-11-21 23:54\n-novid +exec mrwhiteer\\autoexec.vcfg\n----------\n',
            '// made 2026-11-22 01:31\nbind c +smoke_left_click\n')
        self.assertEqual(items, [{"what": "Key C", "was": None, "now": "Smoke left click"}])
        self.assertEqual(history.title_for("bind +smoke_left_click to C"), "Key C: Smoke left click")

    def test_change_during_a_game_waits(self):
        history.session_started(time.time() - 3600 * 24 * 365 * 10)
        self.change(self.file, 'bind "e" "+jump"\nfps_max "400"\n', "bind Jump to E")
        self.assertEqual(history.waiting()[0]["status"], history.WAITING)


class Outside(Case):
    def test_game_finding_waits_and_answers(self):
        history.add_game_finding("1", {"after": time.time(), "sources": {
            "Key binds": [{"key": "f", "kind": "changed", "was": "+use", "now": "+jump"}],
            "Machine settings": [{"key": "x", "kind": "changed", "was": "1", "now": "2"}],
        }})
        entry = history.waiting()[0]
        self.assertEqual(entry["title"], "Changed inside CS2")
        line = entry["items"][0]
        self.assertEqual((line["what"], line["was"], line["now"]), ("Key F", "Use", "Jump"))
        self.assertEqual(entry["items"][1]["status"], history.KEPT)   # can't be answered
        history.set_answer(line["id"], history.BACK)
        self.assertEqual(history.waiting(), [])

    def test_nvidia_compare(self):
        before = {"Every game": {"0x1": {"name": "Vertical sync", "value": "On"}}}
        after = {"Every game": {"0x1": {"name": "Vertical sync", "value": "Off"},
                                "0x2": {"name": "Low latency", "value": "Ultra"}}}
        items = nvwatch.compare(before, after)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[1]["was"], "NVIDIA default")

    def test_nvidia_first_look_is_quiet(self):
        with mock.patch.object(nvwatch, "_store", lambda: self.root / "nv.json"):
            snap = {"Every game": {"0x1": {"name": "V", "value": "On"}}}
            self.assertEqual(nvwatch.check(lambda: snap), [])
            snap2 = {"Every game": {"0x1": {"name": "V", "value": "Off"}}}
            self.assertEqual(len(nvwatch.check(lambda: snap2)), 1)


class NvidiaPutBack(Case):
    def test_cs2_profile_lines_can_go_back_when_a_writer_exists(self):
        from cs2cfg import nvidia
        written = {}

        def write_cs2(values, record=True):
            written.update(values)
            return {"ok": True}

        with mock.patch.object(nvidia, "write_cs2", write_cs2, create=True), \
                mock.patch.object(nvwatch, "accept_current", lambda: None):
            before = {"Counter-Strike 2": {"0x00A879CF": {"name": "Vertical sync", "value": "Off", "raw": 0}}}
            after = {"Counter-Strike 2": {"0x00A879CF": {"name": "Vertical sync", "value": "On", "raw": 1}}}
            item = nvwatch.compare(before, after)[0]
            self.assertTrue(item["can_put_back"])
            self.assertTrue(nvwatch.put_back(item)["ok"])
            self.assertEqual(written, {0x00A879CF: 0})

    def test_without_a_writer_it_is_keep_only(self):
        from cs2cfg import nvidia
        if hasattr(nvidia, "write_cs2"):
            self.skipTest("writer present")
        before = {"Counter-Strike 2": {"0x1": {"name": "V", "value": "Off", "raw": 0}}}
        after = {"Counter-Strike 2": {"0x1": {"name": "V", "value": "On", "raw": 1}}}
        self.assertFalse(nvwatch.compare(before, after)[0]["can_put_back"])


class Session(Case):
    def test_closing_however_it_closed_asks_for_review(self):
        up = {"v": True}
        asked, closed = [], []
        history.add_listener(asked.append)
        self.addCleanup(history._listeners.remove, asked.append)
        w = sessionwatch.Watcher(on_closed=lambda: closed.append(1), is_running=lambda: up["v"])
        self.assertEqual(w.tick(), "started")
        history.add_game_finding("1", {"after": time.time(), "sources": {
            "In-game settings": [{"key": "sensitivity", "kind": "changed", "was": "1", "now": "2"}]}})
        up["v"] = False          # quit, closed from the taskbar, or killed: all look the same
        self.assertEqual(w.tick(), "closed")
        self.assertEqual(closed, [1])
        self.assertIn("review", asked)


if __name__ == "__main__":
    unittest.main()
