# Performance overlay (Step 3)

## Enable in the app

Open **Settings > Overlay**, check **Enable overlay**, then save.
It is **off by default**. The choices apply to this machine across Steam
accounts. Choose any corner, the displayed fields, and a shortcut (default
**Ctrl+Alt+O**). The shortcut toggles a manual HUD show/hide override until CS2 closes, while capture continues.
Field, corner and shortcut edits take effect without resetting capture.
The session panel opens with **Ctrl+Alt+P** while CS2 is running in the desktop
app. Configure its shortcut separately in **Settings > Overlay**. The two
shortcuts must differ. A shortcut already registered by another app is reported
in the overlay status. The browser fallback supports the preview below; live
panel hotkeys require the desktop window.

## Game state and visibility

**Auto hide** defaults on. The HUD shows during warmup, freeze time and round
end, and while dead (including spectating another player). It hides during a
live round while alive. Missing or stale game state (over 15 seconds without a
heartbeat) keeps it hidden. The HUD hotkey toggles a manual show/hide override
for this game session. **Always visible** overrides Auto hide; turning Auto hide
off also shows it throughout the round. Fullscreen Windowed and focus checks
still apply, including to manual overrides.

On enable, the app finds CS2 using its existing Steam install detection and
writes only `<CS2 install>/game/csgo/cfg/gamestate_integration_cs2cfg.cfg`.
Disabling the overlay or closing the server removes that file. Other CS2 files
are untouched by this integration. CS2 reads GSI configs at startup: enable the
overlay before launching CS2, or restart CS2 after enabling it mid-session.
If the install is missing or the cfg folder cannot be written, Settings shows
the error; capture and manual visibility remain available. Toggle off/on after
fixing the install or permissions to retry.

Valve's [Game State Integration](https://developer.valvesoftware.com/wiki/Counter-Strike:_Global_Offensive_Game_State_Integration)
POSTs to `http://127.0.0.1:<app-port>/api/overlay/gsi` on the existing server.
The cfg asks only for provider, map, round, player_id and player_state. The
receiver retains just the fields needed for visibility, authenticates with a
random per-install secret and a constant-time comparison, limits bodies to
64 KiB, rejects streaming bodies, and bounds body reads to two seconds. The
separate secret lives in `overlay-gsi-token` in the app data directory and is
never returned by the overlay API. No browser API token is needed by CS2.

**Hide from capture** defaults on. The HUD and panel request Windows capture
exclusion (`0x11`); turning it off clears that affinity on both windows. This
does not affect the main app window. Unsupported systems silently retain
normal capture behavior. Support depends on Windows and the capture tool.

Settings groups HUD position/fields/shortcut, panel shortcut, behavior and
frame-stats access into the app's existing cards. Live readings appear only
while enabled with CS2 running. Open Settings again or use **Refresh status**
to reread them; no Settings refresh timer runs.

## Session panel

Opening activates the panel so you can use the cursor. Close with **Escape**,
the panel's close button, its window X, or its shortcut again. Closing stops all
panel JavaScript timers, aborts pending view requests, hides the window and
returns focus to CS2 while this app is foreground. If you switched to another
app, it leaves focus there. Game exit hides the panel without changing focus;
disabling the overlay also hides it. The window is created only on first open
and reused. Refreshes run once per second while visible (including graph draws,
well below the 10 Hz cap); there is no panel Python polling worker.

- **Profiles:** choose a saved setup for the app's next Apply, or switch a saved
  keyboard/mouse layout using the existing file-writing API. After switching a
  layout, press the shown Apply Saved Settings key in game. If no key is bound,
  follow **Open Keyboard tab** to bind it. No input is sent to CS2.
- **Performance:** current FPS; session average, 1% low and worst frame; a
  frame-time graph of one-second summaries for 2, 5 or 10 minutes; CPU/GPU load
  and GPU temperature. Missing readings stay blank. The setup/sign-out hint and
  persistent sign-out dismissal appear here while resource stats keep working.
- **Stutters and freezes:** newest first, local time, duration, and frame spike
  or not responding. The list is bounded by the existing service's 200 events.
- **Server region lock:** currently **Coming soon**, since the optional
  `cs2cfg.serverlock` module is absent on this branch. When merged, the adapter
  offers a region picker and Lock/Unlock, displays setup, pending, restart and
  error messages, and checks asynchronous completion at most once per second
  while busy and the panel is open. It only delegates to that module's four
  public functions. Opening the panel is the first possible status query.

### Screenshot preview (no CS2 required)

