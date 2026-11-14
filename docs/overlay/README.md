# Overlay step 0

This CLI-only spike measures a native external HUD over CS2 in **Fullscreen
Windowed**. It reads frame data from Intel PresentMon's ETW console, system CPU
from the existing `monitor.py` ctypes code, NVIDIA GPU zero's utilization and
temperature from `nvml.dll`, and window/process metadata from Win32. Missing GPU
support or frame data stays missing (`null` in JSON, `--` on the HUD).

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

The SHA256 was verified locally. `tools/presentmon/` is ignored by git; no
binary is committed or downloaded by the probe. Discovery globs
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

A non-elevated administrator is not automatically allowed to start this ETW
session. PresentMon needs membership in **Performance Log Users**. The probe
detects the stderr error and exit code, shows
`PresentMon: access denied - see docs/overlay/README.md`, and continues writing
resource/status samples. When CS2 is also absent, both conditions appear in
`status`, with separate `presentmon_status` and `game_status` fields.

If you choose to enable ETW access, run this once from an **elevated Command
Prompt**, then **sign out and back in** before starting the probe normally:

```bat
net localgroup "Performance Log Users" %USERNAME% /add
```

The group name may be localized on non-English Windows. The probe does not run
this command, change group membership, or attempt to elevate.

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

The overlay parser, one-second aggregator, status classifier, executable
discovery, session-stop scoping, HUD text, and benchmark math tests do not need
CS2, PresentMon, administrator privileges, a GPU, or a display.
