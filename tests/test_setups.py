"""Named setups: what they hold, what they refuse to hold, and switching."""

import unittest

from cs2cfg import profiles, setups


def ui(**over):
    base = {"intent": "balanced", "target_fps": "300", "stretch_mode": "borderless",
            "patch_video": True, "write_video": True, "write_cfg": True,
            "write_launch": True, "link_autoexec": False, "fix_scaling": True}
    base.update(over)
    return base


class WhatASetupHolds(unittest.TestCase):
    def test_it_takes_the_choices_that_differ_between_uses(self):
        snap = setups.snapshot(ui())
        self.assertEqual(set(snap), set(setups.KEYS))
        self.assertEqual(snap["intent"], "balanced")

    def test_it_never_takes_the_folder_or_the_account(self):
        """Switching what you are tuning for must not point the tools at
        somebody else's files. That is the one way this could do damage."""
        snap = setups.snapshot(ui(cfg_folder=r"C:\somewhere\cfg",
                                  account="244173392", pinned_account="1"))
        for leak in ("cfg_folder", "account", "pinned_account"):
            self.assertNotIn(leak, snap)

    def test_nothing_it_holds_is_machine_wide(self):
        """A setup belongs to an account. Anything machine-wide in it would be
        written to the shared half and follow every other account around."""
        for key in setups.KEYS:
            self.assertFalse(profiles.is_machine(key),
                             f"{key} is machine-wide and must not be in a setup")


class Saving(unittest.TestCase):
    def test_save_then_use_gives_the_values_back(self):
        state = ui()
        state.update(setups.save(state, "Practice"))
        state.update({"intent": "quality", "target_fps": "120"})
        state.update(setups.use(state, "Practice"))
        self.assertEqual(state["intent"], "balanced")
        self.assertEqual(state["target_fps"], "300")

    def test_a_name_is_tidied_not_taken_literally(self):
        state = ui()
        state.update(setups.save(state, "  Match   day  "))
        self.assertIn("Match day", state[setups.STORE])

    def test_an_empty_name_is_refused(self):
        for bad in ("", "   ", "\t"):
            with self.assertRaises(setups.SetupError):
                setups.save(ui(), bad)

    def test_using_one_that_is_not_there_says_so(self):
        with self.assertRaises(setups.SetupError):
            setups.use(ui(), "Nope")

    def test_there_is_a_ceiling_on_how_many(self):
        state = ui()
        for i in range(setups.MAX_SETUPS):
            state.update(setups.save(state, f"s{i}"))
        with self.assertRaises(setups.SetupError):
            setups.save(state, "one too many")
        # overwriting one that exists is still fine at the ceiling
        state.update(setups.save(state, "s0"))

    def test_a_setup_from_a_later_version_only_gives_up_what_we_know(self):
        """Applying a key this copy cannot show is how a setting ends up at a
        value nothing can display or undo."""
        state = ui()
        state[setups.STORE] = {"Odd": {"intent": "quality", "warp_drive": "on"}}
        got = setups.use(state, "Odd")
        self.assertEqual(got["intent"], "quality")
        self.assertNotIn("warp_drive", got)


class Listing(unittest.TestCase):
    def test_it_says_which_one_is_actually_being_followed(self):
        state = ui()
        state.update(setups.save(state, "Practice"))
        self.assertEqual(setups.listing(state)["live"], "Practice")
        self.assertFalse(setups.listing(state)["changed"])

        state["target_fps"] = "999"
        seen = setups.listing(state)
        self.assertEqual(seen["live"], "Practice")
        self.assertTrue(seen["changed"], "a changed setting must stop reading as saved")
        self.assertFalse(seen["setups"][0]["matches"])

    def test_a_live_name_that_was_deleted_stops_being_live(self):
        state = ui()
        state.update(setups.save(state, "Gone"))
        state.update(setups.remove(state, "Gone"))
        self.assertEqual(setups.listing(state)["live"], "")

    def test_renaming_carries_the_live_marker(self):
        state = ui()
        state.update(setups.save(state, "Old"))
        state.update(setups.rename(state, "Old", "New"))
        self.assertEqual(setups.listing(state)["live"], "New")
        self.assertIn("New", state[setups.STORE])

    def test_renaming_onto_an_existing_name_is_refused(self):
        state = ui()
        state.update(setups.save(state, "A"))
        state.update(setups.save(state, "B"))
        with self.assertRaises(setups.SetupError):
            setups.rename(state, "A", "B")


if __name__ == "__main__":
    unittest.main()
