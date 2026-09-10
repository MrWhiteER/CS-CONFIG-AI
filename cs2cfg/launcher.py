"""Seamless launcher: fix alt-tab, then start the game through Steam.

The problem this exists for
---------------------------

Exclusive fullscreen means the game owns the display mode. Alt-tabbing forces
Windows to hand the mode back to the desktop and then take it again on return,
and on a high-refresh panel — especially with G-Sync or FreeSync, HDR, or a
second monitor in the mix — that renegotiation is what you experience as the
screen going black for several seconds. CS2 makes it worse by default:
``fullscreen_min_on_focus_loss`` minimises the game outright when it loses
focus, so coming back is a full restore rather than a raise.

Borderless windowed removes the cause rather than shortening the symptom. A
window never owns the display mode, so there is no renegotiation and alt-tab is
instant. The catch is that a 1550x1440 borderless window on a 2560x1440 desktop
is a small window in the corner unless something stretches it.

Stretching is done by switching the *desktop* to the narrow mode and letting
the graphics driver scale it across the panel. The game then runs borderless
at exactly the desktop size: full screen, stretched, and never renegotiating
the display mode when you alt-tab. The desktop is put back when you quit.

There was previously a second mode that resized only the game window, leaving
the desktop native. It relied on CS2 keeping its swapchain at the old size so
the present would scale it up, which is how the CS:GO-era window-stretch tools
worked. CS2 rebuilds the swapchain instead, so the picture came out 16:9 rather
than stretched. The mode is removed rather than left as a choice that does not
do what its name says.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from . import steam, telemetry, window
from .backup import BackupSession

STEAM_RUN_URL = "steam://rungameid/730"
GAME_PROCESS = "cs2.exe"

# Settings the launcher overrides so CS2 cooperates with borderless. These are
# normally on the preserve list, because they are the player's choice; the
# launcher is the one operation whose entire purpose is to change them.
SEAMLESS_VIDEO = {
    "setting.fullscreen": 0,
    "setting.nowindowborder": 1,
    "setting.fullscreen_min_on_focus_loss": 0,
}

# Exclusive fullscreen, for the mode that says so on the label. Written
# explicitly rather than left alone: after a borderless session the config is
# windowed, and a button marked "Fullscreen" has to actually produce that.
EXCLUSIVE_VIDEO = {
    "setting.fullscreen": 1,
    "setting.nowindowborder": 0,
}

EXCLUSIVE_REASONS = {
    "setting.fullscreen": "exclusive fullscreen, the standard way CS2 runs",
    "setting.nowindowborder": "not borderless; the game owns the display mode",
}

SEAMLESS_REASONS = {
    "setting.fullscreen": "windowed instead of exclusive, so alt-tab never renegotiates the display mode",
    "setting.nowindowborder": "no title bar or frame, so the window can sit flush over the whole screen",
    "setting.fullscreen_min_on_focus_loss": "stop CS2 minimising itself the moment it loses focus",
    "setting.monitor_index": "pin the game to the primary display so it cannot open on the wrong screen",
}


class LaunchError(RuntimeError):
    """The game could not be launched or prepared."""


@dataclass
class LaunchPlan:
    width: int
    height: int
    refresh: int
    stretch_mode: str
    video_changes: Dict[str, Tuple[Optional[str], str]] = field(default_factory=dict)
    mode_before: Optional[Tuple[int, int, int]] = None


def prepare_video(
    user: steam.SteamUser,
    session: Optional[BackupSession] = None,
    dry_run: bool = False,
    pin_primary: bool = True,
) -> Dict[str, Tuple[Optional[str], str]]:
    """Switch CS2 itself to borderless windowed.

    Must happen before the game starts: CS2 holds its video config in memory
    and rewrites it on exit, so editing it while the game runs achieves
    nothing.

    ``pin_primary`` also points CS2 at the primary display. On a multi-monitor
    desktop the game will otherwise sometimes open on whichever screen it used
    last, and a borderless window on the wrong monitor is worse than useless.
    """
    wanted = dict(SEAMLESS_VIDEO)
    if pin_primary:
        try:
            wanted["setting.monitor_index"] = window.primary_monitor_index()
        except OSError:
            pass

    current = steam.read_video_cfg(user)
    diff = {
        key: (current.get(key), str(value))
        for key, value in wanted.items()
        if current.get(key) != str(value)
    }
    if diff and not dry_run:
        steam.write_video_cfg(user, wanted, session)
    return diff


CONFLICTING_FLAGS = ("-fullscreen", "-full", "-sw")


def ensure_windowed_launch_options(
    user: steam.SteamUser,
    session: Optional[BackupSession] = None,
    report: Optional[Callable[[str, str], None]] = None,
) -> bool:
    """Strip anything forcing fullscreen out of the Steam launch options.

    A launch option outranks the video config, so a leftover ``-fullscreen``
    quietly undoes every windowed setting written here and hands back the
    alt-tab blackout. Returns True if the options are (now) safe.
    """
    say = report or (lambda message, tag="": None)
    current = steam.read_launch_options(user)
    tokens = current.split()
    offenders = [t for t in tokens if t.lower() in CONFLICTING_FLAGS]
    if not offenders:
        return True

    if steam.steam_running():
        say(f"  launch options contain {' '.join(offenders)}, which forces fullscreen", "bad")
        say("  Steam is open, so this cannot be fixed now. Close Steam and re-run,", "dim")
        say("  or the game will start fullscreen no matter what is set here.", "dim")
        return False

    from .kb import KnowledgeBase
    from .profile import plan_launch_options

    machine_stub = None
    try:
        from .hardware import detect

        machine_stub = detect()
    except Exception:  # detection is only needed for the -high rule
        pass

    plan = plan_launch_options(current, machine_stub, KnowledgeBase(), window_mode="windowed") \
        if machine_stub is not None else None
    if plan is None:
        # Fall back to a plain removal if hardware detection failed.
        kept = [t for t in tokens if t.lower() not in CONFLICTING_FLAGS]
        if "-windowed" not in kept:
            kept.append("-windowed")
        if "-noborder" not in kept:
            kept.append("-noborder")
        new_line = " ".join(kept)
    else:
        new_line = plan.line

    steam.write_launch_options(user, new_line, session)
    say(f"  removed {' '.join(offenders)} from the Steam launch options", "good")
    say(f"      {new_line}", "dim")
    return True


def apply_video(
    user: steam.SteamUser,
    wanted: Dict[str, int],
    session: Optional[BackupSession] = None,
) -> Dict[str, Tuple[Optional[str], str]]:
    """Write a set of video settings, returning only what actually changed."""
    current = steam.read_video_cfg(user)
    diff = {
        key: (current.get(key), str(value))
        for key, value in wanted.items()
        if current.get(key) != str(value)
    }
    if diff:
        steam.write_video_cfg(user, wanted, session)
    return diff


def steam_is_installed() -> bool:
    try:
        steam.find_steam_root()
        return True
    except steam.SteamError:
        return False


def launch_via_steam() -> None:
    """Ask Steam to run CS2.

    The URL protocol is the right entry point rather than running the exe
    directly: it starts Steam if it is closed, applies the launch options
    stored against the app, and keeps the game properly parented to Steam for
    overlay and cloud sync.
    """
    try:
        os.startfile(STEAM_RUN_URL)  # noqa: S606 - a protocol handler, not a shell command
        return
    except (AttributeError, OSError):
        pass

    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", STEAM_RUN_URL],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise LaunchError(f"could not hand {STEAM_RUN_URL} to Steam: {exc}") from exc


def wait_for_window(
    timeout: float = 180.0,
    interval: float = 1.0,
    on_tick: Optional[Callable[[float], None]] = None,
) -> Optional[window.WindowInfo]:
    """Poll until the game window appears, or give up."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = window.find_game_window(GAME_PROCESS)
        # A freshly created window is often still 0x0 or a tiny splash; wait
        # for something plausibly the render target.
        if found is not None and found.size[0] > 200 and found.size[1] > 200:
            return found
        if on_tick:
            on_tick(deadline - time.monotonic())
        time.sleep(interval)
    return None


