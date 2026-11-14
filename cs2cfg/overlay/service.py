"""App-owned capture lifecycle and bounded, thread-safe overlay data API.

Construction and snapshots are inert. Only configure(enabled=True) starts a
worker. Future views can read snapshots without creating polling workers here.
"""

from __future__ import annotations

import copy
import math
import threading
import time
from collections import Counter, deque

from . import permissions, settings
from .presentmon import Aggregator, PresentMon, STATUS_TEXT

WINDOWED_MODES = frozenset({
    "Hardware: Independent Flip", "Hardware Composed: Independent Flip",
    "Composed: Flip", "Composed: Copy with GPU GDI", "Composed: Copy with CPU GDI",
})


def hud_allowed(borderless: bool, modes: dict, *, frame_capture_ready: bool = True) -> bool:
    # Without capture permission, the window check still permits resource stats.
    return bool(borderless and (all(mode in WINDOWED_MODES for mode in modes)
                                if modes else not frame_capture_ready))


def hud_position(rect: tuple, corner: str) -> tuple[int, int]:
    from .hud import WIDTH, HEIGHT

    left, top, right, bottom = rect
    return (max(left + 20, right - WIDTH - 20) if corner.endswith("right") else left + 20,
            max(top + 20, bottom - HEIGHT - 20) if corner.startswith("bottom") else top + 20)


