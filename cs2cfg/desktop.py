"""Desktop application shell.

Runs the existing web interface inside a native window instead of a browser
tab, so it behaves like an ordinary Windows program: its own taskbar entry,
title, and icon; no terminal; no separately managed server.

How it holds together:

* The HTTP server binds ``127.0.0.1`` on an **ephemeral port**, so two copies
  can never collide over a fixed one and nothing is exposed to the network.
* A named mutex enforces a single instance. A second launch does not start a
  rival server -- it raises the window that is already open and exits.
* The server is a daemon thread owned by the window. Closing the window shuts
  it down; there is no background service left running afterwards.
* If the native window cannot be created, it falls back to a chromeless browser
  window rather than failing outright, and says which it used.
"""

from __future__ import annotations

import ctypes
import os
import socket
import sys
import threading
import traceback
import webbrowser
from ctypes import wintypes
from pathlib import Path
from typing import Callable, Optional, Tuple

from . import __version__, appicon, webui
from .paths import app_dir, is_frozen, storage_kind, user_data_dir

APP_NAME = "CS2 Launcher"

# How Windows identifies this application to itself. It decides the name and
# the icon at the head of a notification, which is why it is here: without it
# Windows falls back to the executable's filename and a blank icon, so a
# notification about "CS2 Launcher" arrived titled "CS2 Launcher.exe" with
# nothing beside it.
#
# Windows resolves the name and icon by matching this against a Start Menu
# shortcut carrying the same id, which the installer sets. A portable copy has
# no shortcut to match, so it keeps the filename -- there is nowhere for
# Windows to read a nicer one from, and there is no inventing one.
APP_USER_MODEL_ID = "MrWhiteER.CS2Launcher"


