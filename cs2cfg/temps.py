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
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Long enough that the cost disappears, short enough to catch a machine heating
# up during a match.
REFRESH = 20.0

_CREATE_NO_WINDOW = 0x08000000

# Where a part stops boosting and starts losing frames. Not damage thresholds --
# silicon protects itself long before this -- but the point at which the number
# explains a frame rate that has quietly dropped.
WARM = {"system": 55, "gpu": 83, "drive": 60}
HOT = {"system": 70, "gpu": 87, "drive": 70}

# Where the scale starts. A part idling at 35 should not already read as a
# third full: nothing interesting happens below room temperature, so the gauge
# spends its range on the part that matters.
IDLE = 25


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
    part: str                  # "gpu" | "system" | "drive"
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
    # Whether the privileged readings are coming from the helper rather than
    # from this process. The page uses it to decide whether to offer the prompt.
    assisted: bool = False

    @property
    def hottest(self) -> Optional[Reading]:
        known = [p for p in self.parts if p.known]
        return max(known, key=lambda p: p.celsius) if known else None


def _system_zone() -> Reading:
    """The ACPI thermal zone -- and it is not the CPU, whatever guides claim.

    Measured on a 12900K desktop this reads 27.9 C while the machine is awake:
    close to room temperature, and nowhere near a CPU package under any load.
    On most desktop boards TZ00 is a chipset or chassis sensor. It is a real
    temperature and worth showing, so it is shown -- as "System", which is what
    it is.

    Calling it CPU would be the exact failure this module exists to avoid: a
    plausible number from the wrong sensor, which is worse than no number
    because somebody acts on it. A true package temperature needs a kernel
    driver reading the MSRs, and installing one for a read-out is not a trade
    worth making behind anyone's back.

    Reported in tenths of a kelvin. Anything outside a plausible range is
    dropped: some firmware answers with a constant, and a fixed value looks
    exactly like a working sensor.
    """
    found = Reading("system", "System")
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
        found.unavailable = "no thermal zone on this machine"
        return found
    # The warmest zone is the one worth showing; the others are chassis points.
    found.celsius = round(max(values), 1)
    return found



# Makers put their own name and the capacity in the product string, which is
# the least useful part of it when four of them are stacked in a row: the
# model is what tells them apart.
_MAKERS = ("samsung", "western digital", "wd", "seagate", "crucial", "kingston",
           "sk hynix", "hynix", "intel", "corsair", "sabrent", "adata", "toshiba")
_CAPACITY = re.compile(r"\b\d+(?:\.\d+)?\s*[TGM]B\b", re.I)


def _short_drive(name: str) -> str:
    """A drive's model, without the maker and the size.

    Falls back to the full string rather than to nothing: an unrecognised
    naming scheme should read oddly, not vanish.
    """
    trimmed = _CAPACITY.sub("", name or "").strip()
    low = trimmed.lower()
    for maker in _MAKERS:
        if low.startswith(maker):
            trimmed = trimmed[len(maker):].strip()
            break
    trimmed = trimmed.lstrip("-").strip()
    if trimmed.lower().startswith("ssd"):
        trimmed = trimmed[3:].strip()
    return trimmed or (name or "drive").strip()


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
        found.append(Reading("drive", _short_drive(name),
                             celsius=round(celsius, 1)))
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
        # The GPU never needs privileges, so it is always read here. The other
        # two come from the elevated helper when one is running; without it,
        # reading them directly is what produces the "needs administrator"
        # note, which is the honest answer rather than a blank.
        parts = [_gpu()]
        published = _published()
        if published:
            parts.extend(published)
        else:
            parts.append(_system_zone())
            parts.extend(_drives())
        return Readings(parts=parts, elevated=_elevated() or bool(published),
                        at=time.time(), assisted=bool(published))

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
        "assisted": found.assisted,
        "can_elevate": sys.platform == "win32" and not found.assisted,
        "at": found.at,
        # The thresholds travel with the reading. The gauge draws how full the
        # part is against its own limit, and a second copy of these numbers in
        # the page would be one to keep in step.
        "parts": [{"part": p.part, "label": p.label, "celsius": p.celsius,
                   "state": p.state, "known": p.known,
                   "unavailable": p.unavailable,
                   "floor": IDLE,
                   "warm": WARM.get(p.part, 80),
                   "hot": HOT.get(p.part, 90)}
                  for p in found.parts],
        "hottest": (found.hottest.celsius if found.hottest else None),
    }

