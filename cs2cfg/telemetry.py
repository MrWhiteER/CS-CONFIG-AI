"""Session recording: what actually happened while you played.

What this can and cannot see is worth being straight about. Without injecting
into the game there is no frame counter here — anything claiming an fps figure
from outside the process is guessing. What *is* observable from outside, and
what this measures:

* **Stalls.** A window that stops answering a no-op message is a window whose
  message loop is blocked. That is exactly what a display-mode renegotiation
  looks like from outside, so the alt-tab black screen gets timed rather than
  estimated.
* **Focus.** Every switch away from the game and back, and how long each round
  trip took. This is the number that should drop to near zero once the game is
  running borderless.
* **CPU and memory.** Sampled from the process itself, so you can see whether a
  settings change actually moved the load.

Sessions are written one JSON file each, so the history is inspectable with a
text editor and trivially deletable.
"""

from __future__ import annotations

import ctypes
import json
import statistics
import threading
import time
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import window
from .kb import user_data_dir

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Three different clocks, because they measure things of three different sizes.
#
# Focus has to be polled fast. An alt-tab round trip is the number this whole
# tool exists to move, and it is often under a second — sampling it every two
# seconds cannot resolve that at all, and worse, it *inflates* every reading up
# to a full interval. An earlier version did exactly that and reported a 3.45s
# median that was mostly quantisation noise.
FOCUS_POLL = 0.1
PROBE_INTERVAL = 0.5
SAMPLE_INTERVAL = 2.0

# A window that does not answer within this long is treated as stalled. Well
# above a normal frame time, well below anything a person would not notice.
STALL_TIMEOUT_MS = 350


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    @property
    def value(self) -> int:
        return (self.dwHighDateTime << 32) | self.dwLowDateTime


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def sessions_dir() -> Path:
    return user_data_dir() / "sessions"


@dataclass
class FocusSwitch:
    away_at: float
    back_at: Optional[float] = None

    @property
    def seconds(self) -> Optional[float]:
        return round(self.back_at - self.away_at, 2) if self.back_at else None


@dataclass
class Stall:
    at: float
    seconds: float
    focused: bool


@dataclass
class SessionRecord:
    stamp: str
    started: str
    ended: Optional[str] = None
    duration: float = 0.0
    resolution: str = ""
    desktop_mode: str = ""
    stretched: bool = False
    borderless: bool = False
    intent: Optional[str] = None
    tier: Optional[str] = None

    alt_tabs: int = 0
    focus_switches: List[Dict[str, Any]] = field(default_factory=list)
    worst_return: Optional[float] = None
    median_return: Optional[float] = None

    stalls: List[Dict[str, Any]] = field(default_factory=list)
    stall_count: int = 0
    worst_stall: Optional[float] = None
    total_stalled: float = 0.0

    cpu_mean: Optional[float] = None
    cpu_peak: Optional[float] = None
    mem_peak_mb: Optional[float] = None
    samples: int = 0

    notes: List[str] = field(default_factory=list)


