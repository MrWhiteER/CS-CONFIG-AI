# Lineups fixes and picture prototype

The Lineups tool is off by default. Enable the overlay in Settings, open it
with Ctrl+Alt+P, open the Settings tool, enable Lineups in Your dock, and save.
Open Lineups from the dock. It supports search, map and side filters, pinning,
and the GSI round-start smoke card. Only Mirage has data.

## Radar and instructions

The runtime radar reader supports PNG, RGBA8888, BGRA8888 (format 28), BC1 and
BC3, including LZ4 and Zstandard mip data. BGRA channels are converted to RGBA.
No Valve art is shipped. Radar pictures come from the player's own install.
The detail radar is a small square zoomed around the stand and landing points;
steps remain underneath in a scrollable detail pane. The curve is a direction
guide, not a simulated flight path.

Mid is displayed as Mid; only A and B get the word site. The validator rejects
invalid areas, repeated step text, marked-point instructions and Mirage steps
without a named landmark. Each record has separate stand, aim and throw steps.
Expanded landmark descriptions still need visual checks in CS2.

Mirage contains 12 T smokes and 6 CT smokes. One CT entry comes from the MIT
seed; five are app-authored practice candidates. All entries have checked=false
and display Awaiting game check. The five candidates use an ideal ballistic
model between overview landmarks. Actual map collision geometry was unavailable;
wall clearance, bounces and throw accuracy are unverified. This does not fulfill
the requested geometry-validated throws. THIRD_PARTY.md records the assumptions.

## Make lineup pictures: unfinished, radar fallback

The Settings -> Overlay page now has a Lineups section and a Make lineup
pictures button. Pressing it reports that real capture is unavailable. It does
not launch CS2, install a cfg, capture a frame or send commands to the game.
This is the fallback allowed by Pictures point 3 of LINEUPS_BRIEF.md, not a
completed implementation of point 2.

The existing overlay capture module only excludes overlay windows from capture;
it does not capture game pictures. Windows Graphics Capture is the intended
noninvasive method, but no production backend or reliable capture method has
been implemented or verified here. GSI provides map/phase but does not confirm
camera position, aim or an offline server. A map-loaded event alone cannot prove
a shot is ready or safe. Advancing a running game's camera would require an
additional command path beyond the brief's no-input rule. No such path was added.
There are no launch sleeps, console typing, memory access, injection, admin
prompts, confirmation popups, game-input hooks or background picture workers.

A developer-only fake-frame prototype is available:

```
py -3 tools/lineups_pictures_dry_run.py
```

It writes only under tmp/lineups-pictures by default. It uses fake readiness
events for each shot, draws an aim ring and a stand arrow on supplied fake
frames, and saves reviewable practice cfg text that it never executes. The fake
stand arrow uses a supplied pixel location; an exact real stand marker still
requires camera projection/calibration. All frames say TEST PICTURE. Fake caches
are isolated from real art, keyed by map, supplied build and data hash; a
completion manifest is written only after every fake shot. There is no real
game-build discovery or automatic production cache refresh yet. Nothing in the
app loads these fake frames as real pictures. Tests use temporary directories
and never discover or write to a player's CS2 config folders.

## What Edy can click on this PC

1. Open CS2 Auto Config from its usual shortcut (or run cs2cfg.bat in this checkout).
2. Open Settings.
3. Open Overlay.
4. Find the Lineups section.
5. Click Make lineup pictures once.

The button currently shows the radar-fallback explanation. There is no working
click sequence to generate real stand/aim pictures in this build. For browsing,
enable the overlay and Lineups as described above. Run no picture generation
during an online match; the unfinished real path is disabled in every state.

## Verification and handoff

Passed: node tools/lineups_preview.cjs --check (including square, zoomed detail
radar and Mid label), node tools/overlay_preview.cjs --check (six renderers, ten
themes), node tests/overlay_settings_harness.js, node tests/overlay_panel_harness.js,
and git diff --check. Regenerated preview/carbon.png and daylight.png without
game art. Existing local files with real in their names were left alone.

All 97 Python test modules were attempted separately with py -3 -m unittest
 tests.<module>, skipping tests.test_graphics. None started: this environment
has no py command. No Python pass result is claimed. The per-module record is
in tmp/lineups-handoff/python-tests.txt. Unit tests cover BGRA raw/LZ4 conversion,
instruction validation, fake event sequencing, annotations and cache identity.

Real CS2 radar extraction, native card appearance, landmark accuracy, new CT
throws, picture capture and a packaged application build remain untested.

Cumulative file snapshots are in tmp/lineups-handoff/part-1 through part-4,
with repo-relative FILES.txt manifests. Part 4 includes final integration fixes,
documentation and regenerated previews. No paths were deleted. No git add,
commit, push, PR, merge, release or tag operation was run.
