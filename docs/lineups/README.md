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
steps sit beside a 156-pixel radar at the default panel size. Two picture
thumbnails sit below the radar when available; only the catalogue scrolls. The curve is a direction
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

## Player-triggered pictures (step 4 wiring)

Settings -> Overlay -> Lineups now offers a picture key (F8 by default) and
Make lineup pictures. Overlay and Lineups must be saved as enabled first.
Close CS2 before pressing the button. The app writes only its two picture cfgs
in the discovered install's game/csgo/cfg folder, reads the signed-in Steam account's
key config to restore a readable previous binding, and launches Mirage using
the existing Steam launcher. Its strict argument mode refuses a launch if
Steam cannot pass the map and cfg; the rungameid URL drops these arguments.
No keyboard/mouse input, console typing, injection or memory reading is used.
No capture timer, launch deadline, sleep or artificial shot acknowledgement
was added. Capture-only GSI fields are requested only during this session.

Each key press moves the practice camera to the next view: stand looks down
at 89 degrees, aim uses the recorded angle. Keep CS2 foreground and wait until
the overlay advances its picture number before pressing again. Mirage has
18 lineups, hence 36 pictures. The last press executes the undo cfg, restoring
a safe readable previous binding (otherwise unbinding) and turning cheats off.
The app removes its two cfg files on completion, refusal, cancellation or game
exit, and keeps any pictures already saved.

No retail CS2 screenshot console command was confirmed. The wired fallback
copies the visible CS2 window with the existing external GDI backend only after
fresh authenticated GSI matches the expected position and forward direction.
Fake screenshot PNG files and fake frames test ordering without a real game.
The saved SVG annotations put both markers at screen centre. Caches include
the map, Steam build ID and validated lineup data hash. Fake caches stay separate.
The detail card loads available pictures, including partially completed pairs,
and clicking a thumbnail opens a larger picture with a Close picture button.

The offline gate accepts only explicit practice/offline GSI mode, Mirage,
warmup/freezetime/live, the local playing player, and no other humans if a
roster is supplied. Casual, competitive, missing mode or unclear roster is
refused. Startup/menu events wait for a map, with no timeout. This is strict:
normal practice may report casual rather than practice/offline, and playing
clients may omit position/forward. Such builds stop with a plain explanation;
they must never silently bypass these gates. This has not been tested on Edy's
installed CS2. GDI can also fail on DirectX; a failed frame never advances.

Deleting a cfg cannot execute undo in a running game. On early stop the app
asks the player to close CS2 before online play. It cannot promise immediate
unbind/cheat reset on abort without forbidden game input. CS2 itself may save
session bindings; file deletion alone is not proof of restoration. The app
never edits the player's own config to force restoration. Automatic undo on
an arbitrary early abort remains a limitation of this design.

## What Edy clicks

1. Open G:\Projects\cs2-lineups in File Explorer (the codex/lineups worktree).
2. Double-click cs2cfg.bat to launch this checkout, not an installed release.
3. Open Settings -> Overlay. Enable the overlay, then Save overlay settings.
4. Press Ctrl+Alt+P, open the Settings tool, enable Lineups in Your dock, save.
5. Close CS2 if it is running. Return to Settings -> Overlay in the main app.
6. Leave Picture key at F8 (or pick another listed key), click Make lineup pictures.
7. Let Steam launch Mirage. Join the practice side if CS2 asks. Use Fullscreen
   Windowed so the overlay is visible; do not join an online server.
8. Press Ctrl+Alt+P and open Lineups. Read the capture status. If it refuses
   offline mode/camera evidence, close CS2; this build cannot make pictures on
   that reported game state. No console command is required or suggested.
9. If it says Picture 1 of 36 - press F8, close the panel with Ctrl+Alt+P,
   keep the game visible and press F8 once. Reopen Lineups to read progress,
   close the panel again, and repeat only after the number advances. Pin
   Lineups for a status line while the panel is closed.
10. Continue through picture 36. Done - 36 pictures saved means all were saved
    and the final key press ran undo. Open a lineup and click either thumbnail.
11. Close CS2 before returning to normal play, especially if capture stopped.

## Verification and handoff

Python execution is unavailable in this sandbox: py is not recognized. The
operator must run tests.test_lineups_pictures, tests.test_overlay_gsi,
tests.test_lineups_rounds, tests.test_lineups and tests.test_crosshairx_launch
with py -3 -m unittest tests.<module>. No Python pass result is claimed.
JavaScript/Chromium results and both cumulative snapshots are recorded under
tmp/lineups-handoff. No git add, commit, push, PR, merge, release or tag was run.
Real-game offline reports, camera reports, alias timing, GDI rendering, binding
restoration, landmarks and throw accuracy remain untested.

Final browser checks passed in Carbon and Daylight at an asserted 1000 x 620
panel: all 18 detail cards, all three steps, radar, both thumbnails, status
and larger picture view. The list alone scrolls. Regenerated carbon.png and
daylight.png use labelled original preview diagrams and fake picture fixtures,
not Valve artwork. Files with real in their names were untouched.

Passed: node tools/lineups_preview.cjs --check, node tools/overlay_preview.cjs
--check (six renderers, ten themes), tests/overlay_settings_harness.js,
tests/overlay_panel_harness.js, tests/status_bar_harness.cjs,
tests/rgb_settings_harness.js, and git diff --check.

