# Current batch

| Task | State | Next step |
| --- | --- | --- |
| Bundle offline Stats map pictures | Implemented and verified locally | Await GUPDATE |
| Animate profile changes inside Launcher cards | Implemented with a transparent background and verified locally | Await GUPDATE |
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
