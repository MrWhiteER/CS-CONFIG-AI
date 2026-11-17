# Codex brief: one stats view for FACEIT + CS2

Edy's ask (Nov 17): "combine/merge the cs2 game stats and the faceit stats,
the games will be marked by FACEIT icons and CS2 icons, the stats the same
way, and the stats can be filtered by FACEIT stats and CS2 stats." Then:
"use codex to make it more beautiful". You own the design and the front-end
engineering. Make it look great; the data side is done.

## What already exists (backend, done, on this branch)

- `cs2cfg/matchlog.py` records Edy's own CS2 matches locally from CS2's game
  state feed (Competitive, Premier, Wingman; not DM/casual). History starts
  from the first match played after this ships; there is no backfill.
- `POST /api/stats` with body `{"source": "all" | "faceit" | "cs2", "force": bool}`
  returns:

```json
{
  "ok": true,
  "source": "all",
  "matches": [ /* newest first, one row per match */ ],
  "summary": {"matches": 12, "wins": 7, "win_rate": 58, "kills": 210,
              "deaths": 180, "assists": 40, "kd": 1.17, "kr": 0.78,
              "adr": 84.2, "hs_percent": 47},
  "counts": {"all": 12, "faceit": 8, "cs2": 4},
  "faceit": {"linked": true, "player": {"nickname": "...", "elo": 2100,
             "level": 9, "avatar": "...", "country": "..."},
             "error": "...", "stale": true},
  "cs2": {"recording": true}
}
```

Every row has `source` (`"faceit"` or `"cs2"`) plus the same fields:
`match_id, map, mode, won, score ("13 / 9", yours first), rounds, played_at
(unix s), kills, deaths, assists, kd, kr, adr, hs_percent, mvps, double,
triple, quadro, penta`. FACEIT rows also have `elo, elo_delta, team`; CS2 rows
have `elo: null`, `elo_delta: null`, `tied`, and `mode` = Competitive /
Premier / Wingman. Any number can be `null` (show a dash, never 0).
`summary` always describes exactly the filtered list. A FACEIT match is never
listed twice (the recorder sees it too; the backend drops the CS2 copy).

- `/api/faceit` is unchanged and still powers the profile header, ELO chart
  and nickname follow/unfollow.

## What to build (UI)

Today the FACEIT tab (`cs2cfg/web/index.html` panel `data-panel="faceit"`,
logic in `cs2cfg/web/assets/faceit/dashboard.js` `fcRenderDashboard()`, styles
in `assets/faceit/dashboard.css`) shows only FACEIT. Turn it into one combined
stats view:

1. **Filter**: a segmented control `All · FACEIT · CS2` with the counts from
   `counts`. It drives `source` on `/api/stats`. Remember the choice per
   account like other UI prefs if simple; otherwise per session is fine.
2. **Source icon on every match row**: the FACEIT mark
   (`assets/faceit/faceit-mark.svg`) or a CS2 mark. There is no CS2 icon in
   `assets/` yet; draw a simple original CS2-style mark as SVG (do not copy
   Valve's logo artwork). Also put the icon on the recent-form W/L pills.
3. **Same stat layout for both sources**: the K/D, ADR, win-rate, HS%, form
   cards come from `summary`, not computed per source in JS. Rows show the
   same columns for both sources; the ELO column shows `elo_delta` for FACEIT
   and the mode (Premier/Competitive/Wingman) for CS2.
4. **FACEIT-only parts** (profile header with level + ELO, ELO history chart)
   show when FACEIT is linked and the filter is All or FACEIT. With filter CS2
   they hide. If FACEIT is not linked, CS2 stats still show, with the
   follow-a-nickname box offered as a small card, not a blocker.
5. **Stats button**: FACEIT rows keep the 10-player scoreboard. CS2 rows have
   no scoreboard (GSI only knows your own line); expanding a CS2 row shows its
   full own line (MVPs, HS%, K/R, multi-kills) instead.
6. **Empty states**: CS2 filter with no rows: explain matches appear after the
   next Competitive/Premier/Wingman game, and that CS2 must be restarted once
   after this update so it picks up the new feed (only if `cs2.recording`).
7. Rename the tab/heading to fit both (e.g. "Stats", keep the FACEIT tab
   position and icon slot; your call on the wording and rail icon).
8. Poll `/api/stats` where `/api/faceit` is polled today (60 s, only while
   visible); keep the "New match" status toast working for both sources.
9. Use theme tokens only; every theme (violet default, ember, carbon, acid,
   daylight, pro, crimson, frost, neon) must still look right. Respect the
   existing reduced-motion pause (`fcPauseMotion`).

## Rules

- Do not change `cs2cfg/matchlog.py` or `/api/stats` response shape without a
  note; if you need a field, add it and a test.
- No new permission prompts of any kind (Edy's rule: everything is asked once
  at setup).
- Tests: `python -m unittest discover -s tests` must pass (the
  `test_overlay_gsi` too-large-request test is known to be flaky on Windows).
- Deliver preview screenshots with fake data for: All, FACEIT, CS2, CS2 empty,
  FACEIT not linked, plus one light theme (daylight), saved to
  `docs/redesign/stats-merge/preview/*.png`. Commit on the current branch.
