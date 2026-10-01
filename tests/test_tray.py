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

import ctypes
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


class StartingItAgain(unittest.TestCase):
    """Launching the application when a copy is already running.

    It used to say "already running" and leave you to find the window. Worse
    after closing to the notification area: the window is hidden then, and the
    search skipped anything not on screen, so the one window worth finding was
    the one it refused to look at.
    """

    def test_summon_says_no_when_nothing_is_listening(self):
        """Also the regression guard for the import that was missing: this
        raised NameError, the caller swallowed it, and the fallback path it
        fell into deadlocked."""
        if sys.platform != "win32":
            self.skipTest("Windows only")
        from cs2cfg import tray

        with mock.patch.object(tray.user32, "FindWindowExW", return_value=0):
            self.assertFalse(tray.summon())

    def test_the_host_window_has_a_fixed_name(self):
        """Another process has to be able to find it. A name built from the
        instance is unfindable, which is the whole reason it is a constant."""
        if sys.platform != "win32":
            self.skipTest("Windows only")
        from cs2cfg import tray

        self.assertIsInstance(tray.WINDOW_CLASS, str)
        self.assertNotIn("{", tray.WINDOW_CLASS)
        one = tray.Tray("a", None, on_open=lambda: None, on_quit=lambda: None)
        two = tray.Tray("b", None, on_open=lambda: None, on_quit=lambda: None)
        self.assertEqual(tray.WINDOW_CLASS, tray.WINDOW_CLASS)
        del one, two

    def test_it_hands_over_the_right_to_come_forward(self):
        """Windows will not let a background process take the foreground. The
        copy just started by somebody is the one holding that right, so it
        passes it on before asking the other copy to show itself."""
        if sys.platform != "win32":
            self.skipTest("Windows only")
        from cs2cfg import tray

        allowed = []
        with mock.patch.object(tray.user32, "FindWindowExW", return_value=4242),              mock.patch.object(tray.user32, "GetWindowThreadProcessId",
                               side_effect=lambda h, out: out._obj.__setattr__("value", 77)),              mock.patch.object(tray.user32, "AllowSetForegroundWindow",
                               side_effect=lambda pid: allowed.append(pid) or 1),              mock.patch.object(tray.user32, "PostMessageW", return_value=1):
            self.assertTrue(tray.summon())
        self.assertEqual(allowed, [77], "the other copy was never granted it")


