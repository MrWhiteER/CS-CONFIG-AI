"""Closing the window without stopping the application.

Pressing X on a launcher that is watching a game, holding a desktop mode it
has not given back yet, should put the window away rather than end all of
that. So X hides and a notification-area icon keeps the application reachable.

The property worth guarding above every other one here: **if the icon cannot
be put in the tray, X must close the window as it always did.** A window that
refuses to close with nothing to bring it back is not a small bug -- it is a
program somebody has to open Task Manager to be rid of. Most of this file is
about that one case.

Nothing here touches the real shell: the tray is a stub throughout.
"""

from __future__ import annotations

import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import desktop  # noqa: E402


class _Slot(list):
    """Stands in for pywebview's ``window.events.closing``."""

    def __iadd__(self, handler):
        self.append(handler)
        return self


class _Window:
    def __init__(self, hide_raises=False):
        self.events = types.SimpleNamespace(closing=_Slot(), closed=_Slot())
        self.hidden = 0
        self.shown = 0
        self.destroyed = 0
        self._hide_raises = hide_raises

    def hide(self):
        if self._hide_raises:
            raise RuntimeError("the window would not hide")
        self.hidden += 1

    def show(self):
        self.shown += 1

    def restore(self):
        pass

    def destroy(self):
        self.destroyed += 1


class _Tray:
    """A tray that works, unless told not to."""

    instances = []

    def __init__(self, title, icon, on_open, on_quit):
        self.title = title
        self.on_open = on_open
        self.on_quit = on_quit
        self.notices = []
        self.stopped = 0
        self.starts = True
        _Tray.instances.append(self)

    def start(self, timeout=5.0):
        return self.starts

    def stop(self):
        self.stopped += 1

    def notify(self, title, body):
        self.notices.append((title, body))
        return True


def _hook(window, tray_works=True):
    """Run the wiring with a stub tray, and hand back the stub."""
    _Tray.instances.clear()

    def make(title, icon, on_open, on_quit):
        made = _Tray(title, icon, on_open, on_quit)
        made.starts = tray_works
        return made

    with mock.patch.object(desktop.sys, "platform", "win32"), \
         mock.patch("cs2cfg.tray.Tray", side_effect=make):
        ok = desktop._keep_running_in_the_tray(window, None)
    return ok, (_Tray.instances[0] if _Tray.instances else None)


def _press_x(window):
    """What the close button ends up calling. False means "cancelled"."""
    return window.events.closing[0]()


def _settle():
    """The hide is deliberately deferred onto a timer, so give it a moment."""
    time.sleep(0.25)


class NotTrappingAnybody(unittest.TestCase):
    def test_a_tray_that_will_not_start_leaves_x_closing_the_window(self):
        """The one that matters. No icon means no way back, so the window has
        to keep behaving the way it always did."""
        window = _Window()
        ok, _ = _hook(window, tray_works=False)
        self.assertFalse(ok)
        self.assertEqual(len(window.events.closing), 0,
                         "nothing may intercept the close when there is no icon")

    def test_the_tray_module_failing_to_import_is_survivable(self):
        window = _Window()
        with mock.patch.object(desktop.sys, "platform", "win32"), \
             mock.patch.dict(sys.modules, {"cs2cfg.tray": None}):
            ok = desktop._keep_running_in_the_tray(window, None)
        self.assertFalse(ok)
        self.assertEqual(len(window.events.closing), 0)

    def test_it_does_nothing_off_windows(self):
        window = _Window()
        with mock.patch.object(desktop.sys, "platform", "linux"):
            self.assertFalse(desktop._keep_running_in_the_tray(window, None))
        self.assertEqual(len(window.events.closing), 0)

    def test_quit_from_the_tray_really_quits(self):
        """Otherwise the only way out is Task Manager."""
        window = _Window()
        ok, tray = _hook(window)
        self.assertTrue(ok)
        tray.on_quit()
        self.assertEqual(window.destroyed, 1)
        self.assertEqual(tray.stopped, 1, "the icon should go with the window")

    def test_a_close_after_quit_is_allowed_through(self):
        """Quit hides nothing and cancels nothing: it asked for this."""
        window = _Window()
        _, tray = _hook(window)
        tray.on_quit()
        self.assertTrue(_press_x(window), "the close must go ahead")


class PressingX(unittest.TestCase):
    def test_it_cancels_the_close_and_hides_instead(self):
        window = _Window()
        _hook(window)
        self.assertFalse(_press_x(window), "False is what cancels the close")
        _settle()
        self.assertEqual(window.hidden, 1)
        self.assertEqual(window.destroyed, 0)

    def test_the_hide_does_not_happen_inside_the_close_handler(self):
        """Hiding a WinForms window from inside its own close handler
        re-enters it: the call does not come back, the handler never returns,
        and the close goes through as though nothing had objected. Which is
        what it did, on a real window, before this was deferred."""
        window = _Window()
        _hook(window)
        _press_x(window)
        self.assertEqual(window.hidden, 0, "hidden too early -- this re-enters")
        _settle()
        self.assertEqual(window.hidden, 1)

    def test_the_notification_is_shown_once_and_not_again(self):
        """Saying it on every close is the kind of notification people turn
        off, and then the one time it matters they do not see it."""
        window = _Window()
        _, tray = _hook(window)
        for _ in range(4):
            _press_x(window)
            _settle()
        self.assertEqual(len(tray.notices), 1)
        self.assertEqual(window.hidden, 4)

    def test_the_notification_says_where_the_window_went(self):
        window = _Window()
        _, tray = _hook(window)
        _press_x(window)
        _settle()
        title, body = tray.notices[0]
        self.assertIn("still running", title.lower())
        self.assertIn("notification area", body.lower())

    def test_a_window_that_will_not_hide_is_not_pestered_about_it(self):
        """It stays open, nothing is announced, and nothing raises."""
        window = _Window(hide_raises=True)
        _, tray = _hook(window)
        _press_x(window)
        _settle()
        self.assertEqual(tray.notices, [],
                         "announcing a hide that did not happen would be a lie")

    def test_clicking_the_icon_brings_the_window_back(self):
        window = _Window()
        _, tray = _hook(window)
        _press_x(window)
        _settle()
        tray.on_open()
        self.assertEqual(window.shown, 1)


class TheIconItself(unittest.TestCase):
    """The parts of the Win32 side that can be checked without a shell."""

    def test_every_handle_call_declares_its_types(self):
        """ctypes assumes a 32-bit int for anything undeclared, and a handle
        on 64-bit Windows is 64 bits. Undeclared returns truncate silently and
        work right up until a handle is large; undeclared arguments raise. Both
        happened here before they were declared."""
        if sys.platform != "win32":
            self.skipTest("Windows only")
        from cs2cfg import tray

        for name in ("CreateWindowExW", "LoadImageW", "LoadIconW", "CreatePopupMenu"):
            fn = getattr(tray.user32, name)
            self.assertIsNotNone(fn.restype, f"{name} returns a handle undeclared")
        self.assertIsNotNone(tray.user32.CreateWindowExW.argtypes)
        self.assertIsNotNone(tray.shell32.Shell_NotifyIconW.argtypes)

    def test_a_callback_that_raises_does_not_take_the_loop_with_it(self):
        """The message loop is the only route back to the window."""
        if sys.platform != "win32":
            self.skipTest("Windows only")
        from cs2cfg import tray

        def boom():
            raise RuntimeError("no")

        tray.Tray._safely(boom)      # must not raise


if __name__ == "__main__":
    unittest.main()
