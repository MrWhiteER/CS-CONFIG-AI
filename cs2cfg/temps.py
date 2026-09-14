"""Temperatures for the parts that decide whether the frame rate holds.

Heat is the reason a machine that benchmarks well plays badly: nothing reports
an error when a CPU reaches its limit, it simply stops boosting, and the frame
rate sags in exactly the long rounds where it matters. So it is worth showing
next to the load gauges rather than leaving it to a second tool.

What Windows will actually tell an ordinary program is less than people expect:

* **GPU** -- yes. NVIDIA's own tool reports it, no privileges needed.
* **CPU** -- no. There is no user-space API for package temperature. The ACPI
  thermal zone is the documented stand-in and it is both frequently absent and
  frequently measuring something else (a chassis sensor, not the die). Reading
  it needs administrator, and the tools that do better than this ship a kernel
  driver, which is not a thing to install behind somebody's back for a
  read-out.
* **Drives** -- through SMART, and also only with administrator.

So this reports what it can get and says plainly what it cannot, rather than
showing a plausible number from the wrong sensor. A wrong temperature is worse
than no temperature: it is the number somebody takes their side panel off for.

Everything is cached and refreshed on its own thread. The gauges poll about
once a second and each of these costs a PowerShell start, so sampling them in
line with the gauges would cost more than it measures.
"""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Long enough that the cost disappears, short enough to catch a machine heating
# up during a match.
REFRESH = 20.0

_CREATE_NO_WINDOW = 0x08000000

# Where a part stops boosting and starts losing frames. Not damage thresholds --
# silicon protects itself long before this -- but the point at which the number
# explains a frame rate that has quietly dropped.
WARM = {"cpu": 85, "gpu": 83, "drive": 60}
HOT = {"cpu": 95, "gpu": 87, "drive": 70}


def _elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _powershell(script: str, timeout: int = 25) -> str:
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
            creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (done.stdout or "").strip()


@dataclass
class Reading:
    """One sensor, or the reason there is no sensor."""
    part: str                  # "cpu" | "gpu" | "drive"
    label: str
    celsius: Optional[float] = None
    unavailable: str = ""

    @property
    def known(self) -> bool:
        return self.celsius is not None

    @property
    def state(self) -> str:
        if self.celsius is None:
            return "unknown"
        if self.celsius >= HOT.get(self.part, 90):
            return "hot"
        if self.celsius >= WARM.get(self.part, 80):
            return "warm"
        return "fine"


@dataclass
class Readings:
    parts: List[Reading] = field(default_factory=list)
    elevated: bool = False
    at: float = 0.0

    @property
    def hottest(self) -> Optional[Reading]:
        known = [p for p in self.parts if p.known]
        return max(known, key=lambda p: p.celsius) if known else None


def _cpu() -> Reading:
    """The ACPI thermal zone, when the machine exposes one and we may read it.

    Reported in tenths of a kelvin. Anything outside a plausible range is
    dropped rather than shown: some firmware fills this field with a constant,
    and a fixed 27 degrees looks like a working sensor.
    """
    found = Reading("cpu", "CPU")
    if not _elevated():
        found.unavailable = "needs administrator"
        return found

    out = _powershell(
        "Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
        "-ErrorAction SilentlyContinue | "
        "Select-Object -ExpandProperty CurrentTemperature")
    values = []
    for line in out.splitlines():
        line = line.strip()
        if not line.isdigit():
            continue
        celsius = int(line) / 10.0 - 273.15
        if 5 < celsius < 125:
            values.append(celsius)
    if not values:
        found.unavailable = "this machine exposes no thermal zone"
        return found
    # The warmest zone is the one worth showing; the others are chassis points.
    found.celsius = round(max(values), 1)
    return found


def _drives() -> List[Reading]:
    """SMART temperature per physical disk, where the counters can be read."""
    if not _elevated():
        return [Reading("drive", "Drives", unavailable="needs administrator")]

    out = _powershell(
        "Get-PhysicalDisk | ForEach-Object { "
        "$c = $_ | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue; "
        "[pscustomobject]@{ Name = $_.FriendlyName; Temp = $c.Temperature } } | "
        "ConvertTo-Json -Compress")
    if not out:
        return []
    try:
        data = json.loads(out)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]

    found: List[Reading] = []
    for row in data:
        temp = row.get("Temp")
        name = str(row.get("Name") or "drive").strip()
        if temp is None:
            continue
        try:
            celsius = float(temp)
        except (TypeError, ValueError):
            continue
        if not 5 < celsius < 125:
            continue
        found.append(Reading("drive", name, celsius=round(celsius, 1)))
    return found


def _gpu() -> Reading:
    """Straight from the same reading the load gauges already take."""
    found = Reading("gpu", "GPU")
    try:
        from . import monitor

        sample = monitor.shared().gpu()
    except Exception:
        found.unavailable = "no GPU reading"
        return found
    value = sample.get("temperature")
    if value is None:
        found.unavailable = ("no NVIDIA driver tool" if not sample.get("available")
                             else "the driver did not report a temperature")
        return found
    found.celsius = round(float(value), 1)
    return found


class Watcher:
    """Reads on its own schedule so the gauge poll never waits on PowerShell."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._held = Readings()
        self._working = False

    def _collect(self) -> Readings:
        parts = [_gpu(), _cpu()]
        parts.extend(_drives())
        return Readings(parts=parts, elevated=_elevated(), at=time.time())

    def _refresh(self) -> None:
        try:
            fresh = self._collect()
        except Exception:
            fresh = Readings(at=time.time())
        with self._lock:
            self._held = fresh
            self._working = False

    def read(self) -> Readings:
        """The latest reading, kicking off another when it has gone stale.

        Never blocks: a caller during the first few seconds gets an empty set
        and the one after it gets real numbers.
        """
        with self._lock:
            held = self._held
            stale = time.time() - held.at > REFRESH
            if stale and not self._working:
                self._working = True
                threading.Thread(target=self._refresh, daemon=True).start()
        return held


_watcher: Optional[Watcher] = None


def shared() -> Watcher:
    global _watcher
    if _watcher is None:
        _watcher = Watcher()
    return _watcher


def as_dict(found: Readings) -> dict:
    return {
        "elevated": found.elevated,
        "at": found.at,
        "parts": [{"part": p.part, "label": p.label, "celsius": p.celsius,
                   "state": p.state, "known": p.known,
                   "unavailable": p.unavailable}
                  for p in found.parts],
        "hottest": (found.hottest.celsius if found.hottest else None),
    }