Start the existing local server from the repository:

```powershell
python -m cs2cfg web --port 8765
```

Open **http://127.0.0.1:8765/overlay-panel.html?preview=1** in a browser. This
developer preview uses local sample data through the same renderer; it does not
enable the overlay, start capture, query the region module or modify profiles.
The 2/5/10 minute controls work; actions are disabled. It has no refresh timers.
Use a viewport around 1000 × 800 for a screenshot, or resize to inspect layout.
With the desktop server you can use the same path on its assigned local port.

For Settings screenshots, open **http://127.0.0.1:8765/?overlayPreview=off**.
Use `overlayPreview=live` for running-game sample values, or
`overlayPreview=waiting` for the sign-out hint. These modes select Settings >
Overlay, use the production renderer, disable overlay actions, and never enable
the service or save overlay settings. Other app startup features still run;
for an entirely isolated screenshot server, set `CS2CFG_DATA`, `APPDATA` and
`LOCALAPPDATA` to disposable directories before starting it.

## Capture and lifecycle

Use **Refresh status** after starting CS2 to check access and HUD warnings.
Settings is read on entry or explicit refresh; there is no overlay JavaScript
polling. In exclusive fullscreen the HUD is hidden. The notice offers
**Use borderless next launch**, which selects the existing Play mode and
video-patch option. Restart CS2 through Play to apply it. During frame capture,
the HUD requires both a monitor-filling frameless window and a known
composed/independent-flip PresentMode. Unknown modes and missing frame data
hide it too. Loss of focus always hides it. When frame capture permission is
unavailable, a borderless window can still show CPU/GPU stats with **—** for
FPS, 1% low and frame time.

All permission requests belong to the setup wizard, once. The overlay only
checks enabled token membership for Administrators or Performance Log Users,
using Windows SIDs so non-English Windows works. It never requests elevation,
starts an admin helper operation, changes group membership, or opens a UAC
prompt. `permissions.request_frame_capture()` is an inert compatibility stub
returning `"handled by setup wizard"`.

Settings shows **Finish setup to enable frame stats** if the optional setup
helper module is absent or `cs2cfg.elevated.ready()` is false. If the helper is
installed but the current token still lacks access, it shows **Sign out of
Windows and back in once to enable frame stats**. Use **Dismiss** to hide that
sign-out reminder permanently across app restarts and Steam accounts. The
setup reminder is independent of that dismissal. Available capture has no
permission hint. The overlay reads only the helper's readiness; setup owns its
operations.

The running app owns one `OverlayService` through its local server state. Its
constructor and data API start nothing. Disabled means no overlay worker, HUD,
GPU sampler or PresentMon. Enabled without CS2 means one worker blocked on an
interruptible five-second wait between window checks. With CS2 it starts one
capture when permitted and a native HUD, samples once per second, and reuses the telemetry
`SessionRecorder` for stall events. The launcher and service share the recorder
instead of running two stall detectors. Games opened outside the launcher also
get a session record when the enabled service detects their window.

Game exit closes capture and the HUD, saves the summary and returns to the
five-second wait. Disabling joins the worker and releases its resources;
closing the app's server or quitting does the same. Closing the desktop window
to the existing tray keeps the service alive. The app's other existing features
have their own lifecycle independently of this overlay setting.

`snapshot(seconds=120|300|600)` exposes detached JSON-ready current data,
history, events, status and summary for the panel. The HTTP equivalent is
the existing token-protected `POST /api/overlay`. It does not initiate capture.
`POST /api/overlay/settings` validates and saves settings, including hint
dismissal. The snapshot includes `frame_capture_ready`, `frame_capture_hint`,
`frame_capture_hint_dismissible` and formatted `display` values, where missing
fields are **—**; numeric samples retain `null` for missing measurements. No
permission-request endpoint is created; GSI has its separate cfg-secret endpoint. The desktop panel uses
the same authenticated server, with `POST /api/overlay/panel` for its own
visibility-gated region operations and close/navigation actions.

Without frame permission, the service skips PresentMon and continues CPU/GPU
sampling, HUD updates and telemetry stalls. A real PresentMon access-denied
result also disables frame stats for that capture session and stops the failed
capture. No permission retry or Windows approval is triggered.

