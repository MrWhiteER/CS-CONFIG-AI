"""Local web front end.

A third face over the same functions the CLI and Tkinter GUI call. It exists
because a native window cannot be embedded in a browser pane, and looking at
the tool beside the thing you are editing is worth a small server.

Security posture, since this process can write to Steam's files:

* Bound to 127.0.0.1 only. Never reachable from the network.
* Mutating endpoints require a token minted at startup and embedded in the
  page, so a hostile page in the same browser cannot drive it by guessing the
  port. The Host header is checked for the same reason.
* GET endpoints are read-only by construction.
"""

from __future__ import annotations

import json
import mimetypes
import secrets
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from . import __version__, backup, cfglang, emit, steam, window
from .hardware import Machine, ProbeError, detect
from .kb import KnowledgeBase
from .profile import build_profile, plan_launch_options

from .paths import bundle_root

WEB_ROOT = bundle_root() / "web"
ALLOWED_HOSTS = ("127.0.0.1", "localhost", "[::1]")


class State:
    """Everything shared between requests, guarded by one lock.

    Hardware detection takes a few seconds, so the result is cached and reused
    until the page explicitly asks for a rescan.
    """

    def __init__(self, cfg_folder: str, cfg_name: str) -> None:
        self.token = secrets.token_urlsafe(24)
        self.kb = KnowledgeBase()
        self.cfg_folder = cfg_folder
        self.cfg_name = cfg_name
        self.lock = threading.Lock()
        self.machine: Optional[Machine] = None
        self.steam_root: Optional[Path] = None
        self.cs2_install: Optional[Path] = None
        self.users: list = []
        self.launch: Optional[Any] = None   # launcher.LaunchSession, once one starts
        self.ingame: Optional[Any] = None   # gamewatch.Watcher, started on demand
        self.cfg_scan: Optional[Any] = None  # cfgscan.ScanResult of the last scan
        self.updates: Optional[Any] = None   # updates.Checker, started on demand

    def refresh(self, rescan: bool = False) -> None:
        if self.machine is None or rescan:
            self.machine = detect()
        if self.steam_root is None or rescan:
            try:
                self.steam_root = steam.find_steam_root()
                self.cs2_install = steam.find_cs2_install(self.steam_root)
                self.users = steam.list_users(self.steam_root)
            except steam.SteamError:
                self.steam_root = None
                self.users = []

    def user_for(self, account: Optional[str]) -> steam.SteamUser:
        if not self.users:
            raise steam.SteamError("no Steam account with CS2 data was found")
        if account:
            match = next((u for u in self.users if u.account_id == str(account)), None)
            if match is None:
                raise steam.SteamError(f"account {account} not found")
            return match
        return self.users[0]


def _machine_payload(machine: Machine, state: State) -> Dict[str, Any]:
    cpu, gpu = machine.cpu, machine.gpu
    return {
        "cpu": {
            "name": cpu.name, "cores": cpu.cores, "threads": cpu.threads,
            "hybrid": cpu.likely_hybrid,
        } if cpu else None,
        "gpu": {
            "name": gpu.name, "vram_gb": gpu.vram_gb,
            "driver": gpu.driver_version, "driver_date": gpu.driver_date,
        } if gpu else None,
        "ram_gb": machine.ram_gb,
        "ram_speed": machine.ram_speed_mts,
        "os": f"{machine.os_caption} (build {machine.os_build})",
        "power_plan": machine.power_plan,
        "displays": [
            {"width": d.width, "height": d.height, "refresh": d.refresh,
             "primary": d.primary, "confident": d.confident_refresh}
            for d in machine.displays
        ],
        "cs2_install": str(state.cs2_install) if state.cs2_install else None,
        "steam_running": steam.steam_running(),
        "accounts": [
            {"id": u.account_id, "label": u.label, "has_video": u.video_cfg.exists()}
            for u in state.users
        ],
    }


