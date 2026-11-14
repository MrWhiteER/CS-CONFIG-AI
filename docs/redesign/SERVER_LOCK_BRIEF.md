# Server lock + wrong-server check: brief for Codex (phase 1)

Edy plays from Dubai. CS2 often puts him on far servers (80+ ms) even though Dubai exists.
The Play tab already has a server ping drop-up (cs2cfg/serverping.py, the `sp-*` widget in
cs2cfg/web/index.html, routes in cs2cfg/webui.py; see PING_WIDGET_BRIEF.md). Phase 1 adds two
things on top of it. Phase 2 (shared outage reports through the Cloudflare Worker in worker/,
and "others can connect, you can't" diagnosis) is NOT part of this job.

## A. Lock matchmaking to one region

CS2 has no setting that forces a region. The matchmaker picks datacenters from the ping it
measures to Valve's SDR relays, so the working method (the one existing "server picker" tools
use) is: block outbound traffic to every OTHER region's relay IPs with Windows Firewall, so
only the chosen region is reachable.

- In the drop-up, each region row gets a "Play only here" action (a lock icon; keyboard
  reachable). Default suggestion: the preferred region (dxb). Allow choosing a small set
  (e.g. Dubai + Fujairah) if it fits the UI; one region is the minimum.
- Relay IPs come from the SDR config the widget already fetches/caches
  (GetSDRConfig `pops[code].relays[].ipv4`). Block all relays of all non-chosen POPs. Never
  block the chosen POPs. Remote-address rules, outbound, UDP, all programs (Steam's own
  process measures the pings, not only cs2.exe).
- All rules live in ONE named group (e.g. "CS CONFIG AI region lock") so unlock removes
  exactly them and nothing else. Use one rule (or a few) with a remote-address list, not
  hundreds of rules.
- Creating/removing rules needs administrator. Use the app's existing elevated one-shot in
  cs2cfg/quickfix.py (`_run_elevated`), one UAC prompt per lock/unlock. Never elevate the
  whole app (see cs2cfg/temps.py note about Steam).
- State: the pill shows the lock ("LOCKED: DUBAI ..."), the panel shows a clear Unlock
  button. Read the real firewall state on startup (rules present or not), don't trust a
  saved flag alone.
- Warn in plain words before locking: queue can take longer; if the region is down you won't
  find a match until you unlock; CS2 and Steam must be restarted for the matchmaker to
  re-measure (detect if cs2.exe/steam are running and say so).
- If the SDR config revision changes while locked, show "lock is out of date, re-apply"
  (new relay IPs would otherwise be reachable).
- Also show (read-only) the user's `mm_dedicated_search_maxping` and recommend a value just
  above the chosen region's ping if it is lower than that ping or far above it. Don't write the
  convar in this phase.

## B. Tell the user when a match landed on the wrong server, and why

- While cs2.exe runs and a lock or preferred region is set, find out which region the current
  match server is in. Do not guess the mechanism; verify it. Candidates, in order:
  1. CS2's console output via the `-condebug` launch option (writes game/csgo/console.log).
     The app already manages launch options (localconfig.vdf) and watches CS2 files
     (cs2cfg/gamewatch.py). Find the line(s) that name the data center / SDR POP or server
     address on connect. If you can't confirm the exact log format from real data, write the
     parser against clearly marked assumptions and say so in your summary; Edy will play a
     match and send a real console.log.
  2. Otherwise, any other reliable, read-only, VAC-safe source. NEVER read or touch CS2's
     process memory, inject anything, or hook the game.
- When the region differs from the locked/preferred one, show an in-app notice (the app
  already has a corner notice pattern used by updates) with the likely reason, checked in
  this order and stated honestly as "likely":
  - no lock active and max ping allows that region;
  - lock rules missing/out of date (firewall state check);
  - Steam/CS2 not restarted since the lock was applied;
  - preferred region unreachable or high loss at queue time (from the last ping sweep);
  - in a party: the party's combined ping decides the region (say so; we can't see members);
  - the region simply had no match available for the chosen mode at that time.
- Keep a short local history (last ~20 matches: time, region, expected region, reason).

## Rules

- Pure standard library like the rest of the app. Windows only.
- Keep all existing ids/APIs; add new ones. All 10 themes, transform/opacity animation,
  prefers-reduced-motion, existing tokens.
- Unit tests in tests/ for: building the block list from an SDR config fixture, the firewall
  command text (mock subprocess; tests must never touch the real firewall or network), lock
  state parsing, console.log parsing, reason selection. Run `python -m unittest discover -s
  tests` (it may be blocked in your sandbox; if so say so).
- Work on the current branch (codex/server-lock). Do not push, do not release, do not apply
  real firewall rules on this machine.
- Finish with a summary: what you built, which parts are verified vs assumed, and exactly what
  Edy needs to do to test it (e.g. play one match with -condebug).
