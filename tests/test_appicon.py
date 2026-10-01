"""The application icon.

One file draws the mark that the executable, the window, the notification area
and the installer all use, so a change here is a change to all four at once.
That is the reason these exist: the icon has no other test, and a number
nudged by accident would ship quietly.

The icon is generated rather than committed as a binary -- the whole point of
drawing it in code -- so what is pinned is the bytes it produces, against the
brand set's cs-config-ai.ico that this was taken from.
"""

from __future__ import annotations

import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import appicon  # noqa: E402

# The brand set's cs-config-ai.ico, which this module reproduces exactly.
BRAND_SHA256 = "11a46eb72865afb529d93508a8c51ad9786e7344f3d29234a7c0a5e7217317dd"

# Drawing the full set costs about two seconds, almost all of it in the 256 px
# rendering, so it is done once for the whole file rather than per test.
_ICO = appicon.to_ico()


class TheArtwork(unittest.TestCase):
    def test_it_still_draws_the_brand_icon(self):
        """Pinned against the brand set rather than described in prose. If
        this fails, either the artwork was changed deliberately -- in which
        case update the hash and say so -- or something was nudged by
        accident, which is what this is here to catch."""
        self.assertEqual(hashlib.sha256(_ICO).hexdigest(), BRAND_SHA256)

    def test_the_palette_is_the_interface_palette(self):
        """The icon sitting beside the window should not be a different
        violet from the window."""
        self.assertEqual(appicon.BACKGROUND[:3], (0x13, 0x0C, 0x1F))
        self.assertEqual(appicon.ACCENT[:3], (0xA7, 0x8B, 0xFA))
        self.assertEqual(appicon.CROSS[:3], (0xEC, 0xEC, 0xEC))


class TheIcoItself(unittest.TestCase):
    def setUp(self):
        self.blob = _ICO

    def test_the_header_says_it_is_an_icon(self):
        reserved, kind, count = struct.unpack("<HHH", self.blob[:6])
        self.assertEqual((reserved, kind), (0, 1))
        self.assertEqual(count, len(appicon.ICO_SIZES))

    def test_every_declared_size_is_present_and_square(self):
        """Windows picks the entry closest to what it is drawing. A missing
        16 means the notification area scales 256 down to sixteen pixels of
        mud."""
        _, _, count = struct.unpack("<HHH", self.blob[:6])
        found = []
        for i in range(count):
            head = 6 + i * 16
            width, height = self.blob[head], self.blob[head + 1]
            found.append(((width or 256), (height or 256)))
        self.assertEqual([w for w, _ in found], list(appicon.ICO_SIZES))
        for width, height in found:
            self.assertEqual(width, height)

    def test_the_sizes_cover_the_small_end(self):
        """16 and 24 are the notification area; 32 and 48 are the taskbar and
        the shortcut. Those four matter far more than 256 does."""
        for needed in (16, 24, 32, 48):
            self.assertIn(needed, appicon.ICO_SIZES)

    def test_each_entry_is_a_real_png(self):
        _, _, count = struct.unpack("<HHH", self.blob[:6])
        for i in range(count):
            head = 6 + i * 16
            size, offset = struct.unpack("<II", self.blob[head + 8:head + 16])
            payload = self.blob[offset:offset + size]
            self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")

    def test_the_corners_are_transparent(self):
        """It is a rounded tile. An opaque corner means a square block in the
        notification area."""
        for size in (16, 32, 64):
            pixels = appicon.render(size)
            self.assertEqual(pixels[0][0][3], 0, f"{size}px corner is not clear")

    def test_the_middle_is_not_blank(self):
        """A guard against the drawing silently producing an empty tile."""
        for size in (16, 32, 64):
            pixels = appicon.render(size)
            middle = pixels[size // 2][size // 2]
            self.assertNotEqual(middle[:3], appicon.BACKGROUND[:3],
                                f"{size}px has nothing drawn on it")


class TheCachedCopy(unittest.TestCase):
    """The cached .ico lives in the user's data directory and outlives
    upgrades, so writing it only when absent left every existing installation
    showing the previous icon for good. It is compared now."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        # What is under test here is when the file is written, not what is in
        # it, and drawing it for real costs two seconds a time. The bytes are
        # the genuine ones, computed once for the whole file.
        drawn = mock.patch.object(appicon, "to_ico", return_value=_ICO)
        drawn.start()
        self.addCleanup(drawn.stop)

    def test_it_writes_the_icon_when_there_is_none(self):
        written = appicon.ensure_icon(self.dir)
        self.assertTrue(written.exists())
        self.assertEqual(written.read_bytes(), _ICO)

    def test_it_replaces_an_icon_from_an_older_version(self):
        stale = self.dir / "cs2cfg.ico"
        stale.write_bytes(b"an icon from three releases ago")
        appicon.ensure_icon(self.dir)
        self.assertEqual(stale.read_bytes(), _ICO)

    def test_it_replaces_an_empty_file(self):
        (self.dir / "cs2cfg.ico").write_bytes(b"")
        self.assertEqual(appicon.ensure_icon(self.dir).read_bytes(), _ICO)

    def test_it_does_not_rewrite_one_that_is_already_right(self):
        """Called on every start, so it should not touch the disk for nothing."""
        target = appicon.ensure_icon(self.dir)
        before = target.stat().st_mtime_ns
        appicon.ensure_icon(self.dir)
        self.assertEqual(target.stat().st_mtime_ns, before)

    def test_the_usual_case_does_not_redraw_the_icon(self):
        """The check runs on every start of the application and drawing the
        icon takes about two seconds, so the answer "nothing has changed" has
        to come from the stamp rather than from a comparison."""
        appicon.ensure_icon(self.dir)
        with mock.patch.object(appicon, "to_ico",
                               side_effect=AssertionError("redrew needlessly")):
            appicon.ensure_icon(self.dir)

    def test_a_missing_stamp_means_redraw(self):
        """An icon from before stamps existed cannot be vouched for."""
        appicon.ensure_icon(self.dir)
        (self.dir / "cs2cfg.ico.id").unlink()
        (self.dir / "cs2cfg.ico").write_bytes(b"stale")
        self.assertEqual(appicon.ensure_icon(self.dir).read_bytes(), _ICO)

    def test_the_stamp_follows_the_artwork(self):
        """It has to change when the drawing does, or a changed icon is never
        noticed. Every constant that defines the mark feeds it."""
        before = appicon.fingerprint()
        with mock.patch.object(appicon, "ACCENT", (1, 2, 3, 255)):
            self.assertNotEqual(appicon.fingerprint(), before)
        with mock.patch.object(appicon, "BRACKET", appicon.BRACKET[:-1]):
            self.assertNotEqual(appicon.fingerprint(), before)
        with mock.patch.object(appicon, "ICO_SIZES", (16, 32)):
            self.assertNotEqual(appicon.fingerprint(), before)
        self.assertEqual(appicon.fingerprint(), before)


class ThePageWearsItToo(unittest.TestCase):
    def test_the_interface_carries_the_same_mark(self):
        from cs2cfg import paths

        page = (paths.bundle_root() / "web" / "index.html").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn('<link rel="icon"', page)
        # The same violet, so the tab and the window agree.
        self.assertIn("%23a78bfa", page)


if __name__ == "__main__":
    unittest.main()
