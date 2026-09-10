# cs2-autoconfig

Reads the machine it is running on, works out what Counter-Strike 2 should look
like on it, and writes the settings into the three separate places CS2 actually
keeps them.

Windows only. Pure standard library — no pip install step.

---

## Why three files

This is the part most config guides get wrong, so it is worth stating plainly.

| What | Where it lives | Why |
|---|---|---|
| Picture quality | `userdata\<id>\730\local\cfg\cs2_video.txt` | Shadow quality, MSAA, texture detail and friends are **not** console convars in CS2. Setting them in an autoexec does nothing; the game reads this file. |
| Launch options | `userdata\<id>\config\localconfig.vdf` | Steam's own database. It is held in memory while Steam runs and rewritten on exit, so edits made with Steam open are silently lost. |
| Everything else | a `.vcfg` in the game's `cfg` folder | `fps_max`, `rate`, and the handful of other convars that genuinely are convars. |

A tool that only writes a `.cfg` cannot change your picture quality. That is why
this one touches all three, and backs up all three together.

---

## Install

```
winget install -e --id Python.Python.3.13
```

Then run `cs2cfg.bat` from this folder. No arguments opens the window; with
arguments it is a normal CLI.

---

## Use

```
cs2cfg.bat scan      what hardware was detected, and which Steam accounts have CS2
cs2cfg.bat plan      every change it would make, written out, nothing touched
cs2cfg.bat apply     make the changes (asks first, backs up first)
cs2cfg.bat revert    put everything back
```

`plan` and `apply` print the same report. The only difference is whether
anything is written, so you always see the full diff before committing.

## Running it

It is a normal Windows application. Double-click `dist\cs2cfg.exe`, or the
**CS2 Launcher** shortcut on your desktop. Its own window, its own icon, no
terminal, no service to start or stop.

From source, one command:

```
dev.bat
```

`dev.bat test` runs the suite; `dev.bat build` produces `dist\cs2cfg.exe`.

How the desktop shell holds together:

* The HTTP server binds `127.0.0.1` on an **ephemeral port**, so two copies can
  never fight over a fixed one and nothing is reachable from the network.
* A named mutex enforces a single instance. A second launch raises the window
  that is already open instead of starting a rival server.
* The server is a daemon thread owned by the window. Closing the window shuts
  it down — verified: the port is released and no process is left behind.
* If the native window cannot be created it falls back to a chromeless browser
  window, and says which it used rather than failing silently.
* Startup failures show a message box, because a double-clicked application has
  no console to print to.

The window icon is generated from code (`cs2cfg/appicon.py`, `zlib` + `struct`,
no image library) so there is no binary in the repo.

---

## Configuration studio

```
cs2cfg.exe cfg <folder>                       scan and report
cs2cfg.exe cfg <folder> --polish              preview formatting
cs2cfg.exe cfg <folder> --apply               write it (backed up first)
cs2cfg.exe cfg-rename <folder> !old !new      preview a rename
```

Reads `.cfg` and `.vcfg`, detecting the format from the content rather than the
extension — `.vcfg` holds both KeyValues and plain console commands in the wild.

### What it works out

The load order by following `exec` from the entry point, resolving paths **from
the cfg root** rather than relative to the file doing the exec'ing, which is
what the engine does. Then alias definitions and redefinitions, press/release
pairs, key bindings, cross-file overrides and which definition wins, profile
settings one profile changes that another never restores, and malformed syntax.

Two distinctions the analysis is built around:

**Immediate versus deferred.** A command inside `alias x "..."` or `bind k "..."`
is parsed at load but runs later, if ever. Treating those as immediate would
make every alias body look like it executes at startup.

**Stateful cycles versus recursion.** `alias GM 1GM` where `1GM` ends with
`alias GM 2GM` is a toggle, not a loop — each run replaces the target for the
next one. Only an alias that reaches itself *without* an intervening
redefinition is reported.

An unfamiliar command is not called invalid just because it is not a scanned
alias. Unresolved custom references (a `!name` that resolves to nothing) are
separated from commands that simply need the game to verify.

### Polishing

