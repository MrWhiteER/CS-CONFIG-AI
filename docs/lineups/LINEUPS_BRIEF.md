# Grenade lineups in the overlay: build brief (Codex)

Approved by Edy 2026-11-20. Plan: https://claude.ai/artifact/5ZTKVQhJPo8ky1Gkg6mgv3
Mockup: /mnt/project-files/lineups/lineups-mockup.png (copy in this folder: mockup.html).
You (Codex) own design and engineering. This brief is facts and rules.

## Goal
New overlay tool "Lineups". During buy time it shows the smokes for the current map and the
player's side, drawn on the real CS2 radar. In the open overlay (Ctrl+Alt+P) the player can
search every lineup (smoke, fire, flash, grenade), filter by side, and switch map to practise.
Each lineup shows: where to stand, where to aim, how to throw, with REAL game pictures and the
angle highlighted (Edy: "use original game pictures and highlight the angles, use your imagination").

## Hard rules (project)
- FACEIT/VAC safe: no memory reading, no injection, no input into the game, no console typing.
  Map, round phase and team come ONLY from Game State Integration (cs2cfg/overlay/gsi.py already
  has map name + round phase; add `player_id` team -> T/CT). No -condebug.
- Overlay stays off by default. Tool off -> zero cost (no GSI extra work, no file reads).
- All visible text = plain words. Never show de_mirage, smokegrenade, molotov ids, setpos text,
  error codes. "Mirage", "Smoke", "Fire", "Flash", "Grenade", "Jump throw".
- App ships NO Valve art (same rule as cs2cfg/mapart.py). Pictures are cut/made at runtime from
  the player's own CS2 install and cached in the app data folder. No CS2 found -> plain list,
  no pictures, no crash.
- No admin prompts, no new elevated helper jobs.
- No "are you sure" popups.
- Do not copy lineups/images from Reddit, csdb.gg, SteamAnalyst, tracker.gg (not licensed).
  Allowed seed data: ReneRebsdorf/CS2-annotations (MIT; fork kellran/annotations). Keep its
  MIT notice in docs/lineups/THIRD_PARTY.md and credit "Rene Rebsdorf" in the app's About.

## Pictures: real game pictures, angles highlighted
1. Radar: CS2 pak01 has the overview radar image for each map (look under
   panorama/images/overheadmaps/ or materials/overviews/) and the overview numbers
   (pos_x, pos_y, scale) in resource/overviews/<map>.txt. Read them like mapart.py reads
   map icons (check the texture format; if it is a compressed texture, decode it, add a
   tested decoder, no new heavy dependency). World x/y -> radar pixel:
   px = (x - pos_x) / scale, py = (pos_y - y) / scale. Draw: stand point, throw arc,
   landing area (smoke = grey cloud, fire = orange, flash = white burst, grenade = red ring).
2. Stand / aim pictures: real in-game shots. Build a one-time "Make lineup pictures" action
   (Settings -> Overlay -> Lineups) that, ONLY when the player presses it and CS2 is not in a
   match, starts an offline practice map with the app's own cfg that, per lineup, puts the
   player at the stand spot and aim angle (setpos / setang are fine in a local practice server
   with sv_cheats) and takes a picture. Find the reliable way to capture (CS2 screenshot
   command if one works, or Windows Graphics Capture of the CS2 window, the method the overlay
   already uses if any). Never during online play. Keep FIXED waits out: wait on real state
   (GSI map loaded / phase) before each shot (project rule: no fixed timeouts for launching).
   Then draw on the picture: a bright aim ring + short label ("Aim at the antenna tip"),
   and for the stand picture an arrow to the exact spot. Cache per map + game build; redo
   when CS2 updates.
   Edy will run it once on the home PC to verify; you cannot run CS2 yourself, so make a
   dry-run/test mode with fake frames and unit tests.
3. If any step is impossible, say so plainly in your summary and fall back to radar only.

## Data
- cs2cfg/lineups/data/<map>.json (plain map key internally, plain name shown). Per lineup:
  id, name (plain, e.g. "CT spawn"), side T/CT/both, type smoke/fire/flash/grenade,
  area (A/B/Mid), stand {x,y,z}, aim {pitch,yaw}, throw (left click / right click / both /
  jump throw / run throw / walk throw), land {x,y,z}, steps (1-3 short plain sentences),
  source ("CS2-annotations, MIT" or "own"), checked (bool).
- Start with Mirage: 10-15 smokes per side. Then the other Active Duty maps (check the current
  pool in the game files/mapgroups; as of Jan 2026: Mirage, Inferno, Nuke, Ancient, Anubis,
  Dust II, Overpass), then fire, flash, grenade.
- Validator test: every lineup has all fields, plain names, coordinates inside the map overview.

## Behaviour
- GSI round phase freezetime -> show smokes card for map + side (auto-open even if panel is
  hidden? Only if the player switched "Show smokes at round start" on; default ON when the
  Lineups tool is on). Live -> fold away unless pinned. Warmup -> show too.
- Search: type-ahead over name, area, type ("b site molly" must find B site fire lineups:
  molly/molotov/incendiary/fire are synonyms; nade/he/grenade; flash/pop).
- Pinnable like the other tools; respects per-tool opacity and theme.

## Steps (one commit each on branch codex/lineups, stacked; NO pull request until Edy approves
the preview, because GUPDATE merges open PRs)
1. Data + loader + validator + Mirage smokes + radar cut/draw (+ tests).
2. Overlay tool: radar, list, detail card, search, filters, map switch (+ preview screenshots
   in docs/lineups/preview/, dark + daylight).
3. Round-start card from GSI (team added) + pin/fold.
4. "Make lineup pictures" capture + angle highlight (+ dry-run tests).
5. Other maps, then fire/flash/grenade.
Run tests module by module (test_graphics OOMs in small containers). Summary at the end in
plain words: what works, what is untested in the real game, what Edy must click.
