# Overlay build: steps 1 to 3

Plan (approved by Edy 2026-11-14): https://claude.ai/artifact/D1wTHRxbeuvvNdK9ZRbBW9
Step 0 (prototype, branch `codex/overlay-0`, commit 0aa630c) is the base.
Live CS2 measurement happens later on Edy's home PC, so build everything so it
can be checked there with one command (`overlay-probe` + `tools/overlay_bench.py`
must keep working).

Codex owns design and engineering. This brief gives the facts and the limits.

## Hard safety rules (unchanged, non-negotiable)

Same six rules as docs/overlay/OVERLAY_STEP0_BRIEF.md: no memory access to
cs2.exe (PROCESS_QUERY_LIMITED_INFORMATION only), no injection or swapchain
hooks, no SetWindowsHookEx of any kind, no SendInput / keybd_event / mouse_event
/ PostMessage of input into the game, no kernel drivers, game files only through
the cfg files the app already writes. Hotkeys only via RegisterHotKey.
Reviewer will grep for all of these.

## Load rules

- Overlay **off by default**, enabled in Settings. When off: no thread, no
  PresentMon, nothing.
- When on but CS2 not running: one waitable sleep, checks for cs2.exe at most
  every 5 s (reuse the launcher/gamewatch detection if it already knows).
- PresentMon only runs while CS2 runs and the overlay is on.
- HUD redraw only on change, max 2 Hz. History graph in the panel max 10 Hz,
  and only while the panel is open.
- Panel hidden = suspended (no timers, no polling from JS). Prefer
  WebView2's TrySuspend / pywebview hide; if suspend isn't available, at least
  stop all JS timers on hide.
- No new heavy dependencies (no Qt, no Pillow, no psutil). ctypes only.

## Step 1: data layer and HUD in the app (branch `codex/overlay-1`, from overlay-0)

- `cs2cfg/overlay/service.py`: one OverlayService owned by the running app
  (desktop.py / tray keeps the app alive while CS2 runs). Starts/stops
  PresentMon with CS2, keeps a ring buffer of 1-second summaries (last 10 min)
  and a stutter/freeze event list (last 200).
- Freeze events: PresentMon spikes (existing rule) plus "not responding"
  stalls. telemetry.py already detects stalls (class Stall, SessionRecorder
  started in launcher.py ~line 679); expose those to the service instead of
  writing a second detector.
- GPU: NVML from overlay/metrics.py. Also switch cs2cfg/monitor.py's GPU
  reading from the nvidia-smi subprocess to NVML when nvml.dll loads, keeping
  nvidia-smi as fallback.
- HUD (overlay/hud.py) wired to the service. Corner position and which fields
  show are settings. Hotkey to toggle HUD is a setting (default Ctrl+Alt+O).
- Exclusive fullscreen: if PresentMon's PresentMode says the game is not
  composed/independent-flip windowed, or the window is not borderless
  (window.py knows), hide the HUD and surface a notice in the app offering the
  existing borderless switch.
- PresentMon access: if access denied, show a one-click fix in Settings that
  runs `net localgroup "Performance Log Users" <user> /add` elevated (UAC
  prompt, user-initiated only) and says a sign-out is needed. Never elevate
  silently.
- PresentMon binary: the installer/build must ship it. Add it to the
  PyInstaller spec (cs2cfg.spec) and installer.iss as a data file from
  tools/presentmon/, with the SHA256 checked at runtime before launching it.
  Keep it out of git; document the fetch step in docs/overlay/README.md and
  in the release steps.
- Session history: at game exit, write the summary (avg FPS, 1% low, worst
  frame, stutter count, worst freeze) into the existing session record so the
  app's history shows it.

## Step 2: panel (branch `codex/overlay-2`, from overlay-1)

Opened with a second hotkey (default Ctrl+Alt+P). Built in the app's HTML
design system (cs2cfg/web) so it matches the redesign. Opening it activates
the panel window (so the cursor appears); closing it gives focus back to the
CS2 window (SetForegroundWindow on the cs2 hwnd, which is allowed because we
are the foreground process at that moment).

Contents:
1. **Profiles**
   - Setups: list and switch via the existing API `_setups` / `_setups_act`
     with `do: "use"` (webui.py ~line 4005).
   - Keyboard/mouse layout profiles: list via `_cfg_layouts_profiles`
     (webui.py ~1658), switch via `_cfg_layouts_apply` (~1486). That only
     writes files on disk. To take effect in the running game the player
     presses their "Apply Saved Settings" key (cfgscan.APPLY_SCRIPT_NAME;
     the bound keys come back as `apply_keys`). After switching, the panel
     shows "Press <apply key> in game to load it". If no apply key is bound,
     say so and link to the Keyboard tab where it's set up.
   - Never type into the console or send keys to apply it.
2. **Performance**: FPS and frame-time graph for the last 2 / 5 / 10 minutes,
   current, average, 1% low, worst frame; CPU/GPU load and GPU temp.
3. **Stutters and freezes**: list with time, duration, and type (frame spike
   or not responding), newest first.

## Step 3: game state, capture, settings (branch `codex/overlay-3`, from overlay-2)

- **Valve Game State Integration** (official, used by tournament overlays):
  write `gamestate_integration_cs2cfg.cfg` into
  `<CS2 install>/game/csgo/cfg/` (the app already finds the install:
  state.cs2_install). It POSTs JSON to a localhost endpoint on the app's
  existing server with an auth token from the cfg. Ask only for `provider`,
  `map`, `round`, `player_id`, `player_state`. Remove the file when the
  overlay is turned off.
- **Auto hide** setting (default on): HUD visible in freeze time, warmup,
  round over, while dead, or while the hotkey is held/toggled; hidden during
  a live round while alive. Setting to make it always visible instead.
- **Hide from capture** setting (default on): SetWindowDisplayAffinity
  WDA_EXCLUDEFROMCAPTURE on HUD and panel.
- **Settings section** for all of the above in the app's Settings tab.

## Tests and done

- unittest only (no pytest). Unit tests for the service ring buffer, event
  merge, GSI payload parsing and auto-hide state machine, the PresentMon
  SHA256 check, and setting defaults (overlay off).
- Full suite must pass on each branch.
- Push each branch. No PR and no release: Edy tests on the home PC first.
- Update docs/overlay/README.md with how to enable, hotkeys, and how to run
  the on/off measurement.