The ring holds at most 600 one-second summaries within the last ten minutes;
the event list holds the latest 200, newest first. History starts fresh for a
new detected game/capture session. Events combine overlapping frame spikes and
telemetry stalls; consecutive unresponsive probes coalesce into one freeze.
Event times are epoch seconds at the start and durations are milliseconds;
PresentMon receipt times and telemetry's session-relative times are normalized
to this basis. ETW buffering can delay a spike relative to a stall. Neither
timestamp nor probe intervals can establish an exact in-game freeze boundary.
The existing telemetry detector now queries
[Windows' hung-window state](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-ishungappwindow)
without communicating with the game. Windows currently uses an internal
threshold of about five seconds, subject to change. Recorded stall duration
starts at the first observed hung flag, so it is a lower bound on the full
freeze; shorter freezes come from PresentMon. Unsupported queries produce no
stall measurement. This replaces the older timed responsiveness probe.

Session records retain an `overlay` summary: `avg_fps`, `one_percent_low`,
`worst_frame_ms`, `stutter_count` (PresentMon spikes), `worst_freeze_ms` (either
source), captured `frame_count` and `started_at`. Settings > Logs displays it.
This describes the captured portion of the session; missing frames stay missing.
FPS uses exact frame-count/time totals, not averaged per-second FPS. Session
p99 uses a bounded histogram rounded upward in 0.001 ms bins below 10 ms,
0.01 ms below 100 ms, 0.1 ms below 1 s, 1 ms below 10 s, then 10 ms bins capped
at 60 s. Exact worst frames and raw spike
durations remain available. The probe/benchmark retains its existing finer
histogram for the on/off measurement.

Machine-wide preferences under `ui` in `config.json`:

| Key | Default |
| --- | --- |
| `overlay_enabled` | `false` |
| `overlay_corner` | `"top_left"` |
| `overlay_fields` | `["fps", "one_percent_low", "frame_time_ms", "cpu_percent", "gpu_percent", "gpu_temp_c"]` |
| `overlay_hotkey` | `"Ctrl+Alt+O"` |
| `overlay_panel_hotkey` | `"Ctrl+Alt+P"` |
| `overlay_auto_hide` | `true` |
| `overlay_always_visible` | `false` |
| `overlay_hide_from_capture` | `true` |
| `overlay_sign_out_hint_dismissed` | `false` |

The dashboard now reads GPU load, VRAM and temperature through the same ctypes
NVML implementation, using its existing cached `nvidia-smi` fallback if NVML
cannot provide load. The overlay itself uses NVML only; unsupported counters
remain missing. No Python dependencies were added.

## Fetch PresentMon before running from source

Run this explicitly from the repository root:

```powershell
powershell -NoProfile -File tools/fetch_presentmon.ps1
```

This downloads the pinned official x64 console and checks the SHA256 below.
`tools/presentmon/` stays ignored by git. The app never fetches a binary.
Runtime checks the pinned SHA256 before starting capture or running the
session-stop command. A renamed override still needs the same bytes. Missing
or modified executables are refused and reported in Settings/probe output.

## Release preparation

1. Run the fetch command above. Do not commit the executable.
2. Run `python -m unittest discover -s tests` and the live measurement below.
3. When a release is separately authorized, run the normal build/release flow.
   `cs2cfg.spec` refuses to build without the correct binary and includes it as
   data under `_internal/tools/presentmon/` in the portable folder.
   `installer.iss` explicitly ships the file from `tools/presentmon/` to the same
   installed location. There is no capture subprocess or access prompt during
   installation.
4. Smoke-test both portable and installed copies: fresh settings off; enable;
   missing-game idle; capture; hotkey; fullscreen notice; game exit; disable;
   quit. Check the saved session summary. Repeat on the home PC with CS2.
5. A PresentMon version upgrade must update the reviewed hash/name, fetch
   script, installer source, provenance below, and confirmed CLI/CSV contract
   together. Do not accept a hash from a writable sidecar.

## Step 0 measurement probe

The CLI probe measures a native external HUD over CS2 in **Fullscreen
Windowed**. It reads frame data from Intel PresentMon's ETW console, system CPU
from the existing `monitor.py` ctypes code, NVIDIA GPU zero's utilization and
temperature from `nvml.dll`, and window/process metadata from Win32. Missing GPU
support or frame data stays missing (`null` in JSON, **—** on the HUD).

The probe never changes game files, game windows, display modes, or game input.
Process image queries use only `0x1000` access. Its own CPU/RAM measurements use
the current-process pseudo handle. There are no new Python dependencies or
drivers, and the probe never requests elevation.

## Run

From the repository root with Python 3.12 on Windows:

```powershell
python -m cs2cfg overlay-probe --seconds 120
python -m cs2cfg overlay-probe --no-hud --seconds 120
python -m cs2cfg overlay-probe --exclude-from-capture --seconds 120
```

Without `--seconds`, capture continues until Ctrl+C. Both stop the child process,
close its uniquely named ETW session, and destroy the HUD. The output path is
printed at startup. One JSON line per second goes to
`%LOCALAPPDATA%\cs2cfg\overlay-probe\<timestamp>.jsonl`. This deliberately uses
LocalAppData even if the main application uses a portable data directory.

**Ctrl+Alt+O** toggles the HUD using `RegisterHotKey`. Hidden means a hidden window
and no redraws; capture/logging continues. If another application owns that
hotkey, the probe reports it. The plain HUD is click-through, topmost, absent
from the taskbar, and never activates. It follows the CS2 window's upper-left
corner, or uses the primary desktop's upper-left corner when CS2 is absent.
It uses a 32-bit GDI DIB and `UpdateLayeredWindow`, redraws only on a displayed
value/position change, and redraws at most twice per second. Its thread blocks
on an event and the Windows message queue between changes.

`--exclude-from-capture` requests `SetWindowDisplayAffinity` with
`WDA_EXCLUDEFROMCAPTURE` (`0x11`). Windows/capture-tool support varies; a failed
request silently falls back to normal capture. Leave it off for the initial measurement.

## PresentMon provenance and command

The locally supplied console is **PresentMon 2.6.0 x64**, Authenticode-signed by
Intel Corporation, under the upstream MIT license.

- Source/release: <https://github.com/GameTechDev/PresentMon/releases/tag/v2.6.0>
- Local file: `tools/presentmon/PresentMon-2.6.0-x64.exe`
- SHA256: `b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af`

The SHA256 was recorded during Step 0 and is pinned in the runtime/build.
`tools/presentmon/` is ignored by git; no binary is committed or downloaded by
the probe. Discovery globs
`tools/presentmon/PresentMon*.exe` and chooses the highest numeric version
(mtime breaks ties). An explicit path takes precedence:

```powershell
$env:CS2CFG_PRESENTMON = 'C:\path\to\PresentMon.exe'
```

The actual bundled executable's `--help` was run successfully and confirmed
every flag below:

```text
PresentMon-2.6.0-x64.exe --process_name cs2.exe --output_stdout --session_name cs2cfg-overlay-<pid>-<unique> --stop_existing_session --terminate_on_proc_exit --no_console_stats --v2_metrics
```

On shutdown the probe invokes the same executable with
`--session_name <its-own-name> --terminate_existing_session`, then waits for its
child, terminating that child if necessary. It never targets another capture
session. `--terminate_on_proc_exit` closes capture when an observed game exits;
the probe itself continues logging. Restart the probe to capture a later game
launch after that exit. A game that has not started yet simply produces no
frames, with `cs2.exe not found` on the HUD and in the log.

`--help` describes flags, not CSV columns. A live CSV header could not be
obtained on this account because starting ETW returned **exit code 6, access
denied**. The v2 column names were checked against the
[official v2.6.0 CSV writer](https://github.com/GameTechDev/PresentMon/blob/v2.6.0/PresentMon/CsvOutput.cpp):
`FrameTime`, `PresentMode`, `DisplayLatency`, `ClickToPhotonLatency`, and
`AllInputToPhotonLatency`. The parser also reads `Application`, `ProcessID`, and
`SwapChainAddress` for filtering/baselines. It accepts case-insensitive
`MsBetweenPresents` / `msBetweenPresents` as frame-time aliases and
`MsUntilDisplayed` / `msUntilDisplayed` as an optional latency metric. Unknown
columns are ignored; `NA`, empty, malformed, negative, or nonfinite numeric
values are missing. Zero frame intervals are also excluded.

## Access denied

A filtered administrator token is not automatically allowed to start this ETW
session. PresentMon needs an elevated administrator token or enabled membership
in **Performance Log Users**. The probe
detects the stderr error and exit code, shows
`PresentMon: access denied - see docs/overlay/README.md`, and continues writing
resource/status samples. When CS2 is also absent, both conditions appear in
`status`, with separate `presentmon_status` and `game_status` fields.

Finish the setup wizard once, then sign out of Windows and back in so the new
group membership reaches the token before starting the probe normally. The
app's Settings section shows the setup/sign-out hints described above. Neither
the overlay nor the probe requests permissions or changes Windows membership.

## Metrics and comparison

Each reporting interval contains `fps`, `one_percent_low`, `frame_time_ms`,
`p99_frame_time_ms`, `max_frame_time_ms`, `spikes`, `present_modes` (histogram),
`latency_ms` (mean of each available metric), `cpu_percent`, `gpu_percent`,
`gpu_temp_c`, `overlay_cpu_percent`, and `working_set_mb`, plus timestamps,
HUD state, status, and PresentMon diagnostics. Frame count, summed frame time,
and a frame-time histogram are retained for comparison.

Average FPS is `1000 / mean(frame time in ms)`. The 1% low is `1000 / p99(frame
time)`, using the nearest-rank percentile. A spike is **strictly greater than
2.5 times the median of the preceding 120 frames and strictly greater than
8 ms**. Each process/swapchain has its own baseline, which persists across
reporting intervals; its first frame cannot be a spike. Missing frame times do
not count as frames, but independently available mode/latency data still counts.
Intervals are grouped by receipt time because ETW delivers events with delay;
the frame-time metrics themselves come from PresentMon, not the receipt clock.

The benchmark merges the histograms (frame times rounded to 0.0001 ms) to compute
a run-wide p99. It does not average per-second percentiles. PresentMode shares
are weighted by row counts; CPU and RAM are means of one-second samples (RAM
peak is also shown). CPU is a percentage of **all logical processors**, not one
core. CPU/RAM describe the Python overlay/probe process, excluding its separate
PresentMon child. HUD-off runs include the same capture, sampling, and logging
costs as HUD-on runs.

## Measurement procedure (requires CS2)

1. Set CS2 to **Fullscreen Windowed**. Use the same map/demo, graphics settings,
   resolution, and playback segment for both runs. Let shader/loading activity
   settle first, and keep the game in the foreground.
2. Run `python -m cs2cfg overlay-probe --no-hud --seconds 120`. Record the path.
3. Repeat with `python -m cs2cfg overlay-probe --seconds 120`, leaving the HUD
   visible for the entire run. Verify it appears over CS2 and remains
   click-through without taking focus. Record the second path.
4. Compare the two files, HUD-off first:

   ```powershell
   python tools/overlay_bench.py '<HUD-off.jsonl>' '<HUD-on.jsonl>'
   ```

5. Aim for average FPS and 1% low within **1%**, overlay process CPU below
   **0.5% of total CPU**, and working set below **40 MB**. The benchmark prints
   `(HUD-on - HUD-off) / HUD-off * 100`; an unavailable/zero baseline yields
   `--`, not an invented percentage. Runs without frames cannot establish FPS
   overhead.
6. Compare PresentMode shares: does the visible HUD retain
   `Hardware: Independent Flip` / `Hardware Composed: Independent Flip`, or
   shift to `Composed: Flip`? Record that result to decide whether a future
   overlay should default to always-on or between-rounds visibility. Repeat
   the pair if normal run-to-run variation could explain a 1% difference.

CS2 was not running on the development machine, and this account lacked ETW
access. In-game visibility, presentation-mode effects, and the performance
targets still require the measurement above; they cannot be inferred from an
idle smoke test.

## Tests

```powershell
# Isolate all app-data writes; the tests never need the real CS2 install.
$testData = Join-Path $env:TEMP ('cs2cfg-overlay-tests-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $testData | Out-Null
$env:LOCALAPPDATA = Join-Path $testData 'local'
$env:APPDATA = Join-Path $testData 'roaming'
$env:CS2CFG_DATA = Join-Path $testData 'app'
py -m unittest discover -s tests
```

The tests cover the parser, aggregator, status classifier, executable discovery
and SHA256 gate, bounded service history, event merge, lifecycle, shared
telemetry, default-off settings, token membership, setup-helper hints, persistent
sign-out dismissal, inert permission requests, resource/stall collection without
frame access, NVML/fallback selection, HUD/API dashes and benchmark math. Panel
tests cover lazy creation, hide/disable/exit, focus ownership, shortcuts, API
gates and the optional region module's missing, busy, pending and error paths.
The unittest browser-script harness also checks timer cancellation, late
responses, graph throttling, profile messages and permission hints when Node is
already on PATH; those optional checks skip otherwise. It needs no npm packages.
GSI tests cover cfg write/removal and secret persistence in temporary directories,
authentication/body/Host gates on the existing HTTP handler, payload filtering,
auto-hide transitions/staleness, settings defaults, and capture affinity.
They use unittest and mocks, and need no CS2, PresentMon, administrator
privileges, GPU or display. Win32 integration modules still require Windows.
