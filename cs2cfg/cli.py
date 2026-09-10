"""Command line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__, backup, console, emit, steam
from .hardware import Machine, ProbeError, detect
from .kb import KnowledgeBase, KnowledgeError, user_data_dir
from .profile import Profile, build_profile, plan_launch_options

DEFAULT_CFG_FOLDER = "mrwhiteer"
DEFAULT_CFG_NAME = "autoperf.vcfg"

STRETCH_MODE_TEXT = {
    "borderless": "Windowed - Fullscreen (for Multiple screen users)",
    "fullscreen": "Fullscreen (Standard/Original)",
}


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

class Out:
    """Tiny formatter. Colour only when the terminal will actually render it."""

    def __init__(self, colour: bool = True) -> None:
        stream = getattr(sys, "stdout", None)
        # A GUI-subsystem build can have no stdout at all, so this cannot
        # assume the stream exists before asking whether it is a terminal.
        try:
            interactive = stream is not None and stream.isatty()
        except (AttributeError, ValueError):
            interactive = False
        self.colour = colour and interactive and os.environ.get("TERM") != "dumb"

    def _c(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.colour else text

    def bold(self, text: str) -> str:
        return self._c("1", text)

    def dim(self, text: str) -> str:
        return self._c("2", text)

    def green(self, text: str) -> str:
        return self._c("32", text)

    def yellow(self, text: str) -> str:
        return self._c("33", text)

    def red(self, text: str) -> str:
        return self._c("31", text)

    def cyan(self, text: str) -> str:
        return self._c("36", text)

    def header(self, text: str) -> None:
        print()
        print(self.bold(text))
        print(self.dim("-" * max(len(text), 20)))

    def kv(self, key: str, value: str, width: int = 18) -> None:
        print(f"  {key:<{width}} {value}")


# ---------------------------------------------------------------------------
# Persistent preferences
# ---------------------------------------------------------------------------

def config_path() -> Path:
    return user_data_dir() / "config.json"


def load_prefs() -> Dict[str, str]:
    path = config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_prefs(prefs: Dict[str, str]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Shared context
# ---------------------------------------------------------------------------

class Context:
    """Everything a command needs, resolved once."""

    def __init__(self, args: argparse.Namespace, out: Out) -> None:
        self.args = args
        self.out = out
        self.kb = KnowledgeBase()
        self.machine: Optional[Machine] = None
        self.steam_root: Optional[Path] = None
        self.user: Optional[steam.SteamUser] = None
        self.cs2_install: Optional[Path] = None

    def probe(self) -> Machine:
        if self.machine is None:
            self.machine = detect()
        return self.machine

    def resolve_steam(self, require_user: bool = True) -> None:
        self.steam_root = Path(self.args.steam_root) if self.args.steam_root else steam.find_steam_root()
        self.cs2_install = steam.find_cs2_install(self.steam_root)

        users = steam.list_users(self.steam_root)
        if not users:
            if require_user:
                raise steam.SteamError(
                    f"no Steam account under {self.steam_root} has CS2 data. "
                    "Sign in and launch the game once."
                )
            return

        wanted = self.args.account or load_prefs().get("account")
        if wanted:
            match = next((u for u in users if u.account_id == str(wanted)), None)
            if match is None:
                raise steam.SteamError(
                    f"account {wanted} not found. Available: " + ", ".join(u.account_id for u in users)
                )
            self.user = match
        elif len(users) == 1:
            self.user = users[0]
        else:
            self.user = users[0]
            print(self.out.yellow(
                f"  Note: {len(users)} accounts have CS2 data. Using {self.user.label}."
            ))
            print(self.out.dim("        Pick another with --account <id>, or pin one with `cs2cfg use <id>`."))

    def build(self) -> Profile:
        machine = self.probe()
        current_video = steam.read_video_cfg(self.user) if self.user else {}
        return build_profile(
            machine,
            self.kb,
            intent=self.args.intent,
            target_fps=self.args.target_fps,
            resolution=_parse_resolution(self.args.resolution),
            current_video=current_video,
        )


def _parse_resolution(text: Optional[str]):
    if not text:
        return None
    for sep in ("x", "X", "*", ":"):
        if sep in text:
            left, _, right = text.partition(sep)
            if left.strip().isdigit() and right.strip().isdigit():
                return int(left), int(right)
    raise SystemExit(f"could not read resolution {text!r}; expected something like 1920x1080")


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_hardware(ctx: Context, machine: Machine) -> None:
    out = ctx.out
    out.header("Hardware")
    if machine.cpu:
        hybrid = "  (hybrid P/E cores)" if machine.cpu.likely_hybrid else ""
        out.kv("CPU", f"{machine.cpu.name}{hybrid}")
        out.kv("", out.dim(f"{machine.cpu.cores} cores / {machine.cpu.threads} threads, "
                           f"{machine.cpu.max_clock_mhz} MHz base"))
    if machine.gpu:
        out.kv("GPU", machine.gpu.name)
        detail = f"{machine.gpu.vram_gb:g} GB VRAM"
        if machine.gpu.driver_version:
            detail += f", driver {machine.gpu.driver_version}"
        if machine.gpu.driver_date:
            detail += f" ({machine.gpu.driver_date})"
        out.kv("", out.dim(detail))
    out.kv("Memory", f"{machine.ram_gb:g} GB" + (f" @ {machine.ram_speed_mts} MT/s" if machine.ram_speed_mts else ""))

    display = machine.primary_display
    if display:
        suffix = "" if display.confident_refresh else out.dim("  (from EDID; may understate)")
        out.kv("Display", f"{display.width}x{display.height} @ {display.refresh} Hz{suffix}")
    if len(machine.displays) > 1:
        out.kv("", out.dim(f"{len(machine.displays)} displays attached; scoring against the primary"))

    out.kv("OS", f"{machine.os_caption} (build {machine.os_build})")
    out.kv("Power plan", machine.power_plan or "unknown")
    if ctx.cs2_install:
        media = machine.media_type_for(ctx.cs2_install)
        out.kv("CS2 install", f"{ctx.cs2_install}  {out.dim(f'[{media}]')}")


def report_profile(ctx: Context, profile: Profile) -> None:
    out = ctx.out
    out.header("Assessment")

    gpu_note = "" if profile.gpu_match.exact else out.dim(f"  ({profile.gpu_match.note})")
    cpu_note = "" if profile.cpu_match.exact else out.dim(f"  ({profile.cpu_match.note})")
    out.kv("CPU score", f"{profile.cpu_match.index:.0f}/105{cpu_note}")
    out.kv("GPU score", f"{profile.gpu_match.index:.0f}/135{gpu_note}")
    out.kv("CPU ceiling", f"~{profile.cpu_ceiling} fps")
    out.kv("GPU ceiling", f"~{profile.gpu_ceiling} fps at these settings")
    out.kv("Limited by", profile.bottleneck)

    headroom_text = f"{profile.headroom:.2f}x your {profile.target_fps} Hz target"
    colour = out.green if profile.headroom >= 1.15 else out.yellow if profile.headroom >= 0.85 else out.red
    out.kv("Estimate", colour(f"~{profile.estimated_fps} fps  ({headroom_text})"))
    out.kv("Tier", out.bold(profile.tier) + f"  with the {profile.intent} profile")
    print()
    print(out.dim("  " + ctx.kb.video["intents"][profile.intent]["description"]))


def report_video(ctx: Context, profile: Profile, current: Dict[str, str]) -> None:
    out = ctx.out
    out.header("Picture quality  (cs2_video.txt)")

    changed = 0
    for key in sorted(profile.video):
        value = profile.video[key]
        before = current.get(key)
        label = ctx.kb.label(key, value)
        name = ctx.kb.ui_name(key)

        if before is None:
            print(f"  {name:<32} {out.green(label)}  {out.dim('(new)')}")
            changed += 1
        elif str(value) != before:
            try:
                before_label = ctx.kb.label(key, int(before))
            except ValueError:
                before_label = before
            # Some settings store more values than the game's menu has names
            # for -- HDR keeps four but shows three -- so two different values
            # can carry the same label and the line reads as a no-op. Show the
            # raw numbers when that happens rather than printing "Quality ->
            # Quality" and leaving it looking like nothing moved.
            if before_label == label:
                print(f"  {name:<32} {out.dim(before_label + ' (' + str(before) + ')')}"
                      f" -> {out.green(label + ' (' + str(value) + ')')}")
            else:
                print(f"  {name:<32} {out.dim(before_label)} -> {out.green(label)}")
            changed += 1
        else:
            print(out.dim(f"  {name:<32} {label}  (unchanged)"))

    if not changed:
        print(out.dim("\n  Nothing to change; the video config already matches this profile."))
    else:
        print()
        print(out.dim(f"  {changed} setting(s) would change."))

    preserved = [k for k in ctx.kb.video.get("preserve", []) if k in current]
    if preserved:
        print()
        print(out.dim("  Left untouched: " + ", ".join(
            k.replace("setting.", "") for k in preserved[:8]
        ) + ("..." if len(preserved) > 8 else "")))
        print(out.dim("  " + ctx.kb.video.get("preserve_note", "")[:110] + "..."))


def report_launch(ctx: Context, plan, current: str) -> None:
    out = ctx.out
    out.header("Steam launch options")
    print(out.dim(f"  current: {current or '(none set)'}"))
    print()
    print(f"  {out.green(plan.line)}")

    if plan.removed:
        print()
        print(f"  {out.bold('Removed:')}")
        for option, reason in plan.removed:
            print(f"    {out.red(option)}")
            print(out.dim(f"      {reason}"))
    if plan.added:
        print()
        print(f"  {out.bold('Added:')}")
        for option, reason in plan.added:
            print(f"    {out.green(option)}")
            print(out.dim(f"      {reason}"))


def report_advisories(ctx: Context, profile: Profile) -> None:
    if not profile.advisories:
        return
    out = ctx.out
    out.header("Worth knowing")
    for advisory in profile.advisories:
        marker = out.yellow("!") if advisory.level == "warn" else out.cyan("i")
        print(f"  {marker} {advisory.title}")
        print(out.dim(f"    {advisory.detail}"))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_scan(ctx: Context) -> int:
    machine = ctx.probe()
    try:
        ctx.resolve_steam(require_user=False)
    except steam.SteamError as exc:
        print(ctx.out.yellow(f"  Steam: {exc}"))
    report_hardware(ctx, machine)

    if ctx.steam_root:
        ctx.out.header("Steam")
        ctx.out.kv("Install", str(ctx.steam_root))
        try:
            users = steam.list_users(ctx.steam_root)
            for user in users:
                marker = "*" if ctx.user and user.account_id == ctx.user.account_id else " "
                video = "video config present" if user.video_cfg.exists() else "no video config yet"
                print(f"  {marker} {user.label}  {ctx.out.dim(video)}")
        except steam.SteamError as exc:
            print(ctx.out.yellow(f"  {exc}"))
        ctx.out.kv("Steam running", "yes -- close it before applying" if steam.steam_running() else "no")
    return 0


def cmd_plan(ctx: Context) -> int:
    ctx.resolve_steam()
    machine = ctx.probe()
    profile = ctx.build()
    current_video = steam.read_video_cfg(ctx.user)
    current_launch = steam.read_launch_options(ctx.user)

    exec_target = f"{ctx.args.cfg_folder}/{ctx.args.cfg_name}"
    launch = plan_launch_options(
        current_launch, machine, ctx.kb,
        exec_path=exec_target.replace("/", "\\"),
        want_console=ctx.args.console,
    )

    report_hardware(ctx, machine)
    report_profile(ctx, profile)
    report_video(ctx, profile, current_video)
    report_launch(ctx, launch, current_launch)
    report_advisories(ctx, profile)

    print()
    print(ctx.out.dim("  This was a dry run. Nothing was written. Use `cs2cfg apply` to commit."))
    return 0


def cmd_apply(ctx: Context) -> int:
    ctx.resolve_steam()
    out = ctx.out
    machine = ctx.probe()
    profile = ctx.build()
    current_video = steam.read_video_cfg(ctx.user)
    current_launch = steam.read_launch_options(ctx.user)

    exec_target = f"{ctx.args.cfg_folder}/{ctx.args.cfg_name}"
    launch = plan_launch_options(
        current_launch, machine, ctx.kb,
        exec_path=exec_target.replace("/", "\\"),
        want_console=ctx.args.console,
    )

    report_hardware(ctx, machine)
    report_profile(ctx, profile)
    report_video(ctx, profile, current_video)
    report_launch(ctx, launch, current_launch)
    report_advisories(ctx, profile)

    writes_launch = not ctx.args.no_launch
    if writes_launch and steam.steam_running():
        print()
        print(out.yellow("  Steam is running, so the launch options cannot be written."))
        print(out.dim("  Close Steam and re-run, or pass --no-launch to skip that part."))
        return 2

    if not ctx.args.yes:
        print()
        if not console.can_prompt():
            print(out.yellow("  No console to confirm on; re-run with --yes to apply."))
            return 1
        answer = input(out.bold("  Apply these changes? [y/N] ")).strip().lower()
        if answer not in ("y", "yes"):
            print(out.dim("  Nothing written."))
            return 1

    session = backup.BackupSession(note=f"apply {profile.intent}/tier {profile.tier}")
    out.header("Writing")

    if not ctx.args.no_video:
        try:
            diff = steam.write_video_cfg(ctx.user, profile.video, session)
            print(f"  {out.green('ok')}  cs2_video.txt  {out.dim(f'({len(diff)} setting(s) changed)')}")
            print(out.dim(f"      {ctx.user.video_cfg}"))
        except steam.SteamError as exc:
            print(f"  {out.red('--')}  cs2_video.txt: {exc}")

    if not ctx.args.no_cfg and ctx.cs2_install:
        cfg_root = steam.cfg_dir(ctx.cs2_install)
        target = cfg_root / ctx.args.cfg_folder / ctx.args.cfg_name
        emit.write_text_file(target, emit.render_cfg(profile, ctx.kb, ctx.args.cfg_name), session)
        print(f"  {out.green('ok')}  {ctx.args.cfg_name}")
        print(out.dim(f"      {target}"))

        notes = cfg_root / ctx.args.cfg_folder / "launch_options_generated.txt"
        emit.write_text_file(
            notes,
            emit.render_launch_notes(profile, launch.line, launch.removed, launch.added),
            session,
        )
        print(f"  {out.green('ok')}  launch_options_generated.txt")

        autoexec = cfg_root / ctx.args.cfg_folder / "autoexec.vcfg"
        if ctx.args.link_autoexec:
            result = emit.ensure_exec_line(autoexec, exec_target, session)
            print(f"  {out.green('ok')}  autoexec.vcfg  {out.dim(f'({result})')}")
        else:
            print(out.dim(f"      add `exec \"{exec_target}\"` to your autoexec, or re-run with --link-autoexec"))
    elif not ctx.args.no_cfg:
        print(f"  {out.yellow('--')}  CS2 install not found, so no config file was written")

    if writes_launch:
        try:
            action = steam.write_launch_options(ctx.user, launch.line, session)
            print(f"  {out.green('ok')}  Steam launch options  {out.dim(f'({action})')}")
        except steam.SteamError as exc:
            print(f"  {out.red('--')}  launch options: {exc}")

    print()
    if session.empty:
        print(out.dim("  No backup needed; nothing existed to overwrite."))
    else:
        print(out.dim(f"  Backup {session.stamp} written to {session.dir}"))
        print(out.dim(f"  Undo everything with:  cs2cfg revert {session.stamp}"))
    backup.prune()
    return 0


def cmd_revert(ctx: Context) -> int:
    out = ctx.out
    target = backup.find_set(ctx.args.stamp)
    if target is None:
        print(out.red(f"  no backup found for {ctx.args.stamp!r}"))
        print(out.dim("  list what is available with `cs2cfg backups`"))
        return 1

    print(f"  Restoring backup {out.bold(target.stamp)} from {target.when}")
    if target.note:
        print(out.dim(f"  {target.note}"))
    print()

    if any("localconfig.vdf" in f for f in target.files) and steam.steam_running():
        print(out.yellow("  Steam is running and this backup includes localconfig.vdf."))
        print(out.dim("  Close Steam first, or the restore will be overwritten when it exits."))
        return 2

    if not ctx.args.yes:
        if not console.can_prompt():
            print(out.yellow("  No console to confirm on; re-run with --yes to restore."))
            return 1
        answer = input(out.bold(f"  Restore {len(target.files)} file(s)? [y/N] ")).strip().lower()
        if answer not in ("y", "yes"):
            print(out.dim("  Nothing restored."))
            return 1

    for line in backup.restore(target):
        print(f"  {line}")
    return 0


def cmd_backups(ctx: Context) -> int:
    out = ctx.out
    sets = backup.list_sets()
    if not sets:
        print(out.dim("  No backups yet."))
        return 0
    out.header(f"Backups  ({backup.backups_root()})")
    for entry in sets:
        print(f"  {out.bold(entry.stamp)}  {entry.when}  {out.dim(entry.note)}")
        for original in entry.originals:
            state = "" if entry.files[original] else out.dim("  (did not exist)")
            print(out.dim(f"      {original}{state}"))
    return 0


def cmd_update(ctx: Context) -> int:
    out = ctx.out
    prefs = load_prefs()
    url = ctx.args.url or prefs.get("update_url")
    if not url:
        print(out.yellow("  No update URL configured."))
        print(out.dim("  The bundled knowledge base works offline and needs no updates to function."))
        print(out.dim("  To track a published one:  cs2cfg update --url https://example.com/cs2cfg-kb.json"))
        return 1

    try:
        files, where = ctx.kb.update(url)
    except KnowledgeError as exc:
        print(out.red(f"  update failed: {exc}"))
        return 1

    prefs["update_url"] = url
    save_prefs(prefs)
    print(f"  {out.green('ok')}  updated {', '.join(files)}")
    print(out.dim(f"      {where}"))
    print(out.dim("      revert to the bundled tables with `cs2cfg update --reset`"))
    return 0


def cmd_update_reset(ctx: Context) -> int:
    if ctx.kb.reset_overrides():
        print(f"  {ctx.out.green('ok')}  local knowledge overrides removed; using the bundled tables")
    else:
        print(ctx.out.dim("  no local overrides to remove"))
    return 0


def cmd_calibrate(ctx: Context) -> int:
    """Record the values this client actually writes.

    A few of CS2's quality enums are wider than the in-game menu suggests, and
    the safest way to learn the real ceiling is to read it back off a client
    that has been set to maximum by hand.
    """
    ctx.resolve_steam()
    out = ctx.out
    current = steam.read_video_cfg(ctx.user)
    if not current:
        print(out.red(f"  no video config to read at {ctx.user.video_cfg}"))
        return 1

    path = user_data_dir() / "knowledge" / "calibration.json"
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    observed: Dict[str, int] = dict(existing.get("observed_max") or {})

    learned: List[str] = []
    for key, value in current.items():
        if key not in ctx.kb.video.get("keys", {}):
            continue
        try:
            number = int(value)
        except ValueError:
            continue
        if number > observed.get(key, -1):
            observed[key] = number
            declared = ctx.kb.video["keys"][key].get("max", 0)
            if number > declared:
                learned.append(f"{ctx.kb.ui_name(key)}: saw {number}, table said max {declared}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"observed_max": observed}, indent=2), encoding="utf-8")

    out.header("Calibration")
    print(f"  Read {len(observed)} setting(s) from {ctx.user.video_cfg}")
    if learned:
        print()
        print(f"  {out.bold('Wider than the bundled table expected:')}")
        for line in learned:
            print(f"    {out.green(line)}")
        print()
        print(out.dim("  These ceilings now apply on the next run."))
    else:
        print(out.dim("  Nothing new; the bundled ranges already cover what this client writes."))
    print()
    print(out.dim("  Tip: set everything to maximum in the CS2 video menu, quit the game,"))
    print(out.dim("       then run this again to capture the true upper bound."))
    return 0


def cmd_use(ctx: Context) -> int:
    ctx.resolve_steam(require_user=False)
    users = steam.list_users(ctx.steam_root)
    match = next((u for u in users if u.account_id == str(ctx.args.account_id)), None)
    if match is None:
        print(ctx.out.red(f"  account {ctx.args.account_id} has no CS2 data"))
        for user in users:
            print(ctx.out.dim(f"    {user.label}"))
        return 1
    prefs = load_prefs()
    prefs["account"] = match.account_id
    save_prefs(prefs)
    print(f"  {ctx.out.green('ok')}  future runs will use {match.label}")
    return 0


def cmd_stretch(ctx: Context) -> int:
    """Borderless and stretched-borderless window control."""
    from . import window

    out = ctx.out
    args = ctx.args

    if args.list:
        windows = window.list_windows(args.process if args.process != "*" else None)
        out.header("Visible windows")
        if not windows:
            print(out.dim(f"  nothing matching {args.process!r} is running"))
            return 1
        for entry in windows:
            width, height = entry.size
            print(f"  {entry.process:<20} {width:>5}x{height:<5}  {entry.title[:44]}")
        return 0

    if args.restore:
        out.header("Restoring")
        print(f"  {window.restore_window(args.process)}")
        return 0

    # Default to the resolution CS2 is already configured for, which is the
    # stretched one if the player has set one.
    width, height = args.width, args.height
    if not (width and height):
        try:
            ctx.resolve_steam()
            video = steam.read_video_cfg(ctx.user)
            width = width or int(video.get("setting.defaultres", 0))
            height = height or int(video.get("setting.defaultresheight", 0))
        except (steam.SteamError, ValueError):
            pass
    if not (width and height):
        print(out.red("  no resolution given and none could be read from cs2_video.txt"))
        print(out.dim("  pass it explicitly:  cs2cfg stretch --width 1550 --height 1440"))
        return 1

    change_display = not args.fill
    out.header("Stretched borderless" if change_display else "Borderless fill")
    print(f"  target      {width}x{height}")
    print(f"  process     {args.process}")
    if change_display:
        print(out.dim("  The desktop switches to that mode, and the driver's scaler stretches it"))
        print(out.dim("  across the panel. Set GPU scaling to full-screen in the NVIDIA or AMD"))
        print(out.dim("  control panel, or the panel will letterbox instead of filling."))
    else:
        print(out.dim("  Frame removed and window sized to the monitor. The game renders at the"))
        print(out.dim("  monitor's resolution, so this is borderless but not stretched."))
    print()

    if args.watch:
        window.watch(width, height, args.process, args.refresh, change_display,
                     on_event=lambda message: print(f"  {message}"))
        return 0

    try:
        result = window.apply_stretch(width, height, args.process, args.refresh, change_display)
    except window.WindowError as exc:
        print(out.red(f"  {exc}"))
        if "not appear to be running" in str(exc):
            print(out.dim("  start the game first, or use --watch to apply it automatically on launch"))
        return 1

    print(f"  {out.green('ok')}  {result['title'] or args.process}")
    print(f"      window   {result['was'][0]}x{result['was'][1]} -> {result['now'][0]}x{result['now'][1]}")
    if result.get("display_changed"):
        before = result["display_before"]
        after = result["display_after"]
        print(f"      display  {before[0]}x{before[1]}@{before[2]} -> {after[0]}x{after[1]}@{after[2]}")
    print()
    print(out.dim("  undo with:  cs2cfg stretch --restore"))
    return 0


def cmd_play(ctx: Context) -> int:
    """Launch CS2 borderless-stretched so alt-tab stops going black."""
    from . import launcher, window

    ctx.resolve_steam()
    out = ctx.out
    args = ctx.args
    machine = ctx.probe()

    video = steam.read_video_cfg(ctx.user)
    width = args.width or int(video.get("setting.defaultres", 0) or 0)
    height = args.height or int(video.get("setting.defaultresheight", 0) or 0)
    if not (width and height):
        display = machine.primary_display
        if display:
            width, height = display.width, display.height
    if not (width and height):
        print(out.red("  no resolution to use; pass --width and --height"))
        return 1

    refresh = args.refresh or (machine.primary_display.refresh if machine.primary_display else 0)
    stretch_mode = "fullscreen" if args.no_stretch else args.stretch_mode

    out.header("Seamless launch")
    print(f"  resolution  {width}x{height}" + (f" @ {refresh} Hz" if refresh else ""))
    print(f"  stretch     {STRETCH_MODE_TEXT.get(stretch_mode, stretch_mode)}")
    print(f"  account     {ctx.user.label}")
    print()

    if len(machine.displays) > 1:
        print(out.dim(f"  {len(machine.displays)} monitors attached, which is when exclusive fullscreen"))
        print(out.dim("  alt-tab is at its worst. This is the case it fixes."))
        print()

    if stretch_mode == "borderless":
        try:
            window.set_mode(width, height, refresh, test_only=True)
            print(out.dim(f"  the driver accepts {width}x{height}; nothing applied yet"))
        except window.WindowError as exc:
            print(out.yellow(f"  {exc}"))
            print(out.dim("  create the mode with Custom Resolution Utility, or use --no-stretch"))
            return 1

    print()
    if stretch_mode == "borderless":
        print(out.dim("  GPU scaling must be set to full-screen in the NVIDIA or AMD control panel,"))
        print(out.dim("  or the panel will letterbox the narrow mode instead of filling it."))
        print(out.yellow("  Your whole desktop is stretched while the game runs."))
    print()

    if not args.yes:
        prompt = "  Launch? [y/N] " if stretch_mode != "borderless" else "  Change the display mode and launch? [y/N] "
        if not console.can_prompt():
            print(out.yellow("  No console to confirm on; re-run with --yes to launch."))
            return 1
        answer = input(out.bold(prompt)).strip().lower()
        if answer not in ("y", "yes"):
            print(out.dim("  Nothing changed."))
            return 1

    session = backup.BackupSession(note="play: seamless borderless launch")

    def say(message: str, tag: str = "") -> None:
        colour = {"good": out.green, "warn": out.yellow, "bad": out.red, "dim": out.dim}.get(tag)
        print(colour(message) if colour and message else message)

    print()
    try:
        code = launcher.play(
            ctx.user, width, height, refresh,
            stretch_mode=stretch_mode,
            patch_video=not args.no_video_patch,
            wait=not args.no_wait,
            session=session,
            say=say,
        )
    except launcher.LaunchError as exc:
        print(out.red(f"  {exc}"))
        return 1
    except KeyboardInterrupt:
        print(out.dim("\n  interrupted; the desktop mode has been put back"))
        return 130

    if not session.empty:
        print()
        print(out.dim(f"  Video settings backed up as {session.stamp}"))
        print(out.dim(f"  Put them back with:  cs2cfg revert {session.stamp}"))
    return code


def cmd_shortcut(ctx: Context) -> int:
    """Create a desktop shortcut that launches CS2 through Steam, seamlessly."""
    import subprocess

    out = ctx.out
    project = Path(__file__).resolve().parent.parent
    bat = project / "cs2cfg.bat"
    if not bat.exists():
        print(out.red(f"  launcher script not found at {bat}"))
        return 1

    desktop = _desktop_dir()
    if desktop is None:
        print(out.red("  could not locate your Desktop folder"))
        print(out.dim("  create the shortcut by hand, pointing at:"))
        print(out.dim(f"    {bat} play -y"))
        return 1

    link = desktop / f"{ctx.args.name}.lnk"
    arguments = "play -y" + ("" if not ctx.args.no_stretch else " --no-stretch")

    # CS2's own icon, so the shortcut looks like what it starts.
    icon = ""
    if ctx.cs2_install is None:
        try:
            ctx.resolve_steam(require_user=False)
        except steam.SteamError:
            pass
    if ctx.cs2_install:
        candidate = ctx.cs2_install / "game" / "bin" / "win64" / "cs2.exe"
        if candidate.exists():
            icon = str(candidate)

    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut({link});"
        "$s.TargetPath = {bat};"
        "$s.Arguments = {args};"
        "$s.WorkingDirectory = {cwd};"
        "$s.Description = 'Launch CS2 through Steam, borderless and stretched';"
        "{icon}"
        "$s.Save()"
    ).format(
        link=_ps_quote(str(link)),
        bat=_ps_quote(str(bat)),
        args=_ps_quote(arguments),
        cwd=_ps_quote(str(project)),
        icon=f"$s.IconLocation = {_ps_quote(icon)};" if icon else "",
    )

    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        print(out.red(f"  could not create the shortcut: {result.stderr.strip()[:300]}"))
        return 1

    out.header("Shortcut created")
    print(f"  {out.green(str(link))}")
    print(out.dim(f"      runs: cs2cfg.bat {arguments}"))
    if icon:
        print(out.dim("      using CS2's own icon"))
    print()
    print(out.dim("  Double-click it to play. It goes through Steam every time, so your"))
    print(out.dim("  launch options, the overlay, VAC and inventory all behave normally."))
    return 0


def _desktop_dir() -> Optional[Path]:
    """Find the Desktop, wherever Windows has actually put it.

    ``%USERPROFILE%\\Desktop`` is a guess, not a fact: OneDrive folder backup
    redirects it, and so does any roaming profile. The registry holds the real
    location, so ask that first and only fall back to the guess.
    """
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as handle:
            raw, _ = winreg.QueryValueEx(handle, "Desktop")
            candidate = Path(os.path.expandvars(str(raw)))
            if candidate.is_dir():
                return candidate
    except (ImportError, OSError):
        pass

    for guess in (
        Path(os.environ.get("USERPROFILE", Path.home())) / "OneDrive" / "Desktop",
        Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop",
        Path.home() / "Desktop",
    ):
        if guess.is_dir():
            return guess
    return None


def _ps_quote(value: str) -> str:
    """Single-quote a string for PowerShell, escaping embedded quotes."""
    return "'" + value.replace("'", "''") + "'"


def cmd_web(ctx: Context) -> int:
    """Serve the browser front end on localhost."""
    import webbrowser

    from . import webui

    out = ctx.out
    try:
        server, state = webui.serve(ctx.args.port, ctx.args.cfg_folder, ctx.args.cfg_name)
    except OSError as exc:
        print(out.red(f"  could not bind 127.0.0.1:{ctx.args.port}: {exc}"))
        print(out.dim("  something else is using that port; try --port 8766"))
        return 1

    url = f"http://127.0.0.1:{ctx.args.port}/"
    out.header("Web interface")
    print(f"  {out.green(url)}")
    print(out.dim("  Bound to localhost only. Writes require a token embedded in the page,"))
    print(out.dim("  so another page in your browser cannot drive it."))
    print()
    print(out.dim("  Ctrl+C to stop."))

    if not ctx.args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(out.dim("\n  stopped"))
    finally:
        server.shutdown()
        server.server_close()
    return 0


def cmd_desktop(ctx: Context) -> int:
    """Open the launcher as a normal desktop application."""
    from . import desktop

    return desktop.run(
        cfg_folder=ctx.args.cfg_folder,
        cfg_name=ctx.args.cfg_name,
        port=getattr(ctx.args, "port", None),
    )


def cmd_cfg(ctx: Context) -> int:
    """Scan, diagnose and polish a configuration collection."""
    from . import cfgformat, cfglang, cfgscan
    from .cfglang import Severity

    out = ctx.out
    folder = Path(ctx.args.folder).expanduser().resolve()
    if not folder.is_dir():
        print(out.red(f"  not a folder: {folder}"))
        return 1

    result = cfgscan.scan(folder)

    out.header("Files")
    for key in sorted(result.files):
        config = result.files[key]
        order = "" if config.exec_order is None else f"#{config.exec_order}"
        mark = out.dim("[generated]") if config.generated_by else ""
        kind = "" if config.is_commands else out.yellow("[not console commands]")
        print(f"  {order:<4} {config.relative:<40} {config.role:<12} {mark}{kind}")

    if result.exec_chain:
        out.header("Load order")
        for relative, depth in result.exec_chain:
            print("  " + "   " * depth + relative)

    out.header("Totals")
    out.kv("Aliases", str(len(result.aliases)))
    out.kv("Bound keys", str(len(result.binds)))
    out.kv("Settings", str(len(result.settings)))

    for label, severity, paint in (
        ("Errors", Severity.ERROR, out.red),
        ("Warnings", Severity.WARNING, out.yellow),
        ("Notes", Severity.INFO, out.cyan),
    ):
        group = result.issues_by_severity(severity)
        if not group:
            continue
        out.header(f"{label} ({len(group)})")
        for issue in group:
            print(f"  {paint(issue.code)}  {issue.where()}")
            print(f"      {issue.message}")
            if ctx.args.verbose and issue.detail:
                print(out.dim(f"      {issue.detail}"))

    duplicates = result.duplicate_binds()
    if duplicates:
        out.header(f"Keys bound more than once ({len(duplicates)})")
        for key, defs in duplicates:
            identical = len({d.body for d in defs}) == 1
            note = out.dim("identical") if identical else out.yellow("DIFFERENT")
            print(f"  {key:<16} x{len(defs)}  {note}   (last one wins)")
            for entry in defs:
                print(out.dim(f"      {entry.file}:{entry.line}  {entry.body[:60]}"))

    overrides = result.overridden_settings()
    if overrides:
        out.header(f"Settings written more than once with different values ({len(overrides)})")
        shown = overrides if ctx.args.verbose else overrides[:12]
        for name, defs in shown:
            print(f"  {name}")
            for entry in defs:
                tag = out.green("  <- effective") if entry is defs[-1] else ""
                print(out.dim(f"      {entry.file}:{entry.line} = {entry.value}") + tag)
        if len(shown) < len(overrides):
            print(out.dim(f"  ... {len(overrides) - len(shown)} more; use --verbose"))

    if ctx.args.polish or ctx.args.apply:
        out.header("Polishing")
        session = backup.BackupSession(note=f"cfg polish {folder.name}") if ctx.args.apply else None
        touched = 0
        for key in sorted(result.files):
            config = result.files[key]
            if not config.is_commands:
                continue
            text = config.path.read_bytes().decode(
                config.document.encoding, errors="replace")
            outcome = cfgformat.polish(text, config.relative)

            if not outcome.safe:
                print(f"  {out.yellow('skip')}  {config.relative}")
                print(out.dim(f"        {outcome.skipped_reason}"))
                continue
            if not outcome.changed:
                print(out.dim(f"  ok    {config.relative}  (already tidy)"))
                continue

            touched += 1
            stats = outcome.stats()
            print(f"  {out.green('diff')}  {config.relative}  "
                  + out.dim(f"{stats['lines_touched']} line(s)"))
            if ctx.args.verbose:
                for chunk in outcome.diff.splitlines()[:40]:
                    print(out.dim("        " + chunk))

            if ctx.args.apply and session is not None:
                session.add(config.path)
                cfglang.write_config_text(
                    config.path, outcome.formatted, config.document.encoding)

        print()
        if ctx.args.apply:
            if session is not None and not session.empty:
                print(out.dim(f"  Backup {session.stamp} -> {session.dir}"))
                print(out.dim(f"  Undo with:  cs2cfg revert {session.stamp}"))
            else:
                print(out.dim("  Nothing needed changing."))
        else:
            print(out.dim(f"  Preview only. {touched} file(s) would change; "
                          "add --apply to write them."))
    return 0


def cmd_cfg_rename(ctx: Context) -> int:
    """Rename an alias and every reference to it."""
    from . import cfgedit, cfglang, cfgscan
    from .cfglang import Severity

    out = ctx.out
    folder = Path(ctx.args.folder).expanduser().resolve()
    if not folder.is_dir():
        print(out.red(f"  not a folder: {folder}"))
        return 1

    result = cfgscan.scan(folder)
    try:
        plan = cfgedit.plan_rename(result, ctx.args.old_name, ctx.args.new_name,
                                   include_family=not ctx.args.no_family)
    except cfgedit.EditError as exc:
        print(out.red(f"  {exc}"))
        return 1

    out.header(f"Rename {ctx.args.old_name} -> {ctx.args.new_name}")
    print(out.dim("  Renaming changes the identifier only. The commands the script runs are"))
    print(out.dim("  not modified, so its behaviour is unchanged."))
    print()

    blocking = [i for i in plan.issues if i.severity == Severity.ERROR]
    for issue in plan.issues:
        paint = out.red if issue.severity == Severity.ERROR else out.yellow
        print(f"  {paint(issue.code)}  {issue.message}")
        if issue.detail:
            print(out.dim(f"      {issue.detail}"))
    if plan.issues:
        print()

    if plan.family:
        print("  " + out.bold("Related names moving with it:"))
        for source, target in plan.family:
            print(f"    {source}  ->  {target}")
        print()

    if not plan.edits:
        print(out.dim("  No references found."))
        return 1

    print("  " + out.bold(f"Code changes ({len(plan.edits)}):"))
    for edit in plan.edits:
        print(f"    {edit.file}:{edit.line}  " + out.dim(edit.kind))
        print(out.red(f"      - {edit.before.strip()[:100]}"))
        print(out.green(f"      + {edit.after.strip()[:100]}"))

    if plan.wording_edits:
        print()
        print("  " + out.bold(f"Wording ({len(plan.wording_edits)})")
              + out.dim("  -- comments and messages; opt in with --wording"))
        for edit in plan.wording_edits[:10]:
            print(f"    {edit.file}:{edit.line}")
            print(out.dim(f"      {edit.before.strip()[:96]}"))

    if blocking:
        print()
        print(out.red("  Not applying: the collisions above would make an alias unreachable."))
        return 1

    if not ctx.args.apply:
        print()
        print(out.dim("  Preview only. Add --apply to write these changes."))
        return 0

    edits = list(plan.edits)
    if ctx.args.wording:
        for edit in plan.wording_edits:
            edit.selected = True
        edits += plan.wording_edits

    try:
        updates = cfgedit.apply_edits(result, edits)
    except cfgedit.EditError as exc:
        print(out.red(f"  {exc}"))
        return 1

    session = backup.BackupSession(note=f"cfg rename {ctx.args.old_name} -> {ctx.args.new_name}")
    for relative, text in updates.items():
        config = next(c for c in result.files.values() if c.relative == relative)
        session.add(config.path)
        cfglang.write_config_text(config.path, text, config.document.encoding)
        print("  " + out.green("written") + f"  {relative}")

    print()
    print(out.dim(f"  Backup {session.stamp}; undo with:  cs2cfg revert {session.stamp}"))
    return 0


def cmd_gui(ctx: Context) -> int:
    from .gui import launch as launch_gui

    return launch_gui(ctx.args)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _add_global_options(parser: argparse.ArgumentParser, suppress: bool = False) -> None:
    """Attach the options that apply to every command.

    They are added twice: once to the top-level parser and once to each
    subparser, so both ``cs2cfg --intent quality plan`` and the way people
    actually type it, ``cs2cfg plan --intent quality``, work. The subparser
    copies default to SUPPRESS so an unspecified flag there cannot overwrite
    one that was given before the subcommand.
    """
    def default(value):
        return argparse.SUPPRESS if suppress else value

    parser.add_argument("--no-color", action="store_true", default=default(False),
                        help="disable coloured output")
    parser.add_argument("--steam-root", default=default(None),
                        help="path to the Steam install, if it cannot be found automatically")
    parser.add_argument("--account", default=default(None),
                        help="Steam account id (the numeric userdata folder name)")
    parser.add_argument("--intent", choices=("competitive", "balanced", "quality"),
                        default=default("balanced"),
                        help="what to optimise for (default: balanced)")
    parser.add_argument("--target-fps", type=int, default=default(None),
                        help="override the frame rate target (defaults to your refresh rate)")
    parser.add_argument("--resolution", default=default(None),
                        help="score against a different render resolution, e.g. 1280x960")
    parser.add_argument("--cfg-folder", default=default(DEFAULT_CFG_FOLDER),
                        help=f"config subfolder (default: {DEFAULT_CFG_FOLDER})")
    parser.add_argument("--cfg-name", default=default(DEFAULT_CFG_NAME),
                        help=f"generated config filename (default: {DEFAULT_CFG_NAME})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cs2cfg",
        description="Tune Counter-Strike 2 to the machine it is running on.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Typical use:\n"
            "  cs2cfg scan               see what hardware was detected\n"
            "  cs2cfg plan               dry run: show every change first\n"
            "  cs2cfg apply              write the config, video settings and launch options\n"
            "  cs2cfg revert latest      undo the last apply\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"cs2-autoconfig {__version__}")
    _add_global_options(parser)

    shared = argparse.ArgumentParser(add_help=False)
    _add_global_options(shared, suppress=True)

    sub = parser.add_subparsers(dest="command", parser_class=lambda **kw: argparse.ArgumentParser(**kw))

    sub.add_parser("scan", parents=[shared], help="report detected hardware and Steam accounts")

    for name, help_text in (("plan", "show every change without writing anything"),
                            ("apply", "write the changes")):
        cmd = sub.add_parser(name, parents=[shared], help=help_text)
        cmd.add_argument("--console", action="store_true", default=None,
                         help="ensure -console is in the launch options")
        cmd.add_argument("--no-video", action="store_true", help="do not touch cs2_video.txt")
        cmd.add_argument("--no-launch", action="store_true", help="do not touch Steam launch options")
        cmd.add_argument("--no-cfg", action="store_true", help="do not write a .vcfg file")
        cmd.add_argument("--link-autoexec", action="store_true",
                         help="append an exec line for the generated config to your autoexec")
        if name == "apply":
            cmd.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")

    revert = sub.add_parser("revert", parents=[shared], help="restore a backup set")
    revert.add_argument("stamp", nargs="?", default="latest", help="backup id, or 'latest' (default)")
    revert.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")

    sub.add_parser("backups", parents=[shared], help="list backup sets")

    update = sub.add_parser("update", parents=[shared], help="refresh the hardware tier tables")
    update.add_argument("--url", help="URL of a knowledge bundle")
    update.add_argument("--reset", action="store_true", help="discard local overrides")

    sub.add_parser("calibrate", parents=[shared], help="learn the real setting ranges from your own client")

    use = sub.add_parser("use", parents=[shared], help="pin which Steam account to configure")
    use.add_argument("account_id", help="numeric account id from `cs2cfg scan`")

    play = sub.add_parser(
        "play", parents=[shared],
        help="launch CS2 borderless-stretched so alt-tab stops going black",
        description=(
            "Puts the desktop into your stretched mode, switches CS2 to borderless "
            "windowed, launches through Steam, fits the window to the screen, and puts "
            "the desktop back when you quit. Fixes the multi-monitor alt-tab blackout "
            "by removing its cause: a window never owns the display mode, so there is "
            "nothing to renegotiate."
        ),
    )
    play.add_argument("--width", type=int, help="render width (default: whatever CS2 is set to)")
    play.add_argument("--height", type=int, help="render height")
    play.add_argument("--refresh", type=int, default=0, help="refresh rate for the mode switch")
    play.add_argument("--mode", dest="stretch_mode",
                      choices=("borderless", "fullscreen"), default="borderless",
                      help="'borderless' runs windowed-fullscreen over a stretched desktop, "
                           "which keeps alt-tab instant on multi-monitor setups; 'fullscreen' "
                           "is standard exclusive fullscreen")
    play.add_argument("--no-stretch", action="store_true",
                      help="alias for --mode fullscreen")
    play.add_argument("--no-video-patch", action="store_true",
                      help="leave CS2's own fullscreen settings alone")
    play.add_argument("--no-wait", action="store_true",
                      help="launch and exit immediately (the desktop mode is not restored)")
    play.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")

    stretch = sub.add_parser(
        "stretch", parents=[shared],
        help="borderless / stretched-borderless window control",
        description=(
            "Strip the game window's frame and size it to the monitor. By default the "
            "desktop mode is switched first, which is what makes the result genuinely "
            "stretched rather than merely borderless; use --fill to skip that."
        ),
    )
    stretch.add_argument("--width", type=int, help="render width (default: whatever CS2 is set to)")
    stretch.add_argument("--height", type=int, help="render height")
    stretch.add_argument("--refresh", type=int, default=0, help="refresh rate for the mode switch")
    stretch.add_argument("--process", default="cs2.exe", help="process to target (default: cs2.exe)")
    stretch.add_argument("--fill", action="store_true",
                         help="borderless fill only; do not change the desktop mode")
    stretch.add_argument("--watch", action="store_true",
                         help="apply on launch and undo on exit, like the old tray tools")
    stretch.add_argument("--restore", action="store_true", help="undo the last stretch")
    stretch.add_argument("--list", action="store_true",
                         help="list matching windows ('--process *' for all)")

    shortcut = sub.add_parser(
        "shortcut", parents=[shared],
        help="create a desktop shortcut that launches CS2 seamlessly through Steam",
    )
    shortcut.add_argument("--name", default="Play CS2", help="shortcut name (default: 'Play CS2')")
    shortcut.add_argument("--no-stretch", action="store_true",
                          help="make the shortcut launch borderless at native aspect")

    desktop_parser = sub.add_parser(
        "desktop", parents=[shared],
        help="open the launcher as a desktop application (the default when packaged)",
    )
    desktop_parser.add_argument("--port", type=int,
                                help="fix the local port instead of picking a free one")

    cfg = sub.add_parser(
        "cfg", parents=[shared],
        help="scan and polish a configuration collection",
        description=(
            "Reads a folder of .cfg / .vcfg files, works out the load order and dependencies, "
            "reports diagnostics, and can reformat them without changing what they do."
        ),
    )
    cfg.add_argument("folder", help="folder to scan (searched recursively)")
    cfg.add_argument("--polish", action="store_true", help="preview formatting changes")
    cfg.add_argument("--apply", action="store_true",
                     help="write the formatting changes (backed up first)")
    cfg.add_argument("-v", "--verbose", action="store_true", help="show full detail and diffs")

    rename = sub.add_parser(
        "cfg-rename", parents=[shared],
        help="rename an alias and every reference to it",
        description=(
            "Renames an identifier across every scanned file: the definition, calls, key "
            "bindings and nested redefinitions, plus related _on/_off and +/- names. The "
            "commands a script runs are not touched, so behaviour is unchanged."
        ),
    )
    rename.add_argument("folder", help="folder to scan")
    rename.add_argument("old_name", help="current alias name, e.g. !wallhack")
    rename.add_argument("new_name", help="new alias name")
    rename.add_argument("--no-family", action="store_true",
                        help="rename only this exact name, not its _on/_off or +/- relatives")
    rename.add_argument("--wording", action="store_true",
                        help="also update comments and messages that mention the old name")
    rename.add_argument("--apply", action="store_true",
                        help="write the changes (backed up first)")

    web = sub.add_parser("web", parents=[shared],
                         help="serve the browser interface on localhost")
    # A supervisor that assigns ports passes one in the environment; honour it
    # when no --port is given, so the command works both ways round.
    web.add_argument(
        "--port", type=int, default=int(os.environ.get("PORT") or 8765),
        help="port to bind (default: $PORT, else 8765)")
    web.add_argument("--no-browser", action="store_true", help="do not open a browser window")

    sub.add_parser("gui", parents=[shared], help="open the graphical interface")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        args.command = "gui" if os.environ.get("CS2CFG_DEFAULT_GUI") else "scan"
        if args.command == "scan":
            parser.print_help()
            print()

    # Give every command the flags the shared code expects, even when its own
    # subparser does not define them.
    for flag, default in (
        ("no_video", False), ("no_launch", False), ("no_cfg", False),
        ("link_autoexec", False), ("yes", False), ("console", None),
        ("verbose", False), ("polish", False), ("apply", False),
    ):
        if not hasattr(args, flag):
            setattr(args, flag, default)

    # Remembered choices act as defaults, never as overrides: anything typed on
    # the command line wins. Shared with the web and native front ends so all
    # three start where the last one left off.
    remembered = load_prefs().get("ui", {})
    if remembered:
        explicit = set(argv if argv is not None else sys.argv[1:])
        if "--intent" not in explicit and remembered.get("intent") in ("competitive", "balanced", "quality"):
            args.intent = remembered["intent"]
        if "--target-fps" not in explicit and not args.target_fps and remembered.get("target_fps"):
            try:
                args.target_fps = int(remembered["target_fps"])
            except (TypeError, ValueError):
                pass

    out = Out(colour=not args.no_color)
    handlers = {
        "scan": cmd_scan,
        "plan": cmd_plan,
        "apply": cmd_apply,
        "revert": cmd_revert,
        "backups": cmd_backups,
        "calibrate": cmd_calibrate,
        "use": cmd_use,
        "play": cmd_play,
        "shortcut": cmd_shortcut,
        "stretch": cmd_stretch,
        "web": cmd_web,
        "desktop": cmd_desktop,
        "cfg": cmd_cfg,
        "cfg-rename": cmd_cfg_rename,
        "gui": cmd_gui,
    }

    try:
        ctx = Context(args, out)
        if args.command == "update":
            return cmd_update_reset(ctx) if args.reset else cmd_update(ctx)
        return handlers[args.command](ctx)
    except (ProbeError, steam.SteamError, KnowledgeError) as exc:
        print(out.red(f"\n  {exc}"))
        return 1
    except KeyboardInterrupt:
        print(out.dim("\n  interrupted"))
        return 130


if __name__ == "__main__":
    sys.exit(main())
