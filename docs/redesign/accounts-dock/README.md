# Accounts dock

Four compact identities sit above Update centre. Names and service labels share
the rail's type and spacing; theme tokens supply every colour. Linked avatars
breathe over six seconds, the top edge has an eight-second sheen, and Steam's
reading dot pulses over four seconds. Motion pauses in hidden windows and is
removed with reduced motion. The collapsed rail retains each identity's tooltip
and accessible name.

Steam client selection opens the existing Settings switcher. Cloud opens the
existing account entry. FACEIT opens Stats and focuses the nickname box (or
Refresh for a followed player). Steam web Connect opens Steam's own window;
status polls every three seconds until linked or ten minutes, continues while
history is reading, and settles to thirty seconds otherwise. Requests do not
overlap and polling pauses while hidden. History errors can retry the read;
expired sessions offer Connect. Completion refreshes Stats. No backend or CS2
config changes are included.

## Previews

All accounts, avatars and matches are fictional. The harness uses the actual
app HTML/styles, dock and Stats renderer without starting the backend.

- [All linked, ember](preview/all-linked-ember.png)
- [Nothing linked, violet](preview/nothing-linked-violet.png)
- [Steam web reading](preview/steam-web-reading.png)
- [Collapsed rail](preview/collapsed-rail.png)
- [Daylight](preview/daylight.png)

Regenerate screenshots and run the dock browser checks with Node 22+ and Chrome:

```powershell
node docs/redesign/accounts-dock/capture.cjs
```

Set `CHROME_PATH` for a different Chrome installation. Browser data stays in the
ignored `.work/` directory. To explore manually, serve the repository root and
open `docs/redesign/accounts-dock/preview.html?state=ember`; other states are
`violet`, `reading`, `collapsed`, and `daylight`. The harness must be served over
HTTP so it can load the shipped app markup.

## Validation

- 42 dock browser checks: previews, layout at 1280×900 and 1024×768, account
  destinations, real switcher click-away handling, duplicate login prevention,
  polling cadence, reading/completion, timeout, expired/unavailable sessions,
  errors, focus preservation, all ten themes, reduced motion and hidden windows.
- Existing Stats integration: 67 browser checks passed
  (`STATS_CAPTURE_PREVIEWS=0 node tools/check_stats_merge.cjs`). Its isolated
  fixture now stubs the dock render hook; the dock harness tests the real hook.
- JavaScript syntax and `git diff --check` passed.
- `py -m unittest discover -s tests` could not run: this sandbox denied execution
  of both the installed `py.exe` and `python.exe`. No unittest result is claimed.
