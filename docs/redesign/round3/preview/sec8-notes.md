# R3-8: ready configs and Bring your own configs

Worked in the supplied `codex/r3-8` worktree after reading the complete round 3
brief, section 7 notes and section 8 reference. No Python, backend/server startup,
git writes, helper calls, dependencies, helper jobs or new administrator prompts.

## What changed

- **R3-8 follow-up / Edy's decision: “keep all”. Question 7 is closed.**
  Deferred execs in binds and aliases now remain deferred. Each reachable
  command config gets one separate app-owned copy under `imported_profiles/`.
  Names combine a safe source basename with source-path identity, so profiles
  with the same name in different folders cannot overwrite each other. Bind,
  alias and nested exec targets are rewritten to the configured layout prefix
  and copied filename, including explicit extensions. Copies only use the
  bounded selected snapshot; no external target is read or executed.
- A queue guards deferred/self-referencing profile graphs without dropping
  normal switches back to an earlier profile. Immediate exec cycles in copied
  files have their closing link dropped with its source, line and reason.
  Missing targets still count as Dropped; safe sibling commands remain. Alias
  reporting has a cycle guard, and deferred bodies share the command budget.
  The review refuses a layout prefix containing whitespace because it cannot
  be embedded safely inside Source's quoted bind/alias body; source filenames
  are sanitized independently and do not have that restriction.
- The wizard includes copied commands in **Kept** and shows a **Profiles**
  count. What changed distinguishes kept profiles from actual losses and
  lists direct binds and binds reached through alias chains against copied
  targets. Alias mappings describe possible definitions in the imported set;
  they do not execute or predict the player's runtime alias state.
- Finish writes the reviewed startup stream, all copied profiles and source
  protection metadata through one `write_changed` / `BackupSession` batch:
  every backup completes before any replacement. Review exposes counts and
  mapping details, not config bodies. Later Keyboard/Editing changes in an
  installed copied profile survive preparation just like the imported stream;
  a changed newly accepted copy replaces its predecessor with a backup.
  Original-file collision behavior stays app-only. NVIDIA targets are unchanged.

- Startup builds the standard starter layout, the chosen preset's performance
  config and launch-options notes in account-scoped app data. It uses the
  existing `starter` loading-coordinator task, after first-run decisions and
  preference restoration. Other startup loaders remain independent, and the
  existing 15-second loading-screen deadline remains in place. No new worker,
  service or timer is introduced.
- Without saved `cfg_write_ok === True`, the game folder receives no files.
  The app copy is usable by Keyboard, Scripts and the scanner. With consent,
  generation sends the ready files to CS2 only while CS2 is closed. Missing
  CS2, a running game, a protected original or an unwritable destination leave
  the app copy ready and show the reason. Refresh retries; it never requests
  elevation. The wizard's existing Allow action is the only permission path.
  The legacy Create it action now checks consent and the running game too.
- Preparing does **not** apply picture settings, edit Steam launch options or
  assert an Apply verification result. The suggested launch options remain a
  text file; Apply still installs the launch entry point through its existing
  flow. “Ready in CS2” means the files are present, not that CS2 has loaded them.
- All changed destinations are backed up with `BackupSession` before the first
  replacement. Complete files replace destinations atomically. Existing personal
  starter files stay intact; existing autoexecs only gain missing exec links.
  Same-second backup sessions now reserve separate directories instead of
  overwriting each other's files/manifests. Generated writes do not prune old
  restore points during startup.
- The wizard's optional **Bring your own configs** step follows permission.
  Choose multiple files with the existing native Windows dialog, or choose a
  folder with the existing folder picker. No autoexec filename is guessed.
  Folder imports require explicit entry-file choices; files load in the listed
  order. Cancellation, read errors and Skip leave the current setup intact.
- Imports are bounded read-only snapshots: at most 256 configs / 4 MiB, with
  folder traversal and exec-expansion limits. Links/junctions are refused.
  The same scanner, language parser, formatter and layout-profile analysis used
  by Configuration studio / Keyboard process the snapshot. No config command
  is executed and no helper is consulted.
