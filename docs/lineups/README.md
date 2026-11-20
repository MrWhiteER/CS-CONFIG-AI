# Lineups: steps 1–3

The overlay contains a read-only Lineups browser and a round-start smoke card.
The tool is off by default. It reads team, map and round phase only from GSI.
No game input, memory access, console commands or elevated jobs were added.

## Try it

Enable the overlay in Settings, open it with Ctrl+Alt+P, and open its Settings tool.
In Your dock, enable Lineups and save. Open Lineups from the dock. Search a name,
choose a side or throw, or select another map. Only Mirage currently has data;
the other maps show an empty list. Pin the Lineups window to keep the smoke card
through a live round. The round-start setting can be turned off independently.
The normal pinned-tools shortcut also hides this card.

During buy time or warmup, fresh GSI from the local player selects the current
map and side for the native smoke card even when the panel is closed. The card
folds in live rounds unless pinned. It hides when game focus is lost, when the
panel is open, when game state is stale, and when spectating a different player.

## Pictures and data limits

No Valve artwork is included. At runtime the radar reader searches the player's
own game package, reads overview coordinates, and caches the radar in the app
data folder under a name containing the package modification time. PNG, RGBA,
BC1 and BC3 textures are supported, including raw LZ4 and existing Zstandard
compressed mip data. Other formats fall back to a plain list. Native PNG
drawing supports noninterlaced 8-bit RGB and RGBA images. Actual installed CS2
texture layouts, GSI behavior and native Windows drawing still need a game test.
The dashed curve is a direction guide, not a physics simulation.

The permitted seed and its named fork supply only one CT smoke. This version
contains 12 T-side smokes and one CT-side smoke, below the requested CT count.
All are marked as awaiting a game check. No throws or pictures were invented.
The MIT notice and seed attribution are in THIRD_PARTY.md and About Lineups.
Stand/aim picture capture is step 4 and has not been added.

## Verification in this worktree

Passed:

- `node tools/lineups_preview.cjs --check`: list, search, side filters, synonyms,
  empty state, plain text, credits, radar annotations, round card folding,
  preservation of search during refresh, and map switching.
- `node tools/overlay_preview.cjs --check`: six existing renderers and ten themes.
- `node tests/overlay_panel_harness.js`: existing panel lifecycle and controls.
- `node tests/overlay_settings_harness.js`: settings states and syntax.
- Node JSON checks: 13 unique records, required fields, coordinate bounds and
  plain instructions.
- `git diff --check`.

Generated and visually reviewed: `preview/carbon.png` and `preview/daylight.png`.
These previews show the fallback without CS2 pictures; their game state is a fixture.
The preview runner keeps its temporary Chromium profile inside this worktree.

Python execution was denied by the sandbox. Python unit tests were written but
could not be run. Run them one module at a time with TEMP, TMP, TMPDIR and
CS2CFG_DATA pointing inside this worktree:

```
python -m unittest discover -s tests -p test_lineups.py
python -m unittest discover -s tests -p test_lineups_rounds.py
python -m unittest discover -s tests -p test_overlay_gsi.py
python -m unittest discover -s tests -p test_overlay_tools.py
python -m unittest discover -s tests -p test_overlay_pinned.py
python -m unittest discover -s tests -p test_overlay_service.py
python -m unittest discover -s tests -p test_mapart.py
```

Real CS2, its radar extraction, throw accuracy, native card appearance and a
packaged application build were not tested. No real game configuration folder
was written to during this work.

## Git handoff

Staging and committing each step were attempted and blocked by permission to
create the linked worktree's index.lock. No workaround was used. The original
brief and mockup remain staged. There are no new commit hashes.

Read-only checkpoints are in `tmp/lineups-handoff/`. The first patch captures
step 1; later checkpoints are cumulative against the original HEAD. They are
recovery/review copies, not a replacement Git repository. The later checkpoint
contains final integration fixes to earlier steps. Keep the brief and mockup
in step 1 when the operator creates the three commits. No pull request, merge,
release or tag was created.

The requested `git push -u origin codex/lineups` was also attempted. The sandbox
could not connect to github.com on port 443, so the push did not complete.
