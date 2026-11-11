"""tools/release.py: what a failed release leaves behind.

A release that fails before its commit puts the working tree back. One that
fails after it -- the case that left 1.20.8 tagged and pushed but never
published -- must leave the committed files alone and say how to finish,
because putting the old version back would leave a stray edit and a re-run
would skip straight to the next version.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_release():
    spec = importlib.util.spec_from_file_location(
        "release_under_test", ROOT / "tools" / "release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FailedReleaseTest(unittest.TestCase):

    def setUp(self):
        self.release = load_release()
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.init = tmp / "__init__.py"
        self.init.write_text('__version__ = "1.0.0"\n', encoding="utf-8")
        self.dist = tmp / "dist"
        self.commands = []

    def _run_failing_at(self, failing: str) -> str:
        r = self.release

        def fake_run(command, capture=False, check=True):
            printed = command if isinstance(command, str) else " ".join(command)
            self.commands.append(printed)
            if failing in printed:
                raise r.Stop(f"`{printed}` failed with exit code 1")
            return ""

        def write_version(version):
            self.init.write_text(f'__version__ = "{version}"\n',
                                 encoding="utf-8")

        patches = [
            mock.patch.object(r, "INIT", self.init),
            mock.patch.object(r, "UPDATES", self.init.with_name("none1")),
            mock.patch.object(r, "ISS", self.init.with_name("none2")),
            mock.patch.object(r, "DIST", self.dist),
            mock.patch.object(r, "run", fake_run),
            mock.patch.object(r, "read_version", lambda: "1.0.0"),
            mock.patch.object(r, "write_version", write_version),
            mock.patch.object(r, "origin_repo", lambda: "owner/repo"),
            mock.patch.object(r, "find_gh", lambda: "gh"),
            mock.patch.object(r, "find_iscc", lambda: "iscc"),
            mock.patch.object(r, "point_updater_at", lambda repo: False),
            mock.patch.object(r, "build_archive",
                              lambda v: Path(f"dist/a-{v}.zip")),
            mock.patch.object(r, "build_installer",
                              lambda v: Path(f"dist/a-{v}-Setup.exe")),
            mock.patch.object(sys, "argv",
                              ["release.py", "--notes", "- a change"]),
        ]
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(contextlib.redirect_stdout(out))
            with self.assertRaises(r.Stop):
                r.main()
        return out.getvalue()

    def test_a_failure_before_the_commit_puts_the_version_back(self):
        output = self._run_failing_at("build")
        self.assertIn('"1.0.0"', self.init.read_text(encoding="utf-8"))
        self.assertIn("nothing was published", output)

    def test_a_failed_publish_leaves_the_committed_version_alone(self):
        output = self._run_failing_at("gh release create")
        self.assertIn('"1.0.1"', self.init.read_text(encoding="utf-8"),
                      "the committed version must not be set back")
        self.assertNotIn("put back", output)
        self.assertIn("Do NOT run this script again", output)
        self.assertIn("gh release create v1.0.1", output)
        self.assertNotIn("git push", output.split("To finish")[1],
                         "the pushes already happened")
        notes = self.dist / "release-notes-1.0.1.txt"
        self.assertEqual(notes.read_text(encoding="utf-8"), "- a change")

    def test_a_failed_push_lists_the_remaining_pushes(self):
        output = self._run_failing_at("push origin HEAD")
        rest = output.split("To finish")[1]
        self.assertIn("git push origin HEAD", rest)
        self.assertIn("git push origin v1.0.1", rest)
        self.assertNotIn("git tag", rest, "the tag already exists")
        self.assertIn('"1.0.1"', self.init.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
