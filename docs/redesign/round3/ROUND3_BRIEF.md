# Redesign round 3 brief (for Codex)

Edy reviewed v1.23.x and left 8 groups of comments. This brief turns them into work. You (Codex)
own the design and engineering. Claude only supplies facts and references.

Edy's reference images are in `docs/redesign/round3/refs/` (file names start with the section
number). Edy's own words are quoted where they matter.

Big theme across all 8 sections:

> "I want to minimalize the text in our software. Everything should be with icons and gifs. So
> instead of CPU it will show the actual CPU icon, and the same applies for everything else."

So: fewer words, more icons and motion. Keep a tooltip or `aria-label` with the words so the app
stays accessible.

Edy also asked you to use your picture and GIF generating abilities. Use image generation (if
your build has it) for concept art and raster pieces. Ship icons as SVG with CSS animation so
they follow the theme tokens (`--accent` etc.) and stay sharp. Use animated WebP or Lottie-style
CSS/SVG instead of GIF where you can (smaller, smoother, themeable).

---

## 1. One combined, clickable hardware graph (Play tab)

Refs: `01-graph-reference.png` (target look), `01-current-home-system-card.png` (current).

> "the animation of the graph is broken ... all the hardware usage will be in that one graph ...
> by clicking on the graph line, let's say GPU, it will show only the GPU, same with the others.
> But the default will show all the hardware usages."

- Replace the separate CPU load and GPU load charts (`index.html` around the System card, "CPU
  load" near line 5972) with ONE stacked/overlaid area chart like the reference: smooth lines,
  gradient fills, dark grid, hover crosshair with a tooltip showing every series at that moment.
- Series: CPU, GPU, RAM, VRAM, plus temperatures if they fit on a second axis or as a toggle.
- Legend chips use the new hardware icons (section 2). Click a chip OR a line: show only that
  series (others fade out). Click again or "All": back to all. Default is all.
- Fix the broken animation: it should scroll smoothly (requestAnimationFrame, transform-based),
  no jumps when a new sample arrives.

## 2. New hardware icon set, icons instead of text everywhere

Refs: `02-icon-ref-a-cpu-temp.png` and `02-icon-ref-b-thermo-circle.png`. Edy: "there are 2
designs, check them both and make their baby design." The CPU can follow ref A, redrawn.

- Design one family: CPU, GPU, RAM, SSD/NVMe, HDD, motherboard, PSU/power, monitor/display,
  network, fan/cooling, temperature, plus mouse, keyboard, headset, mic. Blend: ref A's line chip
  with a thermometer badge, ref B's round gradient frame and big number.
- Temperature icons: replace the current thermometers with the new style (gradient ring + value).
- Animate them subtly (fill level, pulse with load, heat colour shift). Respect
  `prefers-reduced-motion`.
- Swap text labels for these icons app-wide (Play tab gauges, Detected info, Machine box,
  Graphics tab, overlay later). Keep the word in a tooltip.
- Also fix the Fix It toolbox icons (`02-current-fixit-icons-broken.png`). Edy: "check the icons
  which you created with Codex, they are broken or something is off." They live in
  `cs2cfg/web/assets/fixit/`. Redraw them in the new family.

## 3. Detected box to Settings, automatic connection test, speed chip

Refs: `03-current-detected-box.png`, `03-topbar-chips-style-for-speed.png`.

- Move the Detected card (`index.html` near line 5988) out of the Play tab into Settings (a
  "System" or "This PC" sub-tab), shown with icons per section 2.
- Connection: today it is a button (`#net-run`, `/api/net/start` then `/api/net`). Instead run the
  test automatically during the loading screen (the loading screen already waits for the startup
  loads) and show the result as a chip in the top bar next to the CPU / GPU / RAM chips, in the
  same style (ref `03-topbar-chips...`). Chip shows speed and ping, click opens details. Add a
  small re-test action inside the details, not a big button.

## 4. Drop the estimated-FPS promises, show a real "PC is set" confirmation

Ref: `04-current-target-fps-promise.png`.

> "as much as the software is capable of smoothing out the user's PC, it will not actually bring
> the quality of the gameplay to the number which we give. So this is useless."

- Remove the FPS promises: `EST. FPS` on the three mode cards (around line 5941), `~342 est fps`
  and the tier/headroom stats in the Detected assessment (around line 7231), `385 FPS / 414 FPS`
  in the Machine box, and "Tier S 5.7x headroom" in Target frame rate. Keep the internal logic
  that picks settings; just stop showing numbers as promises. Update tests that assert them.
- Add an "applied and verified" confirmation. After Apply, the app reads back every value it
  wrote (cs2_video.txt, autoexec/cfg, launch options, NVIDIA profile, Windows power/graphics
  settings) and shows an animated checklist: each item ticks green when the read-back matches,
  amber when something else overwrote it (e.g. CS2 was running and rewrote cs2_video.txt), red if
  it failed. End state: a clear badge like "Your PC is set: 14/14 verified", with the time.
  Keep that badge visible on the Play tab until something changes.
- Patterns to borrow: NVIDIA App "Optimized" status per game, Windows Security green shield "No
  actions needed", Razer Cortex "Boost complete" summary, Steam "All files verified". Edy: "check
  the net how to show that and replicate it."

## 5. Settings tab: layout, preset animation, Steam tab, remove "Worth knowing", Machine box

Refs: `05-current-settings-apply.png`, `05-current-machine-box.png`.

- Layout: "the boxes are big and small, nothing symmetrical, nothing follows a pattern." Put every
  Settings sub-pane on one grid with consistent card sizes, gutters and alignment.
- Preset animation (Play tab): when the user clicks Competitive / Balanced / Quality, dim the page
  behind that card, then inside the card play the changes "like code typing, but with GUI and
  nice": each setting appears as `icon  name  old -> new`, one after another. Data comes from the
  same preview that fills the "Picture quality" box (render code near line 7270). Same for all 3.
- Steam tab: new Settings sub-tab "Steam" holding the Steam launch options box (near line 7288)
  and every other Steam-related setting/action (restart Steam, launch options, Steam path,
  account). Move them, don't duplicate.
- "Worth knowing" box (near line 7298): remove the box and its render code completely. Keep the
  settings it talks about; they must still be applied.
- Machine box: much less text, the CPU / GPU icons from section 2 instead of "Processor" /
  "Graphics card", animated icons, and an animated switch between Automatic / Lean on GPU / Lean
  on CPU (sliding highlight, short description in a tooltip).

## 6. Apps page: FACEIT, Discord, TeamSpeak, Crosshair X tiles

Ref: `06-current-apps-page.png` (today just "Add a companion").

- Add 4 default tiles at the top of Apps: FACEIT (+ anti-cheat), Discord, TeamSpeak, Crosshair X.
  Nice animated tiles (glow, shine sweep, hover lift). Use each app's official logo from its
  brand assets (as done for FACEIT in `assets/faceit/`). Animate the tile around the logo, not
  the logo's shape: brand rules forbid altering logos. Source of each logo goes in a README next
  to it.
- Clicking a tile opens that app's settings page. What the app can do for each (only things that
  don't touch the other app's files, see safety below):
  - FACEIT: launch client + anti-cheat, start with CS2, match-found alert on/off and its options.
    Backend exists: `cs2cfg/faceit_apps.py`, `cs2cfg/matchwatch.py`, `/api/match/*`.
  - Crosshair X: start with CS2, wake overlay. Backend: `cs2cfg/crosshairx.py`.
  - Discord: installed/running status, launch now, start with CS2, close after CS2 (optional),
    tips with deep links to Discord's own settings (overlay off saves FPS, hardware acceleration,
    input sensitivity / push-to-talk). Use `cs2cfg/companions.py` for start/watch.
  - TeamSpeak: launch, start with CS2, and "auto-join my server": save host/port/nickname and
    open `ts3server://HOST?port=PORT&nickname=NAME` when CS2 starts (TS3, TS5 and TS6 accept it).
  - Keep "Add a companion" below the 4 tiles for anything else.
