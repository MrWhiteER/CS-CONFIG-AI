# Phase 1 server lock: implementation and Edy's test steps

Built on `codex/server-lock`. No push, release, real rule application, or CS2
process-memory access was performed during development.

## What is implemented

- Every ping row has a keyboard-reachable lock action, labeled “Play only
  here.” Dubai is suggested. One city at a time; numbered POP variants for that
  city are included together. Switching city replaces the previous lock.
- The confirmation shows the exact city, revision, number of blocked relay
  addresses, running Steam/CS2 processes, queue/outage warnings, restart
  requirement, persistence after app exit, and the effect on CS2 traffic.
- The setup-installed helper creates one outbound block rule per blocked POP,
  named `CS CONFIG AI lock - <pop>`, protocol/profile Any, program set to the
  discovered `game\bin\win64\cs2.exe`. Only the exact `CS CONFIG AI region lock`
  group is ever removed. Empty POPs and POPs with only selected/shared IPs are
  skipped. Partner and unnamed POPs with blocked addresses are included.
  Plans exceeding 64 POPs, 2000 CIDRs or the helper's safe name format fail.
- Apply/unlock use `elevated.run("firewall.lock", args, wait=True)` and
  `elevated.run("firewall.unlock", wait=True)` on a background worker, with the
  helper's default timeout. There is no UAC fallback. Without the helper/current
  setup permission, `needs_setup: true` tells the UI to direct the user to
  Settings > **Run setup again**. The reference files stay in `docs/redesign/`;
  until the helper branch is merged/installed, this checkout needs setup.
- If CS2 is running, either change is persisted as pending and shows **Will
  apply when CS2 closes**. The 10-second observer executes it after confirming
  CS2 is closed. A new request replaces queued work; **Cancel pending change**
  clears it. App restarts preserve pending work. A changed directory invalidates
  a queued apply plan; the user must request it again. Helper failures are shown
  without automatically retrying the firewall mutation.
- Startup and subsequent local checks read effective Windows Firewall rules,
  filters, profile policy and service status. Disabled/changed rules, a disabled
  firewall, excluded local policy, missing rules and unreadable state have
  distinct results. Read-back must confirm the requested city before success.
- Helper rules have no description metadata. The local intent file stores the
  selected code/codes/city, revision, apply time, address digest and full plan.
  Real filters, POP rule names and remote-address sets must match that intent.
  Directory drift is outdated; missing/modified rules are missing/damaged.
  With rules but no selection, a unique region whose relays are all unblocked
  can be inferred and verified against a full plan; otherwise state is damaged.
  Inference cannot recover apply time, so restart timing stays unknown.
- The pill shows `LOCKED: DUBAI` and relay ping, or a lock-check state; the panel
  offers Unlock and re-apply. Changes persist when the app closes.
- `mm_dedicated_search_maxping` is read from the active account, shown in the
  panel/confirmation, and compared with the selected city's last ping. Advice
  is ping + 5 ms, rounded up, when the saved value is below the relay ping or
  more than 30 ms above that recommendation. The cvar is never written.
- An explicit “Enable -condebug” button appends that option through the
  existing backed-up launch-options writer. It preserves all other options,
  is idempotent, and refuses edits while Steam runs.
- A background local observer watches new console output while CS2 runs, even
  on other tabs or while the page is hidden. It does not start any ping sweeps.
  An explicit server datacenter different from the expected selection produces
  the existing corner-notice style and an ordered, evidence-based likely reason.
- Up to 20 detected server connections are stored locally with observation
  time, region, expected POPs and reason, and shown under “Server detection &
  recent matches.” Numbered variants of the selected city are treated together.
  Files are `server-matches.json` and `server-lock-selection.json` in the app's
  normal data directory. Raw console contents and server identities are not
  saved or uploaded.
- Existing ids, ping APIs, token protection, theme tokens and transform/opacity
  motion remain. New controls support keyboard focus and reduced motion.
  Phase 2/shared outage reporting is excluded.

## Verified and unverified

Automated verification uses synthetic fixtures and mocked external effects.
It covers block-list exclusions, numbered/partner/unnamed POPs, exact helper
operations/arguments, limits, setup-required responses without elevation,
subprocess inspection, helper rule filters, inference, revision drift, restart
times, confirmation expiry/change detection, durable queue/replacement/cancel,
read-back, shared Python/HTTP service, local history, partial lines/rotation,
deduplication, reason priority and launch-option writes. JavaScript is syntax
checked. No live firewall or relay integration test was run.
The full suite passed: **1,252 tests, 2 skips**.

