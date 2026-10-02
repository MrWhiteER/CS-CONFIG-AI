"""The other applications somebody runs alongside the game.

Crosshair X was written in by name; a clip recorder is not Crosshair X, and
the one after that is neither. So the general case -- where it is, whether it
is up, start it -- lives here, and anything that knows about a *particular*
program is an integration on top.

The rule these guard hardest is the one that is tempting to break: nothing
here writes into another application's settings. Those files belong to the
program that wrote them, are usually open while it runs, and mostly rewrite
themselves on exit, so a change from out here is either ignored or lost --
and either way somebody's configuration was touched without their say.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import companions  # noqa: E402


class WhatIsRunning(unittest.TestCase):
    def setUp(self):
        companions.forget_running()
        self.addCleanup(companions.forget_running)

    def _listing(self, *names):
        rows = "\n".join('"%s","123","Console","1","1,000 K"' % n for n in names)
        return mock.patch.object(companions.subprocess, "run",
                                 return_value=mock.Mock(stdout=rows))

    def test_it_finds_a_running_process(self):
        with self._listing("CrosshairX.exe", "cs2.exe"):
            self.assertTrue(companions.running("CrosshairX.exe"))
            self.assertFalse(companions.running("Medal.exe"))

    def test_the_name_is_matched_regardless_of_case_or_path(self):
        with self._listing("Medal.exe"):
            self.assertTrue(companions.running("medal.exe"))
            self.assertTrue(companions.running(r"C:\Program Files\Medal\Medal.exe"))

    def test_one_listing_answers_for_every_companion(self):
        """It used to run tasklist once per application. Invisible with one
        companion; with eight it is eight processes every four seconds."""
        with self._listing("a.exe", "b.exe", "c.exe") as ran:
            for name in ("a.exe", "b.exe", "c.exe", "d.exe"):
                companions.running(name)
            self.assertEqual(ran.call_count, 1)

    def test_a_failed_listing_is_not_an_answer(self):
        with mock.patch.object(companions.subprocess, "run",
                               side_effect=OSError("no tasklist")):
            self.assertFalse(companions.running("anything.exe"))


class TheStoredList(unittest.TestCase):
    """Preferences are a file somebody can edit and which survives upgrades,
    so nothing that comes out of them can be assumed."""

    def test_an_entry_without_an_executable_is_dropped(self):
        self.assertEqual(companions.listed({"companions": [{"name": "ghost"}]}), [])

    def test_rubbish_in_the_list_is_dropped(self):
        got = companions.listed({"companions": ["nonsense", 42, None,
                                                {"exe": "C:/x/Real.exe"}]})
        self.assertEqual([e["name"] for e in got], ["Real"])

    def test_a_missing_list_is_not_an_error(self):
        self.assertEqual(companions.listed({}), [])
        self.assertEqual(companions.listed({"companions": "not a list"}), [])

    def test_a_name_defaults_to_the_executable(self):
        got = companions.listed({"companions": [{"exe": r"C:\Apps\Medal.exe"}]})
        self.assertEqual(got[0]["name"], "Medal")


class Starting(unittest.TestCase):
    def setUp(self):
        companions.forget_running()
        self.addCleanup(companions.forget_running)

    def test_it_does_not_start_a_second_copy(self):
        entry = {"name": "Medal", "exe": r"C:\Apps\Medal.exe"}
        with mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(companions, "running", return_value=True), \
             mock.patch.object(companions.subprocess, "Popen") as popen:
            out = companions.start(entry)
        popen.assert_not_called()
        self.assertTrue(out["already"])

    def test_a_missing_executable_is_reported_not_raised(self):
        with mock.patch.object(Path, "is_file", return_value=False):
            out = companions.start({"name": "Gone", "exe": r"C:\nope.exe"})
        self.assertFalse(out["ok"])
        self.assertIn("not where it was", out["error"])

    def test_one_refusing_to_start_does_not_stop_the_next(self):
        """A clip recorder that will not start is not a reason to stop
        somebody launching their game."""
        prefs = {"companions": [
            {"exe": r"C:\a\First.exe"}, {"exe": r"C:\b\Second.exe"}]}
        with mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(companions, "running", return_value=False), \
             mock.patch.object(companions.subprocess, "Popen",
                               side_effect=[OSError("nope"), mock.Mock()]):
            out = companions.start_all(prefs)
        self.assertEqual(len(out), 2)
        self.assertFalse(out[0]["ok"])
        self.assertTrue(out[1]["ok"])

    def test_only_the_ones_asked_for_come_up_with_the_game(self):
        prefs = {"companions": [
            {"exe": r"C:\a\Wanted.exe", "with_game": True},
            {"exe": r"C:\b\Manual.exe", "with_game": False}]}
        with mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(companions, "running", return_value=False), \
             mock.patch.object(companions.subprocess, "Popen"):
            out = companions.start_all(prefs)
        self.assertEqual([e["name"] for e in out], ["Wanted"])


class NothingReachesIntoAnotherApp(unittest.TestCase):
    """The limit worth a test, because it is the tempting one to break."""

    def test_the_module_never_writes_another_programs_settings(self):
        source = (Path(__file__).resolve().parents[1]
                  / "cs2cfg" / "companions.py").read_text(encoding="utf-8")
        body = source.split('"""', 2)[-1]        # past the module docstring
        for forbidden in ("json.dump", "shutil.copy", "os.replace"):
            self.assertNotIn(forbidden, body,
                             forbidden + " would be writing somebody else's files")

    def test_the_only_thing_it_writes_is_its_own_icon_cache(self):
        from cs2cfg import paths

        cached = companions.icon_path(r"C:\Apps\Medal.exe")
        self.assertTrue(str(cached).startswith(str(paths.user_data_dir())))


class Icons(unittest.TestCase):
    def test_the_name_is_stable_and_per_executable(self):
        a = companions.icon_name(r"C:\Apps\Medal.exe")
        self.assertEqual(a, companions.icon_name(r"c:\apps\medal.exe"),
                         "the same program should not cache twice")
        self.assertNotEqual(a, companions.icon_name(r"C:\Apps\Other.exe"))
        self.assertTrue(a.endswith(".png"))

    def test_a_missing_executable_yields_no_icon(self):
        self.assertIsNone(companions.extract_icon(r"C:\definitely\not\here.exe"))

    @unittest.skipUnless(sys.platform == "win32", "Windows only")
    def test_it_really_pulls_an_icon_out_of_a_binary(self):
        """Against a real executable, because the whole of this is ctypes and
        a mock would only prove the mock works. Every handle is declared in
        both directions -- an undeclared one truncates or raises on 64-bit,
        which is exactly what happened on the first binary tried."""
        rows = companions._icon_pixels(sys.executable, 32)
        self.assertIsNotNone(rows, "no icon came back")
        self.assertEqual(len(rows), 32)
        self.assertEqual(len(rows[0]), 32)
        drawn = sum(1 for row in rows for px in row if px[3] > 0)
        self.assertGreater(drawn, 50, "the icon came back blank")


if __name__ == "__main__":
    unittest.main()
