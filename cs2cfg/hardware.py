"""Hardware detection.

Shells out to ``probe.ps1`` and normalises the result. Everything Windows
specific lives in the PowerShell side; everything judgemental lives here.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import bundle_root

PROBE = bundle_root() / "probe.ps1"

# Refresh rates a panel plausibly runs at. Used to sanity-check a reported
# rate before we trust it as a frame-rate target.
COMMON_REFRESH = (60, 75, 100, 120, 144, 165, 170, 175, 180, 200, 240, 280, 360, 480, 540)


class ProbeError(RuntimeError):
    """The hardware probe could not be run or its output made no sense."""


@dataclass
class Gpu:
    name: str
    vram_gb: float
    vendor: str
    driver_version: Optional[str] = None
    driver_date: Optional[str] = None
    vendor_id: Optional[int] = None
    device_id: Optional[int] = None

    @property
    def is_nvidia(self) -> bool:
        return self.vendor == "nvidia"

    @property
    def is_amd(self) -> bool:
        return self.vendor == "amd"


@dataclass
class Cpu:
    name: str
    cores: int
    threads: int
    max_clock_mhz: int
    vendor: str

    @property
    def likely_hybrid(self) -> bool:
        """True for Intel P/E-core designs (12th gen and newer).

        Detected structurally rather than by model list: on a hybrid part the
        thread count is less than twice the core count, because E-cores have
        no SMT. A 16C/24T 12900K gives 24 < 32; a 8C/16T 10700K gives 16 == 16.
        """
        return self.vendor == "intel" and self.cores > 4 and self.threads < self.cores * 2


@dataclass
class Display:
    width: int
    height: int
    refresh: int
    primary: bool = False
    name: Optional[str] = None
    confident_refresh: bool = True

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 0.0

    @property
    def pixels(self) -> int:
        return self.width * self.height


@dataclass
class Machine:
    cpu: Optional[Cpu]
    gpu: Optional[Gpu]
    all_gpus: List[Gpu]
    displays: List[Display]
    ram_gb: float
    ram_speed_mts: Optional[int]
    os_caption: str
    os_build: str
    power_plan: Optional[str]
    display_source: str
    disks: Dict[str, str] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def primary_display(self) -> Optional[Display]:
        if not self.displays:
            return None
        return next((d for d in self.displays if d.primary), self.displays[0])

    def media_type_for(self, path: Path) -> str:
        """SSD / HDD / Unknown for whichever drive holds ``path``."""
        drive = str(path.drive).rstrip(":").upper()
        return self.disks.get(drive, "Unknown")


def _powershell() -> str:
    """Locate PowerShell, without trusting PATH.

    A portable build is exactly the case where the environment cannot be relied
    on: PATH may be minimal, inherited from a stripped-down shell, or missing
    the WindowsPowerShell directory entirely. PowerShell ships at a known
    absolute location on every supported Windows, so check there too rather
    than failing on a technicality.
    """
    for candidate in ("pwsh.exe", "powershell.exe", "pwsh", "powershell"):
        found = shutil.which(candidate)
        if found:
            return found

    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    fixed = [
        # SysNative first: it is how a 32-bit process reaches the 64-bit
        # PowerShell, and is simply absent on a 64-bit process, so trying it
        # costs nothing.
        Path(system_root) / "SysNative" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
        Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
        Path(system_root) / "SysWOW64" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "PowerShell" / "7" / "pwsh.exe",
    ]
    for path in fixed:
        if path.is_file():
            return str(path)

    raise ProbeError(
        "PowerShell could not be found, on PATH or at any standard location. "
        "The hardware probe needs it."
    )


def run_probe(timeout: int = 90) -> Dict[str, Any]:
    """Execute probe.ps1 and return its parsed JSON."""
    if not PROBE.exists():
        raise ProbeError(f"probe script missing: {PROBE}")

    try:
        proc = subprocess.run(
            [
                _powershell(),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-File", str(PROBE),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(f"hardware probe timed out after {timeout}s") from exc

    if proc.returncode != 0:
        raise ProbeError(f"probe failed (exit {proc.returncode}): {proc.stderr.strip()[:500]}")

    text = proc.stdout.strip()
    if not text:
        raise ProbeError("probe produced no output")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"probe output was not JSON: {text[:300]}") from exc


def _vendor_from_name(name: str, vendor_id: Optional[int]) -> str:
    if vendor_id == 0x10DE:
        return "nvidia"
    if vendor_id in (0x1002, 0x1022):
        return "amd"
    if vendor_id == 0x8086:
        return "intel"
    low = name.lower()
    if "nvidia" in low or "geforce" in low or "quadro" in low:
        return "nvidia"
    if "radeon" in low or "amd" in low:
        return "amd"
    if "intel" in low or "arc " in low:
        return "intel"
    return "unknown"


def _is_virtual_gpu(name: str) -> bool:
    """Filter out the adapters that are not really rendering the game."""
    noise = (
        "microsoft basic display", "remote display", "virtual", "parsec",
        "citrix", "vmware", "teamviewer", "meta virtual", "oray", "ddm",
        "usb display", "displaylink", "idd ", "sunshine",
    )
    low = name.lower()
    return any(token in low for token in noise)


def _pick_primary_gpu(gpus: List[Gpu]) -> Optional[Gpu]:
    """Choose the adapter CS2 will actually run on.

    Discrete beats integrated, and among discrete the most VRAM wins. This is
    what matters on laptops, where WMI happily lists an iGPU first.
    """
    if not gpus:
        return None
    discrete = [g for g in gpus if not (g.vendor == "intel" and g.vram_gb < 4)]
    pool = discrete or gpus
    return max(pool, key=lambda g: (g.vendor != "intel", g.vram_gb))


def _reconcile_refresh(reported_max: int, current: int) -> tuple[int, bool]:
    """Settle on a refresh rate, and say whether we trust it.

    The WMI monitor tables only list the modes declared in the base EDID, so a
    240 Hz panel often reports 60 or 144 there. The adapter's current mode is
    ground truth for "at least this fast", so never let the table drag it down.
    Values are snapped to the nearest common rate because adapters report 239
    for a 240 Hz panel.
    """
    best = max(reported_max or 0, current or 0)
    if best <= 0:
        return 60, False

    snapped = min(COMMON_REFRESH, key=lambda r: abs(r - best))
    if abs(snapped - best) <= 3:
        best = snapped

    confident = (current or 0) > 0
    return best, confident


def detect(probe_data: Optional[Dict[str, Any]] = None) -> Machine:
    """Probe the machine (or interpret an existing probe payload)."""
    data = probe_data if probe_data is not None else run_probe()

    raw_gpus = data.get("gpus") or []
    gpus: List[Gpu] = []
    for g in raw_gpus:
        name = (g.get("name") or "").strip()
        if not name or _is_virtual_gpu(name):
            continue
        vram_bytes = g.get("vram_bytes") or 0
        gpus.append(
            Gpu(
                name=name,
                vram_gb=round(vram_bytes / (1024 ** 3), 1) if vram_bytes else 0.0,
                vendor=_vendor_from_name(name, g.get("vendor_id")),
                driver_version=g.get("driver_version"),
                driver_date=g.get("driver_date"),
                vendor_id=g.get("vendor_id"),
                device_id=g.get("device_id"),
            )
        )

    raw_cpu = data.get("cpu") or {}
    cpu = None
    if raw_cpu.get("name"):
        manufacturer = (raw_cpu.get("manufacturer") or "").lower()
        cpu = Cpu(
            name=raw_cpu["name"],
            cores=int(raw_cpu.get("cores") or 0),
            threads=int(raw_cpu.get("threads") or 0),
            max_clock_mhz=int(raw_cpu.get("max_clock_mhz") or 0),
            vendor="intel" if "intel" in manufacturer else "amd" if "amd" in manufacturer else "unknown",
        )

    # The adapter's current mode is the only refresh figure we can trust as a
    # floor, so carry it across into whatever the display table reported.
    adapter_refresh = max((g.get("current_refresh") or 0) for g in raw_gpus) if raw_gpus else 0

    displays: List[Display] = []
    for d in data.get("displays") or []:
        width = d.get("native_width") or d.get("current_width") or 0
        height = d.get("native_height") or d.get("current_height") or 0
        if not width or not height:
            continue
        refresh, confident = _reconcile_refresh(
            int(d.get("max_refresh") or 0),
            int(d.get("current_refresh") or 0) or (adapter_refresh if d.get("primary") else 0),
        )
        displays.append(
            Display(
                width=int(width),
                height=int(height),
                refresh=refresh,
                primary=bool(d.get("primary")),
                name=d.get("monitor") or d.get("device"),
                confident_refresh=confident,
            )
        )

    mem = data.get("memory") or {}
    disks = {
        (d.get("letter") or "").upper(): (d.get("media_type") or "Unknown") or "Unknown"
        for d in data.get("disks") or []
        if d.get("letter")
    }

    return Machine(
        cpu=cpu,
        gpu=_pick_primary_gpu(gpus),
        all_gpus=gpus,
        displays=displays,
        ram_gb=round((mem.get("total_bytes") or 0) / (1024 ** 3), 1),
        ram_speed_mts=mem.get("speed_mts"),
        os_caption=(data.get("os") or {}).get("caption") or "Unknown",
        os_build=str((data.get("os") or {}).get("build") or "?"),
        power_plan=data.get("power_plan"),
        display_source=data.get("display_source") or "unknown",
        disks=disks,
        raw=data,
    )


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    machine = detect()
    print(json.dumps(machine.raw, indent=2))
    print(f"\nCPU: {machine.cpu}\nGPU: {machine.gpu}\nDisplay: {machine.primary_display}", file=sys.stderr)