class OverlayService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._control = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._unsubscribe = None
        self._settings = settings.read()
        self._history = deque(maxlen=600)
        self._events = deque(maxlen=200)
        self._aggregator = None
        self._capture = self._hud = self._gpu = self._cpu = self._recorder = None
        self._hwnd = None
        self.panel = None
        self._modes = {}
        self._status = "disabled"
        self._notice = self._error = ""
        self._capture_denied = False
        self._reset_totals()

    def _reset_totals(self) -> None:
        self._frame_count = 0
        self._frame_sum = 0.0
        self._histogram = Counter()
        self._worst_frame = None
        self._spikes = 0
        self._worst_freeze = None
        self._started = None

    def configure(self, ui: dict) -> None:
        wanted = settings.read(ui, strict=True)
        with self._control:
            if wanted["overlay_enabled"] and self._thread and self._thread.is_alive():
                with self._lock:
                    self._settings = wanted
                    if self._hud:
                        self._configure_hud(wanted)
                return
            self._shutdown()
            with self._lock:
                self._settings = wanted
                self._status = "waiting_for_game" if wanted["overlay_enabled"] else "disabled"
                self._error = self._notice = ""
            if not wanted["overlay_enabled"]:
                return
            from .. import telemetry

            self._unsubscribe = telemetry.subscribe(self._stall, self._finalising)
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="overlay-service", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._control:
            self._shutdown()
            with self._lock:
                self._settings["overlay_enabled"] = False
                self._status = "disabled"

    def _shutdown(self) -> None:
        if self.panel:
            self.panel.hide()
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=30)
            if self._thread.is_alive():
                raise RuntimeError("Overlay worker did not stop")
            self._thread = None
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    def summary(self) -> dict:
        with self._lock:
            p99 = None
            target = math.ceil(self._frame_count * .99)
            count = 0
            for value, frequency in sorted(self._histogram.items()):
                count += frequency
                if count >= target:
                    p99 = value
                    break
            return {"avg_fps": 1000 * self._frame_count / self._frame_sum if self._frame_sum else None,
                    "one_percent_low": 1000 / p99 if p99 else None,
                    "worst_frame_ms": self._worst_frame, "stutter_count": self._spikes,
                    "worst_freeze_ms": self._worst_freeze,
                    "frame_count": self._frame_count, "started_at": self._started}

    def snapshot(self, seconds: int = 600) -> dict:
        """Detached JSON-ready data, newest events first; never starts capture."""
        from .hud import display_values

        with self._lock:
            ready = permissions.frame_capture_ready() and not self._capture_denied
            hint = permissions.frame_capture_hint(self._settings, ready=ready)
            current = dict(self._history[-1]) if self._history and self._hwnd else None
            if current is not None:
                current["frame_capture_ready"] = ready
                if not ready:
                    for key in (*settings.FIELDS[:3], "p99_frame_time_ms", "max_frame_time_ms"):
                        current[key] = None
            cutoff = time.time() - max(1, min(600, int(seconds)))
            return copy.deepcopy({
                "settings": self._settings, "status": self._status,
                "notice": self._notice, "error": self._error,
                "frame_capture_ready": ready, "frame_capture_hint": hint,
                "frame_capture_hint_dismissible": hint == permissions.SIGN_OUT_HINT,
                "display": display_values({**(current or {}), "frame_capture_ready": ready}),
                "game_running": self._hwnd is not None,
                "hud_visible": bool(self._hud and self._hud.visible),
                "hud_warning": (self._hud.error or self._hud.warning) if self._hud else "",
                "panel_warning": self.panel.error if self.panel else "",
                "current": current,
                "history": [sample for sample in self._history if sample["at"] >= cutoff],
                "events": sorted(self._events, key=lambda e: e["at"], reverse=True),
                "summary": self.summary(),
            })

    def add_event(self, event: dict) -> None:
        """Coalesce overlapping sources and consecutive unresponsive probes.

        All event times are epoch seconds at the start, durations milliseconds.
        Frame receipt timestamps are translated by ingest() to the same basis.
        Separate frame spikes remain separate events.
        """
        with self._lock:
            event = dict(event)
            event["sources"] = [event["type"]]
            start, end = event["at"], event["at"] + event["duration_ms"] / 1000
            matches = []
            for old in self._events:
                both_stalls = old["type"] == event["type"] == "not_responding"
                different = old["type"] != event["type"]
                gap = .6 if both_stalls else 0
                old_end = old["at"] + old["duration_ms"] / 1000
                if (both_stalls or different) and start <= old_end + gap and end >= old["at"] - gap:
                    matches.append(old)
                    start, end = min(start, old["at"]), max(end, old_end)
                    event["sources"] = sorted(set(event["sources"] + old["sources"]))
            for old in matches:
                self._events.remove(old)
            event.update(at=start, duration_ms=(end - start) * 1000)
            if "not_responding" in event["sources"]:
                event["type"] = "not_responding"
            # Retain the newest 200 even when an older callback arrives late.
            ordered = sorted([*self._events, event], key=lambda e: e["at"])
            self._events = deque(ordered[-200:], maxlen=200)
            self._worst_freeze = max(self._worst_freeze or 0, event["duration_ms"])

    def ingest(self, sample: dict, *, at: float | None = None) -> None:
        """Store one capture interval. Also usable by deterministic data tests."""
        with self._lock:
            sample = copy.deepcopy(sample)
            sample["at"] = time.time() if at is None else at
            for event in sample.pop("events", []):
                event["at"] -= event["duration_ms"] / 1000
                self.add_event(event)
            self._frame_count += sample.get("frame_count", 0)
            self._frame_sum += sample.get("frame_time_sum_ms", 0)
            self._spikes += sample.get("spikes", 0)
            if sample.get("max_spike_ms") is not None:
                self._worst_freeze = max(self._worst_freeze or 0, sample["max_spike_ms"])
            worst = sample.get("max_frame_time_ms")
            if worst is not None:
                self._worst_frame = max(self._worst_frame or 0, worst)
            # A bounded session distribution, with <= .001 ms rounding below
            # 10 ms, then .01/.1/1/10 ms bins. Retain exact sums and maxima.
            for value, frequency in sample.pop("frame_time_histogram_ms", {}).items():
                value = float(value)
                step = (.001 if value < 10 else .01 if value < 100 else
                        .1 if value < 1000 else 1 if value < 10000 else 10)
                bucket = min(60000, math.ceil(value / step - 1e-9) * step)
                self._histogram[bucket] += frequency
            self._history.append(sample)
            while self._history and self._history[0]["at"] < sample["at"] - 600:
                self._history.popleft()
            if self._recorder:
                self._recorder.record.overlay = self.summary()

    def _stall(self, recorder, stall) -> None:
        with self._lock:
            if recorder is not self._recorder:
                return
            self.add_event({"at": recorder.started + stall.at - stall.seconds,
                            "duration_ms": stall.seconds * 1000, "type": "not_responding",
                            "focused": stall.focused})

    def _finalising(self, recorder) -> None:
        with self._lock:
            capture = self._capture if recorder is self._recorder else None
        # The launcher can finish before the worker notices the vanished
        # window. Flush the CSV readers before the existing record is written.
        if capture:
            try:
                capture.stop()
            except Exception as exc:
                self._error = str(exc)
        with self._lock:
            if recorder is self._recorder:
                self._drain()
                recorder.record.overlay = self.summary()

    def _drain(self, *, store_empty: bool = False) -> dict:
        with self._lock:
            sample = self._aggregator.snapshot() if self._aggregator else {}
            if sample.get("frame_count") or sample.get("events") or store_empty:
                self.ingest(sample)
            return sample

    def _begin_game(self, found) -> None:
        from .. import telemetry
        from ..monitor import Monitor
        from .hud import Hud
        from .metrics import Nvml

        with self._lock:
            self._history.clear()
            self._events.clear()
            self._reset_totals()
            self._started = time.time()
            self._hwnd = found.hwnd
            self._modes = {}
            self._capture_denied = False
            self._aggregator = Aggregator()
        self._recorder = telemetry.acquire_recorder(found.hwnd, {
            "resolution": f"{found.size[0]}x{found.size[1]}",
        })
        if permissions.frame_capture_ready():
            self._capture = PresentMon(self._aggregator)
            self._capture.start()
        self._cpu, self._gpu = Monitor(), Nvml()
        self._cpu.cpu_percent()
        self._hud = Hud(corner=self._settings["overlay_corner"],
                        fields=self._settings["overlay_fields"],
                        hotkey=self._settings["overlay_hotkey"],
                        panel_hotkey=self._settings["overlay_panel_hotkey"],
                        on_panel=self.panel.toggle if self.panel else None)
        self._hud.set_allowed(False)
        try:
            self._hud.start()
            with self._lock:
                self._configure_hud(self._settings)
        except (OSError, RuntimeError) as exc:
            self._error = f"HUD: {exc}"

    def _end_game(self) -> None:
        from .. import telemetry

        if self.panel:
            self.panel.hide(restore=False)
        # Independent cleanup: a failed native resource cannot strand capture.
        for resource, method in ((self._hud, "stop"), (self._capture, "stop"), (self._gpu, "close")):
            if resource:
                try:
                    getattr(resource, method)()
                except Exception as exc:
                    self._error = str(exc)
        with self._lock:
            self._drain()
            if self._recorder:
                self._recorder.record.overlay = self.summary()
        if self._recorder:
            telemetry.release_recorder(self._recorder)
        with self._lock:
            self._capture = self._hud = self._gpu = self._cpu = self._recorder = None
            self._aggregator = None
            self._hwnd = None

    def _configure_hud(self, wanted):
        self._hud.configure(fields=wanted["overlay_fields"], hotkey=wanted["overlay_hotkey"],
                            panel_hotkey=wanted["overlay_panel_hotkey"])

    def panel_allowed(self):
        return bool(self._settings["overlay_enabled"] and self._hwnd)

    def game_hwnd(self):
        return self._hwnd

    def _run(self) -> None:
        from .. import window

        next_tick = time.monotonic()
        try:
            while not self._stop.is_set():
                found = window.find_game_window("cs2.exe")
                if self._hwnd and (found is None or found.hwnd != self._hwnd):
                    self._end_game()
                if found is None:
                    with self._lock:
                        self._status, self._notice = "waiting_for_game", ""
                    self._stop.wait(5)
                    continue
                if self._hwnd is None:
                    self._begin_game(found)
                    next_tick = time.monotonic() + 1
                if self._stop.wait(max(0, next_tick - time.monotonic())):
                    break
                metrics = {"cpu_percent": self._cpu.cpu_percent(), **self._gpu.sample()}
                with self._lock:
                    sample = self._aggregator.snapshot()
                    state = (self._capture.status(True, bool(sample["frame_count"])) if self._capture
                             else "access_denied" if self._capture_denied else "permissions_required")
                    if state == "access_denied":
                        self._capture_denied = True
                        if self._capture:
                            self._capture.stop()
                            self._capture = None
                            self._aggregator = Aggregator()
                            sample = self._aggregator.snapshot()
                    ready = self._capture is not None and not self._capture_denied
                    sample.update(metrics)
                    sample["frame_capture_ready"] = ready
                    sample["status"] = ("Frame stats unavailable" if not ready else STATUS_TEXT[state])
                    self.ingest(sample)
                modes = sample.get("present_modes", {})
                if modes:
                    self._modes = modes
                borderless = window.is_borderless(found)
                allowed = hud_allowed(borderless, self._modes, frame_capture_ready=ready)
                allowed = allowed and (state == "ok" or not ready)
                with self._lock:
                    self._status = state
                    self._notice = ("HUD needs Fullscreen Windowed. Switch to borderless in Play."
                                    if not borderless or (self._modes and not hud_allowed(True, self._modes))
                                    else "")
                self._hud.set_allowed(allowed and window.foreground_hwnd() == found.hwnd)
                self._hud.update(sample, hud_position(found.rect, self._settings["overlay_corner"]))
                next_tick += 1
                if next_tick < time.monotonic():
                    next_tick = time.monotonic() + 1
        except Exception as exc:
            with self._lock:
                self._status, self._error = "error", str(exc)
        finally:
            self._end_game()