The SDR JSON field names and Dubai addresses were already verified on Edy's PC
in [PING_WIDGET_BRIEF.md](PING_WIDGET_BRIEF.md). New rule/filter commands follow
Microsoft's documented [New-NetFirewallRule](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule)
and [Get-NetFirewallRule / ActiveStore](https://learn.microsoft.com/en-us/powershell/module/netsecurity/get-netfirewallrule)
interfaces. Actual helper integration, resultant policy and matchmaking enforcement
still need the manual test below. The small bundled ping fallback has no full
revision and is deliberately insufficient for locking. Use a full live or saved
Valve directory; locking itself never fetches one. The existing widget refreshes
that directory at most daily, so revision warnings depend on the refreshed cache.

**The current CS2 console format is an explicit assumption, not verified on
Edy's installation.** Existing public logs on Valve's trackers show SDR
connection identities and an explicit `Remote host is in data center` field;
they do not establish that the field is emitted on a successful connect in the
current client. See the [CS2 networking report](https://github.com/ValveSoftware/csgo-osx-linux/issues/3239)
and [Steam networking log example](https://github.com/ValveSoftware/Dota2-Gameplay/issues/15333).

The synthetic fixture `tests/fixtures/server_lock_console_assumed.log` assumes:

```text
[SteamNetSockets] [#123 SDR server steamid:... vport 0] connected
[Networking] Socket 'client' bound to '...' [#123 SDR server ...]
[Networking]         Remote host is in data center 'bom2'
```

Either connection-context line is accepted, followed within 80 lines by the
explicit datacenter. Failed attempts/disconnect summaries and generic primary,
backup or “Selecting” relay lines are excluded. IPs and SteamIDs are never
geolocated: a relay can be in a different city from the actual server. Until a
real log confirms this context/timing, detection can legitimately stay unknown.
If the field appears only on disconnect, this implementation intentionally does
not announce it as the current match. Attaching to an existing log starts at EOF,
so launch this app **before** joining the test match. A connection is a proxy
for a match, not an independently verified match boundary (reconnects can appear
as separate records). Times are observation times, not parsed game timestamps.

Reasons are “likely,” never proof: no lock + saved max ping allows the measured
region; missing/damaged/outdated rules; Steam/CS2 predating apply; recent ICMP
silence/high loss; then conditional party ping or lack of a match for the mode.
The last completed sweep seen when connection context was detected is retained;
a later sweep cannot overwrite it. Actual queue time, party membership and mode
availability are unavailable. Silence means unknown, not a confirmed outage.

Visual QA remains pending: Computer Use was not approved to control Google
Chrome. An offline preview is available; see below. Theme/reduced-motion behavior
uses the app's existing tokens but has not been visually verified across themes.

## Exactly what Edy should do

1. Run this checkout with `dev.bat`. Do not use the installed/released executable
   to test these changes. Open Play → the server regions pill → Refresh. Wait
   for discovery/measurements to finish. If locking is unavailable, the full
   Valve directory has not been obtained; the fallback cannot enable a lock.
2. Close CS2 and exit Steam completely, including its tray icon. In “Server
   detection & recent matches,” click **Enable -condebug**. It adds logging for
   the account selected in this app. Alternatively add `-condebug` yourself in
   Steam → CS2 → Properties → Launch Options, preserving other options.
3. Without setup installed, confirm the panel says the lock needs the one-time
   setup permission and points to Settings > **Run setup again**. Lock/unlock
   must never open UAC. After merging the helper branch, install it through
   setup once. On Dubai's row, review and choose **Lock to Dubai**. Confirm the pill
   says **LOCKED: DUBAI**, the panel offers **Unlock**, and saved max ping/advice
   are visible. Close/reopen the app and confirm it reads the lock again.
4. Optional read-only check in PowerShell: inspect the named group. There should
   be one outbound block rule per blocked POP, protocol/profile Any, program
   set to the full CS2 executable path, with no description metadata. Dubai's relay addresses
   must be absent from the block list. Other firewall groups must be unchanged.

   ```powershell
   $regionRules = Get-NetFirewallRule -PolicyStore ActiveStore | Where-Object { $_.Group -ceq 'CS CONFIG AI region lock' }
   $regionRules | Format-List DisplayName,Group,Direction,Action,Enabled,Profile,Description
   $regionRules | Get-NetFirewallAddressFilter | Format-List RemoteAddress
   $regionRules | Get-NetFirewallPortFilter | Format-List Protocol,LocalPort,RemotePort
   $regionRules | Get-NetFirewallApplicationFilter | Format-List Program
   ```

5. Keep this app open. Start Steam and CS2 **after** applying the lock. Refresh
   the server pings immediately before queuing, then play one match (solo makes
   the result easier to interpret). Compare the actual gameserver location in
   the Steam overlay with the app's recent entry. A different region should
   produce a corner notice with “Likely” reasoning. Check the detector even if
   the region is correct: an expected-region entry should be recorded.
6. If nothing is detected, run `status` once in CS2's console during the match
   to see whether it emits a client socket/datacenter dump. Then finish the
   match, close CS2, and send `game\csgo\console.log` from the CS2 installation
   folder (Steam → CS2 → Installed Files → Browse). Include actual server city,
   mode, solo/party, whether both processes restarted, and whether the lock pill
   was active. Logs may contain account/chat/server details; review before
   sharing. This is the real sample needed to validate or adjust the parser.
7. While CS2 is open, request another region, replace it with **Unlock**, then
   cancel the pending change. Confirm the current firewall lock stays in place.
   Queue **Unlock** again, close/reopen the app while CS2 stays open, then close
   CS2. Within the next observer cycle (plus helper execution), verify the pill
   returns to the normal ping display, with no UAC. Repeat the read-only group check:
   it should return no rules. Restart Steam/CS2 to refresh cached measurements.
   Check switching locks to another city, Esc/cancel, Tab/arrow navigation,
   window resizing, all ten themes and Windows reduced-motion behavior.
8. Do not change Valve's live directory just to exercise stale rules. For a
   safe visual check, run `python tools/preview_server_lock.py`, then open
   `build/server-lock-preview.html`. Its state/theme selectors demonstrate
   locked, outdated, missing and wrong-server states using synthetic data.
   Fetch is disabled and CSP forbids network requests; the preview has no
   backend, elevation or firewall access. Automated revision tests cover the
   backend behavior. Run the suite with `python -m unittest discover -s tests`.

If the app cannot unlock due to an environment/policy error, the exact group is
also removable from Windows Defender Firewall with Advanced Security. Remove
only `CS CONFIG AI region lock` rules; do not reset the firewall.

## Lock API

`cs2cfg.serverlock` exposes one shared service for HTTP, setup and the overlay.
The functions below never request permission or start a ping survey:

| Python function | Result |
| --- | --- |
| `list_regions()` | List of `{code, codes, city, country, partner, ping_ms, loss, status, ...}` from the existing survey/directory; unmeasured ping/loss are null and status is `unknown`. |
| `lock_status()` | Cached observer snapshot (shape below). |
| `request_lock(code)` | Trusted, review-free apply request; same validated plan, worker, helper and pending queue as HTTP. Returns a snapshot. |
| `request_unlock()` | Trusted unlock request through the same worker/queue. Returns a snapshot. |

Immediate validation/busy errors raise `ValueError` in Python. Worker failures
appear in snapshot `error`. Requests return before the helper completes: poll
`lock_status()` or GET until `busy` is false, then check `firewall.status`,
`pending` and `needs_setup`. `busy: false` alone does not prove a lock exists.

All HTTP POSTs require the existing `X-CS2CFG-Token` header. Successful HTTP
responses add `ok: true` to these payloads; this means the request was handled,
not that a firewall mutation has been verified. Validation errors return HTTP
400 with `{ok: false, error: "..."}`; a bad token returns HTTP 403.

| Route | JSON request | Response |
| --- | --- | --- |
| `GET /api/servers/lock` | None | Snapshot. |
| `POST /api/servers/lock/prepare` | `{code: "dxb"}` | `{plan_id, city, revision, relay_count, processes: [{name, started}], advice: {max_ping, recommended, text}}`; or `{needs_setup: true, detail}` with no plan. |
| `POST /api/servers/lock/change` | `{action: "apply", plan_id: "...", confirmed: true}` | Snapshot. Review token is single-use, expires after 5 minutes, and requires an unchanged plan. |
| `POST /api/servers/lock/change` | `{action: "unlock", confirmed: true}` | Snapshot; no plan token needed. |
| `POST /api/servers/lock/cancel` | `{}` | Snapshot with `pending: null`; leaves current rules/selection intact. |

Snapshot (other existing monitor/advice/history fields are retained):

```json
{
  "checking": false,
  "busy": false,
  "needs_setup": false,
  "can_lock": true,
  "pending": null,
  "error": "",
  "detail": "Region lock applied. Restart Steam and CS2 to re-measure relays.",
  "restart_needed": true,
  "firewall": {
    "status": "locked", "present": true, "active": true,
    "code": "dxb", "codes": ["dxb"], "city": "Dubai",
    "revision": 1794268433, "applied_at": 1794600000, "error": ""
  }
}
```

`firewall.status` is `unlocked`, `locked`, `outdated`, `missing`, `damaged` or
`unknown`; `present` and `restart_needed` may be null when inspection/timing is
unknown. Pending apply is `{action: "apply", code, city, requested_at, plan}`;
pending unlock is `{action: "unlock", requested_at}`. `plan` is persisted
implementation data; callers should use action/code/city to display queued work.
Pending changes show `detail: "Will apply when CS2 closes"` and execute once
after CS2 exits while the app is running. A missing/currently unavailable helper
sets `needs_setup: true`; show **Settings > Run setup again**, never a UAC
fallback. Restart Steam/CS2 after either successful change to re-measure relays.
