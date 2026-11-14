"""Read-only Win32 process metrics and optional, driver-provided NVML."""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from pathlib import Path
from typing import Optional

from ..monitor import FILETIME, Monitor


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
            "PagefileUsage", "PeakPagefileUsage")]


class ProcessMetrics:
    """Measure this Python process as a share of total logical CPU capacity."""

    def __init__(self) -> None:
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        api = self.api
        api.GetCurrentProcess.argtypes = []
        api.GetCurrentProcess.restype = wintypes.HANDLE
        api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(FILETIME)] * 4
        api.GetProcessTimes.restype = wintypes.BOOL
        api.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,
                                               ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
        api.K32GetProcessMemoryInfo.restype = wintypes.BOOL
        api.GetActiveProcessorCount.argtypes = [wintypes.WORD]
        api.GetActiveProcessorCount.restype = wintypes.DWORD
        self.handle = api.GetCurrentProcess()  # Pseudo handle to self; never a game handle.
        self.cpus = api.GetActiveProcessorCount(0xFFFF) or os.cpu_count() or 1
        self._previous = None
        self.sample()

    def sample(self) -> dict:
        at = time.monotonic()
        creation, exited, kernel, user = FILETIME(), FILETIME(), FILETIME(), FILETIME()
        percent = None
        if self.api.GetProcessTimes(self.handle, ctypes.byref(creation), ctypes.byref(exited),
                                    ctypes.byref(kernel), ctypes.byref(user)):
            current = kernel.value + user.value
            if self._previous:
                old, old_at = self._previous
                elapsed = at - old_at
                if elapsed > 0:
                    percent = max(0.0, min(100.0, (current - old) / 1e7 / elapsed / self.cpus * 100))
            self._previous = current, at
        memory = PROCESS_MEMORY_COUNTERS()
        memory.cb = ctypes.sizeof(memory)
        ok = self.api.K32GetProcessMemoryInfo(self.handle, ctypes.byref(memory), memory.cb)
        return {"overlay_cpu_percent": percent,
                "working_set_mb": memory.WorkingSetSize / 1024 ** 2 if ok else None}


class GameWindow:
    """Only enumerate/query windows and process image names; change nothing."""

    def __init__(self) -> None:
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user.EnumWindows.argtypes = [self.callback_type, wintypes.LPARAM]
        self.user.EnumWindows.restype = wintypes.BOOL
        self.user.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user.IsWindowVisible.restype = wintypes.BOOL
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.GetWindowRect.restype = wintypes.BOOL
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                         wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL

    def find(self) -> Optional[tuple[int, int]]:
        position = None
        checked = set()

        @self.callback_type
        def visit(hwnd, _):
            nonlocal position
            if not self.user.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in checked:
                return True
            checked.add(pid.value)
            handle = self.kernel.OpenProcess(0x1000, False, pid.value)
            if not handle:
                return True
            try:
                size = wintypes.DWORD(1024)
                name = ctypes.create_unicode_buffer(size.value)
                if (self.kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size))
                        and Path(name.value).name.casefold() == "cs2.exe"):
                    rect = wintypes.RECT()
                    if self.user.GetWindowRect(hwnd, ctypes.byref(rect)):
                        position = (rect.left + 20, rect.top + 20)
                    else:
                        position = (20, 20)
                    return False
            finally:
                self.kernel.CloseHandle(handle)
            return True

        self.user.EnumWindows(visit, 0)
        return position


class Nvml:
    """GPU zero's load and temperature. Missing NVIDIA support returns None."""

    def __init__(self) -> None:
        self.api = None
        self.device = ctypes.c_void_p()
        for path in (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvml.dll",
                     Path(os.environ.get("ProgramFiles", r"C:\Program Files")) /
                     "NVIDIA Corporation" / "NVSMI" / "nvml.dll"):
            try:
                api = ctypes.CDLL(str(path))
                api.nvmlInit_v2.argtypes = []
                api.nvmlInit_v2.restype = ctypes.c_int
                api.nvmlShutdown.argtypes = []
                api.nvmlShutdown.restype = ctypes.c_int
                api.nvmlDeviceGetHandleByIndex_v2.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
                api.nvmlDeviceGetHandleByIndex_v2.restype = ctypes.c_int
                api.nvmlDeviceGetUtilizationRates.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                api.nvmlDeviceGetUtilizationRates.restype = ctypes.c_int
                api.nvmlDeviceGetTemperature.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                                         ctypes.POINTER(ctypes.c_uint)]
                api.nvmlDeviceGetTemperature.restype = ctypes.c_int
                api.nvmlDeviceGetMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                api.nvmlDeviceGetMemoryInfo.restype = ctypes.c_int
                if api.nvmlInit_v2() != 0:
                    continue
                if api.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(self.device)) != 0:
                    api.nvmlShutdown()
                    continue
                self.api = api
                break
            except (OSError, AttributeError):
                continue

    def sample(self) -> dict:
        result = {"gpu_percent": None, "gpu_temp_c": None,
                  "vram_used_mb": None, "vram_total_mb": None}
        if self.api:
            rates = (ctypes.c_uint * 2)()
            temp = ctypes.c_uint()
            if self.api.nvmlDeviceGetUtilizationRates(self.device, ctypes.byref(rates)) == 0:
                result["gpu_percent"] = rates[0]
            if self.api.nvmlDeviceGetTemperature(self.device, 0, ctypes.byref(temp)) == 0:
                result["gpu_temp_c"] = temp.value
            memory = (ctypes.c_ulonglong * 3)()  # total, free, used
            if self.api.nvmlDeviceGetMemoryInfo(self.device, ctypes.byref(memory)) == 0:
                result["vram_total_mb"] = memory[0] / 1024 ** 2
                result["vram_used_mb"] = memory[2] / 1024 ** 2
        return result

    def close(self) -> None:
        if self.api:
            self.api.nvmlShutdown()
            self.api = None


class Metrics:
    def __init__(self) -> None:
        self.cpu = Monitor()
        self.cpu.cpu_percent()  # Prime the existing GetSystemTimes delta code.
        self.process = ProcessMetrics()
        self.gpu = Nvml()
        self.game = GameWindow()

    def sample(self) -> dict:
        return {"cpu_percent": self.cpu.cpu_percent(), **self.process.sample(), **self.gpu.sample()}

    def close(self) -> None:
        self.gpu.close()