- Chosen entry streams are rebuilt into standard
  `mainsettings/imported.vcfg`, linked after the generated preset. Immediate
  execs merge **in place**. Command order, duplicate settings, repeated binds,
  aliases and later overrides are retained rather than sorted into separate
  categories (which could change their meaning). Unknown commands are kept.
  A prior match-profile selection in the app copy is reset through `layouts.py`
  to the new standard layout, with its old pointer backed up; pins are retained.
  Kept / Merged / Dropped have SVG icons and short labels; Details lists every
  dropped item's source file, line where available and reason.
- **Import limit:** malformed lines, missing exec targets, immediate exec
  loops and game-owned KeyValues files are dropped with explicit review
  reasons. Deferred execs are kept through copied profiles and are never moved
  to startup. Merged counts startup exec links; Kept counts retained commands
  across the startup stream and copied files; Profiles counts unique copied
  files. Dropped counts commands/lines/files as explained by each detail.
  This is an import review, not a promise of game compatibility.
- Review does not save anything. Use this copy accepts the review token; Finish
  saves it with a backup. Skip removes the import answer. Tokens are bound to
  the snapshot and Steam account. Choosing new files invalidates old tokens;
  stale/cross-account previews cannot be committed. In-flight pick/review work
  blocks duplicate navigation and Escape. The native picker does not hold the
  shared request lock while Windows is waiting for a choice.
- Original paths are protected persistently. If deployment would touch an
  original (including an original autoexec), the rebuilt set stays in app data
  and the UI explains why. Importing the app's own prepared output is refused.
  Changes made to an installed imported file from Keyboard/Editing survive the
  next startup; accepting a new import can replace it after backing it up.
  Local path-protection and installation records never enter portable exports.
- Config files now opens on readiness, six small file-purpose guides, import
  and portable-copy actions. **Advanced** opens the existing studio and starter
  controls with a native keyboard-accessible disclosure. IDs, scan, formatting,
  repair, rename, behavior editing, file/folder selection, portable setup and
  the Editing tab remain reachable. SVGs and surfaces use theme tokens. The
  preparation glyph uses only transform/opacity, pauses when hidden/backgrounded
  and stops with reduced motion. No raster concept was needed.
- The first-run folder display no longer probes write access by creating a
  temporary file before permission; actual deployment reports access failures.

## Files

- `cs2cfg/configbundle.py`: app storage, safe preparation/deployment, snapshot
  rebuilding and original/edited-file protection.
- `cs2cfg/webui.py`: three token/Host-protected config endpoints, wizard commit,
  consent/game guards and startup preparation using existing profile emission.
- `cs2cfg/firstrun.py`, `picker.py`: wizard step, read-only folder display and
  multiple selection using the existing native picker implementation.
- `cs2cfg/backup.py`: unique reservation for same-second backup sessions.
- `cs2cfg/portable.py`: withholds local installation/source records.
- `cs2cfg/web/index.html`, `web/assets/config/files.js`, `files.css`: simplified
  tab, disclosure, import UI and startup wiring.
- `tests/test_configbundle.py`: temp-directory checks using fake preferences,
  profiles and stubbed native pickers, game state and helper. Follow-up cases
  cover rewritten binds, alias chains/cycles, nested execs, deferred return
  switches, immediate cycles, missing targets, name collisions, original bytes,
  reviewed-snapshot commit, copied-profile installation/edit preservation,
  original collisions and backup failure before any replacement.
- `tests/test_portable.py`: one new local-metadata exclusion test.
- `tests/test_firstrun_web.py`: existing endpoint fixtures now stub helper
  readiness/run/install and app discovery; they cannot invoke the live helper.
- `tools/check_setup_wizard.cjs`, `tools/check_config_files.cjs`: offline
  production markup/renderer/handler browser checks and section 8 captures.

## Validation

Python was **not run**, as instructed. The caller must run `python -m unittest`.
The original round's 49 new Python methods were a definition count, not a
Python pass claim. Follow-up Python cases have also **not been executed**.
No existing Python markup assertions required replacement.

The wizard browser test deliberately updates the old six-step / optional-region
counts, numeric step positions and permission-to-Sound navigation for the new
import step. Its old automatic-starter assertion is replaced by app-copy
preparation checks for skipped, denied and granted permission; backend unit
tests cover the actual write boundary. Existing feature assertions remain.

All eleven `tools/check_*.cjs` suites touching `index.html` pass:

| Suite | Checks |
| --- | ---: |
| check_apps_tiles.cjs | 108 |
| check_config_files.cjs | 73 |
| check_connection_startup.cjs | 8 |
| check_faceit_dashboard.cjs | 83 |
| check_fixit_toolbox.cjs | 97 |
| check_goxlr_sound.cjs | 105 |
| check_graphics_workspace.cjs | 61 |
| check_home_launcher.cjs | 202 |
| check_keyboard_workspace.cjs | 2845 |
| check_server_ping_widget.cjs | 535 |
| check_setup_wizard.cjs | 197 |
| **Total** | **4314** |

Wizard validation also checks all five inline script bodies and full-page
first-run ordering. Config checks exercise the production readiness handlers,
pending/error states, explicit collection preservation, native disclosure via
keyboard, studio scan/format handlers, all ten themes, 820/480/360 widths, long
paths, hidden/background motion and reduced motion. These are synthetic API
fixtures, not backend execution or proof of CS2 loading a config.

All 85 existing section 1–8 PNGs (including section follow-ups) were preserved
byte-for-byte across suites that automatically recapture previews. Only the new
`sec8b-after-wizard-result.png` is added. `git diff --check` passes. No Python,
backend startup, game/helper calls or git write commands were run in this
follow-up.

## Screenshots

Offline fixtures using real markup, CSS and renderers, 1366 × 900. Captures
freeze motion. Shell telemetry and paths are synthetic fixture data.

- `sec8-before-config-files.png`, `sec8-before-wizard.png`: captured before edits.
- `sec8-after-config-files.png`: ready in the app, permission pending.
- `sec8-after-advanced.png`: open disclosure with real scan renderer.
- `sec8-after-wizard-import.png`: folder picked; explicit entry-file choices.
- `sec8-after-wizard-result.png`: Kept / Merged / Dropped review.
- `sec8b-after-wizard-result.png`: follow-up review, scrolled to the results
  with What changed open: Profiles, kept direct/alias binds and actual drops.
- `sec8-after-paper.png`: light theme.

## On a PC with CS2 installed / questions for Edy

1. Run the Python suite first. This development PC has no CS2; neither game
   deployment nor native picker interaction was exercised against a real install.
2. Fresh preferences: skip Allow, import renamed files/folders and Finish.
   Expect an app-only collection, working Keyboard/Editing and no game-folder
   changes. Check original bytes, including non-UTF-8 files.
3. Run setup again, use the existing one-time Allow, close CS2 and Refresh.
   Expect installed files with backups; existing personal binds/aliases survive.
   Use Apply to set the launch entry, start CS2 and verify that the files load
   once, in the displayed order. No new launch-options write is done at startup.
4. Repeat with CS2 running, a read-only game directory and an original file
   occupying a destination. Expect a ready app copy and a clear waiting reason,
   with no overwrite of originals. Close the game / resolve access, then Refresh.
5. Edit an installed imported bind through Keyboard, restart the app, and check
   that it survives. Accept another import, then check that its predecessor can
   be restored from Backups. Check multiple backup sets created within a second.
6. Confirm account switching, Apply/Play, Steam sync, portable save/open and
   manual Advanced formatting with actual installations. Local path metadata
   must not appear in a shared portable setup.
7. **Closed — Edy chose “keep all”.** Deferred profile switching is preserved
   in a separate copied tree. Original collisions continue to keep the rebuilt
   set app-only instead of modifying an original autoexec or profile.
8. On the home PC, import a folder containing an entry with
   `bind F5 "exec practice"`, an alias-chain bind to a match config, and two
   differently located `practice.cfg` files. Select only the intended startup
   entry. Confirm Kept/Profiles and each copied target in What changed. Finish
   without Allow first: originals must retain their exact bytes and no game
   file should change. With Allow and CS2 closed, Refresh, then Apply and launch.
   Startup must not run practice/match commands; F5 and the alias bind must
   switch to the copies, including nested execs and return-profile binds.
9. Repeat with a missing nested target, a deferred A↔B switch and an immediate
   A→B→A exec loop. Missing/unsafe links should be reported with reasons;
   ordinary return switches should remain. Rename or move the source folder
   after deployment to confirm runtime links use only the rebuilt set.
10. Edit a copied profile in Keyboard/Editing and restart/Refresh: the edit must
    survive. Accept a changed import and restore its predecessor from Backups.
    Try an original occupying a generated profile destination: the entire set
    must stay app-only with no partial deployment. Check that the existing
    NVIDIA target and collision messaging still behave as before.