class TheSecondCopy(unittest.TestCase):
    """What `run` does when the mutex is already held."""

    def _run_second(self, summon_works):
        from cs2cfg import desktop as d

        taken = mock.MagicMock()
        taken.acquire.return_value = False
        with mock.patch.object(d, "SingleInstance", return_value=taken),              mock.patch("cs2cfg.tray.summon", return_value=summon_works),              mock.patch.object(d, "focus_existing_window", return_value=True) as raise_it,              mock.patch.object(d, "show_error") as complained:
            code = d.run()
        return code, raise_it, complained

    def test_a_successful_summon_does_not_also_reach_for_the_window(self):
        """Doing both deadlocks: the raise attaches to the other copy's input
        queue, and that queue is busy showing the window this very message
        asked for. It hung for the full timeout."""
        code, raise_it, complained = self._run_second(summon_works=True)
        self.assertEqual(code, 0)
        raise_it.assert_not_called()
        complained.assert_not_called()

    def test_without_a_notification_icon_it_still_raises_the_window(self):
        """Every copy built before the icon existed, and any that could not
        make one."""
        code, raise_it, complained = self._run_second(summon_works=False)
        self.assertEqual(code, 0)
        raise_it.assert_called_once()
        self.assertTrue(raise_it.call_args.kwargs.get("include_hidden"),
                        "a window closed to the tray is hidden; it has to be included")
        complained.assert_not_called()

    def test_it_only_complains_when_nothing_at_all_could_be_found(self):
        from cs2cfg import desktop as d

        taken = mock.MagicMock()
        taken.acquire.return_value = False
        with mock.patch.object(d, "SingleInstance", return_value=taken),              mock.patch("cs2cfg.tray.summon", return_value=False),              mock.patch.object(d, "focus_existing_window", return_value=False),              mock.patch.object(d, "show_error") as complained:
            self.assertEqual(d.run(), 0)
        complained.assert_called_once()


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

    def test_the_balloon_asks_for_the_logo_before_settling_for_less(self):
        """Reported with a screenshot: every notification showed the generic
        blue information icon instead of the application's mark.

        Windows is particular about the pairing and says only "incorrect size
        argument" when it is not happy -- NIIF_USER on its own wants the small
        icon, and the large one needs NIIF_LARGE_ICON with it. The first
        version passed the large icon with the bare flag, so the real icon was
        refused every time and the fallback was all anybody ever saw.
        """
        if sys.platform != "win32":
            self.skipTest("Windows only")
        from cs2cfg import tray

        icon = tray.Tray("t", None, on_open=lambda: None, on_quit=lambda: None)
        icon._ok = True
        icon._hwnd = 1
        icon._hicon = 111
        icon._hicon_large = 222

        tried = []

        def refuse(action, blob):
            data = ctypes.cast(blob, ctypes.POINTER(tray.NOTIFYICONDATAW)).contents
            tried.append((data.dwInfoFlags, data.hBalloonIcon))
            return 0

        with mock.patch.object(tray.shell32, "Shell_NotifyIconW", side_effect=refuse):
            self.assertFalse(icon.notify("t", "b"))

        self.assertEqual([flags for flags, _ in tried],
                         [tray.NIIF_USER | tray.NIIF_LARGE_ICON,
                          tray.NIIF_USER,
                          tray.NIIF_INFO])
        # The large icon goes with the large flag and the small one without.
        self.assertEqual(tried[0][1], 222)
        self.assertEqual(tried[1][1], 111)

    def test_it_stops_at_the_first_pairing_windows_accepts(self):
        if sys.platform != "win32":
            self.skipTest("Windows only")
        from cs2cfg import tray

        icon = tray.Tray("t", None, on_open=lambda: None, on_quit=lambda: None)
        icon._ok, icon._hwnd, icon._hicon, icon._hicon_large = True, 1, 111, 222
        calls = []
        with mock.patch.object(tray.shell32, "Shell_NotifyIconW",
                               side_effect=lambda *a: calls.append(a) or 1):
            self.assertTrue(icon.notify("t", "b"))
        self.assertEqual(len(calls), 1, "it should not keep going after success")

    def test_the_two_icon_sizes_are_asked_for_separately(self):
        """One handle for both is what caused this: the tray showed a 32 px
        icon squashed into 16, and the balloon refused it outright."""
        if sys.platform != "win32":
            self.skipTest("Windows only")
        from cs2cfg import tray

        asked = []
        with mock.patch.object(tray.user32, "LoadImageW",
                               side_effect=lambda *a: asked.append((a[3], a[4])) or 1),              mock.patch.object(Path, "exists", return_value=True):
            icon = tray.Tray("t", Path("x.ico"), on_open=lambda: None,
                             on_quit=lambda: None)
            icon._load_icon()
        self.assertEqual(len(asked), 2)
        self.assertNotEqual(asked[0], asked[1], "both loaded at the same size")

    def test_the_application_names_itself_to_windows(self):
        """The head of a notification showed "CS2 Launcher.exe" and a blank
        icon. Windows takes both from the process's application id, matched
        against a shortcut carrying the same one, so the id has to be set and
        the installer has to put the same string on the shortcut."""
        if sys.platform != "win32":
            self.skipTest("Windows only")
        import ctypes
        from pathlib import Path as P

        from cs2cfg import desktop as d

        self.assertTrue(d._claim_identity())
        got = ctypes.c_wchar_p()
        ctypes.windll.shell32.GetCurrentProcessExplicitAppUserModelID(
            ctypes.byref(got))
        self.assertEqual(got.value, d.APP_USER_MODEL_ID)

        # The two halves are useless apart, so they are checked together.
        installer = (P(__file__).resolve().parents[1] / "installer.iss").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn(f'AppUserModelID: "{d.APP_USER_MODEL_ID}"', installer)

    def test_naming_itself_is_never_fatal(self):
        """Cosmetic. A launcher that will not start because it could not name
        itself would be a poor trade."""
        from cs2cfg import desktop as d

        with mock.patch.object(d.sys, "platform", "linux"):
            self.assertFalse(d._claim_identity())

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
