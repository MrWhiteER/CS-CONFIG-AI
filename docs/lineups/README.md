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

## Round 2 data correction

The Bench proposal no longer has a null pitch. Its old target was outside the
range of the documented ideal ballistic model. The replacement target is a
nearby B apartments exit candidate: horizontal distance 310.64, pitch 9.847065,
yaw 56.821488. This is still an unchecked proposal, not a verified map throw.
Mirage still has 12 T and 6 CT smokes; all five app-authored CT entries remain
checked=false. Validator aim errors now name the lineup. Regression tests reject
a null pitch in every shipped record and check the replacement's model height.

## Make lineup pictures: engineering attempt, radar fallback

The Settings -> Overlay page now has a Lineups section and a Make lineup
pictures button. Pressing it reports that real capture is unavailable. It does
not launch CS2, install a cfg, capture a frame or send commands to the game.
This is the fallback allowed by Pictures point 3 of LINEUPS_BRIEF.md, not a
completed implementation of point 2.

The existing overlay capture module was inspected: it only excludes overlay
windows from capture. Round 2 adds an experimental external GDI backend in
cs2cfg/lineups/window_capture.py. It copies the foreground CS2 client area,
checks the process image name through the same limited Windows query used by
the overlay, converts BGRA to RGBA, rejects uniform blank frames, rechecks the
window, and releases its Windows resources. It never reads game memory or sends
keyboard/mouse input. DirectX capture may still be black or incomplete; this
backend has NOT been run against CS2 and is NOT connected to the button.

The sequencing attempt is CaptureTrial in pictures.py. It models one fresh
practice launch per lineup using the existing local-server cfg text. A shot
needs an authenticated full GSI snapshot with the expected map, warmup phase,
local living player, matching position (within two units), and matching forward
direction. Missing pose, another player, a wrong aim, a live phase or an event
from a previous launch cannot advance it. A fake capture callback exercises this
sequence in tests, including failures and retries. No timer advances a shot.

The first unresolved gate is confirming the playing client's actual position
and aim. Published GSI configuration examples place player_position under
observing/spectating, not the playing client. See the
[CS2 GSI example configuration](https://github.com/JoshuaJKrueger/cs2_gsi/blob/master/gamestate_integration_example.cfg).
The Valve wiki itself returned an access error during this session. This is a
documented-interface limitation, not a live measurement on Edy's installed build.
A map event cannot prove that a launch cfg successfully moved the player. We
must not substitute an expected pose, a fake shot ID, or elapsed time for that
evidence. The trial therefore stays disconnected. GSI map/phase also does not
authenticate a local server; a verified owned offline session is a separate
unsolved prerequisite. CaptureTrial explicitly does not establish that safety.

Launching an offline map with +map/+exec is allowed and can move the camera.
The previous explanation that all such movement would violate the rules was
incorrect. A fresh launch per shot avoids cfg waits, but a complete automatic
exit/relaunch controller is not implemented. A repeating cfg would need a proven
game-side scheduler; rewriting a cfg alone cannot cause the game to execute it.
An exact stand arrow also needs a separate calibrated view of the feet/stand
point; the aim crosshair cannot supply that view. No guessed real stand arrow
is generated.

No actual CS2 launch or real frame capture was attempted in this session, as
the brief says this must be verified by Edy. This engineering attempt is NOT
completion of step 4 and does not prove that every possible allowed approach is
impossible. It identifies the unsupported readiness gate in the attempted
approach. The button retains the radar fallback. No production launch, game cfg
installation, extra GSI subscription, capture worker or cache write was enabled.
There are no launch sleeps, console typing, injection or admin prompts.

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

Round 2: all 97 Python test modules were invoked separately, skipping
tests.test_graphics. The four specifically requested modules were also invoked
for Part 1. None could start. The shell has no py command; executing the supplied
C:\Users\saruk\AppData\Local\Programs\Python\Python313\python.exe returns
Access is denied. Reading its containing folder is denied too. An attempt to
download a portable official Python runtime into tmp failed because network
access is restricted. No Python pass result is claimed. This is a session access
problem, not a claim that Python is absent from the PC. Per-module outcomes are
in tmp/lineups-handoff/round2-python-tests.txt and round2-python-tests.json.
The new Python tests have not been executed.

Real CS2 radar extraction, native card appearance, landmark accuracy, new CT
throws, picture capture and a packaged application build remain untested.

Cumulative round 2 snapshots are in tmp/lineups-handoff/part-1 and part-2,
with repo-relative FILES.txt manifests. They include the inherited uncommitted
changes as well as round 2 edits. No preview files were regenerated in round 2;
files named real in the preview folder were left alone. No git add,
commit, push, PR, merge, release or tag operation was run.
