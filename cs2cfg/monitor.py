"""Live system telemetry for the dashboard.

Everything here is measured, not estimated. CPU and memory come from Win32
calls through ctypes, which cost microseconds and can be polled continuously.
GPU comes from driver-provided NVML, with ``nvidia-smi`` as a fallback. Readings
are cached for a couple of seconds rather than sampled on every request.

Where a figure genuinely cannot be obtained -- no NVIDIA driver, no GPU counter
-- the field comes back ``None`` and the dashboard shows a dash. A gauge that
invents a number is worse than a gauge that admits it does not have one.
"""

from __future__ import annotations

import atexit
import ctypes
import json
import shutil
import subprocess
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Windows only; elsewhere (the test machines) every reading is simply unknown.
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if hasattr(ctypes, "WinDLL") else None

GPU_CACHE_SECONDS = 2.0
HISTORY_LENGTH = 60          # ~2 minutes at a 2s poll
SAMPLE_SECONDS = 2.0         # one slot of history
SAVE_SECONDS = 10.0          # how often the window is written to disk
HISTORY_FILE = "hardware-history.json"
# Every line the System graph can draw. Temperatures sit next to usage so the
# graph's second view is just as full as the first.
SERIES = ("cpu", "gpu", "ram", "vram", "temp-cpu", "temp-gpu", "temp-system")


