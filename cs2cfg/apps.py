"""Named companion settings. Only discover/watch/start apps and open URLs.

All preferences below belong to CS2 Auto Config, never to another program.
"""
from __future__ import annotations

import ipaddress
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlencode

from . import companions

NAMES = {"discord": "Discord", "teamspeak": "TeamSpeak"}


def find(ui: Dict[str, Any], kind: str):
    if kind not in NAMES:
        raise ValueError("Unknown app")
    held = next((c for c in companions.listed(ui)
                 if c["integration"] == kind or c["id"] == kind
                 or (kind == "discord" and c["id"] in ("discordptb", "discordcanary"))
                 or c["name"].lower() == kind), None)
    if held:
        return held
    if kind == "discord":
        from .firstrun import _discord
        found = _discord()
        if found:
            return {**found, "with_game": False, "integration": kind}
    else:
        for env, folder, exe in (
            ("ProgramFiles", "TeamSpeak 3 Client", "ts3client_win64.exe"),
            ("ProgramFiles(x86)", "TeamSpeak 3 Client", "ts3client_win32.exe"),
            ("LOCALAPPDATA", "Programs/TeamSpeak", "TeamSpeak.exe"),
            ("ProgramFiles", "TeamSpeak", "TeamSpeak.exe"),
        ):
            base = os.environ.get(env)
            path = Path(base) / folder / exe if base else None
            if path and path.is_file():
                return {"id": kind, "name": NAMES[kind], "exe": str(path),
                        "args": "", "with_game": False, "integration": kind}
    return None


def running(kind):
    processes = (("Discord.exe", "DiscordPTB.exe", "DiscordCanary.exe")
                 if kind == "discord" else
                 ("ts3client_win64.exe", "ts3client_win32.exe", "TeamSpeak.exe"))
    return any(companions.running(n) for n in processes)


def survey(ui):
    out = {}
    for kind, name in NAMES.items():
        entry = find(ui, kind)
        out[kind] = {"name": name, "installed": bool(entry and Path(entry["exe"]).is_file()),
                     "running": running(kind),
                     "with_game": bool(entry and entry.get("with_game")),
                     "exe": entry["exe"] if entry else ""}
    return out


def server(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid TeamSpeak server")
    host = str(value.get("host") or "").strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        port = int(value.get("port", 9987))
    except (ValueError, TypeError):
        raise ValueError("Port must be between 1 and 65535")
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    if host:
        try:
            ipaddress.ip_address(host)
        except ValueError:
            try:
                host = host.encode("idna").decode("ascii")
            except UnicodeError:
                raise ValueError("Enter a hostname or IP address")
            if len(host) > 253 or not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                                         for label in host.rstrip(".").split(".")):
                raise ValueError("Enter a hostname or IP address, without a URL or path")
    enabled = bool(value.get("enabled"))
    if enabled and not host:
        raise ValueError("Enter a host before enabling auto-join")
    nickname = str(value.get("nickname") or "").strip()
    if len(nickname) > 64 or any(ord(c) < 32 for c in nickname):
        raise ValueError("Nickname must be at most 64 characters without control characters")
    return {"host": host, "port": port, "nickname": nickname, "enabled": enabled}


def join_url(value):
    clean = server(value)
    if not clean["host"]:
        raise ValueError("Enter a TeamSpeak host")
    host = clean["host"]
    if ":" in host:
        host = "[" + host + "]"
    return "ts3server://" + host + "?" + urlencode({"port": clean["port"], "nickname": clean["nickname"]})


def open_url(url):
    # Never shell a user-supplied URI. os.startfile passes it to its handler.
    if url != "ms-gamebar:" and not url.startswith("ts3server://"):
        return {"ok": False, "error": "Unsupported app URL"}
    if sys.platform != "win32":
        return {"ok": False, "error": "Opening app URLs requires Windows"}
    try:
        os.startfile(url)
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "detail": "Opened the app URL"}


def configure(ui, kind, body):
    if kind not in NAMES:
        raise ValueError("Unknown app")
    entry = find(ui, kind)
    exe = str(body.get("exe") or "")
    if exe:
        if Path(exe).suffix.lower() != ".exe" or not Path(exe).is_file():
            raise ValueError("Choose an installed .exe file")
        entry = {"id": kind, "name": NAMES[kind], "exe": exe, "args": "",
                 "integration": kind, "with_game": bool(entry and entry.get("with_game"))}
    if not entry:
        raise ValueError("App not found. Choose its executable first.")
    if "with_game" in body:
        entry["with_game"] = bool(body["with_game"])
    entry["integration"] = kind
    held = companions.listed(ui)
    held = [c for c in held if not (c["id"] == entry["id"] or c["integration"] == kind
                                   or c["exe"].lower() == entry["exe"].lower())]
    if len(held) >= companions.MAX_COMPANIONS:
        raise ValueError("There is no room for another companion")
    return {"companions": held + [entry]}


def launch(ui, kind):
    if kind not in NAMES:
        return {"ok": False, "error": "Unknown app"}
    if survey(ui)[kind]["running"]:
        return {"ok": True, "detail": NAMES[kind] + " is already running"}
    entry = find(ui, kind)
    if not entry:
        return {"ok": False, "error": "App not found. Choose its executable first."}
    return companions.start(entry)
