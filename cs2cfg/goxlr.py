"""Small, loopback-only GoXLR adapter. No file writes, daemon, CLI or helper.

Protocol sources and remaining home-PC checks: preview/sec7-notes.md.
Utility: https://github.com/GoXLR-on-Linux/goxlr-utility/wiki/The-GoXLR-Utility-API
Shapes: upstream ipc/src/{lib,device}.rs (GetStatus, files, mixers, Load*Profile).
Official: https://github.com/oddbear/GoXLR-TouchPortal-Plugin/wiki/Development---specification
The official App is a CLIENT of the plugin's :6805 server, not a public server.
Do not send to that port or take it over: it may belong to Stream Deck. There is
no documented official mic-profile switch in that reference. Official switching
is unavailable until a compatible, documented bridge is provided.
"""
from __future__ import annotations

import csv
import http.client
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

TIMEOUT = 0.7
MAX_RESPONSE = 2 * 1024 * 1024
# UNVERIFIED on Edy's PC: default port 14564, reported in the supplied brief.
# API path and JSON shapes are confirmed by the upstream API wiki and ipc source.
UTILITY_PORT = 14564
BINDINGS = "goxlr_setup_bindings"


class GoXLRError(Exception):
    pass


def _request(command: Any) -> Any:
    """Direct HTTP avoids proxies, redirects, shell execution and remote hosts."""
    conn = http.client.HTTPConnection("127.0.0.1", UTILITY_PORT, timeout=TIMEOUT)
    try:
        conn.request("POST", "/api/command", json.dumps(command).encode("utf-8"),
                     {"Content-Type": "application/json"})
        response = conn.getresponse()
        data = response.read(MAX_RESPONSE + 1)
        if response.status != 200 or len(data) > MAX_RESPONSE:
            raise GoXLRError("GoXLR Utility returned an unreadable response. Refresh to retry.")
        result = json.loads(data)
        if isinstance(result, dict) and "Error" in result:
            raise GoXLRError(str(result["Error"])[:240])
        return result
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise GoXLRError("GoXLR Utility did not respond. Open it and refresh.") from exc
    finally:
        conn.close()


def _status() -> dict:
    result = _request("GetStatus")
    if not isinstance(result, dict) or not isinstance(result.get("Status"), dict):
        raise GoXLRError("GoXLR Utility status format is not supported.")
    result = result["Status"]
    if not isinstance(result.get("mixers"), dict) or not isinstance(result.get("files"), dict):
        raise GoXLRError("GoXLR Utility status format is not supported.")
    if any(not isinstance(k, str) or not isinstance(v, dict) for k, v in result["mixers"].items()):
        raise GoXLRError("GoXLR Utility mixer format is not supported.")
    return result


def _processes() -> set[str]:
    if sys.platform != "win32":
        return set()
    try:
        result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                                text=True, timeout=TIMEOUT, creationflags=0x08000000)
        return {row[0].casefold() for row in csv.reader(result.stdout.splitlines()) if row}
    except (OSError, subprocess.TimeoutExpired):
        return set()


def _documents() -> Path:
    # Resolve redirected/OneDrive Documents using Windows' per-user location.
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                return Path(os.path.expandvars(winreg.QueryValueEx(key, "Personal")[0]))
        except (OSError, ImportError):
            pass
    return Path.home() / "Documents"


def _names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return sorted({v for v in items if isinstance(v, str) and 0 < len(v) <= 240
                   and not any(c in v for c in "/\\\x00\r\n")}, key=str.casefold)


def _official_profiles() -> tuple[list[str], list[str]]:
    # UNVERIFIED: the supplied brief reports these two folders/extensions;
    # no vendor primary reference was found. Directory entries only; never open
    # profile contents, create folders, rename, write or launch these files.
    root = _documents() / "GoXLR"
    def listing(folder: str, extension: str) -> list[str]:
        try:
            return _names([p.stem for p in (root / folder).iterdir()
                           if p.suffix.casefold() == extension.casefold() and p.is_file()])
        except OSError:
            return []
    return listing("Profiles", ".goxlr"), listing("Mic Profiles", ".goxlrMicProfile")


def _utility(status: dict, serial: str = "") -> dict:
    mixers = status["mixers"]
    serial = serial if serial in mixers else (next(iter(mixers)) if not serial and len(mixers) == 1 else "")
    mixer = mixers.get(serial) or {}
    return {"backend": "utility", "state": "ready" if serial else "disconnected",
            "can_switch": bool(serial), "serial": serial,
            "mixers": [{"serial": s, "label": s} for s in sorted(mixers)],
            "profiles": _names(status["files"].get("profiles")),
            "mic_profiles": _names(status["files"].get("mic_profiles")),
            "current": {"device": str(mixer.get("profile_name") or ""),
                        "mic": str(mixer.get("mic_profile_name") or "")},
            "reason": "Choose a mixer." if mixers and not serial else "Connect your GoXLR." if not serial else ""}