def _claim_identity() -> bool:
    """Tell Windows who this process is, before any window exists.

    Has to happen before the first window or notification, because Windows
    works the identity out once and then keeps it.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        set_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_id.argtypes = [ctypes.c_wchar_p]
        return set_id(APP_USER_MODEL_ID) == 0
    except Exception:
        # Cosmetic. A launcher that refuses to start because it could not name
        # itself would be a poor trade.
        return False
WINDOW_TITLE = f"{APP_NAME} — cs2-autoconfig"
MUTEX_NAME = "Global\\cs2-autoconfig-desktop-singleton"

ERROR_ALREADY_EXISTS = 183


class StartupError(RuntimeError):
    """The application could not start, with a reason worth showing."""


# ---------------------------------------------------------------------------
# Single instance
# ---------------------------------------------------------------------------

class SingleInstance:
    """A named mutex held for the lifetime of the process."""

    def __init__(self, name: str = MUTEX_NAME) -> None:
        self.name = name
        self.handle = None
        self.already_running = False

    def acquire(self) -> bool:
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
            self.handle = kernel32.CreateMutexW(None, False, self.name)
            self.already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
        except (OSError, AttributeError):
            # Not Windows, or the call is unavailable. Better to allow a second
            # instance than to refuse to start at all.
            self.already_running = False
        return not self.already_running

    def release(self) -> None:
        if self.handle:
            try:
                ctypes.WinDLL("kernel32").CloseHandle(self.handle)
            except OSError:
                pass
            self.handle = None


def focus_existing_window(title_fragment: str = APP_NAME,
                          same_process: bool = False,
                          include_hidden: bool = False) -> bool:
    """Bring a window of this application to the front.

    ``same_process`` restricts the search to windows this process owns. The
    single-instance path wants the opposite -- it is looking for the *other*
    copy, which is the whole point -- but anything raising the window on its
    own behalf must not reach across processes: run from source with a copy
    of the installed app also open, a title match finds that one and yanks an
    unrelated window to the front. With this set, a session that owns no
    window (the interface open in an ordinary browser tab) simply raises
    nothing, which is the honest answer.

    ``include_hidden`` keeps windows that are not on screen. Closing to the
    notification area hides the window rather than destroying it, so the one
    copy worth finding -- the one somebody is trying to reopen by starting the
    application again -- is exactly the one a visibility test throws away.
    Only the single-instance path asks for this; anything raising a window to
    show somebody something still wants one that is on screen.
    """
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
    except OSError:
        return False

    # Every match, not the first: a title containing the application's name
    # is not the same thing as the application's window. Its own error boxes
    # are called "CS2 Launcher could not start", and the graphics layer leaves
    # a helper called "GDI+ Window (CS2 Launcher.exe)" lying around. Raising
    # either of those instead of the window is worse than raising nothing,
    # and raising a stale error dialog is exactly what happened.
    found: list = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if title_fragment.lower() not in buffer.value.lower():
            return True
        if not include_hidden and not user32.IsWindowVisible(hwnd):
            return True
        if same_process:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != os.getpid():
                return True
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, name, 256)
        found.append((hwnd, buffer.value, name.value))
        return True

    user32.EnumWindows(callback, 0)

    DIALOG = "#32770"
    real = [(hwnd, title) for hwnd, title, cls in found
            if cls != DIALOG and "GDI+" not in title]
    if not real:
        return False

    # The window's actual title first, and any other survivor after it.
    best = next((hwnd for hwnd, title in real if title == WINDOW_TITLE), real[0][0])
    return _to_front(user32, best)


class _FlashInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND),
                ("dwFlags", wintypes.DWORD), ("uCount", wintypes.UINT),
                ("dwTimeout", wintypes.DWORD)]


FLASHW_ALL = 0x00000003
FLASHW_TIMERNOFG = 0x0000000C


def _to_front(user32, hwnd) -> bool:
    """Actually raise a window, not merely ask to.

    Windows refuses ``SetForegroundWindow`` from a process that is not already
    foreground -- it is what stops background programs stealing the keyboard
    mid-sentence. The documented way to be allowed is to share an input queue
    with the window that currently holds focus, so this attaches to that
    thread for the length of the call and detaches straight after.

    When even that is refused -- a full-screen exclusive app owns the input --
    the window is flashed in the taskbar instead. Flashing is the fallback
    rather than the failure: the request was to get the player's attention,
    and a taskbar flash does that without fighting the OS.
    """
    # Shown before restored. A window closed to the notification area is
    # hidden rather than minimised, and SW_RESTORE alone leaves a hidden
    # window hidden -- it un-minimises, which is a different thing.
    user32.ShowWindow(hwnd, 5)          # SW_SHOW
    user32.ShowWindow(hwnd, 9)          # SW_RESTORE
    current = user32.GetForegroundWindow()
    if current == hwnd:
        return True

    ours = user32.GetWindowThreadProcessId(hwnd, None)
    theirs = user32.GetWindowThreadProcessId(current, None) if current else 0

    attached = bool(theirs and ours and theirs != ours
                    and user32.AttachThreadInput(theirs, ours, True))
    try:
        user32.BringWindowToTop(hwnd)
        raised = bool(user32.SetForegroundWindow(hwnd))
    finally:
        if attached:
            user32.AttachThreadInput(theirs, ours, False)

    if raised and user32.GetForegroundWindow() == hwnd:
        return True

    flash = _FlashInfo(ctypes.sizeof(_FlashInfo), hwnd,
                       FLASHW_ALL | FLASHW_TIMERNOFG, 0, 0)
    user32.FlashWindowEx(ctypes.byref(flash))
    return False


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class BackgroundServer:
    """The web UI's HTTP server, owned by the window rather than the user."""

    def __init__(self, cfg_folder: str, cfg_name: str, port: Optional[int] = None) -> None:
        self.port = port or _free_port()
        self.server, self.state = webui.serve(self.port, cfg_folder, cfg_name)
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self.server.serve_forever, daemon=True, name="cs2cfg-http"
        )
        self._thread.start()

    def wait_until_ready(self, timeout: float = 10.0) -> bool:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return True
            except OSError:
                time.sleep(0.1)
        return False

    def stop(self) -> None:
        try:
            self.server.shutdown()
        except Exception:
            pass
        try:
            self.server.server_close()
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)


# ---------------------------------------------------------------------------
# Error reporting
# ---------------------------------------------------------------------------