## Personal lineups (parts 1 and 2, November 2026)

New lineup opens a form in the overlay with name, map, side, type, throw, area
and one instruction per line. New drafts use the current map when available.
Drag the feet on the radar (or click; arrow keys also work). The landing ring
is optional. Use my game position copies the authenticated local player's
position and forward direction when GSI supplies them. Dragging feet clears
that aim, because a radar marker cannot establish a camera angle.

Personal records live under paths.user_data_dir()/lineups/mine/<map>.json.
Radar-only points use {radar_x, radar_y} in overview pixels; world points keep
{x, y, z}. Missing landing points and aim are accepted only on personal rows.
The shipped catalogue still requires finite world coordinates and angles.
Personal rows share the catalogue search and have a Made by you filter and tag.
Edit updates the record; Delete applies immediately and shows a visible Undo
button. Undo is action driven, with no delayed writes or confirmation popup.
Import/export is not included.

Regenerate previews with node tools/lineups_preview.cjs. The Carbon, Daylight
and New lineup screenshots contain original schematic fixtures, no game art.
Run node tools/lineups_preview.cjs --check for the list and editor browser tests.
Run py -3 -m unittest tests.test_lineups_mine tests.test_lineups_editor
on the owner's machine: py is not available inside this execution sandbox.

## Personal pictures (part 3: radar-only fallback)

The separate Lineup picture key in Settings -> Overlay -> Lineups defaults to
F9; the existing catalogue Picture key defaults to F8. Save overlay settings
persists both. They must differ from one another and from the final key of
either overlay shortcut. This reserves the new key; it is not currently bound
in the game. The existing catalogue picture workflow remains available.

Command check on 2026-11-21: the game command registry labels cl_drawhud and
r_drawviewmodel as cheat commands. The intended hide pair would therefore be
cl_drawhud 0 and r_drawviewmodel 0, with both restored to 1 afterwards, in an
app-launched local practice game only. No no-cheats weapon-hiding alternative
was verified. Registry source:
https://github.com/SteamDatabase/GameTracking-CS2/blob/master/DumpSource2/convars.txt
The screenshot, png_screenshot and jpeg_screenshot commands in the companion
commands.txt are development-only; they are not a confirmed retail alternative.

No supported acknowledgement of a picture-key press or HUD visibility was
found in the available GSI path. Position/forward and an ordinary heartbeat
cannot establish either fact. A same-alias hide/restore could restore before
an external capture, and an early cancel cannot execute an undo file simply by
deleting it. These are unresolved prerequisites, not things fake GSI flags can
verify. See cs2cfg/overlay/gsi.py for the fields this app actually accepts.

The least invasive candidate is the existing strict Steam launch with a
one-session +exec for an app-owned cfg, requiring CS2 to be closed first. It
avoids changing launch preferences, autoexec or player config files. Loading
a newly written cfg into an already-running game cannot be assumed. Until
key/HUD evidence and game-side undo can be verified, the personal picture
button explains the limitation and saves nothing to the game folders. It
never launches, binds, enables cheats, hides the overlay or captures a frame.
The requested two-picture capture, cropping, retake and picture-marker flow
is NOT implemented. The brief explicitly permits radar-only fallback when
picture capture cannot be achieved within its hard rules. No creating-mode
cfg/bind is installed, so there is no creating-mode cleanup to execute.

Tests added: tests.test_lineups_mine (optional land and bounded radar points),
tests.test_lineups_editor (local pose, stale/malformed reports and editing),
and tests.test_lineups_creating (key conflicts and refusing unsupported capture
even with fake frames and invented game-state flags). Existing picture tests
still cover the earlier catalogue workflow. All Python tests remain unrun here:
py -3 is not recognized by this sandbox. The operator should run:

    py -3 -m unittest tests.test_lineups tests.test_lineups_mine tests.test_lineups_editor tests.test_lineups_creating tests.test_lineups_pictures tests.test_lineups_rounds tests.test_overlay_gsi

Browser validation passed: node tools/lineups_preview.cjs --check in Carbon and
Daylight (new/edit/save, radar markers, optional landing ring, delete/Undo,
automatic GSI placement without overwriting a dragged marker, and the picture
fallback), node tools/overlay_preview.cjs --check, all four JS harnesses, and
git diff --check. Preview images are original diagrams. Real-game radar file
availability, live GSI position/forward availability, capture and restoration,
and actual throws remain untested. No real game folders were used in tests.

### Make one lineup from this checkout

1. Launch cs2cfg.bat in G:\Projects\cs2-lineups-own.
2. In Settings -> Overlay, enable the overlay and save.
3. Press Ctrl+Alt+P. In the overlay Settings tool, enable Lineups in Your dock
   and save. Open Lineups from the dock.
4. Click New lineup. Choose the map, name, side, type, throw and area; enter
   one instruction per line.
5. Drag the feet to the stand spot. Optionally click Place landing ring and
   drag the ring. If available, Use my game position also records your aim.
6. Click Save lineup. Find it with Made by you. Edit changes it; Delete removes
   it immediately and the visible Undo button restores it.

Cumulative file copies are in tmp/lineups-handoff/part-1, part-2 and part-3,
with FILES.txt manifests. The operator commits; no git staging, commit, push,
PR, merge, release or tag was performed. tools/lineups_handoff.cjs was not recreated.
