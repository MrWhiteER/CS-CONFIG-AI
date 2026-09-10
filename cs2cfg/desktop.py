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


def focus_existing_window(title_fragment: str = APP_NAME) -> bool:
    """Bring an already-running instance to the front."""
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
    except OSError:
        return False

    found: list = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if title_fragment.lower() in buffer.value.lower() and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(callback, 0)
    if not found:
        return False

    hwnd = found[0]
    user32.ShowWindow(hwnd, 9)      # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return True


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
        if not focus_existing_window():
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
