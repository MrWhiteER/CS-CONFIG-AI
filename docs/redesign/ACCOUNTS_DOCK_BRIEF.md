# Codex brief: Accounts dock in the rail

Edy (Nov 17): "why is it in stats bar? It should be connected to my other
tools... a place where the logged-in accounts are shown nicely. Make it a nice
design with nice slow animation." The place Edy means is the empty space at the
foot of the left rail, just above the Update centre (`.rail-foot` in
`cs2cfg/web/index.html`, ~line 5944). You own the design and front end.

## What to build

1. **Accounts dock** in `.rail-foot`, above `#updc`. One compact row per
   account, each with its logo/avatar, name and a status dot:
   - **Steam (this PC)**: the Steam client account the app follows.
     Data: `whoData` from `/api/profile` (`accounts[]`, `active`, `following`,
     avatars via the existing `paintFace`). Click opens the existing
     account switcher (`whoMenu()` / Settings > Steam), unchanged.
   - **Steam web sign-in**: the shared session from `cs2cfg/steamweb.py`
     that unlocks match history and other Steam-site features.
     Data: `POST /api/stats/steam {}` -> `{linked, available, state:
     idle|reading|done|signed_out|error|unavailable, updated, found, error}`.
     Not linked: a "Connect" action calling
     `POST /api/stats/steam {action:"signin"}` (opens Steam's own login
     window; poll the status every 3 s until `linked` or 10 min).
     `state==="reading"`: show a quiet in-progress state ("Reading match
     history"). Linked: show "Match history · N matches" / last updated.
   - **Cloud sync**: `cloudData` from `/api/cloud` (`signed_in`, name/avatar
     fields from `cloud.me()`); not signed in -> the existing sign-in entry.
   - **FACEIT**: `fcData.player` (nickname, avatar, level) when followed;
     not followed -> "Follow" jumps to the Stats tab follow box.
2. **Remove the Steam card from the Stats tab** (`steamCard` in
   `cs2cfg/web/assets/faceit/dashboard.js` and its `#fc-steam-signin`
   click handler). At most, keep a one-line caption under the CS2 filter
   pointing to the dock when Steam web is not linked.
3. **Motion**: slow, calm, premium: e.g. a soft breathing glow on linked
   rows, a slow sheen across the dock, gentle status-dot pulse while reading.
   Long durations (4–8 s), never distracting. Respect
   `prefers-reduced-motion` and pause while the window is hidden (see
   `fcPauseMotion` for the pattern).
4. The rail can collapse to icons: the dock must collapse to a stack of
   avatars/logos with tooltips.
5. Theme tokens only; every theme must look right (violet, ember, carbon,
   acid, crimson, frost, neon, daylight, paper, pro). Ember is Edy's current
   theme, check it carefully.
6. Update the comment above `.rail-foot` that says account selection lives
   only in Settings.

## Rules

- No backend changes needed; if you add a field, add a test.
- No new permission prompts.
- `python -m unittest discover -s tests` must pass.
- Preview screenshots with fake data to `docs/redesign/accounts-dock/preview/`:
  all linked (ember), nothing linked (violet), Steam web reading, collapsed
  rail, daylight. Commit on the current branch.
