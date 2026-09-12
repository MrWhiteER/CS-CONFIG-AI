"""Scan a config collection: structure, dependencies, diagnostics.
The analysis models what the engine actually does, which mostly means being
careful about two distinctions:

*Immediate versus deferred.* A command inside ``alias x "..."`` or
``bind k "..."`` is parsed when the file loads but runs later, if ever. Treating
those as immediate would make every alias body look like it executes at load,
and would turn ordinary state machines into infinite recursion.

*Stateful cycles versus recursion.* ``alias GM 1GM`` where ``1GM`` ends with
``alias GM 2GM`` is a toggle, not a loop: each invocation replaces the target
for the next one. Real recursion is an alias whose body reaches itself without
any intervening redefinition.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from . import cfglang
from .cfglang import (
    Command, Document, Issue, Severity, alias_definition, bind_definition,
    exec_target, family_of, looks_like_commands, normalise_exec_path,
    parse, parse_command_string, press_release_parts, state_suffix, tokenize_line,
)

CONFIG_SUFFIXES = (".cfg", ".vcfg")

# Commands that are real but are not settings and not user aliases. Used to
# avoid calling a normal engine command an unresolved reference.
KNOWN_ENGINE_PREFIXES = (
    "cl_", "sv_", "mp_", "r_", "m_", "snd_", "voice_", "ui_", "cash_", "ff_",
    "bot_", "ammo_", "spec_", "engine_", "fps_", "mat_", "net_", "host_",
    "cq_", "vgui_", "hud_", "gameinstructor_", "player_", "weapon_", "phys_",
    "demo_", "tv_", "func_", "ent_", "vprof_", "con_", "input_",
)

KNOWN_ENGINE_COMMANDS = {
    "alias", "bind", "unbind", "unbindall", "exec", "execifexists", "echo",
    "say", "say_team", "clear", "toggle", "incrementvar", "play", "map",
    "disconnect", "quit", "status", "connect", "retry", "give", "buy",
    "sellbackall", "autobuy", "rebuy", "cancelselect", "toggleconsole",
    "slot1", "slot2", "slot3", "slot4", "slot5", "slot6", "slot7", "slot8",
    "slot9", "slot10", "slot11", "slot12", "lastinv", "drop", "buymenu",
    "teammenu", "radio", "radio1", "radio2", "radio3", "messagemode",
    "messagemode2", "player_ping", "switchhands", "switchhandsleft",
    "switchhandsright", "noclip", "bot_place", "givecurrentammo", "developer",
    "volume", "sensitivity", "rate", "yaw", "pitch", "restart", "showt",
    "toggle_voice", "mp_pause_match", "mp_unpause_match", "mp_restartgame",
    "mp_warmup_end", "stopsound", "ent_fire", "sv_rethrow_last_grenade",
    "host_timescale", "quit_prompt", "callvote", "jointeam",
    # Bound by CS2 itself in cfg/user_keys_default.vcfg, so a config using one
    # of these is using a stock command, not a name that resolves to nothing.
    # Their absence here meant a perfectly ordinary bind was reported unknown.
    "invnext", "invprev", "buyammo1", "buyammo2", "show_loadout_toggle",
    "jpeg", "cs_quit_prompt",
}

# Engine actions that come in +press / -release pairs. Listed without the sign.
# These are built in, so seeing '+forward' with no alias defining it is normal,
# not a dangling reference.
KNOWN_ENGINE_ACTIONS = {
    "forward", "back", "left", "right", "moveleft", "moveright", "jump", "duck",
    "attack", "attack2", "attack3", "reload", "use", "speed", "sprint", "walk",
    "voicerecord", "showscores", "score", "scores", "lookatweapon", "spray_menu",
    "radialradio", "radialradio2", "radialradio3", "cl_show_team_equipment",
    "zoom", "strafe", "alt1", "alt2", "klook", "jlook", "graph", "break",
    "grenade1", "grenade2", "inspect", "lookspin",
}

# The convention this collection uses for its own aliases. A '!' name that
# resolves to nothing is almost certainly a typo; a '+' name that does not is
# more likely an engine command this tool has not been told about.
CUSTOM_PREFIXES = ("!",)
SIGNED_PREFIXES = ("+", "-")


@dataclass
class AliasDef:
    name: str
    body: str
    file: str
    line: int
    nested: bool = False          # defined inside another alias body
    order: int = 0                # position in the resolved execution order

    @property
    def commands(self) -> List[Command]:
        return parse_command_string(self.body, self.line)


@dataclass
class BindDef:
    key: str
    body: str
    file: str
    line: int
    comment: Optional[str] = None
    order: int = 0


@dataclass
class SettingDef:
    name: str
    value: str
    file: str
    line: int
    comment: Optional[str] = None
    order: int = 0


@dataclass
class ConfigFile:
    path: Path
    relative: str
    document: Document
    is_commands: bool
    generated_by: Optional[str] = None
    role: str = "config"
    exec_order: Optional[int] = None

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class ScanResult:
    root: Path
    cfg_root: Path
    files: Dict[str, ConfigFile] = field(default_factory=dict)
    entry_points: List[str] = field(default_factory=list)
    exec_chain: List[Tuple[str, int]] = field(default_factory=list)
    aliases: Dict[str, List[AliasDef]] = field(default_factory=dict)
    binds: Dict[str, List[BindDef]] = field(default_factory=dict)
    settings: Dict[str, List[SettingDef]] = field(default_factory=dict)
    issues: List[Issue] = field(default_factory=list)
    alias_calls: Dict[str, List[Tuple[str, int]]] = field(default_factory=dict)

    # -- convenience -------------------------------------------------------
    def issues_by_severity(self, severity: Severity) -> List[Issue]:
        return [i for i in self.issues if i.severity == severity]

    def effective_alias(self, name: str) -> Optional[AliasDef]:
        """The definition that wins at load time (the last one executed)."""
        defs = [d for d in self.aliases.get(name.lower(), []) if not d.nested]
        return max(defs, key=lambda d: d.order) if defs else None

    def effective_setting(self, name: str) -> Optional[SettingDef]:
        defs = self.settings.get(name.lower(), [])
        return max(defs, key=lambda d: d.order) if defs else None

    def overridden_settings(self) -> List[Tuple[str, List[SettingDef]]]:
        """Settings written more than once with differing values."""
        out = []
        for name, defs in sorted(self.settings.items()):
            ordered = sorted(defs, key=lambda d: d.order)
            if len(ordered) > 1 and len({d.value for d in ordered}) > 1:
                out.append((name, ordered))
        return out

    def duplicate_binds(self) -> List[Tuple[str, List[BindDef]]]:
        out = []
        for key, defs in sorted(self.binds.items()):
            if len(defs) > 1:
                out.append((key, sorted(defs, key=lambda d: d.order)))
        return out


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def find_cfg_root(folder: Path) -> Path:
    """Locate the directory ``exec`` paths resolve against.

    CS2 resolves exec targets from ``game/csgo/cfg``, not from the file doing
    the exec'ing. A collection is usually a subfolder of that, so walk up
    looking for a directory literally named ``cfg``.
    """
    folder = folder.resolve()
    for candidate in (folder, *folder.parents):
        if candidate.name.lower() == "cfg":
            return candidate
    return folder


def _detect_generator(text: str) -> Optional[str]:
    for line in text.splitlines()[:25]:
        stripped = line.strip()
        if not stripped.startswith("//"):
            continue
        upper = stripped.upper()
        if "GENERATED BY" in upper:
            return stripped.lstrip("/ ").strip()
    return None


def _role_for(relative: str, generated: Optional[str]) -> str:
    lower = relative.lower()
    if generated:
        return "generated"
    if "autoexec" in lower:
        return "entry point"
    if "/lan/" in lower or lower.startswith("lan/"):
        return "profile"
    if "/tools/" in lower or lower.startswith("tools/"):
        return "tools"
    if "mainsettings" in lower:
        return "settings"
    return "config"


def discover(folder: Path, cfg_root: Optional[Path] = None) -> Dict[str, ConfigFile]:
    """Read every config file under ``folder``, recursively."""
    folder = Path(folder).resolve()
    root = cfg_root or find_cfg_root(folder)
    files: Dict[str, ConfigFile] = {}

    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in CONFIG_SUFFIXES:
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue

        encoding = "utf-8"
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            # Configs in the wild are sometimes written by editors that default
            # to the system codepage. Keep the bytes readable rather than
            # dropping the file.
            encoding = "cp1252"
            text = raw.decode("cp1252", errors="replace")

        try:
            relative = str(path.relative_to(root)).replace("\\", "/")
        except ValueError:
            relative = path.name

        is_commands = looks_like_commands(text)
        document = parse(text, relative) if is_commands else Document(path=relative)
        document.encoding = encoding
        generated = _detect_generator(text)

        files[normalise_exec_path(relative)] = ConfigFile(
            path=path,
            relative=relative,
            document=document,
            is_commands=is_commands,
            generated_by=generated,
            role=_role_for(relative, generated),
        )
    return files


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _looks_like_engine_command(name: str) -> bool:
    lower = name.lower()
    if lower in KNOWN_ENGINE_COMMANDS:
        return True
    if lower.startswith(SIGNED_PREFIXES) and lower[1:] in KNOWN_ENGINE_ACTIONS:
        return True
    return any(lower.startswith(p) for p in KNOWN_ENGINE_PREFIXES)


def _looks_custom(name: str) -> bool:
    return name.startswith(CUSTOM_PREFIXES) and len(name) > 1


class Scanner:
    """Walks the exec graph and records what it finds."""

    def __init__(self, folder: Path, cfg_root: Optional[Path] = None) -> None:
        self.folder = Path(folder).resolve()
        self.cfg_root = cfg_root or find_cfg_root(self.folder)
        self.result = ScanResult(root=self.folder, cfg_root=self.cfg_root)
        self._order = 0

    # -- helpers ----------------------------------------------------------
    def _next_order(self) -> int:
        self._order += 1
        return self._order

    def _resolve(self, target: str) -> Optional[ConfigFile]:
        key = normalise_exec_path(target)
        direct = self.result.files.get(key)
        if direct:
            return direct
        # An exec without an extension: the engine supplies one. Try both,
        # preferring .cfg the way the engine does.
        if not Path(key).suffix:
            for suffix in (".cfg", ".vcfg"):
                found = self.result.files.get(key + suffix)
                if found:
                    return found
        # Fall back to matching on the tail, for collections scanned from a
        # folder that is not the cfg root.
        tail = key.split("/")[-1]
        matches = [f for k, f in self.result.files.items() if k.split("/")[-1] == tail]
        return matches[0] if len(matches) == 1 else None

    # -- the walk ---------------------------------------------------------
    def scan(self) -> ScanResult:
        self.result.files = discover(self.folder, self.cfg_root)

        for config in self.result.files.values():
            for issue in config.document.all_issues():
                issue.file = config.relative
                self.result.issues.append(issue)

        self.result.entry_points = self._find_entry_points()

        visited: Set[str] = set()
        for entry in self.result.entry_points:
            config = self._resolve(entry)
            if config:
                self._walk(config, visited, depth=0)

        # Files never reached by any exec chain still get recorded, so their
        # aliases and settings are known -- they just are not in the ordering.
        for key, config in self.result.files.items():
            if key not in visited and config.is_commands:
                self._record_file(config, immediate=False)

        self._check_alias_references()
        self._check_exec_targets()
        self._check_recursion()
        return self.result

    def _find_entry_points(self) -> List[str]:
        """Files nothing else execs, preferring an autoexec."""
        exec_targets: Set[str] = set()
        for config in self.result.files.values():
            if not config.is_commands:
                continue
            for command in config.document.commands():
                target = exec_target(command)
                if target:
                    resolved = self._resolve(target)
                    if resolved:
                        exec_targets.add(normalise_exec_path(resolved.relative))

        roots = [
            config.relative for key, config in sorted(self.result.files.items())
            if config.is_commands and key not in exec_targets
        ]
        roots.sort(key=lambda r: (0 if "autoexec" in r.lower() else 1, r))
        return roots

    def _walk(self, config: ConfigFile, visited: Set[str], depth: int) -> None:
        key = normalise_exec_path(config.relative)
        if depth > 24:
            self.result.issues.append(Issue(
                code="exec-depth",
                severity=Severity.WARNING,
                message=f"exec chain deeper than {depth}; stopped following it here",
                line=1, file=config.relative,
            ))
            return

        first_visit = key not in visited
        visited.add(key)
        if first_visit:
            config.exec_order = len(self.result.exec_chain)
        self.result.exec_chain.append((config.relative, depth))

        if not config.is_commands:
            return

        for command in config.document.commands():
            self._record_command(command, config, immediate=True)

            target = exec_target(command)
            if not target:
                continue
            resolved = self._resolve(target)
            if resolved is None:
                self.result.issues.append(Issue(
                    code="missing-exec-target",
                    severity=Severity.ERROR,
                    message=f"exec target not found: {target}",
                    line=command.line, column=command.start, file=config.relative,
                    detail=(
                        f"Resolved against the cfg root ({self.cfg_root}). If the file lives "
                        "outside the scanned folder this may be a false alarm."
                    ),
                ))
                continue
            # A file re-executed from inside an alias is a reload, not a loop.
            if normalise_exec_path(resolved.relative) in visited:
                continue
            self._walk(resolved, visited, depth + 1)

    def _record_file(self, config: ConfigFile, immediate: bool) -> None:
        for command in config.document.commands():
            self._record_command(command, config, immediate=immediate)

    def _record_command(self, command: Command, config: ConfigFile,
                        immediate: bool, nested: bool = False) -> None:
        order = self._next_order()

        definition = alias_definition(command)
        if definition:
            name, body = definition
            entry = AliasDef(name=name, body=body, file=config.relative,
                             line=command.line, nested=nested, order=order)
            self.result.aliases.setdefault(name.lower(), []).append(entry)
            # The body is deferred: parse it to learn what it calls, but do not
            # treat anything in it as running now.
            for inner in parse_command_string(body, command.line):
                self._record_call(inner, config, command.line)
                inner_def = alias_definition(inner)
                if inner_def:
                    inner_name, inner_body = inner_def
                    self.result.aliases.setdefault(inner_name.lower(), []).append(
                        AliasDef(name=inner_name, body=inner_body, file=config.relative,
                                 line=command.line, nested=True, order=self._next_order())
                    )
                    # The nested body is a reference too. Missing this is how a
                    # typo like 'alias !afk !afk_ff' stays invisible: the target
                    # is never called anywhere else, so nothing else reports it.
                    for deepest in parse_command_string(inner_body, command.line):
                        self._record_call(deepest, config, command.line)

                    self._check_state_target(name, inner_name, config, command.line)
            return

        bound = bind_definition(command)
        if bound:
            key, body = bound
            comment = None
            for line in config.document.lines:
                if line.number == command.line:
                    comment = line.comment
                    break
            self.result.binds.setdefault(key.lower(), []).append(
                BindDef(key=key, body=body, file=config.relative, line=command.line,
                        comment=comment, order=order)
            )
            for inner in parse_command_string(body, command.line):
                self._record_call(inner, config, command.line)
            return

        # A convar assignment: name plus exactly one value.
        if immediate and len(command.tokens) == 2 and not _is_action(command):
            comment = None
            for line in config.document.lines:
                if line.number == command.line:
                    comment = line.comment
                    break
            self.result.settings.setdefault(command.lname, []).append(
                SettingDef(name=command.name, value=command.arg_text(0),
                           file=config.relative, line=command.line,
                           comment=comment, order=order)
            )
            return

        self._record_call(command, config, command.line)

    def _check_state_target(self, outer: str, redefined: str,
                            config: ConfigFile, line: int) -> None:
        """A state alias should point its own base name at the next state.

        ``!afk_on`` redefining ``!afk`` is the pattern working. ``!micloopback_on``
        redefining ``!voicechat`` is a copy-paste that leaves the toggle stuck on
        one state while quietly reaching into an unrelated one.
        """
        suffixed = state_suffix(outer)
        if not suffixed:
            return
        base, _ = suffixed
        if redefined.lower() == base.lower():
            return
        # Redefining a sibling state directly is a different, valid pattern.
        sibling = state_suffix(redefined)
        if sibling and sibling[0].lower() == base.lower():
            return

        self.result.issues.append(Issue(
            code="state-redefines-other",
            severity=Severity.WARNING,
            message=f"'{outer}' redefines '{redefined}' rather than its own name '{base}'",
            line=line, file=config.relative,
            detail=(
                f"A toggle works by pointing its base name at the next state. Because this "
                f"redefines '{redefined}' instead, '{base}' keeps whatever it was last set to "
                f"and '{redefined}' is changed as a side effect. Reported, not repaired: the "
                f"intended target cannot be known from the file alone."
            ),
        ))

    def _record_call(self, command: Command, config: ConfigFile, line: int) -> None:
        if not command.tokens:
            return
        name = command.name
        if not name:
            return
        self.result.alias_calls.setdefault(name.lower(), []).append((config.relative, line))

    # -- diagnostics ------------------------------------------------------
    def _check_alias_references(self) -> None:
        """Report calls that resolve to nothing, separated by confidence."""
        for lname, sites in sorted(self.result.alias_calls.items()):
            if lname in self.result.aliases:
                continue
            if _looks_like_engine_command(lname):
                continue

            name = lname
            file, line = sites[0]
            if _looks_custom(name):
                self.result.issues.append(Issue(
                    code="unresolved-custom-reference",
                    severity=Severity.WARNING,
                    message=f"'{name}' is called but never defined in this collection",
                    line=line, file=file,
                    detail=(
                        f"Referenced {len(sites)} time(s). The naming convention says this is a "
                        "player-defined alias, so it is most likely a typo or a definition that "
                        "lives outside the scanned folder."
                    ),
                ))
            else:
                signed = name.startswith(SIGNED_PREFIXES)
                self.result.issues.append(Issue(
                    code="unverified-command",
                    severity=Severity.INFO,
                    message=f"'{name}' is not an alias here and is not a command this tool knows",
                    line=line, file=file,
                    detail=(
                        "This is not evidence that it is invalid. It may be a real engine command "
                        "absent from this tool's list, or one removed in a later game version. "
                        "Checking needs the game, not the config."
                        + (" Names beginning with + or - are usually engine actions." if signed else "")
                    ),
                ))

    def _check_exec_targets(self) -> None:
        for config in self.result.files.values():
            if config.generated_by:
                self.result.issues.append(Issue(
                    code="generated-file",
                    severity=Severity.INFO,
                    message=f"{config.relative} is generated, not hand-written",
                    line=1, file=config.relative,
                    detail=(
                        f"{config.generated_by}. Formatting keeps the provenance header; edits "
                        "here are overwritten the next time the generator runs."
                    ),
                ))

    def _check_recursion(self) -> None:
        """Immediate recursion only. Stateful cycles are not a defect."""
        for lname, defs in sorted(self.result.aliases.items()):
            definition = self.result.effective_alias(lname)
            if definition is None:
                continue
            seen: Set[str] = set()
            if self._reaches(definition, lname, seen, depth=0):
                self.result.issues.append(Issue(
                    code="alias-recursion",
                    severity=Severity.WARNING,
                    message=f"alias '{definition.name}' can reach itself without redefinition",
                    line=definition.line, file=definition.file,
                    detail=(
                        "Unlike a toggle, nothing on this path replaces the alias before it is "
                        "reached again, so invoking it may not terminate."
                    ),
                ))

    def _reaches(self, definition: AliasDef, target: str, seen: Set[str], depth: int) -> bool:
        if depth > 12:
            return False
        for command in definition.commands:
            # A body that redefines the alias is a state machine, not recursion.
            inner = alias_definition(command)
            if inner and inner[0].lower() == target:
                return False
        for command in definition.commands:
            name = command.lname
            if not name or alias_definition(command):
                continue
            if name == target and depth > 0:
                return True
            if name == target and depth == 0:
                return True
            if name in seen:
                continue
            seen.add(name)
            nxt = self.result.effective_alias(name)
            if nxt and self._reaches(nxt, target, seen, depth + 1):
                return True
        return False


def scan(folder: Path, cfg_root: Optional[Path] = None) -> ScanResult:
    return Scanner(folder, cfg_root).scan()


def _is_action(command: Command) -> bool:
    """Whether a two-token command is doing something rather than setting one."""
    return command.lname in cfglang.EXECUTABLE or command.name.startswith(CUSTOM_PREFIXES)


# ---------------------------------------------------------------------------
# Profile comparison
# ---------------------------------------------------------------------------

@dataclass
class ProfileDelta:
    """What one profile changes that another does not put back."""

    from_profile: str
    to_profile: str
    unrestored_settings: List[Tuple[str, str]] = field(default_factory=list)
    unrestored_binds: List[Tuple[str, str]] = field(default_factory=list)


def compare_profiles(result: ScanResult, first: str, second: str) -> ProfileDelta:
    """Settings and binds ``first`` changes that ``second`` never restores.

    Deliberately does not claim to know the correct value: without running the
    game there is no way to know what the setting was before the profile
    touched it. It reports only that nothing puts it back.
    """
    delta = ProfileDelta(from_profile=first, to_profile=second)

    def written_by(relative: str) -> Tuple[Dict[str, str], Dict[str, str]]:
        settings: Dict[str, str] = {}
        binds: Dict[str, str] = {}
        for name, defs in result.settings.items():
            for entry in defs:
                if entry.file == relative:
                    settings[name] = entry.value
        for key, defs in result.binds.items():
            for entry in defs:
                if entry.file == relative:
                    binds[key] = entry.body
        return settings, binds

    first_settings, first_binds = written_by(first)
    second_settings, second_binds = written_by(second)

    for name, value in sorted(first_settings.items()):
        if name not in second_settings:
            delta.unrestored_settings.append((name, value))
    for key, body in sorted(first_binds.items()):
        if key not in second_binds:
            delta.unrestored_binds.append((key, body))
    return delta


def content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Finding folders worth scanning
# ---------------------------------------------------------------------------

@dataclass
class SettingView:
    """One setting, ready for a control, with where its value came from."""

    name: str
    value: str
    label: str
    category: str
    control: str                       # slider | toggle | select | number
    file: str
    line: int
    comment: Optional[str] = None
    spec: Dict[str, object] = field(default_factory=dict)
    sources: List[Dict[str, object]] = field(default_factory=list)
    overridden: bool = False
    profile_only: bool = False
    ambiguous: bool = False
    unset: bool = False
    note: str = ""


def _load_setting_specs() -> Dict[str, Dict[str, object]]:
    import json

    from .kb import BUNDLED

    path = BUNDLED / "cfg_settings.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def settings_view(
    result: ScanResult,
    video_values: Optional[Dict[str, str]] = None,
) -> Tuple[List[SettingView], List[Dict[str, object]]]:
    """Build the settings list, laid out the way the game's own menu is.

    Two sources are merged, because CS2 genuinely splits its settings across
    them: picture quality lives in ``cs2_video.txt`` and is not settable as a
    convar at all, while everything else is a convar in a config file. A view
    that showed only one of them would be missing half the menu.

    Two rules the output holds to:

    *No invented ranges.* A slider appears only where the knowledge base records
    a real engine clamp; everything else gets a number box.

    *No pretending to know the effective value.* A convar written only by a
    profile outside the startup chain is marked ``profile_only``, because which
    value is live depends on what was last loaded and no file can say.
    """
    knowledge = _load_setting_specs()
    specs: Dict[str, Dict[str, object]] = knowledge.get("settings", {})
    sections: List[Dict[str, object]] = knowledge.get("sections", [])
    video_values = video_values or {}

    in_chain = {relative for relative, _ in result.exec_chain}
    views: List[SettingView] = []

    for key, spec in specs.items():
        source = str(spec.get("source", "cfg"))

        if source == "video":
            if key not in video_values:
                continue
            views.append(SettingView(
                name=key,
                value=video_values[key],
                label=str(spec.get("label", key)),
                category=str(spec.get("group", "other")),
                control=str(spec.get("control", "number")),
                file="cs2_video.txt",
                line=0,
                spec=spec,
                sources=[{"file": "cs2_video.txt", "line": 0,
                          "value": video_values[key], "in_startup_chain": True,
                          "wins": True}],
                note=(
                    "Stored in cs2_video.txt under your Steam userdata. CS2 ignores these "
                    "as console commands, so a config file cannot change them."
                ),
            ))
            continue

        defs = result.settings.get(key.lower())
        if not defs:
            # Not in any file. Still worth showing: the catalogue is the
            # game's settings list, not a list of what happens to be written
            # down, and a setting you cannot see is one you cannot change.
            default = spec.get("default")
            views.append(SettingView(
                name=key,
                value="" if default is None else str(default),
                label=str(spec.get("label", key)),
                category=str(spec.get("group", "other")),
                control=str(spec.get("control", "number")),
                file="",
                line=0,
                spec=spec,
                sources=[],
                unset=True,
                note=(
                    "not set in any scanned file, so the game's own default applies"
                    if default is not None else
                    "not set in any scanned file, and this tool does not record a default "
                    "for it -- enter a value to add it"
                ),
            ))
            continue

        ordered = sorted(defs, key=lambda d: d.order)
        chain_defs = [d for d in ordered if d.file in in_chain]
        effective = (chain_defs or ordered)[-1]
        distinct = {d.value for d in ordered}
        mixed = bool(chain_defs) and any(d.file not in in_chain for d in ordered) and len(distinct) > 1

        views.append(SettingView(
            name=effective.name,
            value=effective.value,
            label=str(spec.get("label", effective.name)),
            category=str(spec.get("group", "other")),
            control=str(spec.get("control", "number")),
            file=effective.file,
            line=effective.line,
            comment=effective.comment,
            spec=spec,
            sources=[
                {"file": d.file, "line": d.line, "value": d.value,
                 "in_startup_chain": d.file in in_chain, "wins": d is effective}
                for d in ordered
            ],
            overridden=len(ordered) > 1 and len(distinct) > 1,
            profile_only=not chain_defs,
            ambiguous=mixed,
            note=(
                "only set by a profile that is not loaded at startup, so whether this "
                "value is live depends on which profile you last ran"
                if not chain_defs else
                "a profile file also sets this to a different value; which one is live "
                "depends on whether you have loaded that profile since starting"
                if mixed else ""
            ),
        ))

    return views, sections


def startup_chain(result: ScanResult) -> Set[str]:
    """Files that actually load when the game starts.

    ``exec_chain`` holds every root the scanner walked, and a file that is only
    ever exec'd from inside an alias has nothing exec'ing it at load time, so
    it is a root too. ``lan.vcfg`` is exactly that: reachable only by pressing
    a key. Treating it as part of startup made its match settings look like
    they were live from launch, and made it the busiest "startup" file.

    So the startup chain is the first entry point and everything it reaches --
    the autoexec's subtree, up to the next root in the walk.
    """
    chain: Set[str] = set()
    started = False
    for relative, depth in result.exec_chain:
        if depth == 0:
            if started:
                break
            started = True
        chain.add(relative)
    return chain


def default_target(result: ScanResult, group: str = "") -> Optional[str]:
    """Where a brand new setting should be written.

    The busiest settings file **that actually loads at startup**. Counting
    every file regardless picks a match profile like ``lan.vcfg``, which holds
    far more convars than anything else but is a server configuration run on
    demand: a personal client setting put there would not apply on launch, and
    when the profile was loaded it would be sent to everyone on the server.

    Generated files are skipped as well, since anything written into one is
    lost the next time the generator runs.
    """
    in_chain = startup_chain(result)
    generated = {c.relative for c in result.files.values() if c.generated_by}

    def tally(predicate) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for defs in result.settings.values():
            for entry in defs:
                if predicate(entry.file):
                    counts[entry.file] = counts.get(entry.file, 0) + 1
        return counts

    for predicate in (
        lambda f: f in in_chain and f not in generated,
        lambda f: f not in generated,
        lambda f: True,
    ):
        counts = tally(predicate)
        if counts:
            return max(counts.items(), key=lambda kv: kv[1])[0]
    return None

def append_setting(result: ScanResult, name: str, value: str,
                   file: Optional[str] = None) -> Tuple[str, str]:
    """Add a setting that is not yet in any file.

    Appended at the end so it wins over anything set earlier, with a comment
    marking where it came from. Returns ``(relative_path, new_text)``.
    """
    relative = file or default_target(result)
    if not relative:
        raise ValueError("no file in the scan to add settings to")

    config = next((c for c in result.files.values() if c.relative == relative), None)
    if config is None:
        raise ValueError(f"{relative} is not part of the scan")
    if not config.is_commands:
        raise ValueError(f"{relative} is not a console-command file")

    # Appending a name that is already written somewhere would stack a second
    # line shadowing the first, and every later save would add another. The
    # caller wants write_setting.
    if result.settings.get(name.lower()):
        raise ValueError(
            f"{name} is already set in this collection; edit the existing "
            "line rather than adding another"
        )

    text = config.path.read_bytes().decode(config.document.encoding, errors="replace")
    newline = config.document.newline
    body = text.rstrip("\r\n")

    quoted = f'"{value}"' if value != "" else '""'
    padding = max(1, 44 - len(f"{name} {quoted}"))
    line = f"{name} {quoted}{' ' * padding}// added by cs2-autoconfig"

    block = newline.join(["", "// --------------------------",
                          "// ADDED SETTINGS", "// --------------------------"])
    if "// ADDED SETTINGS" not in text:
        body = body + newline + block

    body = body + newline + line
    if config.document.trailing_newline:
        body += newline
    return relative, body


def write_setting(result: ScanResult, name: str, value: str,
                  file: Optional[str] = None, line: Optional[int] = None) -> Tuple[str, str]:
    """Produce the new text for the file holding a setting.

    Rewrites only the value token on the line the scan recorded, leaving the
    comment, its column and every other character alone. Returns
    ``(relative_path, new_text)``; writing is the caller's job.
    """
    from .cfglang import Token, alias_definition

    defs = result.settings.get(name.lower())
    if not defs:
        raise ValueError(f"{name} is not a setting in this scan")

    # Narrow as far as the caller's hint still fits, then widen. A page that
    # loaded before the last save holds an old line number, and a stale hint
    # should not stop the setting being changed -- the definition that wins is
    # the right one to edit either way.
    ordered = sorted(defs, key=lambda d: d.order)
    if file is None:
        target = ordered[-1]
    else:
        target = None
        for matches in ([e for e in ordered if e.file == file and e.line == line],
                        [e for e in ordered if e.file == file],
                        ordered):
            if matches:
                target = matches[-1]
                break
    if target is None:
        raise ValueError(f"{name} is not set in {file}")

    config = next((c for c in result.files.values() if c.relative == target.file), None)
    if config is None:
        raise ValueError(f"{target.file} is not part of the scan")

    lines = config.path.read_bytes().decode(
        config.document.encoding, errors="replace"
    ).splitlines()
    index = target.line - 1
    if not (0 <= index < len(lines)):
        raise ValueError(f"{target.file}:{target.line} is out of range")

    original = lines[index]
    parsed = tokenize_line(original, target.line)
    if not parsed.commands or len(parsed.commands[0].tokens) < 2:
        raise ValueError(f"{target.file}:{target.line} does not look like a setting any more")

    token = parsed.commands[0].tokens[1]
    quoted = token.quoted
    replacement = f'"{value}"' if quoted else value
    rewritten = original[:token.start] + replacement + original[token.end:]

    # Hold the comment where it was, so changing 0.8 to 0.85 does not shift it.
    if parsed.comment_column is not None and len(rewritten) != len(original):
        code = rewritten[:rewritten.index("//")] if "//" in rewritten else rewritten
        stripped = code.rstrip()
        pad = max(1, parsed.comment_column - len(stripped))
        rewritten = stripped + " " * pad + original[parsed.comment_column:]

    lines[index] = rewritten
    newline = config.document.newline
    text = newline.join(lines) + (newline if config.document.trailing_newline else "")
    return target.file, text


@dataclass
class FolderSuggestion:
    path: str
    label: str
    file_count: int
    reason: str
    is_cfg_root: bool = False


def _count_configs(folder: Path, limit: int = 400) -> int:
    total = 0
    try:
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix.lower() in CONFIG_SUFFIXES:
                total += 1
                if total >= limit:
                    break
    except OSError:
        return total
    return total


def suggest_folders(extra: Optional[Sequence[Path]] = None) -> List[FolderSuggestion]:
    """Offer somewhere to scan instead of making the user type a path.

    Looks for the game's own ``cfg`` directory and the collections inside it.
    A player's configs almost always live in a subfolder there, so listing
    those directly saves a round trip through a file dialog for the common case.
    """
    from . import steam

    roots: List[Tuple[Path, str]] = []

    try:
        steam_root = steam.find_steam_root()
        install = steam.find_cs2_install(steam_root)
        if install:
            cfg = steam.cfg_dir(install)
            if cfg.is_dir():
                roots.append((cfg, "the game's cfg folder"))
    except steam.SteamError:
        pass

    for candidate in extra or ():
        candidate = Path(candidate)
        if candidate.is_dir():
            roots.append((candidate, "previously used"))

    suggestions: List[FolderSuggestion] = []
    seen: Set[str] = set()

    for root, reason in roots:
        key = str(root).lower()
        if key not in seen:
            seen.add(key)
            count = _count_configs(root)
            if count:
                suggestions.append(FolderSuggestion(
                    path=str(root), label=root.name or str(root),
                    file_count=count, reason=reason, is_cfg_root=True,
                ))

        # Subfolders are usually where a personal collection actually lives.
        try:
            children = sorted(p for p in root.iterdir() if p.is_dir())
        except OSError:
            continue
        for child in children:
            child_key = str(child).lower()
            if child_key in seen:
                continue
            count = _count_configs(child)
            if not count:
                continue
            seen.add(child_key)
            suggestions.append(FolderSuggestion(
                path=str(child), label=child.name,
                file_count=count,
                reason=f"collection inside {reason}",
            ))

    suggestions.sort(key=lambda s: (s.is_cfg_root, -s.file_count))
    return suggestions


def browse_for_folder(initial: Optional[str] = None,
                      title: str = "Choose a configuration folder") -> Optional[str]:
    """Open the native folder picker and return the chosen path.

    Runs in a separate STA PowerShell process. The dialog needs a single
    threaded apartment, which the server's worker threads are not, and shelling
    out keeps that requirement from leaking into the rest of the process.
    """
    import subprocess
    import tempfile

    start = initial or ""
    script = (
        "Add-Type -AssemblyName System.Windows.Forms\n"
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog\n"
        f"$d.Description = {_ps_literal(title)}\n"
        "$d.ShowNewFolderButton = $false\n"
        f"$start = {_ps_literal(start)}\n"
        "if ($start -and (Test-Path $start)) { $d.SelectedPath = $start }\n"
        "$top = New-Object System.Windows.Forms.Form\n"
        "$top.TopMost = $true\n"
        "if ($d.ShowDialog($top) -eq [System.Windows.Forms.DialogResult]::OK) "
        "{ [Console]::Out.Write($d.SelectedPath) }\n"
        "$top.Dispose(); $d.Dispose()\n"
    )

    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        script_path = handle.name

    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass",
             "-File", script_path],
            capture_output=True, text=True, timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        try:
            Path(script_path).unlink()
        except OSError:
            pass

    chosen = (proc.stdout or "").strip()
    return chosen or None


def _ps_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def describe_folder(folder: Path) -> Dict[str, object]:
    """A quick, cheap look at a folder so the UI can validate as you type."""
    folder = Path(folder)
    if not folder.exists():
        return {"exists": False, "is_dir": False, "file_count": 0,
                "message": "that path does not exist"}
    if not folder.is_dir():
        return {"exists": True, "is_dir": False, "file_count": 0,
                "message": "that is a file, not a folder"}

    count = _count_configs(folder)
    if not count:
        return {"exists": True, "is_dir": True, "file_count": 0,
                "message": "no .cfg or .vcfg files found in this folder or below it"}
    return {"exists": True, "is_dir": True, "file_count": count,
            "cfg_root": str(find_cfg_root(folder)),
            "message": f"{count} config file(s) found"}
