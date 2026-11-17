"""PresentMon child process, header-driven CSV, and one-second frame metrics."""

from __future__ import annotations

import bisect
import csv
import hashlib
import math
import os
import re
import statistics
import subprocess
import threading
import time
import uuid
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# Pin bytes, not a user-editable sidecar. Upgrades require a reviewed hash.
EXECUTABLE_NAME = "PresentMon-2.6.0-x64.exe"
EXECUTABLE_SHA256 = "b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af"


def verify_executable(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest() == EXECUTABLE_SHA256
    except OSError:
        return False


def _number(value: Optional[str]) -> Optional[float]:
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def _key(value: str) -> str:
    return value.strip().lstrip("\ufeff").casefold()


FRAME_HEADERS = ("frametime", "msbetweenpresents")
LATENCY_HEADERS = {
    "displaylatency": "display_latency",
    "msuntildisplayed": "until_displayed",
    "clicktophotonlatency": "click_to_photon",
    "msclicktophotonlatency": "click_to_photon",
    "allinputtophotonlatency": "all_input_to_photon",
    "msallinputtophotonlatency": "all_input_to_photon",
}


@dataclass
class Frame:
    frame_time_ms: Optional[float]
    present_mode: Optional[str] = None
    latency_ms: dict[str, Optional[float]] = field(default_factory=dict)
    stream: str = "default"


def parse_csv(lines: Iterable[str]) -> Iterable[Frame]:
    """Ignore banners/unknown columns; accept repeated headers and v1 aliases.

    Missing frame times do not become zero-duration frames. Their mode and
    any independently available latency measurements can still be counted.
    """
    headers = None
    for row in csv.reader(lines):
        keys = [_key(cell) for cell in row]
        if any(name in keys for name in FRAME_HEADERS):
            headers = keys
            continue
        if headers is None or len(row) != len(headers):
            continue
        values = dict(zip(headers, (cell.strip() for cell in row)))
        application = values.get("application", "cs2.exe")
        if application.casefold() != "cs2.exe":
            continue
        frame_time = next((_number(values[name]) for name in FRAME_HEADERS
                           if name in values and _number(values[name]) is not None), None)
        mode = values.get("presentmode")
        if not mode or mode.casefold() == "na":
            mode = None
        latency = {alias: _number(values[name]) for name, alias in LATENCY_HEADERS.items()
                   if name in values}
        yield Frame(frame_time if frame_time and frame_time > 0 else None, mode, latency,
                    values.get("processid", "") + ":" + values.get("swapchainaddress", ""))


def percentile99(values: list[float]) -> Optional[float]:
    """Nearest-rank p99, also well defined for fewer than 100 frames."""
    if not values:
        return None
    return sorted(values)[math.ceil(len(values) * 0.99) - 1]


class Aggregator:
    """Drain one reporting interval; keep the last 120 frames per swapchain.

    Spikes compare against the *preceding* rolling median, before inserting
    the new frame. The rolling baseline survives reporting boundaries.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rolling: dict[str, tuple[deque, list]] = {}
        self._frames: list[float] = []
        self._modes: Counter = Counter()
        self._latency: dict[str, list[float]] = {}
        self._spikes = 0
        self._events: deque = deque(maxlen=200)
        self._max_spike = None

    def add(self, frame: Frame) -> None:
        with self._lock:
            if frame.present_mode:
                self._modes[frame.present_mode] += 1
            for name, value in frame.latency_ms.items():
                if value is not None:
                    self._latency.setdefault(name, []).append(value)
            value = frame.frame_time_ms
            if value is None or value <= 0 or not math.isfinite(value):
                return
            # Bound stale swapchain history, including games restarted many times.
            if frame.stream not in self._rolling and len(self._rolling) >= 32:
                del self._rolling[next(iter(self._rolling))]
            recent, ordered = self._rolling.setdefault(frame.stream, (deque(), []))
            if ordered:
                middle = len(ordered) // 2
                median = (ordered[middle] if len(ordered) % 2 else
                          (ordered[middle - 1] + ordered[middle]) / 2)
                if value > 8 and value > 2.5 * median:
                    self._spikes += 1
                    self._max_spike = max(self._max_spike or 0, value)
                    self._events.append({"at": time.time(), "duration_ms": value,
                                         "type": "frame_spike"})
            if len(recent) == 120:
                ordered.pop(bisect.bisect_left(ordered, recent.popleft()))
            recent.append(value)
            bisect.insort(ordered, value)
            self._frames.append(value)

    def snapshot(self) -> dict:
        with self._lock:
            frames, modes, latency, spikes = self._frames, self._modes, self._latency, self._spikes
            events = list(self._events)
            self._events.clear()
            max_spike, self._max_spike = self._max_spike, None
            self._frames, self._modes, self._latency, self._spikes = [], Counter(), {}, 0
        total = sum(frames)
        p99 = percentile99(frames)
        return {
            "frame_count": len(frames),
            "frame_time_sum_ms": total,
            "fps": 1000 * len(frames) / total if total else None,
            "one_percent_low": 1000 / p99 if p99 else None,
            "frame_time_ms": statistics.fmean(frames) if frames else None,
            "p99_frame_time_ms": p99,
            "max_frame_time_ms": max(frames) if frames else None,
            "spikes": spikes,
            "events": events,
            "max_spike_ms": max_spike,
            "present_modes": dict(modes),
            "latency_ms": {name: statistics.fmean(values) for name, values in latency.items()},
            # Retain the distribution so the bench can calculate a run-wide
            # p99 instead of incorrectly averaging each second's 1% low.
            "frame_time_histogram_ms": dict(Counter(f"{value:.4f}" for value in frames)),
        }


def locate_executable(root: Optional[Path] = None) -> Optional[Path]:
    override = os.environ.get("CS2CFG_PRESENTMON")
    if override:
        candidate = Path(override).expanduser()
        return candidate.resolve() if candidate.is_file() else None
    if root is None:
        from ..paths import bundle_root

        root = bundle_root().parent / "tools" / "presentmon"

    def version(path: Path) -> tuple:
        match = re.search(r"PresentMon[-_v]*(\d+(?:\.\d+)*)", path.name, re.IGNORECASE)
        return tuple(int(part) for part in match[1].split(".")) if match else (0,)

    candidates = list(root.glob("PresentMon*.exe"))
    return max(candidates, key=lambda path: (version(path), path.stat().st_mtime)) if candidates else None


def classify_status(stderr: str, exit_code: Optional[int], *, game_running: bool,
                    has_frames: bool = False) -> str:
    """PresentMon 2.6 uses exit code 6 for trace-session access denied."""
    message = stderr.casefold()
    if (exit_code in (5, 6, 0x80070005, -2147024891)
            or "access denied" in message or "access is denied" in message
            or "0x80070005" in message):
        return "access_denied"
    if ("not found" in message or "not running" in message) and "process" in message:
        return "not_found"
    if exit_code not in (None, 0):
        return "error"
    if not game_running:
        return "not_found"
    if has_frames:
        return "ok"
    return "waiting" if exit_code is None else "stopped"


STATUS_TEXT = {
    "access_denied": "PresentMon: access denied - see docs/overlay/README.md",
    "not_found": "cs2.exe not found",
    "waiting": "PresentMon: waiting for frame data",
    "stopped": "PresentMon: capture stopped (restart probe to capture again)",
    "error": "PresentMon: capture failed - see presentmon_stderr in log",
    "missing": "PresentMon executable not found - see docs/overlay/README.md",
    "untrusted": "PresentMon SHA256 mismatch - fetch the supported binary again",
    "ok": "Capturing cs2.exe",
}


class PresentMon:
    """Own exactly one child and one uniquely named ETW session."""

    def __init__(self, aggregator: Aggregator) -> None:
        self.aggregator = aggregator
        self.executable = locate_executable()
        self.session = f"cs2cfg-overlay-{os.getpid()}-{uuid.uuid4().hex[:12]}"
        self.process: Optional[subprocess.Popen] = None
        self._threads: list[threading.Thread] = []
        self._errors: deque[str] = deque(maxlen=24)
        self._lock = threading.Lock()
        self._untrusted = False
        self._stop_lock = threading.Lock()

    @property
    def command(self) -> list[str]:
        return [str(self.executable), "--process_name", "cs2.exe", "--output_stdout",
                "--session_name", self.session, "--stop_existing_session",
                "--terminate_on_proc_exit", "--no_console_stats", "--v2_metrics"]

    @property
    def stderr(self) -> str:
        with self._lock:
            return "\n".join(self._errors)

    def _error(self, message: str) -> None:
        with self._lock:
            self._errors.append(message.strip()[:1000])

    def start(self) -> None:
        if self.executable is None:
            return
        if self.process is not None:
            return
        if not verify_executable(self.executable):
            self._untrusted = True
            self._error(STATUS_TEXT["untrusted"])
            return
        self._untrusted = False
        with self._lock:
            self._errors.clear()
        try:
            self.process = subprocess.Popen(
                self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL, text=True, encoding="utf-8-sig", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            self._error(str(exc))
            return

        def frames() -> None:
            try:
                for frame in parse_csv(self.process.stdout):
                    self.aggregator.add(frame)
            except (OSError, csv.Error) as exc:
                self._error(f"CSV reader: {exc}")

        def errors() -> None:
            for line in self.process.stderr:
                self._error(line)

        for target, name in ((frames, "csv"), (errors, "stderr")):
            thread = threading.Thread(target=target, daemon=True, name=f"presentmon-{name}")
            self._threads.append(thread)
            thread.start()

    def status(self, game_running: bool, has_frames: bool) -> str:
        if self.executable is None:
            return "missing"
        if self._untrusted:
            return "untrusted"
        child = self.process
        if child is None:
            return classify_status(self.stderr, 1, game_running=game_running)
        return classify_status(self.stderr, child.poll(), game_running=game_running,
                               has_frames=has_frames)

    def stop(self) -> None:
        with self._stop_lock:
            self._stop_child()

    def _stop_child(self) -> None:
        child = self.process
        if child is None:
            return
        # Ask PresentMon to close only OUR session, including if the child has
        # already exited. Never stop a user's unrelated PresentMon session.
        try:
            if verify_executable(self.executable):
                subprocess.run([str(self.executable), "--session_name", self.session,
                                "--terminate_existing_session"], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for thread in self._threads:
            thread.join(timeout=2)
        child.stdout.close()
        child.stderr.close()
        self.process = None
        self._threads.clear()
