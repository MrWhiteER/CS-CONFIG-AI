# R3-7 item 3: GoXLR in Settings > Sound

Built on the supplied `codex/r3-7` worktree after reading the whole round 3
brief and the section 5 / 6b notes. No Python execution, git writes, app
backend startup, elevated helper calls, new helper jobs, dependencies or UAC.

## What changed

- Sound has a GoXLR panel beside the existing Windows sound-device panel on
  the shared Settings grid. Device and mic profile buttons switch with one
  click. Inline SVG icons, accessible labels, tooltips, keyboard activation,
  live feedback and theme tokens follow the existing UI. Narrow panes stack.
  Only the in-flight refresh glyph moves; hidden/background panes pause it,
  and reduced motion disables it. No concept/raster art was needed.
- GoXLR Utility uses stdlib HTTP directly to loopback, without proxies,
  redirects or shell commands. Status supplies profile names, active profiles
  and device serials. Multiple mixers require an explicit choice. An offline
  daemon, unplugged mixer, empty list and absent installation have separate
  states; absent installations show the calm `GoXLR not found` panel.
- Only `LoadProfile` and `LoadMicProfile` are sent. Requests validate names
  against a fresh listing and serial, ask for a nonpersistent load, then read
  back both active names. Failed/ambiguous requests keep the previous UI data,
  clear the current-profile claim, disable more switches and focus Refresh.
  This is UI rollback, **not a claim that hardware was rolled back**. A device
  load can succeed before a mic load fails; Refresh reveals the actual state.
- Discovery occurs on opening Sound, or after startup when Sound was restored.
  There is no polling or startup dependency. Sockets/process checks have 0.7s
  timeouts, responses are capped at 2 MiB, operations reject duplicate work,
  and GoXLR status/switch requests do not hold the shared UI request lock.
- **Official App support is deliberately limited to detection and read-only
  profile-name listing. Switching is unavailable.** The original premise
  that the App serves a public WebSocket is contradicted by the integration
  author's protocol reference: the App connects to the plugin's server on
  `:6805/?GOXLRApp`. That reference documents a device-profile `keyUp` message,
  with `com.tchelicon.goxlr.profilechange` and
  `payload.settings.SelectedProfile`, but no mic-profile action. Connecting a
  client to that port does not establish an App API. This implementation does
  not take over Stream Deck's listener, create a bridge job, or invent a mic
  command. An installed-version bridge/API reference is needed to finish
  official switching. The UI makes this limit visible and explains it in a
  keyboard-accessible information tooltip.
- Named Setups already exist (`cs2cfg/setups.py`); Practice is the save-field
  suggestion, and users can save Match / Recording or their own names. Sound
  can link the currently active Utility device + mic profiles to a saved
  Setup, or unlink offline. Select that Setup in Settings > Apply to load its
  bound GoXLR profiles immediately; game settings still wait for Apply.
  Merely saving, restoring preferences, changing account, starting the app,
  Apply and Play do not trigger GoXLR loads. A stale Setup response cannot
  trigger an older binding. Mixer errors do not undo the selected CS2 Setup
  or get hidden behind its success message.
- Bindings live only in this PC's app preferences, scoped by Steam account,
  Setup and mixer serial. Existing Setup rename/delete updates the binding.
  Nothing opens profile contents or edits GoXLR files. No executable or URL
  from a profile name is ever launched. CLI fallback is not used, so no CLI
  installation path or flags are assumed.

## Sources inspected online

No GoXLR source/API documentation was available locally. These primary sources
were read online on 2026-11-16; nothing was downloaded into the application:

- [Utility's API wiki](https://github.com/GoXLR-on-Linux/goxlr-utility/wiki/The-GoXLR-Utility-API):
  JSON POST `/api/command`, `"GetStatus"`, and `Status` envelope. HTTP and
  `/api/websocket` share commands; this adapter uses HTTP only. The embedded
  server can be disabled or moved to another port.
- [Utility IPC command source](https://github.com/GoXLR-on-Linux/goxlr-utility/blob/main/ipc/src/lib.rs):
  `Command(serial, command)`, `LoadProfile(String, bool)`,
  `LoadMicProfile(String, bool)`, `Ok` / `Error` / `Status` responses.
  [CLI source](https://github.com/GoXLR-on-Linux/goxlr-utility/blob/main/client/src/cli.rs)
  identifies the load boolean as `persist`.
- [Utility status source](https://github.com/GoXLR-on-Linux/goxlr-utility/blob/main/ipc/src/device.rs):
  `mixers`, `files.profiles`, `files.mic_profiles`, `profile_name` and
  `mic_profile_name`. The JSON shape used is
  `{"Command":["SERIAL",{"LoadProfile":["Match",false]}]}` (mic equivalent
  substitutes `LoadMicProfile`). These details have high source confidence;
  installed-version and hardware behavior still need the tests below.
- [TouchPortal integration author's protocol reference](https://github.com/oddbear/GoXLR-TouchPortal-Plugin/wiki/Development---specification):
  official connection direction, port/path, device-profile action and lack
  of acknowledgement for that action. This is an integration author's
  reference, not a vendor-supported public API or proof of current-version
  mic support. No official switch message is sent by this implementation.

## Files

- `cs2cfg/goxlr.py`: isolated adapter, discovery, allowlisted switching,
  read-back, local binding helpers and explicit `UNVERIFIED` comments.
- `cs2cfg/webui.py`: four token/Host-protected POST routes, controller lifetime,
  Setup binding housekeeping and isolated GoXLR I/O.
- `cs2cfg/profiles.py`: local machine key for account-scoped bindings.
- `cs2cfg/web/index.html`: Sound panel, lazy entrypoint and explicit Setup hook.
- `cs2cfg/web/assets/goxlr/sound.js`, `sound.css`: renderer, handlers and motion.
- `tests/test_goxlr.py`: 46 new unit-test methods, with fake HTTP/sockets,
  directory entries, registry, processes and preferences. Helper readiness/run
  are stubbed; tests never start the app server or the live elevated helper.
- `tools/check_goxlr_sound.cjs`: production-renderer/handler browser fixtures.
- This note and five requested `sec7-*.png` images.

## Validation

Python was **not run**, as instructed. The caller runs `python -m unittest`.
The 46 added methods are a count of test definitions, not a Python pass claim.
Existing Python assertions were inspected; none were deliberately removed.

All ten Node suites touching `index.html` pass:

| Suite in `tools/` | Checks |
| --- | ---: |
| `check_apps_tiles.cjs` | 108 |
| `check_home_launcher.cjs` | 202 |
| `check_setup_wizard.cjs` | 162 |
| `check_fixit_toolbox.cjs` | 97 |
| `check_graphics_workspace.cjs` | 61 |
| `check_keyboard_workspace.cjs` | 2845 |
| `check_connection_startup.cjs` | 8 |
| `check_faceit_dashboard.cjs` | 83 |
| `check_server_ping_widget.cjs` | 535 |
| `check_goxlr_sound.cjs` | 105 |
| **Total** | **4206** |

Sound covers absent/official/Utility, live button and keyboard handlers,
payloads, pending/duplicate work, acknowledgement and transport errors, stale
state/refetch, binding/unlink, production Setup selection and races, multi-mixer
choice, missing hardware/profiles, escaping, all ten themes in three backend
states, widths 820/480/360, background/hidden motion and reduced motion. Browser
fixtures stub app APIs; they do not prove physical switching. Existing audio
selectors are checked unchanged. Setup also passes all five inline-script
syntax checks and full-page first-run ordering. New JS syntax checks and
`git diff --check` pass. Earlier sections' screenshots were preserved across
their suites' automatic capture runs.

## Screenshots

Offline fixtures, real markup/CSS/renderers, 1366 × 900. Captures freeze motion.
The shell's empty telemetry is fixture data, not a hardware reading.

- `sec7-before-sound.png`: captured before editing Sound.
- `sec7-after-utility.png`: connected Utility, both profile groups and binding.
- `sec7-after-official.png`: official profile names and explicit switch limit.
- `sec7-after-notfound.png`: calm absent state with refresh.
- `sec7-after-paper.png`: Utility in the Paper theme.

## Edy to test on the home PC

Items labelled **UNVERIFIED** correspond to code comments for facts that were
not confirmed by a cited source. Other entries distinguish source confidence
from the live behavior that remains untested. Use existing saved profiles;
this app does not create or modify them.

1. **UNVERIFIED — executable names; medium confidence.** Open Task Manager's
   Details pane with the official App running and Utility closed. Confirm the
   process is `GoXLR App.exe`, `GoXLR.exe` or `GoXLRApp.exe`. Open Settings >
   Sound and click the refresh icon. Expect `Official App`, rather than not
   found. Repeat with Utility alone: names checked are `goxlr-daemon.exe` and
   `goxlr-utility.exe`; a responsive API identifies Utility independently of
   the process name. Record differing names; discovery must be updated if so.

2. **UNVERIFIED — official folders/extensions; medium confidence, supplied
   brief only.** In Explorer, open the current user's Documents, including its
   OneDrive/redirected location if applicable. Check
   `GoXLR\Profiles\*.goxlr` and
   `GoXLR\Mic Profiles\*.goxlrMicProfile`. Compare filenames (without
   extensions) with both groups after Sound > Refresh. Expect the same names;
   a missing/locked folder produces an empty group without creating anything.
   Record any custom profile location. Optionally compare timestamps before
   and after refresh; reading names should leave every profile unchanged.

3. **UNVERIFIED — Utility's default port 14564; high confidence from the supplied
   brief, not independently established in the cited material.** Open Utility
   alone and enable its local web server if it is disabled. Open
   `http://127.0.0.1:14564` in a browser. Return to Sound > Refresh. Expect
   `GoXLR Utility`, your device and saved names. A disabled server/custom port
   is intentionally unavailable here; this version does not discover custom
   ports or fall back to the CLI. Record your installed version and port.

4. **UNVERIFIED — additional official bridge/mic support in Edy's installed
   version; low confidence that it exists.** Open the official App and its
   Stream Deck integration settings, then Sound > Refresh. Expect read-only
   profile buttons and `Profiles only · switching unavailable`. Hover/focus
   the information icon for the reason. Clicking a disabled profile must do
   nothing; Stream Deck should keep working. Do not expect official switching
   from this build. If the installed plugin exposes a newer documented bridge
   or mic-profile action, provide its protocol/source so both controls can be
   implemented without guessing. No listener is installed by this feature.

5. **Utility device switching — high source confidence; live behavior untested.**
   Keep Utility's profile view visible. Open Sound, refresh and click a different
   device profile. Expect Utility and the physical mixer to change, then a
   checkmark on that profile and `Profile switched`. Refresh and confirm the
   name remains active. If the app reports that read-back is not confirmed,
   refresh and record the actual name/version; no successful change is claimed
   until it can be read back.

6. **Utility mic switching / nonpersistent load — high source confidence;
   live behavior untested.** In Sound, click a different mic profile while
   viewing Utility's mic settings. Expect the settings/active name to change
   and the corresponding checkmark to appear after read-back. Device and mic
   loads request `persist=false`, with no Save/SaveAs/Delete command. Check
   that your saved profiles remain intact. Return to your usual mic profile.

7. **Setup bindings — implemented and mocked; hardware behavior untested.**
   In Settings > Apply save Practice, Match and Recording as desired. In Sound
   choose your intended Utility profiles, select Match in the Setup dropdown
   and click the chain icon. Expect `Setup linked`. Change profiles manually,
   return to Apply and click Match. Expect both bound GoXLR profiles to load;
   game settings still await Apply. Restarting/restoring the app must not load
   them automatically. In Sound select Match and click the broken-chain icon;
   choosing Match again must then leave GoXLR alone. Rename/delete a bound
   Setup and verify the link follows/is removed. A second Steam account must
   not inherit the first account's binding.

8. **Disconnect/error reconciliation — implemented and mocked; timing untested.**
   Open Sound with Utility connected. Close Utility (or unplug the mixer),
   then click a previously listed profile. Expect a local error, no new active
   checkmark, enabled Refresh and no UI freeze. Reopen/reconnect and refresh;
   expect the actual active names and working controls. If a two-profile Setup
   changes only one profile before failure, expect the error to remain visible;
   Refresh must show that partial result. No automatic hardware rollback occurs.

9. **Visual/accessibility smoke test — high browser-fixture confidence.**
   In Settings > Look select Paper, Daylight and your usual dark theme, return
   to Sound and check the profile/refresh/link glyphs and focus rings. Narrow
   the window: expect stacked cards and wrapping names. Enable Windows reduced
   motion, then refresh: expect no rotating glyph. Background the app during a
   request: its glyph should pause. With both GoXLR apps closed, Refresh should
   show only the calm not-found state alongside the existing Sound devices.

## Open questions

- Official device + mic switching remains incomplete pending a documented,
  compatible bridge. The shipped read-only state is explicit; it is not a
  simulated successful integration. The source boundary is the reason.
- Confirm the process names, folders, Utility port/version and real hardware
  results using the checklist. Custom official folders and Utility ports are
  not configurable in this first version.
- Caller must run the Python suite. No live GoXLR or helper validation was
  performed on this development PC, where neither GoXLR backend is installed.