def show_error(message: str, detail: str = "") -> None:
    """Report a startup failure somewhere the user will actually see it.

    A desktop launch has no console to print to, so a message box is the only
    place a failure is visible. Falls back to stderr when even that is not
    available.
    """
    body = message if not detail else f"{message}\n\n{detail}"
    try:
        ctypes.WinDLL("user32").MessageBoxW(
            None, body, f"{APP_NAME} could not start", 0x10 | 0x0
        )
        return
    except OSError:
        pass
    print(f"{APP_NAME} could not start: {body}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

def _launch_webview(url: str, icon: Optional[Path], on_closed: Callable[[], None]) -> bool:
    """Native window via pywebview. Returns False if unavailable."""
    try:
        import webview
    except ImportError:
        return False

    try:
        window = webview.create_window(
            WINDOW_TITLE,
            url,
            width=1180,
            height=860,
            min_size=(760, 560),
            confirm_close=False,
        )
        window.events.closed += on_closed
        _keep_running_in_the_tray(window, icon)

        kwargs = {}
        if icon and icon.exists():
            kwargs["icon"] = str(icon)
        try:
            webview.start(**kwargs)
        except TypeError:
            # Older builds do not accept an icon argument.
            webview.start()
        return True
    except Exception:
        return False


def _keep_running_in_the_tray(window, icon: Optional[Path]) -> bool:
    """Make X put the window away rather than end the application.

    Closing the window while a game is being watched ends the watch, and with
    it the thing that gives the desktop mode back. Hiding costs nothing and
    keeps all of that alive.

    The application only behaves this way if the icon is actually there to
    bring it back. A window that refuses to close with nothing in the tray to
    close it from is a program somebody has to open Task Manager to be rid of,
    so every failure here leaves X closing the window as it always did.
    """
    if sys.platform != "win32":
        return False
    try:
        from .tray import Tray
    except Exception:
        return False

    state = {"quitting": False, "told": False}

    def open_window() -> None:
        try:
            window.show()
            window.restore()
        except Exception:
            pass
        # ...and to the front, not merely on screen. Done from in here
        # because this process owns the window: a copy reaching in from
        # outside can make it visible but cannot hand it the keyboard.
        try:
            focus_existing_window(same_process=True, include_hidden=True)
        except Exception:
            pass

    def quit_app() -> None:
        state["quitting"] = True
        try:
            icon_handle.stop()
        except Exception:
            pass
        try:
            window.destroy()
        except Exception:
            pass

    icon_handle = Tray(APP_NAME, icon, on_open=open_window, on_quit=quit_app)
    if not icon_handle.start():
        return False

    def put_away() -> None:
        try:
            window.hide()
        except Exception:
            return
        if not state["told"]:
            # Once. Saying it every time somebody closes the window would be
            # the kind of notification people turn off, and then the one time
            # it matters they do not see it.
            state["told"] = True
            icon_handle.notify(
                f"{APP_NAME} is still running",
                "It is in the notification area, bottom right. Click the icon to "
                "open it again, or right-click it to quit.")

    def on_closing():
        # Quit chose this, so let it happen.
        if state["quitting"]:
            return True
        # Hidden from a timer rather than from here. This runs inside the
        # window's own close handler, and hiding a WinForms window from inside
        # that handler re-enters it -- the call does not come back, the
        # handler never returns, and the close goes through as though nothing
        # had objected. Which is exactly what it did. Cancelling first and
        # hiding a moment later keeps the two apart.
        threading.Timer(0.05, put_away).start()
        return False             # cancels the close

    window.events.closing += on_closing
    return True


def _launch_browser_app_window(url: str) -> bool:
    """Fallback: a chromeless browser window via --app=.

    Not as good as a native window -- the icon and title come from the browser
    -- but it still opens without visible browser furniture and needs nothing
    installed beyond Edge, which ships with Windows.
    """
    import subprocess

    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    for exe in candidates:
        if not exe.exists():
            continue
        try:
            subprocess.Popen([
                str(exe), f"--app={url}", "--window-size=1180,860",
                f"--user-data-dir={user_data_dir() / 'browser-profile'}",
            ])
            return True
        except OSError:
            continue
    return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(
    cfg_folder: str = "mrwhiteer",
    cfg_name: str = "autoperf.vcfg",
    port: Optional[int] = None,
    fallback_to_browser: bool = True,
) -> int:
    """Start the desktop application. Returns a process exit code."""
    instance = SingleInstance()
    if not instance.acquire():
        # Starting it again is how people reopen something they put away, so
        # the second copy's whole job is to fetch the first one back: out of
        # the notification area if that is where it went, off the taskbar if
        # it was minimised. Hidden windows are included for exactly that
        # reason -- after a close to the tray the window to find is not on
        # screen, and refusing to look at it is why this said "already
        # running" at somebody instead of doing the obvious thing.
        # Asked of the running copy first. It can show its own window
        # properly -- and so take focus -- where reaching in from here can
        # only make it visible. Raising it from out here stays as the answer
        # for a copy with no notification icon, which is every copy before
        # this feature existed and any that could not create one.
        summoned = False
        try:
            from .tray import summon

            summoned = summon()
        except Exception:
            summoned = False
        if summoned:
            # Post and leave. Reaching for the window as well deadlocks: the
            # raise attaches to the other copy's input queue, and that queue
            # is busy showing the window this very message asked for. The
            # copy that was summoned raises itself, which it can do properly
            # because it owns the window.
            return 0
        if not focus_existing_window(include_hidden=True):
            show_error(
                f"{APP_NAME} is already running.",
                "Its window could not be brought to the front. Look for it on the taskbar, or "
                "close the existing instance and try again.",
            )
        return 0

    server: Optional[BackgroundServer] = None
    try:
        try:
            server = BackgroundServer(cfg_folder, cfg_name, port)
            server.start()
        except OSError as exc:
            raise StartupError(
                "The local interface could not be started.",
            ) from exc

        if not server.wait_until_ready():
            raise StartupError(
                "The local interface did not come up in time.",
            )

        # Before the window, which is when Windows settles on what this
        # application is called and what it looks like.
        _claim_identity()

        icon = None
        try:
            icon = appicon.ensure_icon(user_data_dir())
        except OSError:
            pass

        closed = threading.Event()

        def on_closed() -> None:
            closed.set()

        opened = _launch_webview(server.url, icon, on_closed)

        if not opened and fallback_to_browser:
            if _launch_browser_app_window(server.url):
                opened = True
                # Nothing tells us when a browser window closes, so hold the
                # process open until the user stops it.
                print(f"{APP_NAME} is running at {server.url}")
                print("Native window unavailable; opened a browser app window instead.")
                print("Press Ctrl+C to quit.")
                try:
                    threading.Event().wait()
                except KeyboardInterrupt:
                    pass
            elif webbrowser.open(server.url):
                opened = True
                print(f"{APP_NAME} is running at {server.url}. Press Ctrl+C to quit.")
                try:
                    threading.Event().wait()
                except KeyboardInterrupt:
                    pass

        if not opened:
            raise StartupError(
                "No window could be opened.",
                "This needs either the Microsoft Edge WebView2 runtime (normally present on "
                f"Windows 10 and 11) or any browser. The interface is still reachable at "
                f"{server.url} while this window is open.",
            )
        return 0

    except StartupError as exc:
        show_error(str(exc.args[0]), exc.args[1] if len(exc.args) > 1 else "")
        return 1
    except Exception as exc:  # never die silently with no window and no console
        show_error(
            "An unexpected error stopped the application from starting.",
            f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc(limit=4)}",
        )
        return 1
    finally:
        if server is not None:
            server.stop()
        instance.release()


def describe_environment() -> dict:
    """Facts the UI and the CLI both want to show about where things live."""
    return {
        "app_name": APP_NAME,
        "version": __version__,
        "frozen": is_frozen(),
        "app_dir": str(app_dir()),
        "data_dir": str(user_data_dir()),
        "storage": storage_kind(),
    }
