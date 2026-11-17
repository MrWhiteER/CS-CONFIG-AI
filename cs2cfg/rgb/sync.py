"""Keeps the desk's lights matching the keyboard tab.

Off by default. When switched on, a background thread finds whichever
lighting APIs are present (Razer Chroma, SteelSeries GG, OpenRGB), paints the
current board on each, keeps their sessions alive, and looks again every half
minute for one that was not running before. Switching off, or closing the
app, hands every device back to its own software, which restores the user's
normal lighting.

No administrator, no driver, no install: each API is a local server the
vendor's own app already runs.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from . import palette
from .base import Provider, owner_vendors

KEEPALIVE_S = 5.0
REPROBE_S = 30.0

FREE_MODES = ("dim", "off")
DEFAULTS = {"rgb_enabled": False, "rgb_free": "dim", "rgb_brightness": 100}


def read_settings(ui: Optional[Mapping[str, Any]] = None, *, strict: bool = False) -> dict:
    ui = ui or {}
    out = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        if key not in ui:
            continue
        value = ui[key]
        if key == "rgb_enabled":
            ok = isinstance(value, bool)
        elif key == "rgb_free":
            ok = value in FREE_MODES
        else:
            ok = isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100
        if ok:
            out[key] = value
        elif strict:
            raise ValueError(f"Invalid {key}.")
    return out


def default_providers() -> List[Provider]:
    from .chroma import ChromaProvider
    from .gamesense import GameSenseProvider
    from .openrgb import OpenRGBProvider

    # Vendor APIs first; OpenRGB last, so it can leave their devices alone.
    return [ChromaProvider(), GameSenseProvider(), OpenRGBProvider()]


def _slim(bound: Mapping[str, Mapping[str, Any]]) -> Dict[str, dict]:
    """Only what the colour depends on, so the cache holds no commands."""
    return {k: {f: v.get(f) for f in ("script", "enabled", "is_default") if f in v}
            for k, v in bound.items()}


class RgbSync:
    def __init__(self, providers: Optional[Callable[[], List[Provider]]] = None,
                 cache: Optional[Path] = None) -> None:
        self._make = providers or default_providers
        self.cache = cache
        self.settings = dict(DEFAULTS)
        self.providers: List[Provider] = []
        self.error = ""
        self._bound: Optional[Dict[str, dict]] = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._halt = threading.Event()
        self._dirty = False
        self._thread: Optional[threading.Thread] = None
        if cache:
            try:
                self._bound = json.loads(Path(cache).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._bound = None

    # -- called by the web layer ---------------------------------------------
    def configure(self, settings: Mapping[str, Any]) -> None:
        with self._lock:
            self.settings = read_settings(settings)
            self._dirty = True
            enabled = self.settings["rgb_enabled"]
        if enabled:
            if self._bound is not None:
                self._save(self._bound)
            self._ensure_thread()
            self._wake.set()
        else:
            self.stop()

    def _save(self, slim: Dict[str, dict]) -> None:
        if not self.cache:
            return
        try:
            Path(self.cache).parent.mkdir(parents=True, exist_ok=True)
            Path(self.cache).write_text(json.dumps(slim), encoding="utf-8")
        except OSError:
            pass

    def update(self, bound: Mapping[str, Mapping[str, Any]]) -> None:
        """The keyboard tab's latest ``bound`` map; repaints if it changed."""
        slim = _slim(bound)
        with self._lock:
            if slim == self._bound:
                return
            self._bound = slim
            self._dirty = True
            enabled = self.settings["rgb_enabled"]
        # Remembered only while in use: a PC that never turns lighting on
        # never gets the file.
        if enabled:
            self._save(slim)
        self._wake.set()

    def frame(self) -> Optional[palette.Frame]:
        with self._lock:
            if self._bound is None:
                return None
            return palette.frame(self._bound, free=self.settings["rgb_free"],
                                 brightness=self.settings["rgb_brightness"])

    def status(self) -> dict:
        with self._lock:
            known = {p.id: p.status() for p in self.providers}
            return {
                "enabled": self.settings["rgb_enabled"],
                "settings": dict(self.settings),
                "running": bool(self._thread and self._thread.is_alive()),
                "has_board": self._bound is not None,
                "providers": list(known.values()),
                "error": self.error,
            }

    def stop(self) -> None:
        """Hand every light back and end the thread. Safe to call twice."""
        self._halt.set()
        self._wake.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=5)
        self._thread = None
        self._release()

    # -- the loop ------------------------------------------------------------
    def _ensure_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._halt.clear()
        self._thread = threading.Thread(target=self._run, name="rgb-sync", daemon=True)
        self._thread.start()

    def _release(self) -> None:
        with self._lock:
            providers = list(self.providers)
        for p in providers:
            if p.active:
                try:
                    p.stop()
                except Exception:
                    p.active = False

    def _run(self) -> None:
        with self._lock:
            self.providers = self._make()
        since_probe = REPROBE_S
        while not self._halt.is_set():
            if since_probe >= REPROBE_S or not any(p.active for p in self.providers):
                self._connect_missing()
                since_probe = 0.0
            frame = None
            with self._lock:
                dirty, self._dirty = self._dirty, False
            if dirty:
                frame = self.frame()
            for p in self.providers:
                if not p.active:
                    continue
                try:
                    if frame is not None:
                        p.apply(frame)
                    else:
                        p.keepalive()
                except Exception as exc:
                    self._drop(p, exc)
            self._wake.wait(KEEPALIVE_S)
            self._wake.clear()
            since_probe += KEEPALIVE_S
        self._release()

    def _connect_missing(self) -> None:
        # Taking a device with nothing to show would only blank it.
        with self._lock:
            if self._bound is None:
                return
        started = False
        for p in self.providers:
            if p.active or self._halt.is_set():
                continue
            try:
                if not p.probe():
                    continue
                if hasattr(p, "skip_vendors"):
                    p.skip_vendors = owner_vendors(self.providers)
                p.start()
                started = True
            except Exception as exc:
                self._drop(p, exc)
        if started:
            with self._lock:
                self._dirty = True

    def _drop(self, p: Provider, exc: Exception) -> None:
        p.why = f"{type(exc).__name__}: {exc}"
        try:
            p.stop()
        except Exception:
            pass
        p.active = False
