"""Administrator jobs, asked for once and never again.

The rule (Edy, Nov 2026): the app asks for every permission once, during
setup, and after that never raises an administrator prompt -- not on start,
not per fix, not per launch.

How: the first-run setup installs a small helper behind one UAC prompt (see
``helper/install.ps1``). It is a PowerShell script under Program Files, run by
a scheduled task with highest privileges for this Windows user. Later the app
drops a request file into a folder only this user and administrators can
write, starts the task (which Windows allows without a prompt, because an
administrator registered it), and reads the answer back.

Why it is safe to leave installed: the helper does a fixed list of jobs
(:data:`OPS`) and checks every argument itself, whatever was checked here.
It never runs a command, a script or a program named in a request, and the
code it runs lives where a normal user cannot change it. The worst a rogue
program running as this user could do through it is what the list allows --
block CS2's own traffic, flush DNS, restart a peripheral or Windows Audio --
all things that user could already do with one prompt.

When the helper is not installed (setup skipped, an older install, not
Windows), :func:`run` says so with ``needs_setup`` and callers fall back to
their old one-off prompt, so nothing that worked before stops working.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Must match $Version in helper/broker.ps1.
HELPER_VERSION = 2

TASK = r"\CS CONFIG AI\Helper"
PROGRAM_DIR_NAME = "CS CONFIG AI Helper"
DATA_DIR_NAME = "CS CONFIG AI Helper"

OPS = (
    "ping",
    "firewall.lock", "firewall.unlock", "firewall.status",
    "dns.flush", "adapter.restart", "audio.restart", "device.restart",
    "power.set", "cfg.grant", "temps.watch", "faceit_ac.start", "defender.cs2",
    "helper.uninstall",
)

TIMEOUT = 45.0
POLL = 0.25
_CREATE_NO_WINDOW = 0x08000000

_NAME = re.compile(r"^[A-Za-z0-9 _\-\.\(\)]{1,48}$")
_GUID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")
_CIDR = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?:/(\d{1,2}))?$")
_CS2 = re.compile(r"\\game\\bin\\win64\\cs2\.exe$", re.I)
_CFG = re.compile(r"\\steamapps\\common\\[^\\]+\\game\\csgo\\cfg\\?$", re.I)


class HelperError(ValueError):
    """A request the helper would refuse anyway, caught before it is sent."""


# --- where things are --------------------------------------------------------

def program_dir() -> Path:
    return Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / PROGRAM_DIR_NAME


def data_dir() -> Path:
    return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / DATA_DIR_NAME


def bundled_dir() -> Path:
    from .paths import bundle_root

    return bundle_root() / "helper"


def installed_version() -> int:
    """The version of the helper in Program Files, or 0 if there is none."""
    try:
        text = (program_dir() / "broker.ps1").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    found = re.search(r"^\$Version\s*=\s*(\d+)", text, re.M)
    return int(found.group(1)) if found else 0


def status() -> Dict[str, Any]:
    version = installed_version()
    return {
        "supported": sys.platform == "win32",
        "installed": version > 0,
        "current": version >= HELPER_VERSION,
        "version": version,
        "wanted": HELPER_VERSION,
    }


def ready() -> bool:
    return sys.platform == "win32" and installed_version() >= HELPER_VERSION


# --- checking a request before it goes ---------------------------------------

def _cidr_ok(text: str) -> bool:
    found = _CIDR.match(text or "")
    if not found:
        return False
    if any(int(found.group(i)) > 255 for i in range(1, 5)):
        return False
    bits = found.group(5)
    return bits is None or 8 <= int(bits) <= 32


def validate(op: str, args: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The request as it will be sent, or HelperError. Mirrors broker.ps1."""
    args = dict(args or {})
    if op not in OPS:
        raise HelperError(f"the helper does not do {op!r}")

    if op == "helper.uninstall":
        if args:
            raise HelperError("uninstalling the helper takes no arguments")
        return {}

    if op == "firewall.lock":
        program = str(args.get("program") or "")
        if not _CS2.search(program):
            raise HelperError("the region lock only ever applies to cs2.exe")
        regions = args.get("regions")
        if not isinstance(regions, list) or not 1 <= len(regions) <= 64:
            raise HelperError("between 1 and 64 regions")
        total = 0
        clean: List[Dict[str, Any]] = []
        for region in regions:
            name = str((region or {}).get("name") or "")
            cidrs = (region or {}).get("cidrs")
            if not _NAME.match(name):
                raise HelperError(f"bad region name {name!r}")
            if not isinstance(cidrs, list) or not cidrs or not all(_cidr_ok(str(c)) for c in cidrs):
                raise HelperError(f"bad addresses for {name}")
            total += len(cidrs)
            clean.append({"name": name, "cidrs": [str(c) for c in cidrs]})
        if total > 2000:
            raise HelperError("too many addresses")
        return {"program": program, "regions": clean}

    if op == "adapter.restart":
        name = str(args.get("name") or "")
        if not name or len(name) > 256:
            raise HelperError("no adapter chosen")
        return {"name": name}

    if op == "device.restart":
        instance = str(args.get("instance_id") or "")
        if not instance or len(instance) > 512:
            raise HelperError("no device chosen")
        return {"instance_id": instance}

    if op == "power.set":
        guid = str(args.get("guid") or "")
        if not _GUID.match(guid):
            raise HelperError("bad power plan id")
        return {"guid": guid}

    if op == "cfg.grant":
        path = str(args.get("path") or "")
        if not _CFG.search(path):
            raise HelperError("that is not a CS2 cfg folder")
        return {"path": path}

    if op == "temps.watch":
        pid = int(args.get("pid") or 0)
        if pid <= 0:
            raise HelperError("no app to watch")
        return {"pid": pid}

    if op == "defender.cs2":
        program = str(args.get("program") or "")
        if not _CS2.search(program):
            raise HelperError("only CS2's own folder")
        return {"program": program, "on": bool(args.get("on"))}

    return {}