Formatting may change whitespace, comment alignment and blank lines. It may not
reorder, merge, split, add, remove, alphabetise, rename, or move anything
between files.

That is enforced rather than intended: the formatter re-parses its own output
and compares the executable token sequence against the input. If they differ it
returns the original untouched and says why. A file with an unterminated quote
is reported and **skipped**, because reformatting around one would bake in a
guess about where it was meant to close.

---

## Script and alias editor

Two operations, kept apart because they carry different risk.

**Rename** changes an identifier and every reference: the definition, calls, key
bindings, nested redefinitions, and related `_on`/`_off` and `+`/`-` names.
Behaviour is unchanged by construction — the commands are not touched.

Edits are made at token positions, never by text substitution. A find-and-replace
for `!afk` would also hit `!afk_on`, `!afk_off`, and the word inside a chat
message. Comments and console messages that mention the old name are offered as
**separate, opt-in** wording changes, so a rename never silently rewrites your
chat text.

**Edit behaviour** changes commands, values, order or toggle states. It explains
the concrete difference, validates quoting, references, press/release partners
and state transitions, and flags problems instead of guessing at repairs.
Nothing is ever executed to preview or validate it.

An alias name is a label its author chose. It is not evidence about what the
commands do, and nothing here is blocked or altered on the basis of the words in
a name — what a script actually does is shown in full, in its commands. Whether
any particular script is permitted at an event is a question for that event's
rules.

---

### Three front ends

```
cs2cfg.bat web        browser UI on http://127.0.0.1:8765
cs2cfg.bat gui        native Tkinter window
cs2cfg.bat scan       command line
```

All three call the same functions. The web one exists because a native window
cannot be embedded in an editor's browser pane, and having the tool beside the
config you are editing is worth a small server.

Since the process can write to Steam's files, the server is deliberately
boxed in:

* bound to `127.0.0.1` only, never reachable from the network;
* every mutating endpoint requires a token minted at startup and injected into
  the page, so a hostile page on another tab cannot drive it by guessing the
  port;
* the `Host` header is checked for the same reason;
* `GET` endpoints are read-only by construction.

`.claude/launch.json` is committed, so editors that read it can start the
server themselves.

### Choosing what to optimise for

```
cs2cfg.bat plan --intent competitive
cs2cfg.bat plan --intent balanced      (default)
cs2cfg.bat plan --intent quality
```

`competitive` keeps shadow quality high on purpose. In CS2 a shadow thrown
around a corner is information, and cutting it costs more than the frames are
worth. What it does cut is clutter: model detail, particles and ambient
occlusion.

### Useful flags

```
--target-fps 240        aim at a specific number instead of your refresh rate
--resolution 1280x960   score against a different render resolution
--account 244173392     pick a Steam account (see `scan` for the list)
--no-launch             leave Steam's launch options alone
--no-video              leave picture quality alone
--link-autoexec         append an exec line for the generated config to autoexec.vcfg
```

---

## How it decides

Two lookups and one model.

**The lookups.** `knowledge/gpus.json` and `knowledge/cpus.json` map a part name
to a performance index. Matching is token-based and most-specific-wins, so
`RTX 3090 Ti` beats `RTX 3090`. Unrecognised parts fall back to a series guess,
and the report says so rather than quietly pretending it knew.

**The model.** CS2 is a CPU-bound game, so a single-thread index drives most of
the estimate:

```
cpu_ceiling = single_thread_index x 5.5
gpu_ceiling = gpu_index x 14 x (1080p_pixels / your_pixels)^0.85 x intent_cost

lower, upper = min(ceilings), max(ceilings)
estimate     = lower x (1 - 0.15 x lower / upper)
```

That last line is a soft minimum. A hard `min()` ignores that the two parts
contend with each other, and a harmonic mean over-corrects badly — it halves
the estimate whenever the two ceilings happen to be equal. What actually
happens is a modest loss that peaks when the parts are evenly matched and
disappears when one clearly dominates, so that is what the model does.

The constants are calibrated against the reference parts: a single-thread index
of 100 is a 14900K at roughly 550 fps, and a GPU index of 100 is a 4090 at
roughly 1400 fps at 1080p low.