# ---------------------------------------------------------------------------
# The elevated half
# ---------------------------------------------------------------------------
#
# CPU and drive temperatures need administrator, and the obvious answer -- run
# the whole application elevated -- is the wrong one here. This app launches
# CS2 through the ``steam://`` protocol, and a protocol handler invoked from an
# elevated process starts Steam elevated too when Steam is not already up.
# Steam then writes its files as administrator, which is a permission mess to
# unpick and something Valve advises against. A UAC prompt on every launch, to
# read a thermometer, is a poor trade on its own; one that can leave the game
# library owned by the wrong user is not a trade at all.
#
# So only the reader is elevated. A small helper process is started on request,
# samples the two privileged sources, and publishes them to a file the
# unelevated application reads. One prompt, and the app -- and therefore Steam
# -- stays exactly as it was.

HELPER_FILE = "temps_elevated.json"

# How long a published reading is worth trusting. Three refreshes: enough that
# a slow sample does not blink the display out, short enough that a helper
# which has died stops being believed.
HELPER_STALE = REFRESH * 3


def helper_path() -> "Path":
    from .paths import user_data_dir

    return user_data_dir() / HELPER_FILE


def _parent_alive(pid: int) -> bool:
    """Whether the application that asked for this helper is still running.

    The helper holds administrator rights, so it must not outlive the thing
    that wanted them. Tying it to the parent means closing the app closes it,
    including on a crash.
    """
    if not pid:
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError:
        return False
    SYNCHRONIZE = 0x00100000
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not handle:
        return False
    # WAIT_TIMEOUT means it is still running; WAIT_OBJECT_0 means it has gone.
    still = kernel32.WaitForSingleObject(handle, 0) != 0
    kernel32.CloseHandle(handle)
    return still


def run_helper(parent_pid: int) -> int:
    """Sample the privileged sources until the application goes away.

    This is what runs behind the UAC prompt. It writes and exits; it never
    reads the application's own state, and it has no other entry point.
    """
    path = helper_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    while _parent_alive(parent_pid):
        parts = [_system_zone()]
        parts.extend(_drives())
        payload = {
            "at": time.time(),
            "parts": [{"part": p.part, "label": p.label, "celsius": p.celsius,
                       "unavailable": p.unavailable} for p in parts],
        }
        try:
            path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            return 1
        time.sleep(REFRESH)
    try:
        path.unlink()
    except OSError:
        pass
    return 0


def _published() -> List[Reading]:
    """Readings from the elevated helper, if one is running and current."""
    try:
        raw = helper_path().read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, ValueError):
        return []
    if time.time() - float(payload.get("at") or 0) > HELPER_STALE:
        return []
    out: List[Reading] = []
    for row in payload.get("parts") or []:
        out.append(Reading(part=str(row.get("part") or ""),
                           label=str(row.get("label") or ""),
                           celsius=row.get("celsius"),
                           unavailable=str(row.get("unavailable") or "")))
    return out


def helper_running() -> bool:
    return bool(_published())


def start_helper() -> dict:
    """Ask Windows for the one prompt, and start the reader behind it.

    Returns without waiting: the prompt is the user's to answer, and the first
    readings appear a moment later through the normal refresh.
    """
    if sys.platform != "win32":
        return {"ok": False, "error": "administrator rights are a Windows thing"}
    if helper_running():
        return {"ok": True, "already": True, "note": "already reading"}
    if _elevated():
        # Already administrator, so no prompt is needed or wanted.
        threading.Thread(target=run_helper, args=(os.getpid(),), daemon=True).start()
        return {"ok": True, "elevated": True, "note": "reading directly"}

    exe, args = _helper_command()
    if not exe:
        return {"ok": False, "error": "could not work out how to start the reader"}
    try:
        # SW_HIDE, and "runas" is what raises the prompt.
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 0)
    except Exception as exc:                # pragma: no cover - shell refusal
        return {"ok": False, "error": str(exc)}
    if int(result) <= 32:
        # 5 is ERROR_ACCESS_DENIED, which here means the prompt was declined.
        if int(result) == 5:
            return {"ok": False, "declined": True,
                    "error": "the administrator prompt was declined"}
        return {"ok": False, "error": f"Windows refused to start the reader ({result})"}
    return {"ok": True, "started": True}


def _helper_command() -> tuple:
    """The executable and arguments that run this module as the helper.

    Frozen, the application is its own helper. From source it is the
    interpreter running the package. Either way the parent's id goes with it so
    the helper cannot outlive the app that asked for it.
    """
    from .paths import is_frozen

    pid = os.getpid()
    if is_frozen():
        return sys.executable, f'temp-helper --parent {pid}'
    script = str(Path(__file__).resolve().parents[1])
    return sys.executable, f'-m cs2cfg temp-helper --parent {pid}'

