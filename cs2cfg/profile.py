"""The decision engine: hardware in, a settings plan out.

Everything here is a heuristic, and every heuristic is written down rather
than buried in a magic number. The aim is not to predict your frame rate to
the digit; it is to place the machine in the right band relative to the
display it has to feed, and to be honest about how it got there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .hardware import Machine
from .kb import KnowledgeBase, Match

INTENTS = ("competitive", "balanced", "quality")
TIERS = ("S", "A", "B", "C", "D")

# How much of the theoretical frame rate each intent gives away for looks.
INTENT_COST = {"competitive": 1.00, "balanced": 0.80, "quality": 0.60}

# Tiering is measured at this cost regardless of what the user asked for, so
# that the tier describes the hardware rather than the request.
TIER_REFERENCE_INTENT = "balanced"

# Headroom (estimated fps / target fps) required to earn each tier.
TIER_THRESHOLDS = ((2.00, "S"), (1.50, "A"), (1.15, "B"), (0.85, "C"))

# Model constants, calibrated against what the reference parts actually do in
# CS2. A single-thread index of 100 (a 14900K) sustains roughly 550 fps at
# competitive settings. A GPU index of 100 (a 4090) is worth roughly 1400 fps
# at 1080p low, far above any CPU, which is why CS2 is a CPU-bound game in
# practice and why the CPU table carries more weight than the GPU one.
CPU_FPS_PER_INDEX = 5.5
GPU_FPS_PER_INDEX_1080P = 14.0
PIXELS_1080P = 1920 * 1080

# Resolution scaling is sublinear: doubling pixels does not halve the frame
# rate, because part of the frame cost is fixed per-draw work.
PIXEL_EXPONENT = 0.85

# How much the two ceilings interfere when they are evenly matched. At worst,
# a perfectly balanced CPU and GPU lose about 15% to imperfect overlap; when
# one part dominates, the result converges on that part's ceiling alone.
CONTENTION = 0.15


@dataclass
class Advisory:
    """Something worth telling the user that this tool will not change itself."""

    level: str  # "warn" | "info"
    title: str
    detail: str


@dataclass
class LaunchPlan:
    options: List[str]
    removed: List[Tuple[str, str]] = field(default_factory=list)
    kept: List[str] = field(default_factory=list)
    added: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def line(self) -> str:
        return " ".join(self.options)


@dataclass
class Profile:
    machine: Machine
    intent: str
    tier: str
    gpu_match: Match
    cpu_match: Match
    target_fps: int
    estimated_fps: int
    cpu_ceiling: int
    gpu_ceiling: int
    headroom: float
    video: Dict[str, int]
    video_reasons: Dict[str, str]
    convars: List[Tuple[str, str, str]]
    advisories: List[Advisory]
    bottleneck: str


def _resolve_target(machine: Machine, override_fps: Optional[int]) -> Tuple[int, Optional[Advisory]]:
    """Decide what frame rate we are aiming for, and flag a shaky guess."""
    if override_fps:
        return override_fps, None

    display = machine.primary_display
    if not display:
        return 240, Advisory(
            "warn",
            "No display detected",
            "Falling back to a 240 fps target. Pass --target-fps to set this yourself.",
        )

    if not display.confident_refresh:
        return display.refresh, Advisory(
            "info",
            f"Refresh rate read as {display.refresh} Hz, but only from the monitor's EDID table",
            "Windows would not hand over the live display mode from this context. If the panel is faster "
            "than that, re-run from a normal desktop session or pass --target-fps.",
        )

    return display.refresh, None


def _render_pixels(machine: Machine, override: Optional[Tuple[int, int]]) -> int:
    if override:
        return override[0] * override[1]
    display = machine.primary_display
    return display.pixels if display else PIXELS_1080P


def estimate_fps(cpu_index: float, gpu_index: float, pixels: int, intent: str) -> Tuple[int, int, int, str]:
    """Estimate a frame rate and name the limiting part.

    The result is a soft minimum of the two ceilings rather than a hard one.
    A hard ``min`` ignores that the parts contend for each other; a harmonic
    mean over-corrects badly, halving the estimate whenever the two ceilings
    happen to be equal. What actually happens is a modest loss that peaks when
    the parts are evenly matched and vanishes when one clearly dominates, so
    that is what this models.
    """
    quality = INTENT_COST.get(intent, 0.8)

    cpu_ceiling = cpu_index * CPU_FPS_PER_INDEX
    gpu_ceiling = gpu_index * GPU_FPS_PER_INDEX_1080P
    gpu_ceiling *= (PIXELS_1080P / max(pixels, 1)) ** PIXEL_EXPONENT
    gpu_ceiling *= quality

    if cpu_ceiling <= 0 or gpu_ceiling <= 0:
        combined = max(cpu_ceiling, gpu_ceiling, 1.0)
    else:
        lower = min(cpu_ceiling, gpu_ceiling)
        upper = max(cpu_ceiling, gpu_ceiling)
        combined = lower * (1.0 - CONTENTION * (lower / upper))

    ratio = gpu_ceiling / cpu_ceiling if cpu_ceiling else 1.0
    if ratio > 1.35:
        bottleneck = "CPU"
    elif ratio < 0.75:
        bottleneck = "GPU"
    else:
        bottleneck = "evenly matched"

    return int(combined), int(cpu_ceiling), int(gpu_ceiling), bottleneck


def _tier_for(headroom: float) -> str:
    for threshold, tier in TIER_THRESHOLDS:
        if headroom >= threshold:
            return tier
    return "D"


def _condition_met(condition: str, ctx: Dict[str, Any]) -> bool:
    """Evaluate one named condition from the settings matrix."""
    checks = {
        "always": lambda: True,
        "gpu_reflex": lambda: ctx["reflex"],
        "not_gpu_reflex": lambda: not ctx["reflex"],
        "vram_below_6": lambda: 0 < ctx["vram_gb"] < 6,
        "pixels_above_4mp_and_tier_below_s": lambda: ctx["pixels"] > 4_000_000 and ctx["tier"] != "S",
        "headroom_above_1_3": lambda: ctx["headroom"] > 1.3,
        # CS2 is CPU-bound on most competitive machines. Where the graphics
        # card can already draw more frames than the processor can feed it,
        # turning GPU-side quality down buys nothing at all -- the processor
        # is still the wall -- and only makes the picture worse.
        "gpu_ahead_of_cpu": lambda: ctx["gpu_ratio"] > 1.15,
    }
    check = checks.get(condition)
    return bool(check and check())


def _build_advisories(machine: Machine, current_video: Dict[str, str], kb: KnowledgeBase) -> List[Advisory]:
    out: List[Advisory] = []

    plan = (machine.power_plan or "").lower()
    if plan and "high performance" not in plan and "ultimate" not in plan:
        out.append(Advisory(
            "warn",
            f"Windows power plan is '{machine.power_plan}'",
            "Balanced parks cores and ramps clocks lazily, which shows up as frametime spikes. "
            "Switch to High performance in Control Panel > Power Options.",
        ))

    if machine.ram_gb and machine.ram_gb < 12:
        out.append(Advisory(
            "warn",
            f"{machine.ram_gb:g} GB of system memory",
            "CS2 wants 12 GB or more to avoid paging mid-round. This is usually the cheapest upgrade available.",
        ))

    if machine.gpu and machine.gpu.driver_date:
        try:
            year = int(machine.gpu.driver_date[:4])
            if year <= 2024:
                out.append(Advisory(
                    "info",
                    f"Graphics driver dates from {machine.gpu.driver_date}",
                    "CS2 has had several driver-side performance fixes. Worth updating before trusting any benchmark.",
                ))
        except ValueError:
            pass

    if current_video.get("setting.mat_vsync") == "1":
        out.append(Advisory(
            "warn",
            "V-Sync is currently enabled",
            "It adds roughly a frame of latency and caps you at the refresh rate. This tool turns it off; "
            "if you enabled it deliberately to stop tearing, use the monitor's own sync instead.",
        ))

    if current_video.get("setting.fullscreen") == "1" and len(machine.displays) > 1:
        minimises = current_video.get("setting.fullscreen_min_on_focus_loss") == "1"
        out.append(Advisory(
            "warn",
            f"Exclusive fullscreen on {len(machine.displays)} monitors"
            + (", and CS2 minimises itself on focus loss" if minimises else ""),
            "This is the alt-tab blackout: exclusive fullscreen owns the display mode, so leaving and "
            "returning forces Windows to renegotiate it, which is the several seconds of black screen. "
            "`cs2cfg play` removes the cause by running the game borderless over a stretched desktop.",
        ))

    display = machine.primary_display
    if display and display.confident_refresh:
        try:
            configured = int(current_video.get("setting.refreshrate_numerator", "0"))
            if configured and configured < display.refresh - 5:
                out.append(Advisory(
                    "warn",
                    f"CS2 is set to {configured} Hz on a {display.refresh} Hz panel",
                    "You are leaving refresh rate on the table. Check the in-game display settings.",
                ))
        except ValueError:
            pass

    return out


def _fps_max_value(headroom: float, target: int, estimated: int) -> Tuple[str, str]:
    """Choose fps_max, and explain the choice.

    A cap only smooths frametimes if the machine can hit it on every frame.
    When there is no headroom a cap just costs frames, so it stays off.
    """
    if headroom >= 1.5:
        return "0", "uncapped: the machine clears the refresh rate with room to spare"
    if headroom >= 1.0:
        return "0", "uncapped: capping here would cost frames you can actually use"
    return "0", "uncapped: the machine is already below the refresh rate, so a cap can only hurt"


def build_profile(
    machine: Machine,
    kb: KnowledgeBase,
    intent: str = "balanced",
    target_fps: Optional[int] = None,
    resolution: Optional[Tuple[int, int]] = None,
    current_video: Optional[Dict[str, str]] = None,
) -> Profile:
    """Score the machine and produce a complete settings plan."""
    if intent not in INTENTS:
        raise ValueError(f"unknown intent {intent!r}; expected one of {', '.join(INTENTS)}")

    current_video = current_video or {}
    advisories: List[Advisory] = []

    gpu_match = kb.match_gpu(machine.gpu.name) if machine.gpu else Match(15.0, None, False, "no GPU detected")
    cpu_match = kb.match_cpu(machine.cpu.name, machine.cpu.max_clock_mhz) if machine.cpu else Match(40.0, None, False, "no CPU detected")

    target, target_advisory = _resolve_target(machine, target_fps)
    if target_advisory:
        advisories.append(target_advisory)

    pixels = _render_pixels(machine, resolution)

    # The tier is a statement about the machine, so it is measured against a
    # fixed reference cost rather than the chosen intent. Deriving it from the
    # intent creates a feedback loop: asking for "quality" raises the cost,
    # which lowers the headroom, which lowers the tier, which hands back worse
    # settings than "balanced" would have. That is the opposite of what was
    # asked for, so tiering and intent are kept independent.
    reference_fps, _, _, _ = estimate_fps(
        cpu_match.index, gpu_match.index, pixels, TIER_REFERENCE_INTENT
    )
    tier = _tier_for(reference_fps / target if target else 1.0)

    # The reported estimate uses the intent actually chosen, so the cost of
    # that choice stays visible even though it no longer moves the tier.
    estimated, cpu_ceiling, gpu_ceiling, bottleneck = estimate_fps(
        cpu_match.index, gpu_match.index, pixels, intent
    )
    headroom = estimated / target if target else 1.0

    # --- video settings ---------------------------------------------------
    matrix = kb.video["intents"][intent]["tiers"][tier]
    video: Dict[str, int] = {}
    reasons: Dict[str, str] = {}
    for key, value in matrix.items():
        video[key] = kb.clamp(key, int(value))
        reasons[key] = f"tier {tier}, {intent} profile"

    reflex = bool(machine.gpu and machine.gpu.is_nvidia and gpu_match.entry.get("reflex"))
    ctx = {
        "reflex": reflex,
        "vram_gb": machine.gpu.vram_gb if machine.gpu else 0.0,
        "pixels": pixels,
        "tier": tier,
        "headroom": headroom,
        "gpu_ratio": (gpu_ceiling / cpu_ceiling) if cpu_ceiling else 1.0,
    }
    for adjustment in kb.video.get("adjustments", []):
        if not _condition_met(adjustment.get("when", ""), ctx):
            continue
        for key, value in (adjustment.get("set") or {}).items():
            video[key] = kb.clamp(key, int(value))
            reasons[key] = adjustment.get("reason", adjustment.get("id", ""))

    # --- console convars --------------------------------------------------
    fps_max, fps_reason = _fps_max_value(headroom, target, estimated)
    convars: List[Tuple[str, str, str]] = [
        ("fps_max", fps_max, fps_reason),
        ("fps_max_ui", str(target), "menus have no reason to render faster than the panel"),
        ("engine_no_focus_sleep", "0", "keeps the frame rate up when the window loses focus"),
        ("rate", "786432", "CS2's own default and maximum; old configs carry a CS:GO-era 128000 downgrade"),
    ]

    advisories.extend(_build_advisories(machine, current_video, kb))

    if headroom < 1.0:
        advisories.append(Advisory(
            "warn",
            f"The {intent} profile is estimated at ~{estimated} fps, under your {target} fps target",
            f"Tier {tier} is what the hardware can carry; this intent spends more of it on looks. "
            "Switch to balanced or competitive if you would rather keep the frames.",
        ))

    if not gpu_match.exact and machine.gpu:
        advisories.append(Advisory(
            "info",
            f"'{machine.gpu.name}' is not in the tier table",
            f"Scored as {gpu_match.index:.0f} ({gpu_match.note}). Add it to knowledge/gpus.json for an exact placement.",
        ))
    if not cpu_match.exact and machine.cpu:
        advisories.append(Advisory(
            "info",
            f"'{machine.cpu.name}' is not in the tier table",
            f"Scored as {cpu_match.index:.0f} ({cpu_match.note}). Add it to knowledge/cpus.json for an exact placement.",
        ))

    return Profile(
        machine=machine,
        intent=intent,
        tier=tier,
        gpu_match=gpu_match,
        cpu_match=cpu_match,
        target_fps=target,
        estimated_fps=estimated,
        cpu_ceiling=cpu_ceiling,
        gpu_ceiling=gpu_ceiling,
        headroom=headroom,
        video=video,
        video_reasons=reasons,
        convars=convars,
        advisories=advisories,
        bottleneck=bottleneck,
    )


# ---------------------------------------------------------------------------
# Launch options
# ---------------------------------------------------------------------------

_ATTACHED_VALUE = re.compile(r"^(-w|-h|-refresh|-freq)(\d+)$")


def parse_launch_options(text: str, kb: KnowledgeBase) -> List[Tuple[str, Optional[str]]]:
    """Split a launch string into ``(flag, value)`` pairs.

    Handles both spellings people use in the wild: ``-w 1920`` and ``-w1920``.
    """
    spec = kb.launch["options"]
    tokens = text.split()
    out: List[Tuple[str, Optional[str]]] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]

        attached = _ATTACHED_VALUE.match(token)
        if attached:
            out.append((attached.group(1), attached.group(2)))
            i += 1
            continue

        if token.startswith(("-", "+")):
            entry = spec.get(token, {})
            if entry.get("takes_value") and i + 1 < len(tokens) and not tokens[i + 1].startswith(("-", "+")):
                out.append((token, tokens[i + 1]))
                i += 2
            else:
                out.append((token, None))
                i += 1
            continue

        # A bare token with no flag in front of it: keep it so we never
        # silently eat something we failed to understand.
        out.append((token, None))
        i += 1
    return out


def plan_launch_options(
    current: str,
    machine: Machine,
    kb: KnowledgeBase,
    exec_path: Optional[str] = None,
    want_console: Optional[bool] = None,
    window_mode: Optional[str] = None,
) -> LaunchPlan:
    """Transform the existing launch options rather than replacing them.

    Resolution and language are the player's decisions and are carried across
    untouched. What gets removed is the CS:GO folklore that CS2 ignores, plus
    anything measurably harmful.

    ``window_mode`` is the one thing that overrides player intent, and only
    when a caller has an explicit reason: the launcher sets ``"windowed"``
    because a stray ``-fullscreen`` silently defeats everything it is trying to
    do. Left as ``None`` the display flags are passed through as found.
    """
    spec = kb.launch["options"]
    parsed = parse_launch_options(current, kb)

    kept: List[Tuple[str, Optional[str]]] = []
    removed: List[Tuple[str, str]] = []
    added: List[Tuple[str, str]] = []
    seen = set()

    for flag, value in parsed:
        entry = spec.get(flag)
        if entry is None:
            kept.append((flag, value))
            seen.add(flag)
            continue

        status = entry.get("status")
        printable = flag if value is None else f"{flag} {value}"

        if status in ("dead", "invalid"):
            removed.append((printable, entry.get("reason", "")))
            continue

        if status == "harmful":
            floor = entry.get("safe_minimum")
            if floor and value and value.isdigit() and int(value) < floor:
                removed.append((printable, entry.get("reason", "")))
                continue
            if floor:
                kept.append((flag, value))
                seen.add(flag)
                continue
            removed.append((printable, entry.get("reason", "")))
            continue

        if flag == "-high" and machine.cpu and machine.cpu.likely_hybrid:
            removed.append((
                printable,
                "Intel hybrid CPU detected. High priority can interfere with how the Thread Director "
                "places the render thread across P and E cores, so it comes off here.",
            ))
            continue

        kept.append((flag, value))
        seen.add(flag)

    # Note: an invalid -full is dropped and NOT "corrected" to -fullscreen.
    # Substituting a working flag for a broken one changes behaviour the player
    # never asked for -- -full did nothing, so CS2's own video settings decided
    # the display mode, and forcing -fullscreen takes that decision away. With
    # it simply gone, the video config stays in charge, which is where the
    # setting belongs.

    if window_mode == "windowed":
        # A launch option beats the video config, so anything forcing exclusive
        # fullscreen has to go or the windowed setting is ignored.
        for flag in ("-fullscreen", "-full"):
            if flag in seen:
                kept = [(f, v) for f, v in kept if f != flag]
                seen.discard(flag)
                removed.append((flag, "forces exclusive fullscreen, which overrides the windowed "
                                      "video setting and brings back the alt-tab blackout"))
        if "-windowed" not in seen:
            kept.append(("-windowed", None))
            seen.add("-windowed")
            added.append(("-windowed", "run windowed so the game never owns the display mode"))
        if "-noborder" not in seen:
            kept.append(("-noborder", None))
            seen.add("-noborder")
            added.append(("-noborder", "no frame, so the window can sit flush over the screen"))
    elif window_mode == "fullscreen":
        for flag in ("-windowed", "-noborder", "-sw"):
            if flag in seen:
                kept = [(f, v) for f, v in kept if f != flag]
                seen.discard(flag)
                removed.append((flag, "conflicts with the requested exclusive fullscreen"))
        if "-fullscreen" not in seen:
            kept.append(("-fullscreen", None))
            seen.add("-fullscreen")
            added.append(("-fullscreen", "requested exclusive fullscreen"))

    if "-novid" not in seen:
        kept.append(("-novid", None))
        seen.add("-novid")
        added.append(("-novid", "skips the intro movie"))

    if want_console and "-console" not in seen:
        kept.append(("-console", None))
        seen.add("-console")
        added.append(("-console", "opens the developer console at startup"))

    if exec_path and "+exec" not in seen:
        kept.append(("+exec", exec_path))
        seen.add("+exec")
        added.append((f"+exec {exec_path}", "loads your config at startup"))

    order = kb.launch.get("build_order", [])

    def sort_key(item: Tuple[str, Optional[str]]) -> Tuple[int, str]:
        flag = item[0]
        return (order.index(flag) if flag in order else len(order), flag)

    ordered = sorted(kept, key=sort_key)
    options = [f"{flag} {value}" if value else flag for flag, value in ordered]

    return LaunchPlan(
        options=options,
        removed=removed,
        kept=[f if v is None else f"{f} {v}" for f, v in ordered],
        added=added,
    )