`estimate / refresh_rate` is the headroom, and headroom picks the tier:

| Headroom | Tier |
|---|---|
| 2.00x and up | S |
| 1.50x | A |
| 1.15x | B |
| 0.85x | C |
| below | D |

Tier plus intent selects a row from the settings matrix. A handful of
conditional adjustments then fire on top: Reflex on GeForce, texture detail
capped under 6 GB of VRAM, MSAA dropped above 4 megapixels on anything but
tier S.

These numbers are heuristics and they are written down rather than hidden. If
you disagree with where a part landed, edit the JSON — the tool picks it up on
the next run.

---

## What it will not touch

Resolution, aspect ratio, monitor index, sensitivity, crosshair, binds, and the
device identity block in the video config.

A stretched 1550x1440 on a 1440p panel is a deliberate competitive choice, not
a misconfiguration. The tool has no business overruling it, and doesn't. The
full list is `preserve` in `knowledge/video_settings.json`.

---

## Launch options

Rather than replacing your launch options, the tool transforms them: it keeps
your decisions and removes the CS:GO folklore CS2 ignores.

For example, given this:

```
-full -console -novid -nojoy +mat_queue_mode 2 -d3d9ex -threads 4
-tickrate 128 -high +cl_updaterate 128 +cl_cmdrate 128 +rate 128000
```

it drops `-nojoy`, `+mat_queue_mode`, `-d3d9ex` and `-tickrate` (parsed and
ignored by CS2), `+cl_updaterate` and `+cl_cmdrate` (removed with the move to
sub-tick networking), `+rate 128000` (a downgrade — CS2 defaults to 786432),
and `-threads 4` (the engine sizes its own job pool better than a fixed number
does). It replaces `-full`, which is not a real flag, with `-fullscreen`, which
is. And on an Intel hybrid P/E-core CPU it drops `-high`, because high priority
can interfere with how the Thread Director places the render thread.

Every removal is printed with its reason. Nothing disappears silently.

`knowledge/launch_options.json` carries a confidence level per flag; the
`medium` ones are worth re-checking after a major game update.

---

## Fixing the alt-tab blackout

```
cs2cfg.bat play
```

If you run exclusive fullscreen on more than one monitor, alt-tabbing out of
CS2 blacks the screen for seconds before the game comes back. `play` fixes it,
then launches the game.

### Why it happens

Exclusive fullscreen means the game **owns the display mode**. Alt-tab forces
Windows to hand that mode back to the desktop and take it again on return, and
on a high-refresh panel — especially with G-Sync, HDR, or a second monitor —
that renegotiation is the black screen. CS2 makes it worse by default:
`setting.fullscreen_min_on_focus_loss` minimises the game outright when it
loses focus, so returning is a full restore rather than a raise.

Everything else people try — `-noborder` alone, disabling the Steam overlay,
priority tweaks — treats the symptom. Borderless windowed removes the cause: a
window never owns the display mode, so there is nothing to renegotiate.

The catch is that a 1550x1440 borderless window on a 2560x1440 desktop is a
small window in the corner, not a stretched game. So the stretch moves one
level down: the **desktop** goes into the narrow mode and the graphics driver
scales it across the panel. The game then runs borderless at exactly the
desktop size — filling the screen, stretched, and never touching the display
mode when you alt-tab.

### Always through Steam

The launcher hands off via `steam://rungameid/730` and never runs `cs2.exe`
directly. That is deliberate — going through Steam is what keeps your launch
options, the overlay, VAC, cloud sync and inventory working. Starting the
executable itself would break all of it.

Steam does not need to be running first; the URL starts it.

### Three ways to launch

```
cs2cfg.bat play             from the command line
cs2cfg.bat shortcut         create a "Play CS2" shortcut on your desktop
cs2cfg.bat web              Play button in the browser UI
```

`shortcut` builds a real `.lnk` pointing at `cs2cfg.bat play -y`, using CS2's
own icon so it looks like what it starts. It resolves the Desktop from the
registry rather than assuming `%USERPROFILE%\Desktop`, because OneDrive folder
backup and roaming profiles both move it.