class SessionRecorder:
    """Samples a running game on its own thread until told to stop."""

    def __init__(self, hwnd: int, meta: Optional[Dict[str, Any]] = None) -> None:
        self.hwnd = hwnd
        self.pid = window.window_pid(hwnd)
        self.meta = meta or {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self.started = time.time()
        self.record = SessionRecord(
            stamp=datetime.now().strftime("%Y%m%d-%H%M%S"),
            started=datetime.now().isoformat(timespec="seconds"),
            resolution=self.meta.get("resolution", ""),
            desktop_mode=self.meta.get("desktop_mode", ""),
            stretched=bool(self.meta.get("stretched")),
            borderless=bool(self.meta.get("borderless")),
            intent=self.meta.get("intent"),
            tier=self.meta.get("tier"),
        )

        self._cpu_samples: List[float] = []
        self._mem_peak = 0
        self._switches: List[FocusSwitch] = []
        self._stalls: List[Stall] = []
        self._handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, self.pid)

    # -- sampling ---------------------------------------------------------
    def _process_times(self) -> Optional[int]:
        if not self._handle:
            return None
        creation, exit_t, kernel, user = FILETIME(), FILETIME(), FILETIME(), FILETIME()
        ok = kernel32.GetProcessTimes(
            self._handle, ctypes.byref(creation), ctypes.byref(exit_t),
            ctypes.byref(kernel), ctypes.byref(user),
        )
        return (kernel.value + user.value) if ok else None

    def _working_set(self) -> Optional[int]:
        if not self._handle:
            return None
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if kernel32.K32GetProcessMemoryInfo(self._handle, ctypes.byref(counters), counters.cb):
            return int(counters.WorkingSetSize)
        return None

    def _run(self) -> None:
        cpu_count = max(1, (kernel32.GetActiveProcessorCount(0xFFFF) or 1))
        last_cpu = self._process_times()
        last_at = time.monotonic()
        was_focused = window.foreground_hwnd() == self.hwnd

        next_probe = time.monotonic()
        next_sample = time.monotonic() + SAMPLE_INTERVAL

        while not self._stop.is_set():
            time.sleep(FOCUS_POLL)
            now = time.monotonic()

            # Focus, every tick. This is the measurement that matters most and
            # the one most easily ruined by a slow clock.
            focused = window.foreground_hwnd() == self.hwnd
            if was_focused and not focused:
                with self._lock:
                    self._switches.append(FocusSwitch(away_at=time.time()))
            elif focused and not was_focused:
                with self._lock:
                    if self._switches and self._switches[-1].back_at is None:
                        self._switches[-1].back_at = time.time()
            was_focused = focused

            # Responsiveness, twice a second. Timed, because the duration is
            # the whole point of recording it.
            if now >= next_probe:
                next_probe = now + PROBE_INTERVAL
                probe_start = time.monotonic()
                alive = window.is_responsive(self.hwnd, STALL_TIMEOUT_MS)
                probe_len = time.monotonic() - probe_start
                if not alive:
                    with self._lock:
                        self._stalls.append(Stall(
                            at=round(time.time() - self.started, 1),
                            seconds=round(probe_len, 2),
                            focused=focused,
                        ))

            # CPU and memory, every couple of seconds. Cheap to read but
            # meaningless at a finer grain than this.
            if now >= next_sample:
                next_sample = now + SAMPLE_INTERVAL
                current = self._process_times()
                if current is not None and last_cpu is not None:
                    elapsed = now - last_at
                    if elapsed > 0:
                        # FILETIME ticks are 100 ns.
                        busy = (current - last_cpu) / 1e7
                        percent = (busy / (elapsed * cpu_count)) * 100
                        with self._lock:
                            self._cpu_samples.append(round(max(0.0, min(100.0, percent)), 1))
                    last_cpu, last_at = current, now

                memory = self._working_set()
                if memory:
                    self._mem_peak = max(self._mem_peak, memory)

    # -- control ----------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="cs2cfg-telemetry")
        self._thread.start()

    def stop(self) -> SessionRecord:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=SAMPLE_INTERVAL + 2)
        self.record.resolution = self.meta.get("resolution", self.record.resolution)
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None
        return self._finalise()

    def _finalise(self) -> SessionRecord:
        with self._lock:
            record = self.record
            record.ended = datetime.now().isoformat(timespec="seconds")
            record.duration = round(time.time() - self.started, 1)

            completed = [s for s in self._switches if s.seconds is not None]
            record.alt_tabs = len(self._switches)
            record.focus_switches = [
                {"at": round(s.away_at - self.started, 1), "seconds": s.seconds}
                for s in self._switches
            ]
            if completed:
                durations = [s.seconds for s in completed]
                record.worst_return = max(durations)
                record.median_return = round(statistics.median(durations), 2)

            record.stalls = [asdict(s) for s in self._stalls]
            record.stall_count = len(self._stalls)
            if self._stalls:
                record.worst_stall = max(s.seconds for s in self._stalls)
                record.total_stalled = round(sum(s.seconds for s in self._stalls), 2)

            if self._cpu_samples:
                record.cpu_mean = round(statistics.fmean(self._cpu_samples), 1)
                record.cpu_peak = max(self._cpu_samples)
            record.samples = len(self._cpu_samples)
            if self._mem_peak:
                record.mem_peak_mb = round(self._mem_peak / (1024 ** 2), 1)

            record.notes = _observations(record)

        _write(record)
        return record


