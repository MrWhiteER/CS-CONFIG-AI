# Overlay step 0: prototype and measure

Plan (approved by Edy 2026-11-14): https://claude.ai/artifact/D1wTHRxbeuvvNdK9ZRbBW9

Goal of this step: prove, on a real PC with CS2 running, that an external overlay
(1) shows over CS2 in Fullscreen Windowed, (2) costs almost nothing, and
(3) gets real frame-time data from outside the game. This is a spike: keep it
small, no UI polish, no app integration beyond a CLI entry point.

## Hard safety rules (VAC / FACEIT). Never break these.

1. Never open cs2.exe with PROCESS_VM_READ / VM_WRITE / VM_OPERATION / ALL_ACCESS.
   At most PROCESS_QUERY_LIMITED_INFORMATION (like cs2cfg/telemetry.py).
2. No DLL injection, no hooks into the game or its DirectX/Vulkan swapchain,
   no RTSS-style hooking, no CreateRemoteThread, no SetWindowsHookEx of any kind.
3. No low-level keyboard/mouse hooks, no SendInput / keybd_event / PostMessage
   of input into the game. Hotkeys only via RegisterHotKey.
4. No kernel drivers (no WinRing0, PawnIO, LibreHardwareMonitor driver).
   FACEIT AC blocks them.
5. Never write game files other than the cfg files the app already writes.
6. Data only from: ETW via Intel PresentMon (MIT), Windows PDH counters,
   NVML (nvml.dll via ctypes), Win32 window queries.

## What to build

Branch `codex/overlay-0`, in a separate worktree so it doesn't clash with
other work (ping widget is on codex/ping-widget, setup wizard is PR 13;
don't touch either).

1. `cs2cfg/overlay/presentmon.py`
   - Locate a PresentMon console exe (official release from
     github.com/GameTechDev/PresentMon, MIT). For the prototype, look in
     `tools/presentmon/` and document where it was downloaded from + SHA256.
     Do not commit the binary yet.
   - Run it as a child process filtered to cs2.exe, CSV to stdout, its own
     session name, stop on exit. Use `--help` on the actual binary for the
     exact flags and column names; don't trust names from memory.
   - Parse rows into a 1-second aggregator: avg FPS, 1% low (FPS of the 99th
     percentile frame time), max frame time, count of spikes
     (frame time > 2.5x rolling median and > 8 ms), PresentMode histogram,
     latency columns if present.
   - Without admin it needs the user to be in "Performance Log Users".
     Detect the access-denied failure and report it clearly; don't elevate.
2. `cs2cfg/overlay/hud.py`
   - Native Win32 layered window via ctypes: WS_EX_LAYERED | WS_EX_TRANSPARENT
     | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE. Click-through,
     never takes focus, no taskbar entry.
   - Draw with GDI into a 32-bit DIB, push with UpdateLayeredWindow.
     Redraw only when a value changes, max 2 Hz. Thread waits on messages /
     an event between redraws (no busy loop, no sleep(0)).
   - Shows: FPS, 1% low, frame time, CPU %, GPU %, GPU temp. Plain styling.
   - Optional flag to call SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE).
   - RegisterHotKey toggle (show/hide). Hidden = window hidden + no redraws.
3. GPU via NVML (ctypes, nvml.dll) for load and temp; fall back to None.
   CPU from the existing ctypes code in cs2cfg/monitor.py.
4. CLI: `python -m cs2cfg overlay-probe [--seconds N] [--no-hud]` that starts
   PresentMon + HUD and writes one JSON line per second to
   `%LOCALAPPDATA%\cs2cfg\overlay-probe\<timestamp>.jsonl`
   (fps, 1% low, spikes, present mode, overlay process CPU %, working set MB).
5. `tools/overlay_bench.py`: given two probe files (HUD off vs HUD on),
   print avg FPS, 1% low, present-mode share, and overlay CPU/RAM for each,
   and the % difference.
6. Unit tests (unittest, no pytest) for the CSV parser and aggregator with a
   small fixture CSV. Existing tests must still pass.

## Measurement Edy runs (needs CS2)

CS2 in Fullscreen Windowed, same map/demo, ~2 minutes each:
`overlay-probe --no-hud --seconds 120` then `overlay-probe --seconds 120`,
then `tools/overlay_bench.py` on both. We want:
- FPS and 1% low within 1% between runs
- overlay process under 0.5% of total CPU, under 40 MB working set
- PresentMode with HUD visible: note whether it stays
  "Hardware: Independent Flip" / "Hardware Composed: Independent Flip" or drops
  to "Composed: Flip". That decides whether the HUD is always-on or
  between-rounds by default.

## Done means

Pushed branch, tests passing, a short README in docs/overlay/ with how to run
the probe. No PR (this is a spike; GUPDATE merges open PRs).