In the web UI the launch runs on its own thread and the page polls for status,
so a refresh mid-game reattaches to the run in progress rather than losing it.

### Alt-tab specifically

Four things have to line up, and `play` sets all four:

| Setting | Value | Why |
|---|---|---|
| `setting.fullscreen` | `0` | windowed, so the game never owns the display mode |
| `setting.nowindowborder` | `1` | no frame, so it sits flush over the screen |
| `setting.fullscreen_min_on_focus_loss` | `0` | stops CS2 minimising itself the moment focus goes |
| `setting.monitor_index` | primary | so it cannot open on the wrong screen |

Plus `engine_no_focus_sleep 0` in the generated config, which keeps the game
rendering while unfocused instead of dropping to a crawl and having to spin
back up when you return.

The primary-display index is read from `EnumDisplayDevices` rather than assumed
to be `0`, because the primary is not always the first adapter enumerated.

### Session history

Every launch is recorded to `%APPDATA%\cs2-autoconfig\sessions\`, one JSON file
each, and summarised in the web UI.

What it measures, and how:

* **Stalls.** A window that stops answering a no-op message is a window whose
  message loop is blocked — which is what a display-mode renegotiation looks
  like from outside. So the black-screen pause gets *timed*, not estimated.
* **Alt-tab round trips.** Every switch away and back, and how long each took.
  This is the number that should collapse once you are running borderless.
* **CPU and memory**, sampled from the process, so you can see whether a
  settings change actually moved the load.

The history view splits your sessions by borderless versus exclusive and shows
the difference in return time, so you can check the claim against your own
machine rather than taking it on faith.

**There is no frame rate here.** Measuring fps from outside the process without
injecting into it would be a guess, and a made-up number is worse than none.
Use the in-game `net_graph` or an overlay for that.

### It remembers what you chose

Intent, target fps, account, and every checkbox persist to
`%APPDATA%\cs2-autoconfig\config.json` and are shared by all three front ends,
so the CLI starts where the web UI left off.

Remembered values are *defaults*, never overrides — anything you type on the
command line still wins.

### What `play` does

1. Writes `fullscreen 0`, `nowindowborder 1`, `fullscreen_min_on_focus_loss 0`
   into `cs2_video.txt` — before launch, because CS2 rewrites that file on exit.
2. Probes the target display mode with `CDS_TEST`, then applies it.
3. Hands off to Steam via `steam://rungameid/730`, so your launch options,
   overlay and cloud sync all still apply.
4. Waits for the real window (ignoring the splash), then fits it flush to the
   screen origin.
5. Waits for you to quit, and **puts the desktop mode back** — including on
   Ctrl+C or a crash, because that restore is in a `finally`.

```
cs2cfg.bat play --no-stretch      borderless at native aspect (no stretching)
cs2cfg.bat play --no-wait         launch and exit (mode is not restored)
cs2cfg.bat play --width 1280 --height 960
```

The video-settings change is backed up like any other write, so
`cs2cfg revert <stamp>` puts your fullscreen settings back.

---

## Stretched borderless

`cs2cfg stretch` replicates what Borderless Gaming and Stretched Borderless
Manager did, without a tray app.

```
cs2cfg.bat stretch                    stretched borderless at CS2's own resolution
cs2cfg.bat stretch --fill             borderless only, no mode change
cs2cfg.bat stretch --watch            apply on launch, undo on exit
cs2cfg.bat stretch --restore          undo
cs2cfg.bat stretch --list             show what windows are open
```

### Stretching

The desktop switches to the narrow mode for as long as you play, and the
graphics driver scales it across the panel. GPU scaling has to be set to
full-screen in the NVIDIA or AMD control panel, or you get letterboxing instead
of filling. The desktop is put back when you quit -- including on Ctrl+C or a
crash, because the mode is set without `CDS_UPDATEREGISTRY`, so Windows reverts
it if the process dies.

A second mode used to resize only the game window and leave the desktop native.
It depended on CS2 keeping its swapchain at the old size so the present would
scale it up, which is how the CS:GO-era window-stretch tools worked. CS2
rebuilds the swapchain, so the result was 16:9 rather than stretched. That mode
has been removed rather than kept as an option that does not do what its name
says.