def _observations(record: SessionRecord) -> List[str]:
    """Turn the numbers into the two or three sentences worth reading."""
    notes: List[str] = []

    if record.alt_tabs == 0:
        notes.append("You never left the game, so there is nothing to say about alt-tab this session.")
    elif record.median_return is not None:
        if record.median_return <= 1.5:
            notes.append(
                f"{record.alt_tabs} alt-tab(s), typically back in {record.median_return}s. "
                "That is what it should look like — no mode renegotiation."
            )
        elif record.median_return <= 4:
            notes.append(
                f"{record.alt_tabs} alt-tab(s), typically {record.median_return}s to come back. "
                "Slower than borderless should be; check the game really was windowed."
            )
        else:
            notes.append(
                f"{record.alt_tabs} alt-tab(s), typically {record.median_return}s to come back, "
                f"worst {record.worst_return}s. That is the blackout pattern — the game was most "
                "likely still in exclusive fullscreen."
            )

    if record.stall_count == 0 and record.duration > 60:
        notes.append("The window stayed responsive throughout; no stalls detected.")
    elif record.stall_count:
        notes.append(
            f"{record.stall_count} stall(s) totalling {record.total_stalled}s, worst {record.worst_stall}s. "
            "A stall is the window not answering at all, which is what the black screen actually is."
        )

    if record.cpu_mean is not None and record.cpu_peak is not None:
        notes.append(f"CPU averaged {record.cpu_mean}% of all cores, peaking at {record.cpu_peak}%.")
    if record.mem_peak_mb:
        notes.append(f"Peak memory {record.mem_peak_mb} MB.")

    notes.append(
        "No frame rate here: measuring that from outside the process would be a guess. "
        "Use the in-game net_graph or an overlay for fps."
    )
    return notes


def _write(record: SessionRecord) -> Path:
    path = sessions_dir() / f"{record.stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")
    return path


def load_sessions(limit: int = 25) -> List[Dict[str, Any]]:
    """Past sessions, newest first."""
    directory = sessions_dir()
    if not directory.exists():
        return []
    out: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("*.json"), reverse=True)[:limit]:
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def summarise(sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate across sessions, split by whether they ran borderless.

    The split is the point: it is what lets you see whether the launcher
    actually changed anything, rather than taking anyone's word for it.
    """
    if not sessions:
        return {"count": 0}

    def stats(group: List[Dict[str, Any]]) -> Dict[str, Any]:
        returns = [s["median_return"] for s in group if s.get("median_return") is not None]
        stalls = [s.get("stall_count", 0) for s in group]
        return {
            "sessions": len(group),
            "hours": round(sum(s.get("duration", 0) for s in group) / 3600, 1),
            "alt_tabs": sum(s.get("alt_tabs", 0) for s in group),
            "median_return": round(statistics.median(returns), 2) if returns else None,
            "stalls": sum(stalls),
        }

    borderless = [s for s in sessions if s.get("borderless")]
    exclusive = [s for s in sessions if not s.get("borderless")]

    return {
        "count": len(sessions),
        "total_hours": round(sum(s.get("duration", 0) for s in sessions) / 3600, 1),
        "borderless": stats(borderless) if borderless else None,
        "exclusive": stats(exclusive) if exclusive else None,
    }
