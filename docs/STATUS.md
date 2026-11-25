# Current batch

| Task | State | Next step |
| --- | --- | --- |
| Create original CT and T Launcher scenes | Dark workshop scenes with fitted balaclavas, fuller pointed hoods and smoked goggles; both previewed in the Launcher | Owner visual review |
| Remove keyboard and handheld RGB from the Launcher | Removed the visual overlays and Launcher palette request; physical-device RGB tested | Await GUPDATE |
| Show the CS2 loading banner on the monitor | Bundled the exact static image from the linked Steam post and checked both screen fits | Await GUPDATE |
| Stop Launcher scene animation during CS2 | Verified launch, running-process and reduced-motion behavior | Await GUPDATE |
| Launcher profile card labels | Removed the three numbered labels and verified the cards in Chrome | Await GUPDATE |
| Desk mixer lights | Removed the yellow light overlay and verified the preview in Chrome | Await GUPDATE |
| Controls tab name | Renamed the keyboard and mouse workspace and its shortcuts | Await GUPDATE |
| End triggering the microphone script | Saved binds and offline alias flow checked; current game bind unverified | Check the game console while reproduced |
| Steam and Accounts settings | Merged the login, account options and Steam client settings in the Steam tab | Await GUPDATE |
| CS2 Settings Recommended tab | Removed the pane; retained the game categories and apply-key control | Await GUPDATE |
| Connection speed checks | Startup download test removed; the test runs from the Connection card | Await GUPDATE |
| Sidebar Rescan and version row | Removed the row; hardware rescan is under This PC | Await GUPDATE |
| FACEIT flash and utility stats | Added both scoreboard fields from FACEIT match totals | Await GUPDATE |
| Premier flash and utility stats | Added replay-backed totals and verified the reader with a real Mirage demo | Await GUPDATE |
| Windows title bar | Verified icon-only dark caption with native controls on Windows 11 | Await GUPDATE |
| Script Builder File view | Added exact generated block preview and validated command editing | Await GUPDATE |
| Claude Launcher handoff | Queued locally | Retry after reported reset at 22:00 Asia/Dubai |

Work is local on `codex/launcher-static-ace-scene`.

## Prior Inventory batch

| Task | State | Next step |
| --- | --- | --- |
| Refresh and filter owned Steam Inventory | Implemented and checked with a live Steam read | Await GUPDATE |
| Inspect items and listen to owned music kits | Shared previews implemented and browser checked | Await GUPDATE |
| Interactive sticker showcase | Implemented with map-inspired lighting presets | Await GUPDATE |
| Sell multiple Steam items | Local multi-item selection and per-item Steam handoff implemented | Direct bulk submission needs a Valve-supported listing integration |

Inventory work is on `codex/inventory-workspace`, based on local `8171136`.

## Prior Stats and Launcher batch

| Task | State | Next step |
| --- | --- | --- |
| Bundle offline Stats map pictures | Implemented and verified locally | Await GUPDATE |
| Animate profile changes inside Launcher cards | Implemented with a transparent background and verified locally | Await GUPDATE |
| Remove the Launcher Review settings banner | Removed locally | Await GUPDATE |
| Claude handoff for Stats and Launcher changes | Queued in the agent log | Check the existing session after its reported reset |

The local branch is `codex/offline-map-art-inline-profile`, based on
`de0bdb0`. The published version is still 1.27.1.

## Previous audit batch

Owner authorized fixing the audit findings and building the proposed tools,
then explicitly authorized GUPDATE after completion and verification.
The audit batch shipped in 1.27.1. The table below records its prior local
handoff before publication.

| Task | State | Next step |
| --- | --- | --- |
| Atomic config saving and editor conflicts | Implemented locally | Final regression/release gate |
| Failed cloud pull accounting | Implemented locally | Final regression/release gate |
| Script release, recursion and input validation | Implemented locally | Final review and simulation coverage |
| Map baseline restoration and concurrent state | Implemented locally | Final regression/release gate; live-game follow-up |
| Updater path quoting | Implemented locally | Generated PowerShell parse check |
| Settings overflow and honest status | Implemented locally | UI verification |
| Four broken browser harnesses | All four pass locally | Run consolidated verification |
| Interactive script debugger | Backend and UI implemented | Workflow verification |
| Home / Work sync comparison | Backend and UI implemented | Workflow verification; real cloud follow-up |
| Preset A/B benchmark | Backend and UI implemented | Recorded-data verification; live capture follow-up |
| Winning-config trace and undo | Backend and UI implemented | Workflow verification |
| Diagnostic preview and ZIP export | Backend and UI implemented | Workflow verification |
| Guided practice and saved-value verification | Backend and UI implemented | Workflow verification; live-game follow-up |
| Consolidated verification / CI | Implemented locally | Full run and release integration |
| Approved publication | Release candidate built, version 1.27.0 | Publish after final checks |
| Claude handoff | Queued; acknowledgement pending | Delivery after reset/resumption; shared notes travel with approved publication |

Other existing worktrees are preserved. This file tracks this batch; older
Claude tasks retain their existing ownership. Do not infer live-game success
from synthetic tests or mark publication complete before it actually occurs.
