# Shared FACEIT + CS2 stats

The Stats tab keeps its existing rail position and uses the app's theme tokens.
The source control filters `/api/stats`; its summary drives K/D, ADR, win rate
and headshots. Recent form and every history row carry source marks. The
original CS2 chevrons and Stats bar mark are local SVG assets.

FACEIT's profile and ELO history appear in All and FACEIT. CS2 Stats expands
the player's own line; FACEIT Stats opens the existing ten-player scoreboard.
An unlinked FACEIT account offers a small follow card while local stats remain
available. Empty local history explains the supported modes, lack of backfill,
and one-time CS2 restart when recording is enabled.

Filters are remembered per Steam account for the browser session. Refresh and
the visible-tab 60-second poll load the combined endpoint. Late requests are
discarded; refreshing preserves expanded rows and unfinished nickname input.
New-match notices track both sources, including the first locally recorded
match. FACEIT refresh warms the cache before reading its separate ELO history.
No backend, response-shape or permission-flow changes were needed.

## Previews

Screenshots use offline fixtures with the real renderer, stylesheet and app shell
at 1440 × 1200. No user match data is captured.

| State | Screenshot |
| --- | --- |
| All | [all.png](preview/all.png) |
| FACEIT | [faceit.png](preview/faceit.png) |
| CS2, own line expanded | [cs2.png](preview/cs2.png) |
| CS2 empty, recording enabled | [cs2-empty.png](preview/cs2-empty.png) |
| FACEIT not linked | [faceit-not-linked.png](preview/faceit-not-linked.png) |
| Daylight | [daylight.png](preview/daylight.png) |

## Validation

Run `node tools/check_stats_merge.cjs` to check the workspace and regenerate all
six previews. `node tools/check_faceit_dashboard.cjs` remains an alias.
The harness reads the actual production scripts and mocks only APIs and game
launching. Chrome's profile and generated HTML stay in the ignored `.work/`
directory here. Override `CHROME_PATH` if Chrome is installed elsewhere.

Browser checks cover server summary values, counts, source icons, filters,
account preferences, late responses, missing values, draws, stale/failed reads,
draft input preservation, follow/unfollow, both new-match notices, first match,
FACEIT scoreboard and replay actions, 60-second visible-only polling, chart
controls, nine themes, and reduced-motion handling.

Validated on November 17, 2026:

- 1440 × 1200: 67 browser assertions passed; all six previews visually reviewed.
- 1366 × 768 with reduced motion: 68 assertions passed.
- 900 × 900 with a 260px rail: 67 assertions passed.
- 1366 × 900 at 125% scale: 67 assertions passed.
- Inline JavaScript parsing and `git diff --check` passed.

For layout variants, set `STATS_CAPTURE_PREVIEWS=0` to retain the delivery images.
The harness accepts `FACEIT_VIEWPORT`, `FACEIT_RAIL`, `FACEIT_SCALE` and
`FACEIT_REDUCED=1` for compatibility with the previous preview command.

**Python suite remains unverified.** The required
`py -m unittest discover -s tests` was attempted using the installed launcher at
`C:/Users/saruk/AppData/Local/Programs/Python/Launcher/py.exe` because `py` is not
on this tool session's PATH. Windows returned **Access is denied** before any
test ran. Executing Python 3.13 directly was also denied. The session permits no
permission escalation, so the full Python suite still needs to run in an
environment that can execute the installed interpreter. No claim of a Python
test pass is made.

**Commit also blocked by the environment.** The branch was verified as
`claude/project-thread-jgvzpv`. Staging the implementation failed because Git
could not create the shared worktree metadata file
`G:/Projects/cs2-autoconfig/.git/worktrees/cs2-stats/index.lock`:
**Permission denied**. No files were staged and no commit, push, merge or release
was created. All implementation files and previews remain in this worktree.

Suggested commit messages once Git metadata writes are available:

- `feat(stats): merge FACEIT and local CS2 match history`
- `docs(stats): add merged stats previews and validation notes`