- Safety: only start and watch these programs and open their URLs. Never edit their files, inject
  or send input to them.

## 7. GoXLR tools (Sound sub-tab)

Edy has a GoXLR and wants quick controls in Settings > Sound: switch the GoXLR profile and the mic
profile. "There will be additional things I want to do with this, but for now that's it."

Facts to verify on Edy's PC before building:
- Official TC-Helicon GoXLR App: no public API, but its Stream Deck plugin talks to it over a
  local WebSocket (reported as `ws://127.0.0.1:6805/?GOXLRApp`), including "change profile".
  Profiles live in `Documents\GoXLR\Profiles\*.goxlr`, mic profiles in
  `Documents\GoXLR\Mic Profiles\*.goxlrMicProfile` (list names from there, read-only).
- GoXLR Utility (open source, replaces the official app): HTTP/WebSocket API on
  `localhost:14564` and a CLI `goxlr-client` with commands to load a device profile and a mic
  profile.
- Detect which one is running, list profiles, and switch with one click. Optional: bind a
  profile to a Setup (Practice / Match / Recording).

## 8. Configs generated on launch + wizard step to import the user's own cfg files

Ref: `08-current-config-files.png`. Edy: "I created this software but I don't understand what
these settings do."

- Generate the configs automatically when the app starts (build the generated set and keep it
  ready), instead of the user going to Config files and pressing things. Writing to the CS2 cfg
  folder still follows the wizard's one-time "Allow config files" permission (`firstrun.py`).
- Setup wizard: add a step "Bring your own configs": the user picks their cfg files or folder
  (users rename `autoexec.cfg`, so we can't guess names). The app reads them with the existing
  scanner (`cfgscan.py`, `cfgformat.py`, `layouts.py`, the Configuration studio backend) and
  rebuilds them into our standard layout, showing what was kept, merged or dropped. Nothing is
  overwritten without a backup (`backup.py`).
- Simplify the Config files sub-tab: plain words + icons for what each part does; hide the
  studio's advanced controls behind "Advanced".

---

## Rules

1. Every feature keeps working (Apply, Play, Fix, profiles, binds, sign-in, sync, match alert).
   Update tests that assert markup you deliberately replaced and say so. `python -m unittest`
   (pytest isn't installed on Edy's PC).
2. All themes keep working. New art takes colours from theme tokens.
3. Animations: transform/opacity, 60 fps, pause when hidden, respect `prefers-reduced-motion`.
4. No new admin/UAC prompts. Anything needing rights goes through the one-time helper
   (`cs2cfg/elevated.py`); a new helper job must be raised first, not added silently.
5. Offline: vendor any library into the repo, no CDNs.
6. Work in a separate worktree from latest `origin/main`, one branch per section, stacked:
   `codex/r3-1` ... `codex/r3-8`. Commit and push each branch. Do NOT open pull requests: Edy's
   release command merges every open PR, so PRs wait for Edy's OK on the preview.
7. After each section, save before/after screenshots to `docs/redesign/round3/preview/`.
