# Accounts dock

The rail footer shows one main Steam identity, its status, a cluster of other
account status dots, and a disclosure chevron. Clicking it opens an upward
popover without changing the nav layout. In the icon-only rail, only the main
avatar remains and the panel opens to its right with names and actions visible.
The panel uses the browser top layer so the rail cannot clip it.

The panel contains the current Steam account, every other local account from
`whoData.accounts`, Steam web / match history, Cloud sync, and FACEIT. Local
Steam rows use the existing `data-use` account switch and reload handler. Manage
on the current Steam row opens the existing Settings switcher. Connect, sign-in,
Follow, and polling retain their existing behavior. The header counts linked
identities against all displayed identities.

Click the main row again, click outside, or press Escape to close. Opening moves
focus to the first account; closing returns focus to the main row. Closed rows
are inert. Status polls preserve focused buttons and do not restart the unfold.

## Motion

The panel rises 16 px and scales from 97% over 680 ms; opacity takes 480 ms.
Rows fan from 18 px below and 6 px left over 720 ms, staggered by 65 ms (capped
at eight steps). The easing is `cubic-bezier(.22,1,.36,1)`. Closing reverses the
movement over 520 ms with a bottom-to-top 22 ms stagger and a 360 ms fade.
The panel leaves the top layer after 760 ms. Existing six-second breathing,
eight-second sheen, and four-second reading pulse remain. Hidden windows pause
ambient animations and settle transitions. Reduced motion makes changes instant.
All surfaces and colors use app theme tokens, with an opaque popover backing.

## Previews

All identities and match data are fictional. The harness loads the actual app
markup, styles, dock, Stats renderer, and Steam switch click handler offline.

- [Closed, ember](preview/closed-ember.png)
- [Open, ember](preview/open-ember.png)
- [Open, violet / disconnected](preview/open-violet.png)
- [Open, daylight](preview/daylight-open.png)
- [Collapsed rail, closed](preview/collapsed-rail-closed.png)
- [Collapsed rail, open](preview/collapsed-open.png)
- [Steam web reading](preview/steam-web-reading.png)
- [Opening animation strip](preview/open-anim-strip.png)
- Individual opening frames: [1](preview/open-anim-1.png),
  [2](preview/open-anim-2.png), [3](preview/open-anim-3.png)

Regenerate screenshots and run browser checks with Node 22+ and Chrome:

```powershell
node docs/redesign/accounts-dock/capture.cjs
$env:STATS_CAPTURE_PREVIEWS='0'; node tools/check_stats_merge.cjs
```

Set `CHROME_PATH` for another Chrome installation. Browser data stays in ignored
`.work/`. For manual exploration, serve the repository root and open
`docs/redesign/accounts-dock/preview.html?state=ember`; other states are `violet`,
`reading`, `collapsed`, and `daylight`. Click the main identity to expand.

## Validation

70 dock browser checks pass, covering full nav visibility at 1280 x 900, layout at 1024 x 768,
open/close, reverse animation, focus return, keyboard entry and navigation,
collapsed flyout geometry, direct Steam switching and reload, existing account
destinations, login duplication, polling, reading/completion, timeout, expired
sessions, errors, refresh focus preservation, all ten themes, reduced motion,
and hidden windows. The existing Stats suite passes 67 checks.

JavaScript syntax checks pass. Python unittest execution is unavailable in this
sandbox: neither `python` nor `py` is on PATH. No unittest result is claimed.
No backend or CS2 config changes are included. Changes remain in the working tree.
