# Job C — FACEIT dashboard

Changes are left in the working tree on `codex/rebuild-c`. No commit or push.
Only the FACEIT page, its rail icon, its assets, packaging entries and checks
were changed. Python endpoints and the existing scoreboard remain unchanged.

## Review previews

These are screenshots of the actual renderer with synthetic API fixtures,
not the owner's account or generated UI screenshots:

- [Overview](rebuild-c/overview.webp)
- [Expanded match history](rebuild-c/match-history.webp)
- [Replay library](rebuild-c/replay-library.webp)

## Data used by each widget

| Widget | Source and calculation |
| --- | --- |
| Player | `/api/faceit` → `player.nickname`, `avatar`, `country`, `level`, `elo`. Missing/broken avatar falls back to an initial; zero/missing ELO is shown as unavailable. Level uses the supplied 1–10 value, never inferred from ELO. |
| Header sparkline / ELO history | `matches[].elo`, chronological order, after each match. Missing/zero ELO breaks the line. No reconstruction from today's ELO or ELO deltas. |
| Headline K/D | Sum of `kills` divided by sum of `deaths` over the returned sample. Zero total deaths shows an em dash. |
| Headline ADR | Arithmetic mean of supplied per-match `adr` values, explicitly labelled “Mean of match ADR”; not represented as round-weighted ADR. |
| Win rate | `won` count divided by number of returned matches. Sample size displayed. |
| Recent form | `won` for the latest five matches, newest first; map/date on hover. |
| Map performance | Group returned matches by `map`; win-rate bars with wins/played counts. Sorted by sample count. |
| Performance trend | K/D derived from each match's kills/deaths, or supplied ADR. K/D and ADR are separate selectable views with their own scale. Oldest to latest. |
| Chart details | Focusable points with map/date/value titles; expandable tables expose exact values and dates. |
| Match cards | `map`, `won`, own-team-first `score`, `kills`, `deaths`, `assists`, `adr`, `elo_delta`, `played_at`. Downloaded marker compares `demoNameFor(m)` with `/api/demos` filenames. |
| Expanded match | `team`, `rounds`, calculated K/D, post-match `elo`, full local date/time. No invented round timeline or opponent data. Expanded cards survive refresh. |
| Stats | Original `data-match` handler → `/api/demos/stats`; original full scoreboard, download/import/browser fallback, waiting and playback controls. |
| Replay cards | `/api/demos` → `demos[].name`, `size`, `when`, and `picked`. Watch uses original one-launch pick/play flow. Choose uses original persistent selection; clicking again clears it, now labelled “Clear choice”. |

`demos.history()` defaults to 20 matches (the server permits up to 50).
The dashboard labels the actual returned sample; it does not claim lifetime
statistics. `hs_percent` exists only in the separately requested full scoreboard,
so HS% is omitted from the dashboard. No extra stats requests were introduced.
The server's existing numeric normalization sometimes turns missing upstream
values into zero; the frontend cannot distinguish those from published zeros.

Following a nickname needs no FACEIT login. Browser sign-in requirements for
demo downloads are still explained by the original scoreboard flow. Unlinked,
account-not-found, transport error, stale cached data, no matches, no CS2 install,
empty library and replay-read errors have visible states.

## Assets and packaging

The rail icon, page heading and faint orange stamp all use the same CSS mask
from `cs2cfg/web/assets/faceit/faceit-logo.svg`. **This is a clearly marked
temporary placeholder**, not FACEIT's official logo. Replace it with the official
standalone SVG from FACEIT's brand kit before release. Keep the filename and a
valid viewBox; no code changes are needed. See the adjacent `README.txt`.

