"""Applying while Steam or CS2 is up.

Each of those two programs keeps one file in memory and rewrites it when it
closes, so writing that file underneath it is pointless. What used to happen
is that either one being open refused the whole apply -- and Steam being open
is the normal state of a machine somebody is about to play on, so pressing
Apply wrote nothing at all and looked broken.

These pin the shape of the answer: stand down the one step at risk, do the
rest, and say out loud which one was skipped.
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import webui  # noqa: E402


class _Session:
    empty = False
    stamp = "test"


def _run(body, steam_up, cs2_up):
    """Drive _apply with everything underneath it stubbed out.

    Nothing real is written: the two write calls are mocks, and what is
    asserted is whether they were reached at all.
    """
    state = types.SimpleNamespace(
        refresh=lambda *a, **k: None, kb=object(), machine=object(),
        cs2_install=None, cfg_folder="mrwhiteer", cfg_name="autoperf.vcfg",
        user_for=lambda account: object())
    profile = types.SimpleNamespace(intent="quality", tier="C", video={})
    launch = types.SimpleNamespace(line="", removed=[], added=[])

    with mock.patch.object(webui, "build_profile", return_value=profile), \
         mock.patch.object(webui, "plan_launch_options", return_value=launch), \
         mock.patch.object(webui.steam, "read_video_cfg", return_value={}), \
         mock.patch.object(webui.steam, "read_launch_options", return_value=""), \
         mock.patch.object(webui.steam, "steam_running", return_value=steam_up), \
         mock.patch.object(webui.steam, "cs2_running", return_value=cs2_up), \
         mock.patch.object(webui.steam, "write_video_cfg", return_value={}) as wrote_video, \
         mock.patch.object(webui.steam, "write_launch_options", return_value="set") as wrote_launch, \
         mock.patch.object(webui.backup, "BackupSession", return_value=_Session()), \
         mock.patch.object(webui.backup, "prune"), \
         mock.patch.object(webui, "_scaling_step", return_value={"ok": True, "what": "scaling",
                                                                "detail": ""}):
        out = webui._apply(state, body)
    return out, wrote_video, wrote_launch


BOTH = {"write_video": True, "write_launch": True, "write_cfg": False,
        "fix_scaling": False}


class SteamBeingOpen(unittest.TestCase):
    def test_the_picture_settings_are_still_written(self):
        """The whole complaint: Steam holds localconfig.vdf and nothing else.
        cs2_video.txt was never in danger, and refusing to write it because
        Steam happened to be open is the bug."""
        out, video, launch = _run(BOTH, steam_up=True, cs2_up=False)
        self.assertTrue(out["ok"])
        video.assert_called_once()
        launch.assert_not_called()

    def test_the_launch_options_are_named_as_skipped(self):
        out, _, _ = _run(BOTH, steam_up=True, cs2_up=False)
        self.assertEqual([s["what"] for s in out["skipped"]], ["Steam launch options"])

    def test_a_skipped_step_is_marked_as_skipped_not_failed(self):
        """The page colours these differently, and it should: a step that was
        never attempted did not go wrong."""
        out, _, _ = _run(BOTH, steam_up=True, cs2_up=False)
        stood = [s for s in out["steps"] if s.get("skipped")]
        self.assertEqual(len(stood), 1)
        self.assertIn("Close Steam", stood[0]["detail"])


class CS2BeingOpen(unittest.TestCase):
    def test_the_launch_options_are_still_written(self):
        """The mirror image, and the same reasoning: CS2 holds cs2_video.txt,
        not localconfig.vdf."""
        out, video, launch = _run(BOTH, steam_up=False, cs2_up=True)
        self.assertTrue(out["ok"])
        launch.assert_called_once()
        video.assert_not_called()

    def test_the_picture_settings_are_named_as_skipped(self):
        out, _, _ = _run(BOTH, steam_up=False, cs2_up=True)
        self.assertEqual([s["what"] for s in out["skipped"]], ["cs2_video.txt"])


class BothOpen(unittest.TestCase):
    def test_an_apply_with_nothing_left_to_do_says_so(self):
        """Rather than reporting a cheerful success that wrote nothing."""
        out, video, launch = _run(BOTH, steam_up=True, cs2_up=True)
        self.assertFalse(out["ok"])
        self.assertIn("error", out)
        video.assert_not_called()
        launch.assert_not_called()

    def test_other_work_still_goes_ahead(self):
        """With something else ticked there is a real apply to do, so it runs
        and the two held files are reported as stood down."""
        body = dict(BOTH, fix_scaling=True)
        out, _, _ = _run(body, steam_up=True, cs2_up=True)
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["skipped"]), 2)


class NothingInTheWay(unittest.TestCase):
    def test_both_are_written_and_nothing_is_skipped(self):
        out, video, launch = _run(BOTH, steam_up=False, cs2_up=False)
        self.assertTrue(out["ok"])
        self.assertEqual(out["skipped"], [])
        video.assert_called_once()
        launch.assert_called_once()

    def test_an_unticked_box_is_not_reported_as_skipped(self):
        """Choosing not to write something is not the same as being stopped."""
        body = dict(BOTH, write_video=False)
        out, video, _ = _run(body, steam_up=False, cs2_up=False)
        video.assert_not_called()
        self.assertEqual(out["skipped"], [])


if __name__ == "__main__":
    unittest.main()
