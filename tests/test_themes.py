"""The themes.

Six looks, each the same twenty-odd CSS variables with different values. The
tests that matter are not "does a colour exist" but the three things that make
a theme system hold together once nobody is looking at it:

* a light theme has to be possible at all, which means no rule may assume the
  background is dark;
* the default has to survive a theme failing to load;
* a theme has to actually win over the rules it is competing with.

The third one is here because it was wrong first time: the per-tab stage hues
are set on `body` and an equally specific rule later in the file quietly beat
every theme, so all six looked violet.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

THEMES = ("ember", "carbon", "acid", "daylight", "paper", "pro")
LIGHT = ("daylight", "paper")


class TheThemes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cs2cfg import paths

        cls.page = (paths.bundle_root() / "web" / "index.html").read_text(
            encoding="utf-8", errors="replace")

    def _block(self, name):
        found = re.search(r':root\[data-theme="%s"\] \{(.*?)\n  \}' % name,
                          self.page, re.S)
        self.assertIsNotNone(found, f"{name} has no theme block")
        return found.group(1)

    def test_every_theme_is_defined(self):
        for name in THEMES:
            self._block(name)

    def test_the_default_carries_no_attribute(self):
        """So a theme that fails to load leaves the application looking like
        itself rather than unstyled."""
        self.assertIn('if (use === "violet") delete document.documentElement.dataset.theme;',
                      self.page)

    def test_an_unknown_theme_falls_back(self):
        """A preferences file is editable by hand and survives upgrades."""
        self.assertIn("const known = THEMES.some", self.page)
        self.assertIn('const use = known ? id : "violet";', self.page)

    def test_the_picker_offers_exactly_what_exists(self):
        """A name in the list with no block behind it is a button that does
        nothing; a block with no button is a theme nobody can reach."""
        const = re.search(r"const THEMES = \[(.*?)\];", self.page, re.S)
        self.assertIsNotNone(const, "the picker has no list")
        listed = re.findall(r'\["(\w+)"', const.group(1))
        self.assertEqual(set(listed), set(THEMES) | {"violet"})


class ALightThemeIsPossible(unittest.TestCase):
    """The awkward one, and the reason --lift exists."""

    @classmethod
    def setUpClass(cls):
        from cs2cfg import paths

        cls.page = (paths.bundle_root() / "web" / "index.html").read_text(
            encoding="utf-8", errors="replace")

    def test_no_rule_assumes_a_dark_background(self):
        """A white overlay on a white panel is invisible. Sixty-odd places
        raise a surface this way, so it is one variable rather than sixty
        edits -- and a new literal creeping back in would break light mode
        quietly, in one corner, which is how it would go unnoticed."""
        # The theme blocks themselves are exempt: on a light theme a white
        # panel is the colour of the panel, not an overlay raising it off
        # something darker. Everywhere else, white is an assumption.
        outside = re.sub(r':root\[data-theme="\w+"\] \{.*?\n  \}', "",
                         self.page, flags=re.S)
        stray = re.findall(r"rgba\(255, ?255, ?255, ?\.?\d", outside)
        self.assertEqual(stray, [], f"{len(stray)} hardcoded white overlays are back")

    def test_the_lift_is_actually_used(self):
        self.assertGreater(self.page.count("rgba(var(--lift)"), 40)

    def test_the_light_themes_flip_it(self):
        for name in LIGHT:
            block = re.search(r':root\[data-theme="%s"\] \{(.*?)\n  \}' % name,
                              self.page, re.S).group(1)
            self.assertIn("--lift: 0, 0, 0", block, f"{name} would have invisible depth")
            self.assertIn("color-scheme: light", block, f"{name} has no colour scheme")

    def test_the_navigation_is_not_a_fixed_dark_bar(self):
        """It was, and on a light theme that meant dark text on a dark rail:
        the navigation, invisible."""
        self.assertIn("--rail-bg", self.page)
        self.assertIn("background: var(--rail-bg);", self.page)
        for name in LIGHT:
            block = re.search(r':root\[data-theme="%s"\] \{(.*?)\n  \}' % name,
                              self.page, re.S).group(1)
            self.assertIn("--rail-bg", block, f"{name} keeps the dark rail")


class AThemeWinsItsArgument(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cs2cfg import paths

        cls.page = (paths.bundle_root() / "web" / "index.html").read_text(
            encoding="utf-8", errors="replace")

    def test_the_stage_gradient_outranks_the_per_tab_hue(self):
        """The tab hues are set on body. A theme setting the same variables on
        :root is equally specific and loses to whichever comes last -- which
        is why all six looked violet until the selector changed."""
        for name in THEMES:
            self.assertRegex(
                self.page, r':root\[data-theme="%s"\]\s+body\s*\{[^}]*--g1' % name,
                f"{name}'s gradient does not outrank the tab hues")

    def test_the_tab_hues_still_exist_for_the_default(self):
        self.assertIn('body[data-hue="launcher"]', self.page)


class ItIsRemembered(unittest.TestCase):
    def test_the_theme_is_a_saved_preference(self):
        from cs2cfg import paths

        server = (Path(paths.__file__).parent / "webui.py").read_text(encoding="utf-8")
        self.assertIn('"theme",', server)

    def test_it_is_applied_as_soon_as_preferences_arrive(self):
        """A window that repaints itself a moment after opening looks broken,
        however briefly."""
        from cs2cfg import paths

        page = (paths.bundle_root() / "web" / "index.html").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn('applyTheme(ui.theme || "violet");', page)


if __name__ == "__main__":
    unittest.main()