Skill badge color bands were checked against the badge references in
[FACEIT's CS2 skill-level documentation](https://support.faceit.com/hc/en-us/articles/10525200579740-FACEIT-CS2-Elo-and-skill-levels).
The badge displays the API level directly; the app does not hardcode ELO brackets.

All map images are original generated art, optimized to 560 × 315 WebP.
Unknown maps use `fallback.webp`. No Valve screenshots, CDN, chart library or
new runtime dependency. `cs2cfg.spec` now explicitly includes both new folders.
Animation uses finite transform/opacity entry effects, pauses when the page or
window is hidden, and is disabled by reduced-motion preferences. UI colors use
theme tokens; orange is reserved for brand marks and the relevant badge levels.
All seven themes currently defined in `const THEMES` were checked.

### Generation prompt set

Built-in imagegen was used once per map. Each prompt used this template:

> Use case: stylized-concept. Asset: small widescreen map thumbnail for competitive FPS match history. Original cinematic environment illustration evoking MAP: SCENE. Strong architectural silhouette, painterly realistic game concept art, crisp readable composition at 320px, landscape 3:2. No people, guns, logos, text, UI, watermark. Original layout, never copy a Valve screenshot.

| MAP | SCENE |
| --- | --- |
| dust2 | sunlit sandstone desert alley, arched gateway and stacked crates, dusty gold |
| mirage | warm North African courtyard, pink plaster tower and palm trees, blue sky |
| inferno | Italian village lane, ochre stucco, flower pots, terracotta roofs |
| nuke | blue and white nuclear power station exterior, cooling towers, industrial pipes |
| ancient | rainforest stone temple courtyard, mossy stepped ruins, lush green canopy |
| anubis | ancient Egyptian canal, sandstone columns and turquoise water |
| vertigo | unfinished skyscraper rooftop, yellow crane, concrete slabs and city skyline |
| overpass | European urban park over a concrete canal, bridge and distant television tower |
| train | industrial railway depot, rust red freight cars, overhead wires |
| cache | abandoned eastern European warehouse, white brick, green doors and weathered pipes |
| fallback | atmospheric empty tactical training yard, concrete walls and stacked cargo crates |

Two additional imagegen UI references established the player/chart layout and
match/replay layout before implementation. Their illustrative numbers are not
used by the application.

## Validation

- `python -m pytest` could not run: pytest is absent from the available Python
  runtime, and the sandbox blocked package installation from PyPI.
- Ran `python -m unittest discover -s tests -q` using the provisioned Python:
  **1,151 tests run, OK, two skipped**.
- `node tools/check_faceit_dashboard.cjs`: **75 browser checks**. Uses the real
  renderer, existing demo/scoreboard handlers and app CSS; stubs only APIs and
  launching CS2. Payload shapes follow `demos.player`, `demos.history`,
  `demos.stats`, `demos.installed` and `webui._demos`.
- Checks cover aggregates, chronological ELO, gaps, map samples, expansion and
  refresh, metric selection, Stats, Follow/Unfollow, forced refresh, Watch,
  Choose/clear, Get demo, progress/cancel, errors/empty/stale states, unknown maps,
  all levels, escaped payload text, image loading, replaceable masks, theme
  controls, layout overflow, hidden-window/tab animation pause and reduced motion.
- Viewports: 1440 × 1000, 1100 × 850, 1000 × 800; expanded 340px navigation rail;
  1366 × 768 at 125% scale. Reduced-motion run: **76 checks**.
- Play regression: `node tools/check_home_launcher.cjs`, **20 checks passed**.
- Device workspace regression: `node tools/check_keyboard_workspace.cjs`,
  **1,830 checks passed**.
- All inline JavaScript and the new external renderer parsed successfully;
  `git diff --check` passed.

No existing files in `tests/` were changed. The new browser check replaces no
old assertions; it adds coverage for the rebuilt markup and preserved behavior.

## Manual checks with the owner's data

1. Follow the real account; confirm avatar, nickname, level, current ELO and the
   sample matches against FACEIT. Compare chart points with their value tables.
2. Open Stats from several wins/losses and compare the unchanged scoreboard.
3. Get a demo directly and through the signed-in-browser fallback; confirm
   progress, Cancel, import and the Downloaded label.
4. Watch a local replay with CS2 closed; Choose and clear a replay; verify the
   existing console guidance while CS2 is already running.
5. Check the preferred theme, Windows scale and expanded rail; try keyboard
   expansion/metric controls and reduced motion.
6. Disconnect the network, Refresh, then reconnect; verify cached data and
   recovery. Try an invalid nickname and an account with no CS2 matches.
7. Replace the placeholder SVG and verify the rail, heading and stamp in a
   packaged Windows build. Run the owner's normal `python -m pytest` environment.

## Questions

None. The official logo replacement is the requested release handoff.

Temporary browser outputs, the map contact sheet and the generation source-path
manifest remain under `tmp/`. Automatic approval review blocked recursive cleanup
with the reason “blocked by policy”. They are not referenced or packaged by the
application. Deliverable previews are under `docs/redesign/rebuild-c/`.

## File sizes

<!-- FILE_SIZES -->

| File | Bytes |
| --- | ---: |
| `cs2cfg/web/index.html` | 701765 |
| `cs2cfg.spec` | 4690 |
| `cs2cfg/web/assets/faceit/dashboard.css` | 11579 |
| `cs2cfg/web/assets/faceit/dashboard.js` | 13258 |
| `cs2cfg/web/assets/faceit/faceit-logo.svg` | 208 |
| `cs2cfg/web/assets/faceit/README.txt` | 411 |
| `cs2cfg/web/assets/maps/ancient.webp` | 59674 |
| `cs2cfg/web/assets/maps/anubis.webp` | 50668 |
| `cs2cfg/web/assets/maps/cache.webp` | 54970 |
| `cs2cfg/web/assets/maps/dust2.webp` | 38876 |
| `cs2cfg/web/assets/maps/fallback.webp` | 30852 |
| `cs2cfg/web/assets/maps/inferno.webp` | 56980 |
| `cs2cfg/web/assets/maps/mirage.webp` | 44180 |
| `cs2cfg/web/assets/maps/nuke.webp` | 37506 |
| `cs2cfg/web/assets/maps/overpass.webp` | 51064 |
| `cs2cfg/web/assets/maps/train.webp` | 46692 |
| `cs2cfg/web/assets/maps/vertigo.webp` | 44374 |
| `tools/check_faceit_dashboard.cjs` | 17287 |
| `docs/redesign/rebuild-c/match-history.webp` | 88270 |
| `docs/redesign/rebuild-c/overview.webp` | 57842 |
| `docs/redesign/rebuild-c/replay-library.webp` | 81176 |
| `docs/redesign/REBUILD_C_NOTES.md` | 10563 |