def detect(serial: str = "") -> dict:
    try:
        return _utility(_status(), serial)
    except GoXLRError:
        pass
    running = _processes()
    # UNVERIFIED executable names: common official App / Utility names, not
    # confirmed against Edy's installed versions. Files alone never mean running.
    if running & {"goxlr app.exe", "goxlr.exe", "goxlrapp.exe"}:
        # UNVERIFIED: whether Edy's installed official App offers a newer bridge
        # or mic-profile action. No speculative action IDs/connections are used.
        device, mic = _official_profiles()
        return {"backend": "official", "state": "limited", "can_switch": False,
                "serial": "", "mixers": [], "profiles": device, "mic_profiles": mic,
                "current": {"device": "", "mic": ""},
                "reason": "Official App profiles are read-only here. Switching needs a supported bridge."}
    if running & {"goxlr-daemon.exe", "goxlr-utility.exe"}:
        return {"backend": "utility", "state": "unavailable", "can_switch": False,
                "serial": "", "mixers": [], "profiles": [], "mic_profiles": [],
                "current": {"device": "", "mic": ""},
                "reason": "Open Utility's local web server on port 14564, then refresh."}
    return {"backend": "none", "state": "not_found", "can_switch": False,
            "serial": "", "mixers": [], "profiles": [], "mic_profiles": [],
            "current": {"device": "", "mic": ""}, "reason": "GoXLR not found"}


class Controller:
    def __init__(self) -> None:
        self.lock = threading.Lock()

    def switch(self, backend: str, serial: str, choices: dict) -> dict:
        """Only allowlisted load commands, checked against a fresh device/listing.

        Never optimistically report success. If a command times out after being
        applied, the caller must refresh: the previous state is not proof of a
        physical rollback. A two-profile Setup can partially succeed.
        """
        if backend != "utility":
            raise GoXLRError("Official App switching needs a supported bridge.")
        if (not isinstance(serial, str) or not serial or not isinstance(choices, dict)
                or not choices or set(choices) - {"device", "mic"}
                or any(not isinstance(v, str) for v in choices.values())):
            raise GoXLRError("Choose a mixer and a profile first.")
        if not self.lock.acquire(blocking=False):
            raise GoXLRError("A GoXLR switch is still in progress.")
        try:
            before = _utility(_status(), serial)
            if before["serial"] != serial:
                raise GoXLRError("That GoXLR is disconnected. Refresh before switching.")
            for kind, name in choices.items():
                if name not in before["profiles" if kind == "device" else "mic_profiles"]:
                    raise GoXLRError("That profile is no longer available. Refresh before switching.")
            for kind, name in choices.items():
                command = "LoadProfile" if kind == "device" else "LoadMicProfile"
                # Upstream CLI calls this boolean `persist`. False requests a
                # runtime load, without saving/replacing the user's profiles.
                result = _request({"Command": [serial, {command: [name, False]}]})
                if result != "Ok":
                    raise GoXLRError("GoXLR did not acknowledge the switch. Refresh to check its state.")
            after = _utility(_status(), serial)
            if after["serial"] != serial or any(after["current"][k] != v for k, v in choices.items()):
                raise GoXLRError("GoXLR has not confirmed the profile yet. Refresh to check its state.")
            return after
        finally:
            self.lock.release()


def bindings(ui: dict, account: Any, setups: list[str]) -> dict:
    stored = ui.get(BINDINGS)
    stored = stored.get(str(account or ""), {}) if isinstance(stored, dict) else {}
    return {name: value for name, value in stored.items()
            if name in setups and isinstance(value, dict)} if isinstance(stored, dict) else {}


def update_binding(ui: dict, account: Any, name: str, value: Any = None, rename: str = "") -> dict:
    """Local app preferences only. Used for unlink, rename and delete as well."""
    old = ui.get(BINDINGS)
    stored = dict(old) if isinstance(old, dict) else {}
    key = str(account or "")
    mine = dict(stored[key]) if isinstance(stored.get(key), dict) else {}
    if rename and name in mine:
        mine[rename] = mine.pop(name)
    elif value is None:
        mine.pop(name, None)
    else:
        mine[name] = value
    stored[key] = mine
    return {BINDINGS: stored}
