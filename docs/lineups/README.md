# Lineups: pictures first

All work for this revision is in G:\Projects\cs2-lineups-own. No staging,
commit, push, pull request, merge, tag or release was performed. Tests do not
use a real game installation. No Valve art is included.

## What changed

1. **Own pictures:** New/Edit lineup ? Take pictures registers the app's
   Lineup picture key (F9 by default) only while waiting. The panel closes;
   a pinned status asks for the stand picture, then the aim picture. Each
   key press captures the foreground CS2 window. After the second picture,
   the key is released and the panel reopens with both pictures for review.
   Crop by dragging a box, keep the whole image, retake either picture, and
   drag to place feet or an aim ring. Cropping removes the game HUD; the app
   does not change the game's HUD, bindings, camera or settings.
   Cancel, game exit, overlay off and tool off release the key and frames.
   Native status is always excluded from capture. Drafts survive panel hiding.
2. **Position:** Overlay + Lineups enabled requests position before game
   launch, without needing the editor open. Tool off removes extra components.
   Unchanged GSI configuration is not rewritten. Missing position explains
   either Restart CS2 once so the game can share your position, or The game
   has not shared your position yet. Move a step and press again. A received
   local position places feet and stores world coordinates and aim angles.
3. **Pictures first:** Stand and aim pictures lead the detail card; steps
   follow and the small corner map can be enlarged. Missing pictures have an
   explicit capture button. Built-in Mirage pictures use the same manual
   capture and review path. The reported stand position must match; the aim
   shot must also match the recorded angle. The player moves themselves.
   The Settings button now directs to a selected lineup. The former launch,
   game-bind and cheat-cfg flow is retired from the app entry point.
4. **Transparency:** New tool backgrounds default to 10% opacity. The slider
   still controls backgrounds while text remains opaque. The default edge
   shade is a light vignette. Existing saved opacity choices are retained;
   move the slider to 10% if an older layout still uses another value.

Personal records: user data / lineups / mine / map.json.
Pictures: user data / lineups / pictures / unique folder / stand.png and aim.png.
Crop and normalized marker positions are stored with the record. Built-in
picture metadata is in user data / lineups / builtin-map.json. Retaking a
saved pair leaves the previous files available; no personal pictures are
stored in this repository or in the game's folders.

The existing capture backend in this checkout is **GDI window capture**,
not Windows Graphics Capture. No new capture dependency was added. DirectX
capture may fail or return a blank frame; a failure does not advance the
session. Real-game capture compatibility still needs verification.

## Owner: make one lineup with pictures

1. Run cs2cfg.bat from G:\Projects\cs2-lineups-own.
2. Enable the overlay in Settings ? Overlay and save. Press Ctrl+Alt+P,
   enable Lineups in the overlay Settings dock list, and save.
3. If CS2 was already running, restart it once for position sharing. Use
   Fullscreen Windowed so the overlay can appear over the game. Own pictures
   need no position report and can be taken in any game mode.
4. Open Lineups ? New lineup. Enter name, map, side, type, area, throw and
   steps. Place feet on the radar or press Use my game position. Landing is
   optional. If position is missing, follow the displayed message.
5. Press Take pictures. With the panel closed, go to your stand spot and
   press F9 once. Aim at your throw landmark, then press F9 again when the
   status asks for the aim picture. Use your chosen Lineup picture key if
   you changed it in Settings.
6. The panel reopens for review. For each picture choose Crop and drag a
   rectangle to remove HUD, or Keep whole. Drag the feet on picture one and
   the aim ring on picture two. Retake is available for either picture.
7. Press Keep pictures, then Save lineup. Find it using Made by you. Edit
   can take a new pair. Delete offers Undo without a confirmation popup.

## Verification

Passed in this sandbox:

- node tools/lineups_preview.cjs --check (Carbon + Daylight, all 18 detail
  cards fit the default panel, editor save/edit/delete/Undo, position, picture
  waiting, two-picture review, crop math and marker placement).
- node tools/overlay_preview.cjs --check (six renderers, ten themes).
- All four JavaScript harness files; all twelve overlay panel scenarios.
- git diff --check.

Python and py are unavailable on PATH in this sandbox. Python tests were
updated but **not run**. On the owner's PC run:

    py -3 -m unittest tests.test_lineups tests.test_lineups_mine tests.test_lineups_editor tests.test_lineups_creating tests.test_lineups_pictures tests.test_lineups_rounds tests.test_overlay_gsi tests.test_overlay_pinned

Added fake-frame tests cover key lifecycle, stand ? aim order, retry, retake,
crop pixels, marker metadata, user-data file location, cancel, capture-excluded
status, panel hiding/reopening, pre-launch GSI components and both missing
position messages. Older standalone picture helpers remain covered with
fake installs only; the app no longer launches them.

Still untested in real CS2: native F9 registration/conflicts and release,
DirectX frame capture, capture exclusion, overlay focus and review reopening,
position/forward reports in each mode, startup-time diagnosis, radar extraction,
landmarks and throw accuracy. Mirage has 12 T and 6 CT smokes; all remain
Awaiting game check. No real-game success is claimed.

Regenerate original-art previews with node tools/lineups_preview.cjs:
carbon.png, daylight.png, new-lineup.png and pictures-card.png. The generated
placeholder-scenery.png is an invented courtyard illustration, not game art.

Cumulative plain file copies and FILES.txt manifests are under
 tmp/lineups-handoff/part-1 through part-4. Part 4 is the final complete handoff.