class FILETIME(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    @property
    def value(self) -> int:
        return (self.high << 32) | self.low


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _system_times() -> Optional[tuple]:
    if kernel32 is None:
        return None
    idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
    if not kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return None
    return idle.value, kernel.value, user.value


def memory() -> Dict[str, Optional[float]]:
    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if kernel32 is None or not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return {"percent": None, "used_gb": None, "total_gb": None}
    total = status.ullTotalPhys
    used = total - status.ullAvailPhys
    return {
        "percent": round(status.dwMemoryLoad, 1),
        "used_gb": round(used / (1024 ** 3), 1),
        "total_gb": round(total / (1024 ** 3), 1),
    }


def _find_nvidia_smi() -> Optional[str]:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    for candidate in (
        Path(r"C:\Windows\System32\nvidia-smi.exe"),
        Path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"),
    ):
        if candidate.is_file():
            return str(candidate)
    return None


@dataclass
class Monitor:
    """Rolling live stats, safe to poll from many requests at once."""

    _last_times: Optional[tuple] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _gpu_lock: threading.Lock = field(default_factory=threading.Lock)
    _gpu_cache: Optional[Dict[str, Optional[float]]] = None
    _gpu_at: float = 0.0
    _smi: Optional[str] = None
    _smi_checked: bool = False
    _nvml: object = None
    _nvml_checked: bool = False
    history: Dict[str, List[Optional[float]]] = field(default_factory=lambda: {
        key: [] for key in SERIES
    })
    _history_at: Optional[float] = None       # wall time of the newest slot
    _reading: Optional[Dict[str, object]] = None
    _reading_at: float = 0.0
    _thread: Optional[threading.Thread] = None
    _stop: threading.Event = field(default_factory=threading.Event)
    _store: Optional[Path] = None
    _saved_at: float = 0.0

    # -- cpu ---------------------------------------------------------------
    def cpu_percent(self) -> Optional[float]:
        """Load since the previous call.

        The first call has no previous sample to compare against and returns
        None rather than a made-up figure.
        """
        current = _system_times()
        if current is None:
            return None

        with self._lock:
            previous = self._last_times
            self._last_times = current

        if previous is None:
            return None

        idle_delta = current[0] - previous[0]
        kernel_delta = current[1] - previous[1]
        user_delta = current[2] - previous[2]
        total = kernel_delta + user_delta          # kernel time includes idle
        if total <= 0:
            return None
        busy = total - idle_delta
        return round(max(0.0, min(100.0, busy * 100.0 / total)), 1)

    # -- gpu ---------------------------------------------------------------
    def gpu(self) -> Dict[str, Optional[float]]:
        # Serialize readers and cache unsuccessful samples too, so a missing
        # driver cannot trigger repeated fallback processes on concurrent polls.
        with self._gpu_lock:
            now = time.monotonic()
            with self._lock:
                if self._gpu_cache is not None and now - self._gpu_at < GPU_CACHE_SECONDS:
                    return dict(self._gpu_cache)
            result = self._read_gpu()
            with self._lock:
                self._gpu_cache, self._gpu_at = result, now
            return dict(result)

    def _read_gpu(self) -> Dict[str, Optional[float]]:
        now = time.monotonic()
        with self._lock:
            if self._gpu_cache is not None and now - self._gpu_at < GPU_CACHE_SECONDS:
                return dict(self._gpu_cache)
            if not self._nvml_checked:
                from .overlay.metrics import Nvml

                self._nvml = Nvml()
                self._nvml_checked = True
            if self._nvml.api:
                sample = self._nvml.sample()
                if sample.get("gpu_percent") is not None:
                    used, total = sample.get("vram_used_mb"), sample.get("vram_total_mb")
                    result = {"percent": sample["gpu_percent"],
                              "temperature": sample.get("gpu_temp_c"),
                              "vram_used_mb": used, "vram_total_mb": total,
                              "vram_percent": round(used * 100 / total, 1)
                              if used is not None and total else None,
                              "available": True}
                    self._gpu_cache, self._gpu_at = result, now
                    return dict(result)
            if not self._smi_checked:
                self._smi = _find_nvidia_smi()
                self._smi_checked = True
            smi = self._smi

        blank = {"percent": None, "vram_used_mb": None, "vram_total_mb": None,
                 "vram_percent": None, "temperature": None, "available": bool(smi)}
        if not smi:
            return blank

        try:
            proc = subprocess.run(
                [smi, "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return blank

        line = (proc.stdout or "").strip().splitlines()
        if not line:
            return blank
        parts = [p.strip() for p in line[0].split(",")]
        try:
            used, total = float(parts[1]), float(parts[2])
            result = {
                "percent": float(parts[0]),
                "vram_used_mb": used,
                "vram_total_mb": total,
                "vram_percent": round(used * 100.0 / total, 1) if total else None,
                "temperature": float(parts[3]) if len(parts) > 3 else None,
                "available": True,
            }
        except (ValueError, IndexError):
            return blank

        with self._lock:
            self._gpu_cache = result
            self._gpu_at = now
        return dict(result)

    def close(self) -> None:
        with self._lock:
            if self._nvml is not None:
                self._nvml.close()

    # -- game --------------------------------------------------------------
    def game(self) -> Dict[str, object]:
        from . import window

        found = window.find_game_window("cs2.exe")
        if found is None:
            return {"running": False}
        return {
            "running": True,
            "title": found.title,
            "width": found.size[0],
            "height": found.size[1],
            "focused": window.foreground_hwnd() == found.hwnd,
        }

    # -- combined ----------------------------------------------------------
    def _measure(self) -> Dict[str, object]:
        return {"cpu": {"percent": self.cpu_percent()}, "ram": memory(), "gpu": self.gpu()}

    @staticmethod
    def _temperatures(gpu: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
        """CPU and System from the sensor reader, GPU from the reading just taken.

        Only asks the sensor reader for a fresh reading when the administrator
        helper is publishing them, which is a file read. Without it a refresh
        starts PowerShell, and that is not something to do every few seconds
        in the background while somebody is playing; the last held reading
        is used instead, and only while it is recent.
        """
        found: Dict[str, Optional[float]] = {"temp-cpu": None, "temp-system": None,
                                             "temp-gpu": gpu.get("temperature")}
        try:
            from . import temps

            watcher = temps.shared()
            if temps._published():
                held = watcher.read()
            else:
                held = watcher._held
            if time.time() - held.at <= 2 * temps.REFRESH:
                for part in held.parts:
                    key = "temp-" + part.part
                    if key in found and part.known and part.celsius is not None:
                        found[key] = part.celsius
        except Exception:
            pass
        return found

    def _record(self, reading: Dict[str, object], at: float) -> None:
        gpu = reading.get("gpu") or {}
        values = {"cpu": (reading.get("cpu") or {}).get("percent"),
                  "gpu": gpu.get("percent"),
                  "ram": (reading.get("ram") or {}).get("percent"),
                  "vram": gpu.get("vram_percent"),
                  **self._temperatures(gpu)}
        with self._lock:
            self._append(values, at)
            self._reading, self._reading_at = reading, at

    def _append(self, values: Dict[str, Optional[float]], at: float) -> None:
        """One slot per two seconds. Time the app was closed stays a gap."""
        if self._history_at is not None:
            missed = int(round((at - self._history_at) / SAMPLE_SECONDS)) - 1
            for _ in range(max(0, min(missed, HISTORY_LENGTH))):
                for key in SERIES:
                    self.history[key].append(None)
        for key in SERIES:
            series = self.history[key]
            series.append(values.get(key))
            if len(series) > HISTORY_LENGTH:
                del series[0:len(series) - HISTORY_LENGTH]
        self._history_at = at

    def sample(self) -> Dict[str, object]:
        """The newest reading and the window of history behind it.

        With the background sampler running this only reads what it last
        measured, so any number of pages polling never bends the timeline.
        """
        with self._lock:
            reading, at = self._reading, self._reading_at
            running = self._thread is not None and self._thread.is_alive()
        if not running or reading is None or time.time() - at > 2 * SAMPLE_SECONDS:
            at = time.time()
            reading = self._measure()
            self._record(reading, at)
        with self._lock:
            history = {k: list(v) for k, v in self.history.items()}

        return {
            **reading,
            "game": self.game(),
            "history": history,
            "at": at,
        }

    # -- background ------------------------------------------------------------
    def start(self, store: Optional[Path] = None) -> None:
        """Measure from the moment the app starts, not from when a page asks.

        The graph on the System page then opens already full. The window is
        also kept on disk, so a restart -- an update, say -- picks up where it
        left off instead of starting from nothing.
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._store = store
        if store is not None:
            self._load(store)
            atexit.register(self.save)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="hardware-history", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.save()

    def _run(self) -> None:
        # Primes the CPU counter, so the first slot is a real load figure.
        self.cpu_percent()
        while not self._stop.wait(SAMPLE_SECONDS if self._reading is not None else 0.5):
            try:
                self._record(self._measure(), time.time())
                if time.time() - self._saved_at >= SAVE_SECONDS:
                    self.save()
            except Exception:
                pass                # a missed sample is a gap, never a crash

    def save(self) -> None:
        with self._lock:
            store, at = self._store, self._history_at
            history = {k: list(v) for k, v in self.history.items()}
        if store is None or at is None:
            return
        self._saved_at = time.time()
        try:
            temp = store.with_suffix(".tmp")
            temp.write_text(json.dumps({"at": at, "step": SAMPLE_SECONDS,
                                        "history": history}), encoding="utf-8")
            temp.replace(store)
        except OSError:
            pass

    def _load(self, store: Path) -> None:
        """Bring back whatever of the saved window is still inside it now."""
        try:
            saved = json.loads(store.read_text(encoding="utf-8"))
            at = float(saved["at"])
            history = saved["history"]
        except (OSError, ValueError, KeyError, TypeError):
            return
        if not 0 <= time.time() - at < HISTORY_LENGTH * SAMPLE_SECONDS:
            return
        with self._lock:
            for key in SERIES:
                values = history.get(key) or []
                self.history[key] = [v if isinstance(v, (int, float)) else None
                                     for v in values][-HISTORY_LENGTH:]
            length = max(len(v) for v in self.history.values())
            for key in SERIES:      # every line the same length, oldest padded
                self.history[key][:0] = [None] * (length - len(self.history[key]))
            self._history_at = at


_monitor: Optional[Monitor] = None


def shared() -> Monitor:
    """One monitor per process, so CPU deltas and history are continuous."""
    global _monitor
    if _monitor is None:
        _monitor = Monitor()
    return _monitor