def wait_for_exit(
    interval: float = 1.0,
    on_tick: Optional[Callable[[], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> bool:
    """Block until the game window is gone. Returns True if it actually exited.

    Requires two consecutive misses, because CS2 briefly destroys and recreates
    its window during some resolution and device changes. At a one second
    interval that costs at most two seconds of lag before the desktop is
    restored; it used to be three, which felt like the tool had hung.
    """
    misses = 0
    while misses < 2:
        if should_stop and should_stop():
            return False
        if window.find_game_window(GAME_PROCESS) is None:
            misses += 1
        else:
            misses = 0
            if on_tick:
                on_tick()
        time.sleep(interval)
    return True


def play(
    user: steam.SteamUser,
    width: int,
    height: int,
    refresh: int = 0,
    stretch_mode: str = "borderless",
    patch_video: bool = True,
    wait: bool = True,
    session: Optional[BackupSession] = None,
    say: Optional[Callable[[str, str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    phase: Optional[Callable[[str], None]] = None,
) -> int:
    """The whole sequence: prepare, switch mode, launch, fit, restore.

    Returns a process-style exit code.
    """
    report = say or (lambda message, tag="": None)
    mark = phase or (lambda name: None)
    mark("preparing")

    if window.find_game_window(GAME_PROCESS) is not None:
        raise LaunchError("CS2 is already running. Close it first, or use `cs2cfg stretch` on the running window.")

    if not steam_is_installed():
        raise LaunchError("Steam could not be located, so the game cannot be launched through it.")

    # 1. Put CS2 into the display mode this launch actually asked for, before
    #    it starts: CS2 holds its video config in memory and rewrites it on
    #    exit, so editing it once the game is up achieves nothing.
    if patch_video:
        if stretch_mode == "fullscreen":
            diff = apply_video(user, EXCLUSIVE_VIDEO, session)
            for key, (before, after) in diff.items():
                report(f"  {key.replace('setting.', ''):<32} {before} -> {after}", "good")
                report(f"      {EXCLUSIVE_REASONS.get(key, '')}", "dim")
            if not diff:
                report("  CS2 is already set to exclusive fullscreen", "dim")
            if len(getattr(user, "_displays", ()) or ()) != 1:
                report("  note: exclusive fullscreen owns the display mode, so alt-tab has to", "warn")
                report("  renegotiate it. That is the black screen, and it is worst with more", "dim")
                report("  than one monitor. The windowed-fullscreen mode avoids it.", "dim")
        else:
            diff = prepare_video(user, session)
            if diff:
                for key, (before, after) in diff.items():
                    report(f"  {key.replace('setting.', ''):<32} {before} -> {after}", "good")
                    report(f"      {SEAMLESS_REASONS.get(key, '')}", "dim")
            else:
                report("  CS2 is already set to borderless windowed", "dim")

            # The video config is only half of it. A -fullscreen in the launch
            # options outranks everything above, so check that too.
            ensure_windowed_launch_options(user, session, report)

    # 2. Only the borderless mode touches the display. Exclusive fullscreen
    #    takes the mode itself, so switching the desktop first would just be
    #    undone by the game.
    mode_before: Optional[Tuple[int, int, int]] = None
    if stretch_mode == "borderless":
        mark("switching")
        mode_before = window.current_mode()
        if (mode_before[0], mode_before[1]) == (width, height):
            report(f"  desktop is already {width}x{height}", "dim")
            mode_before = None
        else:
            try:
                window.set_mode(width, height, refresh, test_only=True)
            except window.WindowError as exc:
                raise LaunchError(
                    f"{exc}. Create the mode with Custom Resolution Utility, or use the standard fullscreen mode."
                ) from exc
            window.set_mode(width, height, refresh)
            report(f"  desktop  {mode_before[0]}x{mode_before[1]}@{mode_before[2]} -> "
                   f"{width}x{height}@{refresh or mode_before[2]}", "good")
            time.sleep(0.5)

    # 3. Hand off to Steam.
    try:
        mark("launching")
        report("  launching through Steam...", "")
        launch_via_steam()

        if not wait:
            report("  launched; not waiting (desktop mode will not be restored automatically)", "warn")
            return 0

        # CS2 writes its own settings on shutdown, so a snapshot taken now is
        # the "before" for whatever gets changed in the menus this session.
        try:
            from . import gamewatch
            settings_before = gamewatch.take(user.video_cfg.parent)
        except Exception:
            settings_before = None

        mark("waiting")
        found = wait_for_window()
        if found is None:
            raise LaunchError("the game window never appeared within three minutes")

        report(f"  window   {found.title or GAME_PROCESS}  "
               f"{found.size[0]}x{found.size[1]}", "good")

        # 4. Sit it flush over the screen. With the desktop already at the
        #    target mode this is usually a no-op, but it corrects CS2 when it
        #    places the window off-origin or a pixel short.
        time.sleep(1.5)
        fresh = window.find_game_window(GAME_PROCESS) or found
        if stretch_mode == "borderless":
            new_w, new_h = window.make_borderless(fresh)
            report(f"  fitted   {new_w}x{new_h} borderless at the screen origin", "good")
        else:
            new_w, new_h = fresh.size
            report("  exclusive fullscreen; the window is left to the game", "dim")

        report("", "")
        if stretch_mode == "borderless":
            report("  Alt-tab should now be instant. Waiting for you to quit...", "dim")
        else:
            report("  Running fullscreen. Waiting for you to quit...", "dim")
        mark("running")

        desktop_now = window.current_mode()
        recorder = telemetry.SessionRecorder(fresh.hwnd, {
            "resolution": f"{new_w}x{new_h}",
            "desktop_mode": f"{desktop_now[0]}x{desktop_now[1]}@{desktop_now[2]}",
            "stretched": stretch_mode == "borderless",
            "stretch_mode": stretch_mode,
            "borderless": stretch_mode == "borderless",
        })
        recorder.start()

        # Keep the stretch. The desktop mode is deliberately temporary (see
        # window.set_mode), so Windows hands it back whenever it re-evaluates
        # the display topology -- a monitor sleeping, the session locking,
        # another application taking exclusive fullscreen and releasing it.
        # Until now nothing re-asserted it, so the stretch was simply lost for
        # the rest of the session. This checks each tick and acts only on drift.
        heal = {"last": 0.0, "count": 0}
        COOLDOWN = 5.0

        def keep_stretched() -> None:
            if stretch_mode != "borderless":
                return
            now = time.monotonic()
            if now - heal["last"] < COOLDOWN:
                return
            try:
                state = window.check_stretch(width, height, GAME_PROCESS)
            except window.WindowError:
                return
            if state["mode_ok"] and state["window_ok"]:
                return
            heal["last"] = now
            try:
                fix = window.repair_stretch(width, height, GAME_PROCESS, refresh)
            except window.WindowError as exc:
                report(f"  could not restore the stretch: {exc}", "warn")
                return
            for line in fix["actions"]:
                heal["count"] += 1
                report(f"  restored {line}", "warn")

        try:
            exited = wait_for_exit(should_stop=should_stop, on_tick=keep_stretched)
        finally:
            record = recorder.stop()
            if heal["count"]:
                report(f"  put the stretch back {heal['count']} time(s) during the session",
                       "warn")

        report("  game closed" if exited else "  stopped early at your request", "")

        # Only meaningful once CS2 has actually exited and flushed its files.
        if exited and settings_before is not None:
            try:
                from . import gamewatch
                after = gamewatch.take(user.video_cfg.parent)
                changed = gamewatch.compare(settings_before, after)
                if changed:
                    report(f"  you changed {len(changed)} setting(s) in-game:", "warn")
                    for entry in changed[:12]:
                        report(f"    {entry.describe()}", "warn")
                    if len(changed) > 12:
                        report(f"    and {len(changed) - 12} more", "dim")
                gamewatch.save_baseline(user.account_id, after)
            except Exception as exc:
                report(f"  could not compare in-game settings: {exc}", "dim")
        report(f"  played for {round(record.duration / 60, 1)} min", "")
        for note in record.notes:
            report(f"  {note}", "dim")
        return 0

    finally:
        # 5. Always give the desktop back, including on Ctrl+C or a failure.
        mark("restoring")
        if mode_before is not None:
            try:
                window.restore_mode()
                report(f"  desktop restored to {mode_before[0]}x{mode_before[1]}@{mode_before[2]}", "good")
            except window.WindowError as exc:
                report(f"  could not restore the desktop mode: {exc}", "bad")
                report(f"  set it back manually: {mode_before[0]}x{mode_before[1]} @ {mode_before[2]} Hz", "dim")


class LaunchSession:
    """A run of :func:`play` on its own thread, with a pollable status.

    The web front end cannot block for the length of a gaming session, so it
    starts one of these and polls. Everything it needs to render lives in
    :meth:`snapshot`.
    """

    PHASES = ("idle", "preparing", "switching", "launching", "waiting",
              "running", "restoring", "done", "error")

    def __init__(self, user: steam.SteamUser, width: int, height: int,
                 refresh: int = 0, stretch_mode: str = "borderless",
                 patch_video: bool = True) -> None:
        self.user = user
        self.width = width
        self.height = height
        self.refresh = refresh
        self.stretch_mode = stretch_mode
        self.patch_video = patch_video

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.phase = "idle"
        self.error: Optional[str] = None
        self.backup_stamp: Optional[str] = None
        self.started_at: Optional[float] = None
        self.lines: List[Dict[str, str]] = []

    # -- plumbing ---------------------------------------------------------
    def _say(self, message: str, tag: str = "") -> None:
        with self._lock:
            self.lines.append({"text": message.strip(), "tag": tag})

    def _phase(self, name: str) -> None:
        with self._lock:
            self.phase = name

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "phase": self.phase,
                "active": self.active,
                "error": self.error,
                "backup": self.backup_stamp,
                "elapsed": round(time.monotonic() - self.started_at, 1) if self.started_at else 0,
                "lines": list(self.lines),
            }

    # -- control ----------------------------------------------------------
    def start(self) -> None:
        if self.active:
            raise LaunchError("a launch is already in progress")
        self._stop.clear()
        self.error = None
        self.lines = []
        self.started_at = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True, name="cs2cfg-launch")
        self._thread.start()

    def stop(self, close_game: bool = False, force: bool = True) -> str:
        """Stop watching, and optionally close the game itself.

        Without ``close_game`` this only ends the watch and restores the
        desktop, leaving CS2 running — which is what you want if you meant to
        keep playing. With it, the game is asked to close and then ended if it
        will not.
        """
        result = ""
        if close_game:
            found = window.find_game_window(GAME_PROCESS)
            if found is None:
                result = "the game was not running"
            else:
                result = window.close_process_window(found.hwnd, force=force)
                self._say(f"  {result}", "good" if "closed" in result or "ended" in result else "warn")
        self._stop.set()
        return result

    def _run(self) -> None:
        session = BackupSession(note="play: seamless borderless launch")
        try:
            play(
                self.user, self.width, self.height, self.refresh,
                stretch_mode=self.stretch_mode, patch_video=self.patch_video, wait=True,
                session=session, say=self._say,
                should_stop=self._stop.is_set, phase=self._phase,
            )
            self._phase("done")
        except (LaunchError, steam.SteamError, window.WindowError) as exc:
            with self._lock:
                self.error = str(exc)
            self._say(f"  {exc}", "bad")
            self._phase("error")
        except Exception as exc:  # never leave the page spinning on a surprise
            with self._lock:
                self.error = f"{type(exc).__name__}: {exc}"
            self._say(f"  unexpected failure: {exc}", "bad")
            self._phase("error")
        finally:
            if not session.empty:
                with self._lock:
                    self.backup_stamp = session.stamp
