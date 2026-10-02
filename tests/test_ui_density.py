"""The interface's information density.

Measured, not argued about. On the CS2 Settings tab one 126-character sentence
was printed on every video-sourced row -- ten times on a single screen, 56% of
all the prose on the tab -- and a setting cost five lines, so three of them
filled the panel.

The sentence is not deleted. It is said once, in the heading of the group it is
true of, and everything else a row knows moves behind a click. These pin the
shape of that so it cannot quietly grow back.

Assertions are on the page source: there is no browser in this suite. The
behaviour was checked in one, against the real settings of a real install.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TheSettingRow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cs2cfg import paths

        cls.page = (paths.bundle_root() / "web" / "index.html").read_text(
            encoding="utf-8", errors="replace")

    def test_a_row_can_be_opened(self):
        self.assertIn('class="why"', self.page)
        self.assertIn(".setting.open .src", self.page)

    def test_the_detail_is_hidden_until_it_is_asked_for(self):
        """Hidden, not removed. Everything a row used to say is still there."""
        block = re.search(r"\.setting \.src \{[^}]*\}", self.page)
        self.assertIsNotNone(block, "the detail has no style block")
        self.assertIn("display: none", block.group(0))

    def test_the_shared_sentence_is_hoisted_out_of_the_rows(self):
        """The whole fix. A note identical across every item in a group is
        printed once, above them, where it is true of all of them."""
        self.assertIn("subcat-note", self.page)
        self.assertIn("notes.every", self.page)
        self.assertIn('x.note !== saidAlready', self.page)

    def test_the_per_setting_help_is_never_hoisted(self):
        """It is written per setting and is the reason somebody opened the row,
        so it always stays with the row."""
        self.assertIn('if (spec.help) src += "<br>" + esc(spec.help);', self.page)

    def test_the_file_badge_is_not_repeated_on_every_row(self):
        """cs2_video.txt is true of the whole group. On the row it was forty
        identical chips saying what the heading already says."""
        row = self.page[self.page.index("function cs2Row("):]
        row = row[:row.index("function renderCs2Body") if "function renderCs2Body" in row else 4000]
        marker = row.index('let quiet = ""')
        # The badge is built into the quiet half, after the inline flags end.
        self.assertIn('cs2_video.txt', row[marker:])
        self.assertNotIn('cs2_video.txt', row[:marker])

    def test_a_changed_setting_is_visible_without_opening_anything(self):
        """The one thing on the row worth noticing at a glance, and it used to
        be buried in a wall of identical grey text."""
        self.assertIn('class="differs"', self.page)
        self.assertIn(".setting .differs", self.page)

    def test_using_a_control_does_not_open_the_row(self):
        """Reaching for a dropdown is changing the setting, not asking what it
        means."""
        self.assertIn('if (e.target.closest("select, input, button, a")) return;', self.page)

    def test_a_row_is_reachable_without_a_mouse(self):
        self.assertIn('tabindex="0"', self.page)
        self.assertIn('aria-expanded', self.page)
        self.assertIn('e.key !== "Enter" && e.key !== " "', self.page)

    def test_the_change_list_is_not_squeezed_into_one_column_of_the_deck(self):
        """It is the output of everything above it. In a 340px column a row
        like "NVIDIA Reflex Low Latency" wrapped onto three lines and the list
        became a scroll -- and a name, the value being left and the value being
        taken have to sit on one line or the arrow between them means nothing."""
        self.assertIn('<div id="results" class="wide">', self.page)
        self.assertIn("#results {", self.page)
        self.assertIn("minmax(460px, 1fr)", self.page)

    def test_a_focusable_row_shows_that_it_is_focused(self):
        """It was given a tabindex and no focus ring, which makes it reachable
        by keyboard and invisible once reached. Caught by auditing against a
        UX ruleset, not by looking at it."""
        self.assertIn(".setting .top:focus-visible", self.page)

    def test_anything_focusable_gets_a_ring_without_being_asked(self):
        """Written as a catch-all rather than per component: the one that was
        missed was missed by being added later, and so would the next."""
        self.assertIn('[tabindex]:focus-visible, [role="button"]:focus-visible',
                      self.page)

    def test_the_handler_is_delegated_not_per_row(self):
        """Rows are rewritten on every render, so a listener per row would be a
        listener per render."""
        self.assertIn('document.addEventListener("click", e => {\n  const top = e.target.closest(".setting .top");',
                      self.page)


if __name__ == "__main__":
    unittest.main()