def _plan_payload(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    state.refresh()
    user = state.user_for(body.get("account"))
    kb = state.kb

    current_video = steam.read_video_cfg(user)
    current_launch = steam.read_launch_options(user)
    target = body.get("target_fps")

    profile = build_profile(
        state.machine, kb,
        intent=body.get("intent", "balanced"),
        target_fps=int(target) if target else None,
        current_video=current_video,
    )
    launch = plan_launch_options(
        current_launch, state.machine, kb,
        exec_path=f"{state.cfg_folder}\\{state.cfg_name}",
    )

    settings = []
    for key in sorted(profile.video):
        value = profile.video[key]
        before = current_video.get(key)
        try:
            before_label = kb.label(key, int(before)) if before is not None else None
        except ValueError:
            before_label = before
        after_label = kb.label(key, value)
        settings.append({
            "key": key,
            "name": kb.ui_name(key),
            "before": before_label,
            "after": after_label,
            # A few settings store more values than the menu has names for, so
            # two different values can share a label. The page needs the raw
            # numbers to keep such a change from reading as a no-op.
            "before_raw": before,
            "after_raw": str(value),
            "same_label": before_label == after_label,
            "changed": before is None or str(value) != before,
            "reason": profile.video_reasons.get(key, ""),
        })

    return {
        "account": user.account_id,
        "tier": profile.tier,
        "intent": profile.intent,
        "description": kb.video["intents"][profile.intent]["description"],
        "cpu_score": round(profile.cpu_match.index),
        "gpu_score": round(profile.gpu_match.index),
        "cpu_exact": profile.cpu_match.exact,
        "gpu_exact": profile.gpu_match.exact,
        "cpu_note": profile.cpu_match.note,
        "gpu_note": profile.gpu_match.note,
        "cpu_ceiling": profile.cpu_ceiling,
        "gpu_ceiling": profile.gpu_ceiling,
        "bottleneck": profile.bottleneck,
        "estimated_fps": profile.estimated_fps,
        "target_fps": profile.target_fps,
        "headroom": round(profile.headroom, 2),
        "settings": settings,
        "changed_count": sum(1 for s in settings if s["changed"]),
        "launch_current": current_launch,
        "launch_new": launch.line,
        "launch_removed": [{"option": o, "reason": r} for o, r in launch.removed],
        "launch_added": [{"option": o, "reason": r} for o, r in launch.added],
        "advisories": [
            {"level": a.level, "title": a.title, "detail": a.detail}
            for a in profile.advisories
        ],
    }


def _apply(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    state.refresh()
    user = state.user_for(body.get("account"))
    kb = state.kb
    steps = []

    target = body.get("target_fps")
    profile = build_profile(
        state.machine, kb,
        intent=body.get("intent", "balanced"),
        target_fps=int(target) if target else None,
        current_video=steam.read_video_cfg(user),
    )
    launch = plan_launch_options(
        steam.read_launch_options(user), state.machine, kb,
        exec_path=f"{state.cfg_folder}\\{state.cfg_name}",
    )

    write_launch = bool(body.get("write_launch", True))
    if write_launch and steam.steam_running():
        return {"ok": False, "error":
                "Steam is running. It rewrites localconfig.vdf when it exits, so the launch "
                "options would be lost. Close Steam, or untick the launch options box."}

    session = backup.BackupSession(note=f"web apply {profile.intent}/tier {profile.tier}")

    if body.get("write_video", True):
        try:
            diff = steam.write_video_cfg(user, profile.video, session)
            steps.append({"ok": True, "what": "cs2_video.txt",
                          "detail": f"{len(diff)} setting(s) changed"})
        except steam.SteamError as exc:
            steps.append({"ok": False, "what": "cs2_video.txt", "detail": str(exc)})

    if body.get("write_cfg", True) and state.cs2_install:
        root = steam.cfg_dir(state.cs2_install)
        target_path = root / state.cfg_folder / state.cfg_name
        emit.write_text_file(target_path, emit.render_cfg(profile, kb, state.cfg_name), session)
        steps.append({"ok": True, "what": state.cfg_name, "detail": str(target_path)})

        notes = root / state.cfg_folder / "launch_options_generated.txt"
        emit.write_text_file(
            notes, emit.render_launch_notes(profile, launch.line, launch.removed, launch.added), session
        )
        steps.append({"ok": True, "what": "launch_options_generated.txt", "detail": str(notes)})

        if body.get("link_autoexec"):
            result = emit.ensure_exec_line(
                root / state.cfg_folder / "autoexec.vcfg",
                f"{state.cfg_folder}/{state.cfg_name}", session
            )
            steps.append({"ok": True, "what": "autoexec.vcfg", "detail": result})

    if write_launch:
        try:
            action = steam.write_launch_options(user, launch.line, session)
            steps.append({"ok": True, "what": "Steam launch options", "detail": action})
        except steam.SteamError as exc:
            steps.append({"ok": False, "what": "Steam launch options", "detail": str(exc)})

    backup.prune()
    return {"ok": True, "steps": steps, "backup": None if session.empty else session.stamp}


def _revert(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    target = backup.find_set(body.get("stamp") or "latest")
    if target is None:
        return {"ok": False, "error": "no backup found"}
    if any("localconfig.vdf" in f for f in target.files) and steam.steam_running():
        return {"ok": False, "error":
                "Steam is running and this backup includes localconfig.vdf. Close Steam first."}
    return {"ok": True, "stamp": target.stamp, "lines": backup.restore(target)}


def _play(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """Start a launch. Always through Steam; never by running cs2.exe."""
    from .launcher import LaunchError, LaunchSession

    state.refresh()
    if state.launch is not None and state.launch.active:
        return {"ok": False, "error": "a launch is already in progress"}

    user = state.user_for(body.get("account"))
    video = steam.read_video_cfg(user)
    width = int(body.get("width") or video.get("setting.defaultres") or 0)
    height = int(body.get("height") or video.get("setting.defaultresheight") or 0)

    display = state.machine.primary_display if state.machine else None
    if not (width and height) and display:
        width, height = display.width, display.height
    if not (width and height):
        return {"ok": False, "error": "no resolution to launch at; set one explicitly"}

    refresh = int(body.get("refresh") or (display.refresh if display else 0))
    stretch_mode = body.get("stretch_mode") or "borderless"
    # Earlier names, kept working so a saved preference does not break.
    stretch_mode = {"window": "borderless", "desktop": "borderless",
                    "none": "fullscreen"}.get(stretch_mode, stretch_mode)
    if stretch_mode not in ("borderless", "fullscreen"):
        return {"ok": False, "error": f"unknown launch mode {stretch_mode!r}"}

    if stretch_mode == "borderless":
        try:
            window.set_mode(width, height, refresh, test_only=True)
        except window.WindowError as exc:
            return {"ok": False, "error":
                    f"{exc}. Create the mode with Custom Resolution Utility, or choose native aspect."}

    state.launch = LaunchSession(user, width, height, refresh, stretch_mode,
                                 patch_video=bool(body.get("patch_video", True)))
    try:
        state.launch.start()
    except LaunchError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "width": width, "height": height, "refresh": refresh,
            "stretch_mode": stretch_mode}


def _play_stop(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    close_game = bool(body.get("close_game"))
    force = bool(body.get("force", True))

    if state.launch is None or not state.launch.active:
        # The watcher can be gone while the game is still up, so closing has to
        # work independently of whether we are still watching.
        if close_game:
            found = window.find_game_window("cs2.exe")
            if found is None:
                return {"ok": False, "error": "CS2 does not appear to be running"}
            return {"ok": True, "closed": window.close_process_window(found.hwnd, force=force)}
        return {"ok": False, "error": "nothing is running"}

    return {"ok": True, "closed": state.launch.stop(close_game=close_game, force=force)}


def _save_prefs(_state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """Remember what the user chose, so the next run starts where they left off."""
    from .cli import load_prefs, save_prefs

    prefs = load_prefs()
    prefs.setdefault("ui", {})
    # An allowlist rather than a blind update, so the page cannot write
    # arbitrary keys into the config file. Anything the UI remembers has to be
    # named here too, or it is silently dropped.
    allowed = (
        "intent", "target_fps", "account", "write_video", "write_cfg",
        "write_launch", "link_autoexec", "stretch_mode", "patch_video",
        "cfg_folder", "tab", "favourites", "mouse_shape", "kb_layout", "kb_shown",
        "update_auto_download", "update_skip",
    )
    for key in allowed:
        if key in body:
            prefs["ui"][key] = body[key]
    save_prefs(prefs)
    return {"ok": True, "saved": prefs["ui"]}


def _history(_state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    from . import telemetry

    sessions = telemetry.load_sessions(int(body.get("limit") or 25))
    return {"ok": True, "sessions": sessions, "summary": telemetry.summarise(sessions)}


def _cfg_scan(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """Scan a config folder and return structure, dependencies and diagnostics."""
    from . import cfgformat, cfgscan
    from .cfglang import Severity

    folder = Path(str(body.get("folder") or "")).expanduser()
    if not folder.is_dir():
        return {"ok": False, "error": f"not a folder: {folder}"}

    result = cfgscan.scan(folder)
    state.cfg_scan = result

    files = []
    for key in sorted(result.files):
        config = result.files[key]
        polish = None
        if config.is_commands:
            text = config.path.read_bytes().decode(
                config.document.encoding, errors="replace")
            outcome = cfgformat.polish(text, config.relative)
            polish = {
                "changed": outcome.changed,
                "safe": outcome.safe,
                "skipped_reason": outcome.skipped_reason,
                "lines_touched": outcome.stats()["lines_touched"] if outcome.safe else 0,
                "diff": outcome.diff if outcome.changed else "",
            }
        files.append({
            "relative": config.relative,
            "role": config.role,
            "order": config.exec_order,
            "generated_by": config.generated_by,
            "is_commands": config.is_commands,
            "lines": len(config.document.lines),
            "polish": polish,
        })

    aliases = []
    for lname in sorted(result.aliases):
        effective = result.effective_alias(lname)
        if effective is None:
            continue
        defs = result.aliases[lname]
        aliases.append({
            "name": effective.name,
            "body": effective.body,
            "file": effective.file,
            "line": effective.line,
            "definitions": len(defs),
            "commands": [c.name for c in effective.commands if c.name],
        })

    binds = []
    for key, defs in sorted(result.binds.items()):
        winner = max(defs, key=lambda d: d.order)
        binds.append({
            "key": winner.key,
            "body": winner.body,
            "file": winner.file,
            "line": winner.line,
            "comment": winner.comment,
            "count": len(defs),
            "identical": len({d.body for d in defs}) == 1,
            "all": [{"file": d.file, "line": d.line, "body": d.body} for d in defs],
        })

    overrides = []
    for name, defs in result.overridden_settings():
        overrides.append({
            "name": name,
            "effective": defs[-1].value,
            "effective_file": defs[-1].file,
            "sources": [
                {"file": d.file, "line": d.line, "value": d.value, "wins": d is defs[-1]}
                for d in defs
            ],
        })

    return {
        "ok": True,
        "root": str(result.root),
        "cfg_root": str(result.cfg_root),
        "entry_points": result.entry_points,
        "exec_chain": [{"file": f, "depth": d} for f, d in result.exec_chain],
        "files": files,
        "aliases": aliases,
        "binds": binds,
        "overrides": overrides,
        "counts": {
            "aliases": len(result.aliases),
            "binds": len(result.binds),
            "settings": len(result.settings),
        },
        "issues": [
            {"code": i.code, "severity": i.severity.value, "message": i.message,
             "detail": i.detail, "file": i.file, "line": i.line}
            for i in result.issues
        ],
    }


def _cfg_polish_apply(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """Write selected formatting changes, backing the files up first."""
    from . import cfgformat

    result = getattr(state, "cfg_scan", None)
    if result is None:
        return {"ok": False, "error": "scan a folder first"}

    wanted = set(body.get("files") or [])
    if not wanted:
        return {"ok": False, "error": "no files selected"}

    session = backup.BackupSession(note="cfg polish (web)")
    written, skipped = [], []
    for config in result.files.values():
        if config.relative not in wanted or not config.is_commands:
            continue
        text = config.path.read_bytes().decode(
            config.document.encoding, errors="replace")
        outcome = cfgformat.polish(text, config.relative)
        if not outcome.safe or not outcome.changed:
            skipped.append({"file": config.relative,
                            "reason": outcome.skipped_reason or "nothing to change"})
            continue
        session.add(config.path)
        cfglang.write_config_text(config.path, outcome.formatted, config.document.encoding)
        written.append(config.relative)

    backup.prune()
    return {"ok": True, "written": written, "skipped": skipped,
            "backup": None if session.empty else session.stamp}


def _cfg_rename_preview(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    from . import cfgedit

    result = getattr(state, "cfg_scan", None)
    if result is None:
        return {"ok": False, "error": "scan a folder first"}

    try:
        plan = cfgedit.plan_rename(
            result,
            str(body.get("old_name") or ""),
            str(body.get("new_name") or ""),
            include_family=bool(body.get("include_family", True)),
        )
    except cfgedit.EditError as exc:
        return {"ok": False, "error": str(exc)}

    def pack(edits):
        return [
            {"file": e.file, "line": e.line, "before": e.before, "after": e.after,
             "kind": e.kind, "description": e.description}
            for e in edits
        ]

    return {
        "ok": True,
        "old_name": plan.old_name,
        "new_name": plan.new_name,
        "family": [{"from": a, "to": b} for a, b in plan.family],
        "edits": pack(plan.edits),
        "wording": pack(plan.wording_edits),
        "issues": [
            {"code": i.code, "severity": i.severity.value,
             "message": i.message, "detail": i.detail}
            for i in plan.issues
        ],
        "blocked": any(i.severity.value == "error" for i in plan.issues),
        "summary": plan.summary(),
    }


def _cfg_rename_apply(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    from . import cfgedit

    result = getattr(state, "cfg_scan", None)
    if result is None:
        return {"ok": False, "error": "scan a folder first"}

    try:
        plan = cfgedit.plan_rename(
            result,
            str(body.get("old_name") or ""),
            str(body.get("new_name") or ""),
            include_family=bool(body.get("include_family", True)),
        )
    except cfgedit.EditError as exc:
        return {"ok": False, "error": str(exc)}

    if any(i.severity.value == "error" for i in plan.issues):
        return {"ok": False, "error": "the rename has blocking problems; resolve them first"}

    edits = list(plan.edits)
    if body.get("include_wording"):
        for edit in plan.wording_edits:
            edit.selected = True
        edits += plan.wording_edits

    try:
        updates = cfgedit.apply_edits(result, edits)
    except cfgedit.EditError as exc:
        return {"ok": False, "error": str(exc)}

    session = backup.BackupSession(note=f"cfg rename {plan.old_name} -> {plan.new_name}")
    written = []
    for relative, text in updates.items():
        config = next(c for c in result.files.values() if c.relative == relative)
        session.add(config.path)
        cfglang.write_config_text(config.path, text, config.document.encoding)
        written.append(relative)

    backup.prune()
    return {"ok": True, "written": written,
            "backup": None if session.empty else session.stamp}


def _cfg_behaviour_preview(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    from . import cfgedit

    result = getattr(state, "cfg_scan", None)
    if result is None:
        return {"ok": False, "error": "scan a folder first"}

    try:
        change = cfgedit.plan_behaviour_change(
            result, str(body.get("alias") or ""), str(body.get("body") or "")
        )
    except cfgedit.EditError as exc:
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "alias": change.alias,
        "file": change.file,
        "line": change.line,
        "before_body": change.before_body,
        "after_body": change.after_body,
        "before_commands": change.before_commands,
        "after_commands": change.after_commands,
        "added": change.added,
        "removed": change.removed,
        "explanation": change.explain(),
        "valid": change.valid,
        "issues": [
            {"code": i.code, "severity": i.severity.value,
             "message": i.message, "detail": i.detail}
            for i in change.issues
        ],
    }


def _environment(_state: State, _body: Dict[str, Any]) -> Dict[str, Any]:
    from . import desktop

    return {"ok": True, **desktop.describe_environment()}


def _cfg_suggest(_state: State, _body: Dict[str, Any]) -> Dict[str, Any]:
    """Folders worth scanning, so the common case needs no typing at all."""
    from . import cfgscan
    from .cli import load_prefs

    remembered = load_prefs().get("ui", {}).get("cfg_folder")
    extra = [Path(remembered)] if remembered else []
    found = cfgscan.suggest_folders(extra)
    return {"ok": True, "suggestions": [
        {"path": f.path, "label": f.label, "files": f.file_count,
         "reason": f.reason, "is_cfg_root": f.is_cfg_root}
        for f in found
    ], "remembered": remembered}


def _cfg_browse(_state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """Open the native folder picker."""
    from . import cfgscan

    chosen = cfgscan.browse_for_folder(str(body.get("initial") or ""))
    if not chosen:
        return {"ok": True, "cancelled": True, "path": None}
    return {"ok": True, "cancelled": False, "path": chosen,
            "info": cfgscan.describe_folder(Path(chosen))}


def _cfg_check(_state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    from . import cfgscan

    folder = str(body.get("folder") or "").strip()
    if not folder:
        return {"ok": True, "info": {"exists": False, "is_dir": False,
                                     "file_count": 0, "message": ""}}
    return {"ok": True, "info": cfgscan.describe_folder(Path(folder))}


def _cfg_settings(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """The CS2-style settings view, merging config convars and cs2_video.txt."""
    from . import cfgscan

    result = getattr(state, "cfg_scan", None)
    if result is None:
        return {"ok": False, "error": "scan a configuration folder first"}

    video_values: Dict[str, str] = {}
    video_path = None
    try:
        state.refresh()
        user = state.user_for(body.get("account"))
        video_values = steam.read_video_cfg(user)
        video_path = str(user.video_cfg)
    except steam.SteamError:
        pass

    views, sections = cfgscan.settings_view(result, video_values)
    return {
        "ok": True,
        "sections": sections,
        "video_path": video_path,
        "default_target": cfgscan.default_target(result),
        "settings": [
            {
                "name": v.name, "value": v.value, "label": v.label,
                "group": v.category,
                "subgroup": v.spec.get("subgroup"),
                "control": v.control,
                "source": v.spec.get("source", "cfg"),
                "file": v.file, "line": v.line, "comment": v.comment,
                "spec": v.spec, "sources": v.sources,
                "overridden": v.overridden, "profile_only": v.profile_only,
                "ambiguous": v.ambiguous, "unset": v.unset, "note": v.note,
            }
            for v in views
        ],
    }


def _cfg_settings_apply(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """Write changed settings back to whichever file each one lives in."""
    from . import cfgscan

    result = getattr(state, "cfg_scan", None)
    if result is None:
        return {"ok": False, "error": "scan a configuration folder first"}

    changes = body.get("changes") or []
    if not changes:
        return {"ok": False, "error": "nothing to change"}

    cfg_changes = [c for c in changes if c.get("source") != "video"]
    video_changes = {str(c["name"]): c["value"] for c in changes if c.get("source") == "video"}

    session = backup.BackupSession(note="cs2 settings (web)")
    applied, files = [], []

    # Config convars: build every file's new text first, so one bad entry
    # cannot leave the collection half written.
    pending: Dict[str, str] = {}
    try:
        for change in cfg_changes:
            name = str(change.get("name") or "")
            value = str(change.get("value") or "")
            # Decide from the scan, not from what the page believed. A page
            # holding a stale view would otherwise append a second copy of a
            # setting that already exists, and every later edit would stack
            # another line instead of changing the value.
            if result.settings.get(name.lower()):
                target, text = cfgscan.write_setting(
                    result, name, value, change.get("file"), change.get("line"))
            else:
                target, text = cfgscan.append_setting(result, name, value)
            if target in pending:
                # A second change to the same file has to build on the first,
                # so flush what we have. Back it up first: after this write the
                # file on disk is no longer the original, and the session
                # records each path only once.
                config = next(c for c in result.files.values() if c.relative == target)
                session.add(config.path)
                cfglang.write_config_text(config.path, pending[target], config.document.encoding)
                result = cfgscan.scan(result.root, result.cfg_root)
                state.cfg_scan = result
                if result.settings.get(name.lower()):
                    target, text = cfgscan.write_setting(result, name, value)
                else:
                    target, text = cfgscan.append_setting(result, name, value)
            pending[target] = text
            applied.append({"name": name, "value": value, "file": target})
    except (ValueError, StopIteration) as exc:
        return {"ok": False, "error": str(exc)}

    for relative, text in pending.items():
        config = next(c for c in result.files.values() if c.relative == relative)
        session.add(config.path)
        cfglang.write_config_text(config.path, text, config.document.encoding)
        files.append(relative)

    # Video settings live in Steam's userdata, not the config folder.
    if video_changes:
        try:
            state.refresh()
            user = state.user_for(body.get("account"))
            diff = steam.write_video_cfg(
                user, {k: int(v) if str(v).lstrip("-").isdigit() else v
                       for k, v in video_changes.items()}, session)
            for key in diff:
                applied.append({"name": key, "value": str(video_changes[key]),
                                "file": "cs2_video.txt"})
            if diff:
                files.append("cs2_video.txt")
        except steam.SteamError as exc:
            return {"ok": False, "error": f"video settings: {exc}"}

    # Re-scan so the next request sees what was just written. Without this a
    # newly added setting still looks unset and gets appended all over again.
    if files:
        state.cfg_scan = cfgscan.scan(result.root, result.cfg_root)

    backup.prune()
    return {"ok": True, "applied": applied, "files": sorted(set(files)),
            "backup": None if session.empty else session.stamp}


def _rescan(state: State):
    """Re-read the collection from disk, or None if none has been chosen.

    The views below are meant to show what is on disk right now, so they read
    it rather than trusting what was in memory from an earlier request.
    """
    from . import cfgscan

    held = getattr(state, "cfg_scan", None)
    if held is None:
        return None
    try:
        state.cfg_scan = cfgscan.scan(held.root, held.cfg_root)
    except OSError:
        return held          # the folder went away; the old view beats an error
    return state.cfg_scan


def _cfg_tree(state: State, _body: Dict[str, Any]) -> Dict[str, Any]:
    """The scanned folder as a tree, with what the scanner learned per file.

    Read-only. The scan already knows the load order, which files are reachable
    at startup, and where the problems are, so the browser can show that rather
    than a plain directory listing.
    """
    from . import cfgscan

    result = _rescan(state)
    if result is None:
        return {"ok": False, "error": "scan a configuration folder first"}

    startup = cfgscan.startup_chain(result)
    order = {name: i for i, (name, _depth) in enumerate(result.exec_chain)}
    errors: Dict[str, int] = {}
    warnings: Dict[str, int] = {}
    for issue in result.issues:
        bucket = errors if issue.severity.name == "ERROR" else warnings
        bucket[issue.file] = bucket.get(issue.file, 0) + 1

    files = []
    for config in result.files.values():
        rel = config.relative
        try:
            size = config.path.stat().st_size
        except OSError:
            size = 0
        files.append({
            "path": rel,
            "name": config.name,
            "dir": rel.rsplit("/", 1)[0] if "/" in rel else "",
            "lines": len(config.document.lines),
            "bytes": size,
            "commands": config.is_commands,
            "generated_by": config.generated_by,
            "role": config.role,
            "entry": rel in result.entry_points,
            "startup": rel in startup,
            "order": order.get(rel),
            "errors": errors.get(rel, 0),
            "warnings": warnings.get(rel, 0),
            "settings": sum(1 for defs in result.settings.values()
                            for d in defs if d.file == rel),
            "aliases": sum(1 for defs in result.aliases.values()
                           for d in defs if d.file == rel),
            "binds": sum(1 for defs in result.binds.values()
                         for d in defs if d.file == rel),
        })
    files.sort(key=lambda f: (f["dir"], f["name"].lower()))

    return {
        "root": str(result.root),
        "cfg_root": str(result.cfg_root),
        "files": files,
        "entry_points": result.entry_points,
        "totals": {
            "files": len(files),
            "lines": sum(f["lines"] for f in files),
            "bytes": sum(f["bytes"] for f in files),
            "errors": sum(errors.values()),
            "warnings": sum(warnings.values()),
        },
    }


def _cfg_file(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """One file's text, for viewing. Never writes, and never leaves the scan.

    The path has to name a file the scan already found; anything else is
    refused rather than read, so this cannot be talked into opening something
    outside the folder that was chosen.
    """
    result = _rescan(state)
    if result is None:
        return {"ok": False, "error": "scan a configuration folder first"}

    wanted = str(body.get("path") or "")
    config = next((c for c in result.files.values() if c.relative == wanted), None)
    if config is None:
        return {"ok": False, "error": f"{wanted} is not part of the scan"}

    text = config.path.read_bytes().decode(config.document.encoding, errors="replace")
    marks: Dict[str, list] = {}
    for issue in result.issues:
        if issue.file == wanted:
            marks.setdefault(str(issue.line), []).append({
                "severity": issue.severity.name.lower(),
                "message": issue.message,
                "code": issue.code,
            })

    return {
        "path": wanted,
        "name": config.name,
        "text": text,
        "encoding": config.document.encoding,
        "newline": "CRLF" if config.document.newline == "\r\n" else "LF",
        "commands": config.is_commands,
        "generated_by": config.generated_by,
        "issues": marks,
    }


def _cfg_plugins(state: State, _body: Dict[str, Any]) -> Dict[str, Any]:
    """The self-contained features the collection defines. Read-only."""
    from . import plugins

    result = _rescan(state)
    if result is None:
        return {"ok": False, "error": "scan a configuration folder first"}

    found = plugins.find(result)
    payload = plugins.as_dict(found)
    payload["empty_sections"] = [
        {"file": f, "name": n, "line": ln}
        for f, n, ln in getattr(plugins.find, "empty_sections", [])
    ]
    return payload


def _unclaimed_keys(result, found) -> list:
    """The script's keys that nothing else in the collection also binds.

    A key some other line already binds is left alone. Adding ours after it
    would settle which of the two wins by whichever happens to be read last,
    and quietly overriding a bind the user wrote is worse than leaving the key
    as they had it.
    """
    free = []
    for binding in found.bound_to:
        others = [b for b in result.binds.get(binding, [])
                  if (b.body or "").strip().strip(chr(34)).lower()
                  != (found.entry or "").lower()]
        if not others:
            free.append(binding)
    return free


def _cfg_plugin_toggle(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """Switch one feature block off or back on, by commenting it out.

    The block is located by re-reading the collection rather than trusting the
    line numbers the page happens to be holding: the file may have been edited
    since it loaded, and commenting out the wrong span would be silent damage.
    """
    from . import cfgscan, defaults, plugins

    result = getattr(state, "cfg_scan", None)
    if result is None:
        return {"ok": False, "error": "scan a configuration folder first"}

    wanted = str(body.get("id") or "")
    enable = bool(body.get("enable"))

    found = next((p for p in plugins.find(result)
                  if f"{p.file}:{p.line}" == wanted), None)
    if found is None:
        return {"ok": False, "error": "that script is no longer where it was; re-read the list"}
    if found.enabled == enable:
        return {"path": found.file, "name": found.name,
                "enabled": found.enabled, "changed": False}

    config = next((c for c in result.files.values() if c.relative == found.file), None)
    if config is None:
        return {"ok": False, "error": f"{found.file} is not part of the scan"}

    original = config.path.read_bytes().decode(config.document.encoding, errors="replace")
    # Normalised to plain newlines for the edit, then given the file's own
    # ending back below -- the same round trip the editor uses.
    flat = cfglang.restore_newlines(original, chr(10), False)
    updated = plugins.set_enabled(flat, found.line, found.end_line, enable)

    # The keys this script was holding, and what CS2 does with them itself.
    restored, dropped = [], []
    if enable:
        updated, dropped = plugins.drop_stock(updated, found.bound_to)
    else:
        free = _unclaimed_keys(result, found)
        if free:
            table = defaults.load(state.cs2_install)
            updated, restored = plugins.restore_stock(
                updated, found.end_line, free, table)

    updated = cfglang.restore_newlines(
        updated, config.document.newline, config.document.trailing_newline)

    session = backup.BackupSession(
        note=f"{'enabled' if enable else 'disabled'} {found.name}")
    session.add(config.path)
    cfglang.write_config_text(config.path, updated, config.document.encoding)
    backup.prune()

    state.cfg_scan = cfgscan.scan(result.root, result.cfg_root)
    return {
        "path": found.file, "name": found.name, "enabled": enable,
        "restored": restored, "dropped": len(dropped),
        "changed": True, "backup": session.stamp,
        "lines": found.end_line - found.line + 1,
    }


def _cfg_keys(state: State, _body: Dict[str, Any]) -> Dict[str, Any]:
    """What every key in the collection is bound to, ready to draw.

    Where a key runs one of the collection's own features, that is worth
    saying: it is the difference between "this key types something" and "this
    key is one of your tools".
    """
    from . import keys, plugins

    result = _rescan(state)
    if result is None:
        return {"ok": False, "error": "scan a configuration folder first"}

    features = {}
    for feature in plugins.find(result):
        if feature.entry:
            features.setdefault(feature.entry.lower(), feature)

    bound = {}
    for key, entries in result.binds.items():
        # The last bind to load is the one the engine keeps.
        winner = max(entries, key=lambda b: b.order)
        command = (winner.body or "").strip().strip('"')
        feature = features.get(command.lower())
        bound[key] = {
            "key": key,
            "label": keys.label(key),
            "command": command,
            "file": winner.file,
            "line": winner.line,
            "comment": (winner.comment or "").strip(),
            "shadowed": len(entries) - 1,
            "script": feature.name if feature else None,
            "script_id": f"{feature.file}:{feature.line}" if feature else None,
            "kind": feature.kind if feature else None,
            "enabled": feature.enabled if feature else True,
        }

    return {
        "bound": bound,
        "count": len(bound),
        "scripted": sum(1 for b in bound.values() if b["script"]),
    }


def _cfg_plugin_bind(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """Move a script onto a different key.

    The existing bind is rewritten where there is one, so the comment beside it
    survives; otherwise a new line is added next to the others. A key that is
    already doing something else is refused unless the caller insists, because
    silently stealing a key is how a config ends up with a dead feature nobody
    can find.
    """
    from . import cfgscan, keys, plugins

    result = _rescan(state)
    if result is None:
        return {"ok": False, "error": "scan a configuration folder first"}

    wanted = str(body.get("id") or "")
    # The page reports what the browser saw; the config wants a scancode.
    binding = str(body.get("binding") or "").strip()
    if not binding and body.get("code"):
        binding = keys.from_code(str(body["code"])) or ""
        if not binding:
            return {"ok": False,
                    "error": str(body["code"]) + " is not a key this tool can write"}
    if not binding:
        return {"ok": False, "error": "no key given"}

    found = next((p for p in plugins.find(result)
                  if f"{p.file}:{p.line}" == wanted), None)
    if found is None:
        return {"ok": False, "error": "that script is no longer where it was"}
    if not found.entry:
        return {"ok": False, "error": f"{found.name} has nothing to bind"}

    # Who has this key now?
    taken = []
    for existing in result.binds.get(binding, []):
        target = (existing.body or "").strip().strip('"')
        if target.lower() != found.entry.lower():
            taken.append({"file": existing.file, "line": existing.line,
                          "runs": target})
    if taken and not body.get("force"):
        return {"ok": False, "taken": taken, "needs_confirm": True,
                "error": f"{keys.label(binding)} already runs "
                         f"{taken[-1]['runs']}"}

    # Where the script is bound now, if anywhere.
    current = [b for entries in result.binds.values() for b in entries
               if (b.body or "").strip().strip('"').lower() == found.entry.lower()]

    target_file = None
    if current:
        target_file = current[0].file
    else:
        # Put a new bind beside the others rather than at the end of a file.
        counts: Dict[str, int] = {}
        for entries in result.binds.values():
            for b in entries:
                counts[b.file] = counts.get(b.file, 0) + 1
        if not counts:
            return {"ok": False, "error": "no file in the scan holds any binds"}
        target_file = max(counts.items(), key=lambda kv: kv[1])[0]

    config = next((c for c in result.files.values() if c.relative == target_file), None)
    if config is None:
        return {"ok": False, "error": f"{target_file} is not part of the scan"}

    original = config.path.read_bytes().decode(config.document.encoding, errors="replace")
    flat = cfglang.restore_newlines(original, chr(10), False)
    lines = flat.split(chr(10))

    changed = None
    for b in current:
        if b.file != target_file:
            continue
        index = b.line - 1
        if 0 <= index < len(lines) and "bind" in lines[index]:
            lines[index] = lines[index].replace(f'"{b.key}"', f'"{binding}"', 1)
            changed = f"moved from {keys.label(b.key)}"
            break

    if changed is None:
        anchor = next((i for i, l in enumerate(lines)
                       if l.lstrip().startswith("bind ")), None)
        if anchor is None:
            return {"ok": False, "error": f"{target_file} has no binds to sit beside"}
        pad = lines[anchor][:len(lines[anchor]) - len(lines[anchor].lstrip())]
        lines.insert(anchor, f'{pad}bind "{binding}" "{found.entry}"'.ljust(60) +
                     f"// {found.name.upper()}")
        changed = "added"

    session = backup.BackupSession(note=f"bind {found.name} to {keys.label(binding)}")
    session.add(config.path)
    body_text = cfglang.restore_newlines(chr(10).join(lines), config.document.newline,
                                         config.document.trailing_newline)
    cfglang.write_config_text(config.path, body_text, config.document.encoding)
    backup.prune()
    state.cfg_scan = cfgscan.scan(result.root, result.cfg_root)

    return {"name": found.name, "entry": found.entry, "binding": binding,
            "label": keys.label(binding), "file": target_file,
            "action": changed, "backup": session.stamp}


def _cfg_save(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """Write an edited config file back, after backing the original up.

    The path has to be one the scan already found, so this cannot be pointed at
    anything outside the chosen folder. The file's own line ending and encoding
    are put back before writing: the browser hands over text with plain
    newlines, and writing those into a CRLF file would change every line in it.

    The new text is parsed first and its problems reported, but a file that
    still has problems is written anyway when asked -- it is the user's config,
    and refusing to save half-finished work would be worse than saying what is
    wrong with it.
    """
    from . import cfgscan

    result = getattr(state, "cfg_scan", None)
    if result is None:
        return {"ok": False, "error": "scan a configuration folder first"}

    wanted = str(body.get("path") or "")
    config = next((c for c in result.files.values() if c.relative == wanted), None)
    if config is None:
        return {"ok": False, "error": f"{wanted} is not part of the scan"}
    if "text" not in body:
        return {"ok": False, "error": "no text to save"}

    text = str(body["text"])
    newline = config.document.newline
    # The browser hands back plain newlines; cfglang puts the file's own
    # ending back, because writing LF into a CRLF file would rewrite every
    # line in it and show up as a change to the whole file.
    body_text = cfglang.restore_newlines(
        text, newline, config.document.trailing_newline)

    before = config.path.read_bytes()
    if body_text.encode(config.document.encoding, errors="replace") == before:
        return {"path": wanted, "written": False, "note": "nothing changed"}

    # Problems the tokeniser finds are attached to the line they occur on,
    # not to the document, so the document's own list is nearly always empty --
    # reading only that missed every unterminated quote.
    parsed = cfglang.parse(body_text, wanted)
    found = list(parsed.issues)
    for line in parsed.lines:
        found.extend(line.issues)
    issues = [
        {"line": i.line, "severity": i.severity.name.lower(),
         "message": i.message, "code": i.code}
        for i in sorted(found, key=lambda i: i.line)
    ]
    errors = sum(1 for i in found if i.severity.name == "ERROR")
    if errors and not body.get("force"):
        return {"ok": False, "needs_confirm": True, "errors": errors,
                "issues": issues,
                "error": f"that would leave {errors} syntax error(s) in the file"}

    session = backup.BackupSession(note=f"edited {wanted}")
    session.add(config.path)
    cfglang.write_config_text(config.path, body_text, config.document.encoding)
    backup.prune()

    state.cfg_scan = cfgscan.scan(result.root, result.cfg_root)
    return {
        "path": wanted,
        "written": True,
        "backup": session.stamp,
        "bytes": len(body_text.encode(config.document.encoding, errors="replace")),
        "issues": issues,
        "errors": errors,
    }


def _ingame_watcher(state: State):
    """The background watcher for the account in use, started once.

    Nothing polls CS2 while it runs -- the game only writes these files as it
    shuts down, so the watcher waits for the timestamps to move and then reads.
    """
    from . import gamewatch

    if state.ingame is not None:
        return state.ingame
    state.refresh()
    try:
        user = state.user_for(None)
    except steam.SteamError:
        return None
    folder = user.video_cfg.parent
    if not folder.is_dir():
        return None
    watcher = gamewatch.Watcher(folder, user.account_id)
    watcher.start()
    state.ingame = watcher
    return watcher


def _ingame(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """What has changed in CS2's own settings since we last looked.

    CS2 writes these files when it shuts down, so this is meaningful after a
    session rather than during one. Reads only; the baseline it compares
    against lives in this application's data directory.
    """
    from . import gamewatch

    state.refresh()
    user = state.user_for(body.get("account"))
    folder = user.video_cfg.parent
    if not folder.is_dir():
        return {"ok": False, "error": f"no CS2 settings folder for {user.label}"}

    watcher = _ingame_watcher(state)
    found = watcher.pending if watcher else None
    if found and not body.get("recheck"):
        found = dict(found)
        found["account"] = user.account_id
        found["auto"] = True
        found["running"] = window.find_game_window("cs2.exe") is not None
        return found

    now = gamewatch.take(folder)
    baseline = gamewatch.load_baseline(user.account_id)
    if baseline is None:
        # Nothing to compare with yet. Record where things stand so the next
        # session has a starting point, and say so rather than inventing a diff.
        gamewatch.save_baseline(user.account_id, now)
        return {"account": user.account_id, "first_run": True, "count": 0,
                "sources": {}, "missing": now.missing,
                "note": "Recorded how your settings look now. Changes you make "
                        "in-game from here on will be listed after each session."}

    changes = gamewatch.compare(baseline, now,
                                include_machine=bool(body.get("include_machine")))
    payload = gamewatch.as_dict(changes, baseline, now)
    payload["account"] = user.account_id
    payload["running"] = window.find_game_window("cs2.exe") is not None
    return payload


def _ingame_ack(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """Accept the current settings as the new starting point."""
    from . import gamewatch

    state.refresh()
    user = state.user_for(body.get("account"))
    folder = user.video_cfg.parent
    if not folder.is_dir():
        return {"ok": False, "error": f"no CS2 settings folder for {user.label}"}
    gamewatch.save_baseline(user.account_id, gamewatch.take(folder))
    watcher = _ingame_watcher(state)
    if watcher:
        watcher.clear()
    return {"account": user.account_id, "count": 0, "sources": {},
            "note": "Marked as seen."}


def _play_fix(state: State, _body: Dict[str, Any]) -> Dict[str, Any]:
    """Put the stretch and resolution back while the game is running.

    Windows takes the desktop mode back on its own -- it is set temporarily so
    a crash cannot strand the desktop -- and when it does, the game keeps its
    window size but stops filling the screen. This re-asserts only what has
    drifted, so pressing it when nothing is wrong costs nothing and does not
    disturb the game.
    """
    from . import launcher, window

    found = window.find_game_window(launcher.GAME_PROCESS)
    if found is None:
        return {"ok": False, "error": "CS2 is not running, so there is nothing to fix"}

    # The size the running session was launched at, or failing that whatever
    # the game's own video settings ask for.
    watcher = state.launch
    if watcher is not None and getattr(watcher, "width", 0):
        width, height, refresh = watcher.width, watcher.height, watcher.refresh
    else:
        state.refresh()
        user = state.user_for(None)
        video = steam.read_video_cfg(user) if user else {}
        width = int(video.get("setting.defaultres") or 0)
        height = int(video.get("setting.defaultresheight") or 0)
        refresh = 0
        if not width or not height:
            return {"ok": False,
                    "error": "could not work out the resolution to restore; "
                             "launch through Play once so it is known"}

    before = window.check_stretch(width, height, launcher.GAME_PROCESS)
    result = window.repair_stretch(width, height, launcher.GAME_PROCESS, refresh)
    return {
        "target": f"{width}x{height}",
        "repaired": result["repaired"],
        "actions": result["actions"],
        "was_ok": bool(before["mode_ok"] and before["window_ok"]),
    }


def _gpu(_state: State, _body: Dict[str, Any]) -> Dict[str, Any]:
    """Driver profile and per-monitor display modes. Reads only."""
    from . import displays, nvidia

    return {"nvidia": nvidia.as_dict(nvidia.probe(("cs2.exe", "csgo.exe"))),
            "displays": displays.summary()}


def _display_refresh(_state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """Move one screen to another refresh rate it already offers.

    A display mode, not a driver setting, so it works on any GPU. Without
    ``apply`` the mode is only tested, and the rate in use beforehand comes
    back either way so the page can offer to undo it.
    """
    from . import displays

    device = str(body.get("device") or "")
    try:
        refresh = int(body.get("refresh"))
    except (TypeError, ValueError):
        raise ValueError("refresh must be a whole number of Hz")
    if not device:
        raise ValueError("which display?")
    return displays.set_refresh(device, refresh, apply=bool(body.get("apply")),
                                force=bool(body.get("force")))


def _backups(_state: State, _body: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "sets": [
        {"stamp": s.stamp, "when": s.when, "note": s.note, "files": s.originals}
        for s in backup.list_sets()
    ]}


def _updater(state: State):
    """The update checker, started the first time anything asks for it.

    Starting it lazily rather than at import keeps the command line free of a
    background thread it has no use for, and means a user who never opens the
    window never talks to GitHub.
    """
    from . import updates

    if state.updates is not None:
        return state.updates

    from .cli import load_prefs

    ui = load_prefs().get("ui", {})
    checker = updates.Checker(
        auto_download=bool(ui.get("update_auto_download")),
        skip=str(ui.get("update_skip") or ""),
    )
    checker.start()
    state.updates = checker
    return checker


def _update_status(state: State, _body: Dict[str, Any]) -> Dict[str, Any]:
    """Where the update stands. Polled by the page; does not itself hit GitHub."""
    return {"ok": True, **_updater(state).summary()}


def _update_check(state: State, _body: Dict[str, Any]) -> Dict[str, Any]:
    """Ask GitHub now rather than waiting for the timer."""
    checker = _updater(state)
    checker.check_once()
    return {"ok": True, **checker.summary()}


def _update_download(state: State, _body: Dict[str, Any]) -> Dict[str, Any]:
    """Start fetching the update in the background.

    Returns immediately: the download runs on the checker's own thread and the
    page follows it through the status endpoint.
    """
    from . import updates

    checker = _updater(state)
    if checker.summary()["state"] == updates.DOWNLOADING:
        return {"ok": True, **checker.summary()}
    checker.want_download()
    threading.Thread(target=checker.download_once, daemon=True,
                     name="cs2cfg-update-download").start()
    return {"ok": True, **checker.summary()}


def _update_install(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """Put the downloaded version in place and restart.

    Only ever reached because someone pressed the button. The swap itself is
    handed to a script that waits for this process to exit, so the reply goes
    out first and the application closes a moment later.
    """
    from . import updates

    checker = _updater(state)
    summary = checker.summary()
    if summary["state"] != updates.READY:
        return {"ok": False, "error": "there is nothing downloaded to install"}

    release = updates.Release(version=str((summary["latest"] or {}).get("version", "")))
    try:
        script = updates.install(release, relaunch=bool(body.get("relaunch", True)))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "installing": True, "script": str(script),
            "version": release.version}


def _quit(_state: State, _body: Dict[str, Any]) -> Dict[str, Any]:
    """End the process, a moment after this reply has gone out.

    Used by the updater: the swap script cannot replace an executable that is
    still running, so it waits for this pid to vanish. The delay is only long
    enough for the response to reach the page.
    """
    import os

    def bye() -> None:
        os._exit(0)

    threading.Timer(0.6, bye).start()
    return {"ok": True, "closing": True}


def _update_settings(state: State, body: Dict[str, Any]) -> Dict[str, Any]:
    """Change how the updater behaves, and remember it.

    "auto_download" only ever governs fetching. Installing stays a decision the
    user makes each time, so there is deliberately no setting for it.
    """
    from .cli import load_prefs, save_prefs

    checker = _updater(state)
    prefs = load_prefs()
    prefs.setdefault("ui", {})

    if "auto_download" in body:
        wanted = bool(body["auto_download"])
        checker.set_auto_download(wanted)
        prefs["ui"]["update_auto_download"] = wanted
    if body.get("skip"):
        version = str(body["skip"])
        checker.skip_version(version)
        prefs["ui"]["update_skip"] = version
    if body.get("unskip"):
        checker.skip_version("")
        prefs["ui"]["update_skip"] = ""

    save_prefs(prefs)
    return {"ok": True, **checker.summary()}


def make_handler(state: State):
    routes_get: Dict[str, Callable[[], Dict[str, Any]]] = {}
    routes_post: Dict[str, Callable[[State, Dict[str, Any]], Dict[str, Any]]] = {
        "/api/plan": _plan_payload,
        "/api/apply": _apply,
        "/api/revert": _revert,
        "/api/backups": _backups,
        "/api/play": _play,
        "/api/play/stop": _play_stop,
        "/api/play/fix": _play_fix,
        "/api/ingame": _ingame,
        "/api/ingame/ack": _ingame_ack,
        "/api/prefs": _save_prefs,
        "/api/cfg/scan": _cfg_scan,
        "/api/cfg/tree": _cfg_tree,
        "/api/cfg/file": _cfg_file,
        "/api/cfg/save": _cfg_save,
        "/api/cfg/plugins": _cfg_plugins,
        "/api/cfg/plugin/toggle": _cfg_plugin_toggle,
        "/api/cfg/plugin/bind": _cfg_plugin_bind,
        "/api/cfg/keys": _cfg_keys,
        "/api/cfg/settings": _cfg_settings,
        "/api/cfg/settings/apply": _cfg_settings_apply,
        "/api/cfg/suggest": _cfg_suggest,
        "/api/cfg/browse": _cfg_browse,
        "/api/cfg/check": _cfg_check,
        "/api/cfg/polish": _cfg_polish_apply,
        "/api/cfg/rename": _cfg_rename_preview,
        "/api/cfg/rename/apply": _cfg_rename_apply,
        "/api/cfg/behaviour": _cfg_behaviour_preview,
        "/api/gpu": _gpu,
        "/api/display/refresh": _display_refresh,
        "/api/env": _environment,
        "/api/update": _update_status,
        "/api/update/check": _update_check,
        "/api/update/download": _update_download,
        "/api/update/install": _update_install,
        "/api/update/settings": _update_settings,
        "/api/quit": _quit,
        "/api/history": _history,
    }

    class Handler(BaseHTTPRequestHandler):
        server_version = f"cs2cfg/{__version__}"
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:  # quiet; the CLI prints its own line
            pass

        # -- helpers --------------------------------------------------------
        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            return host in ALLOWED_HOSTS

        def _send_json(self, payload: Dict[str, Any], code: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path: Path) -> None:
            if not path.is_file():
                self._send_json({"error": "not found"}, 404)
                return
            data = path.read_bytes()
            if path.suffix == ".html":
                # The token is injected rather than fetched, so it never exists
                # at a URL another page could read.
                data = data.replace(b"__CS2CFG_TOKEN__", state.token.encode())
                data = data.replace(b"__CS2CFG_VERSION__", __version__.encode())
            kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", f"{kind}; charset=utf-8" if "text" in kind or "javascript" in kind else kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        # -- verbs ----------------------------------------------------------
        def do_GET(self) -> None:
            if not self._host_ok():
                self._send_json({"error": "host not allowed"}, 403)
                return

            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send_file(WEB_ROOT / "index.html")
                return
            if path == "/api/play/status":
                # Deliberately outside state.lock: the page polls this every
                # second and must never block behind a slow operation.
                if state.launch is None:
                    self._send_json({"ok": True, "phase": "idle", "active": False, "lines": []})
                else:
                    self._send_json({"ok": True, **state.launch.snapshot()})
                return
            if path == "/api/monitor":
                # Read-only and cheap: CPU and memory come from ctypes calls,
                # and the GPU query is cached, so this is safe to poll.
                from . import monitor

                payload = {"ok": True, **monitor.shared().sample()}
                watcher = _ingame_watcher(state)
                if watcher is not None:
                    payload["ingame"] = watcher.summary()
                self._send_json(payload)
                return
            if path == "/api/gpu":
                from . import displays, nvidia

                self._send_json({
                    "ok": True,
                    "nvidia": nvidia.as_dict(nvidia.probe(("cs2.exe", "csgo.exe"))),
                    "displays": displays.summary(),
                })
                return
            if path == "/api/prefs":
                from .cli import load_prefs

                self._send_json({"ok": True, "ui": load_prefs().get("ui", {})})
                return
            if path == "/api/scan":
                try:
                    with state.lock:
                        state.refresh(rescan="rescan=1" in self.path)
                        self._send_json({"ok": True, **_machine_payload(state.machine, state)})
                except (ProbeError, steam.SteamError) as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 500)
                return

            candidate = (WEB_ROOT / path.lstrip("/")).resolve()
            if WEB_ROOT.resolve() in candidate.parents:
                self._send_file(candidate)
                return
            self._send_json({"error": "not found"}, 404)

        def do_POST(self) -> None:
            # Drain the body first, before any check that might reject the
            # request. On a keep-alive connection an unread body stays in the
            # socket and gets parsed as the start of the next request, which
            # shows up as a bogus 501 on some later, innocent call.
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            raw = self.rfile.read(length) if length > 0 else b""

            if not self._host_ok():
                self._send_json({"error": "host not allowed"}, 403)
                return
            if self.headers.get("X-CS2CFG-Token") != state.token:
                self._send_json({"error": "bad or missing token"}, 403)
                return

            handler = routes_post.get(self.path.split("?", 1)[0])
            if handler is None:
                self._send_json({"error": "not found"}, 404)
                return

            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._send_json({"error": "body was not JSON"}, 400)
                return

            try:
                with state.lock:
                    self._send_json({"ok": True, **handler(state, body)})
            except (ProbeError, steam.SteamError, ValueError) as exc:
                self._send_json({"ok": False, "error": str(exc)}, 400)
            except Exception as exc:  # surfaced in the page, not swallowed
                self._send_json({
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "trace": traceback.format_exc(limit=6),
                }, 500)

    return Handler


def serve(port: int = 8765, cfg_folder: str = "mrwhiteer",
          cfg_name: str = "autoperf.vcfg") -> Tuple[ThreadingHTTPServer, State]:
    state = State(cfg_folder, cfg_name)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    server.daemon_threads = True
    return server, state