# --- running a job -----------------------------------------------------------

def _start_task() -> Optional[str]:
    """Start the helper's task. None on success, otherwise what went wrong."""
    try:
        done = subprocess.run(
            ["schtasks", "/run", "/tn", TASK], capture_output=True, text=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except (OSError, subprocess.SubprocessError) as exc:
        return str(exc)
    if done.returncode != 0:
        return (done.stderr or done.stdout or "").strip() or f"schtasks said {done.returncode}"
    return None


def run(op: str, args: Optional[Dict[str, Any]] = None, timeout: float = TIMEOUT,
        wait: bool = True) -> Dict[str, Any]:
    """Ask the helper to do one job. Never raises; never prompts."""
    if not ready():
        return {"ok": False, "needs_setup": True,
                "error": "finish setup once to allow this without a prompt"}
    try:
        body = validate(op, args)
    except HelperError as exc:
        return {"ok": False, "error": str(exc)}

    job = uuid.uuid4().hex
    requests = data_dir() / "requests"
    results = data_dir() / "results"
    try:
        tmp = requests / f"{job}.part"
        tmp.write_text(json.dumps({"op": op, "args": body}), encoding="utf-8")
        tmp.replace(requests / f"{job}.json")
    except OSError as exc:
        return {"ok": False, "error": f"could not reach the helper: {exc}"}

    trouble = _start_task()
    if trouble:
        try:
            (requests / f"{job}.json").unlink()
        except OSError:
            pass
        return {"ok": False, "error": f"the helper did not start: {trouble}"}
    if not wait:
        return {"ok": True, "started": True, "job": job}

    answer = results / f"{job}.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            raw = answer.read_text(encoding="utf-8-sig").strip()
        except OSError:
            raw = ""
        if raw:
            try:
                out = json.loads(raw)
            except ValueError:
                return {"ok": False, "error": "the helper answered with something unreadable"}
            return out if isinstance(out, dict) else {"ok": False, "error": "unreadable answer"}
        time.sleep(POLL)
    return {"ok": False, "error": "the helper did not answer in time"}


def temps_published() -> Optional[Dict[str, Any]]:
    """What a running ``temps.watch`` last wrote, if anything."""
    try:
        return json.loads((data_dir() / "results" / "temps.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


# --- the one prompt -----------------------------------------------------------

def install(cfg_path: Optional[Path] = None) -> Dict[str, Any]:
    """Put the helper in place. The one administrator prompt the app raises."""
    if sys.platform != "win32":
        return {"ok": False, "error": "the helper is for Windows"}
    from .quickfix import _run_elevated

    source = str(bundled_dir()).replace("'", "''")
    cfg = str(cfg_path or "").replace("'", "''")
    result = _run_elevated(
        f"  $r = & '{source}\\install.ps1' -Source '{source}' -CfgPath '{cfg}'\n"
        "  $out.ok = [bool]$r.ok\n"
        "  $out.detail = [string]$r.detail\n",
        timeout=120)
    if result.get("ok") and not ready():
        return {"ok": False, "error": "setup ran but the helper is not in place"}
    return result


def remove() -> Dict[str, Any]:
    if sys.platform != "win32":
        return {"ok": False, "error": "the helper is for Windows"}
    from .quickfix import _run_elevated

    source = str(bundled_dir()).replace("'", "''")
    return _run_elevated(
        f"  $r = & '{source}\\install.ps1' -Remove\n"
        "  $out.ok = [bool]$r.ok\n  $out.detail = [string]$r.detail\n")


def uninstall_cleanup(timeout: float = 30.0) -> Dict[str, Any]:
    """Run by the uninstaller: undo everything the helper made, with no prompt.

    Firewall rules, CS2 Defender exclusions, the scheduled task and both
    helper folders. Needs the current helper; an older one cannot do this job
    silently, and nothing else may prompt, so that case is only reported.
    """
    state = status()
    if not state["installed"]:
        return {"ok": True, "detail": "no helper installed; nothing to remove"}
    if not state["current"]:
        return {"ok": False, "error": "an older helper is installed and cannot remove itself silently"}
    return run("helper.uninstall", {}, timeout=timeout)
