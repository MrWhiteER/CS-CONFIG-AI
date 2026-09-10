"""Live system telemetry for the dashboard.

Everything here is measured, not estimated. CPU and memory come from Win32
calls through ctypes, which cost microseconds and can be polled continuously.
GPU comes from ``nvidia-smi`` when it is present, which is a subprocess and so
is cached for a couple of seconds rather than run on every request.

Where a figure genuinely cannot be obtained -- no NVIDIA driver, no GPU counter
-- the field comes back ``None`` and the dashboard shows a dash. A gauge that
invents a number is worse than a gauge that admits it does not have one.
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GPU_CACHE_SECONDS = 2.0
HISTORY_LENGTH = 60          # ~2 minutes at a 2s poll


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
    idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
    if not kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return None
    return idle.value, kernel.value, user.value


def memory() -> Dict[str, Optional[float]]:
    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
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
    _gpu_cache: Optional[Dict[str, Optional[float]]] = None
    _gpu_at: float = 0.0
    _smi: Optional[str] = None
    _smi_checked: bool = False
    history: Dict[str, List[Optional[float]]] = field(default_factory=lambda: {
        "cpu": [], "gpu": [], "ram": [], "vram": [],
    })

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
        now = time.monotonic()
        with self._lock:
            if self._gpu_cache is not None and now - self._gpu_at < GPU_CACHE_SECONDS:
                return dict(self._gpu_cache)
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
    def sample(self) -> Dict[str, object]:
        cpu = self.cpu_percent()
        ram = memory()
        gpu = self.gpu()

        with self._lock:
            for key, value in (("cpu", cpu), ("gpu", gpu.get("percent")),
                               ("ram", ram.get("percent")), ("vram", gpu.get("vram_percent"))):
                series = self.history[key]
                series.append(value)
                if len(series) > HISTORY_LENGTH:
                    del series[0:len(series) - HISTORY_LENGTH]
            history = {k: list(v) for k, v in self.history.items()}

        return {
            "cpu": {"percent": cpu},
            "ram": ram,
            "gpu": gpu,
            "game": self.game(),
            "history": history,
            "at": time.time(),
        }


_monitor: Optional[Monitor] = None


def shared() -> Monitor:
    """One monitor per process, so CPU deltas and history are continuous."""
    global _monitor
    if _monitor is None:
        _monitor = Monitor()
    return _monitor
