# Performance overlay (Step 1)

## Enable in the app

Open **Settings > Overlay**, check **Enable performance overlay**, then save.
It is **off by default**. The choices apply to this machine across Steam
accounts. Choose any corner, the displayed fields, and a shortcut (default
**Ctrl+Alt+O**). The shortcut toggles HUD visibility while capture continues.
Field, corner and shortcut edits take effect without resetting capture.
No panel, second shortcut, game-state receiver, or round-based visibility is
included in Step 1.

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
history, events, status and summary for the later panel. The HTTP equivalent is
the existing token-protected `POST /api/overlay`. It does not initiate capture.
`POST /api/overlay/settings` validates and saves settings, including hint
dismissal. The snapshot includes `frame_capture_ready`, `frame_capture_hint`,
`frame_capture_hint_dismissible` and formatted `display` values, where missing
fields are **—**; numeric samples retain `null` for missing measurements. No
permission-request endpoint, GSI endpoint or panel window is created.

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
request is reported. Leave it off for the initial measurement.

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
python -m unittest discover -s tests
```

The tests cover the parser, aggregator, status classifier, executable discovery
and SHA256 gate, bounded service history, event merge, lifecycle, shared
telemetry, default-off settings, token membership, setup-helper hints, persistent
sign-out dismissal, inert permission requests, resource/stall collection without
frame access, NVML/fallback selection, HUD/API dashes and benchmark math.
They use unittest and mocks, and need no CS2, PresentMon, administrator
privileges, GPU or display. Win32 integration modules still require Windows.
