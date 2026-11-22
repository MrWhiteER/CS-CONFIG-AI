"""Notice CS2 closing, however it closed, and ask about the session's changes.

The game can end three ways: ``quit`` in its console or the menu, closing it
from the taskbar, or killing it in Task Manager. All three end the same way
from out here -- the cs2.exe process is gone -- so that is what is watched: a
list of running processes every two seconds, the same cheap Windows call
Task Manager itself uses. Nothing in the game is opened or touched.

The moment it is gone:

1. CS2's own settings files are compared straight away (a normal quit has
   written them by then; a killed game never saved its changes, so there is
   honestly nothing to find), which records anything changed in the game's
   menus in the change history.
2. If anything in the history is waiting for an answer -- changes made in the
   game, in the app while the game ran, or in NVIDIA's tools -- the review
   window is asked for. It comes up on top of everything.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from . import history

GAME_EXE = "cs2.exe"


def _game_up() -> bool:
    from .faceit_apps import _pids

    return bool(_pids(GAME_EXE))


class Watcher:
    def __init__(self, on_closed: Optional[Callable[[], None]] = None,
                 interval: float = 2.0,
                 is_running: Callable[[], bool] = _game_up) -> None:
        # Called first when the game goes, before the review is asked for:
        # the server uses it to read CS2's settings files at once.
        self.on_closed = on_closed
        self.interval = interval
        self.is_running = is_running
        self.running = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def tick(self) -> Optional[str]:
        """One look. Returns 'started', 'closed' or None."""
        try:
            up = bool(self.is_running())
        except Exception:
            return None
        if up and not self.running:
            self.running = True
            history.session_started()
            return "started"
        if not up and self.running:
            self.running = False
            history.session_ended()
            if self.on_closed is not None:
                try:
                    self.on_closed()
                except Exception:
                    pass
            history.request_review()
            return "closed"
        return None

    def _run(self) -> None:
        # A game already up when the app starts is a session too.
        self.tick()
        while not self._stop.wait(self.interval):
            self.tick()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="cs2cfg-session-watch")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


_shared: Optional[Watcher] = None


def shared() -> Optional[Watcher]:
    return _shared


def start(on_closed: Optional[Callable[[], None]] = None) -> Watcher:
    global _shared
    if _shared is None:
        _shared = Watcher(on_closed=on_closed)
        _shared.start()
    return _shared


def game_running() -> bool:
    w = _shared
    if w is not None:
        return w.running
    try:
        return _game_up()
    except Exception:
        return False