### How it works

Plain `ctypes` against `user32`, no dependencies:

1. `EnumWindows` + `QueryFullProcessImageNameW` to find the game's window,
   taking the largest when a process owns several (the others are splash and
   IME helpers).
2. `SetWindowLongPtrW` to clear `WS_CAPTION`, `WS_THICKFRAME`, `WS_BORDER`,
   `WS_DLGFRAME`, the min/max boxes and the edge ex-styles, then set `WS_POPUP`.
3. `SetWindowPos` with `SWP_FRAMECHANGED` to the bounds from
   `MonitorFromWindow` + `GetMonitorInfoW`.
4. For the stretch, `ChangeDisplaySettingsExW` — probed with `CDS_TEST` first,
   so an unsupported mode fails before anything is committed.

The original style, ex-style and rectangle are written to
`%APPDATA%\cs2-autoconfig\window_state.json` before anything changes, so
`--restore` works even after the tool has exited.

### Do you need it?

Probably not, if you are on CS2 and already running stretched. CS2 handles
this natively through `setting.aspectratiomode` plus `-windowed -noborder`,
which is the gap those tools existed to fill in CS:GO. Where `stretch` still
earns its place is `--watch`: switching the desktop mode on launch and back on
exit, so the rest of Windows is not stuck at 4:3 while you are not playing.

---

## Backups

Every `apply` writes one backup set covering all three files, because they are
only consistent with each other.

```
cs2cfg.bat backups          list them
cs2cfg.bat revert latest    undo the last apply
cs2cfg.bat revert 20260906-143022
```

Sets live in `%APPDATA%\cs2-autoconfig\backups`; the newest 20 are kept. A file
that did not exist before is recorded as such, so a restore removes it again
rather than leaving debris.

---

## Calibration

A few of CS2's quality enums are wider than the in-game menu suggests — the
menu shows three options where the file accepts four. Those keys are marked
`"confidence": "medium"` and clamped conservatively.

To pin them down on your own client: set everything to maximum in the CS2 video
menu, quit the game, then run

```
cs2cfg.bat calibrate
```

It reads back what your client actually wrote and records the true ceiling. The
wider range applies from the next run.

---

## Updating the tier tables

The bundled tables work offline and need no updates to function. If you publish
a newer bundle somewhere:

```
cs2cfg.bat update --url https://example.com/cs2cfg-kb.json
cs2cfg.bat update --reset      go back to the bundled tables
```

The bundle is one JSON object keyed by filename. Nothing is written until every
member parses and passes a schema check, so a truncated download cannot leave a
half-updated knowledge base behind.

---

## Layout

```
cs2cfg/
  probe.ps1            hardware probe, emits JSON
  hardware.py          runs the probe, normalises the result
  kb.py                loads the knowledge base, matches parts to tiers
  profile.py           the decision engine
  vdf.py               Valve KeyValues parser + line-accurate patcher
  steam.py             finds Steam, reads and writes its files
  emit.py              generates the .vcfg
  backup.py            backup sets and restore
  cli.py / gui.py      two front ends over the same functions
  knowledge/*.json     all the data, hand-editable
tests/test_core.py     python -m unittest discover tests
```

The GUI is deliberately thin — it calls the same functions the CLI calls.
Behaviour that only exists in a GUI is behaviour that cannot be scripted or
reviewed.

---

## Notes on the risky bits

**`localconfig.vdf` is Steam's file, not ours.** It holds friends state and a
lot else. The tool never parses and re-emits it; it locates one line and
rewrites that line, leaving every other byte alone. There is a test for exactly
this.

**Steam must be closed** to write launch options. The tool checks and refuses
rather than making a change that would be thrown away.

**VRAM comes from the registry,** not WMI. `Win32_VideoController.AdapterRAM` is
a signed 32-bit field that saturates at 4 GB and lies about every modern card.

**Refresh rate has three sources,** tried in order: the live display mode, the
monitor's EDID table, and the adapter's current mode. The EDID table often
under-reports a high-refresh panel, so a reading it cannot corroborate is
flagged in the report instead of being trusted silently.
