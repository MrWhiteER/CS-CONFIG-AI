# Phase 1 server lock: implementation and Edy's test steps

Built on `codex/server-lock`. No push, release, real rule application, or CS2
process-memory access was performed during development.

## What is implemented

- Every ping row has a keyboard-reachable lock action, labeled “Play only
  here.” Dubai is suggested. One city at a time; numbered POP variants for that
  city are included together. Switching city replaces the previous lock.
- The confirmation shows the exact city, revision, number of blocked relay
  addresses, running Steam/CS2 processes, queue/outage warnings, restart
  requirement, persistence after app exit, and the effect on all programs.
- Outbound UDP block rules use a remote-address list, all programs/ports and
  profiles. Only the exact `CS CONFIG AI region lock` group is ever removed.
  Every non-selected POP is included, even partner or unnamed POPs. Shared IPs
  belonging to the selected POPs are excluded from the block list.
- Apply/unlock each use the existing `quickfix._run_elevated` one-shot. The
  application and Steam are never elevated by this feature. The UI stays
  responsive during UAC. Canceling or failing UAC does not claim success.
- Startup and subsequent local checks read effective Windows Firewall rules,
  filters, profile policy and service status. Disabled/changed rules, a disabled
  firewall, excluded local policy, missing rules and unreadable state have
  distinct results. Read-back must confirm the requested city before success.
- Rule descriptions contain revision, selected POPs and apply time. A directory
  revision or address change triggers “lock is out of date, re-apply.” A saved
  selection only detects missing rules; it never proves the lock is active.
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
It covers block-list exclusions, numbered/partner/unnamed POPs, script text,
subprocess inspection, effective-state parsing, revision drift, restart times,
confirmation expiry/change detection, UAC cancellation, read-back, local history,
partial lines/rotation, deduplication, reason priority and launch-option writes.
The full suite passed: **1,227 tests, 2 skips**. JavaScript was syntax checked.
Windows PowerShell's parser accepted apply, unlock and inspect scripts without
executing them. No live firewall or relay integration test was run.

The SDR JSON field names and Dubai addresses were already verified on Edy's PC
in [PING_WIDGET_BRIEF.md](PING_WIDGET_BRIEF.md). New rule/filter commands follow
Microsoft's documented [New-NetFirewallRule](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule)
and [Get-NetFirewallRule / ActiveStore](https://learn.microsoft.com/en-us/powershell/module/netsecurity/get-netfirewallrule)
interfaces. Actual UAC behavior, resultant policy and matchmaking enforcement
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
3. On Dubai's row, Tab to the lock icon (or click it), review the warning and
   choose **Lock to Dubai**. First cancel UAC once: the app must show an error
   and must not claim a new lock. Repeat and accept UAC once. Confirm the pill
   says **LOCKED: DUBAI**, the panel offers **Unlock**, and saved max ping/advice
   are visible. Close/reopen the app and confirm it reads the lock again.
4. Optional read-only check in PowerShell: inspect the named group. There should
   be one outbound UDP block rule with all programs/profiles, a remote list,
   and a description containing revision/selected POPs. Dubai's relay addresses
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
7. After the match, click **Unlock**, accept its single UAC prompt and verify
   the pill returns to the normal ping display. Repeat the read-only group check:
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
