# Round 3, section 6: Apps

Implemented only section 6 on codex/r3-6 in the supplied worktree. No branch
switches, commits, pushes, PRs, merges or releases. Python was not run as instructed.

## What changed

- Four default tiles: FACEIT (+ anti-cheat), Discord, TeamSpeak, Crosshair X.
  Each opens its own settings view; Back/Escape restore focus. Add a companion
  and generic launch/start-with-CS2/remove controls remain below the tiles.
- Theme-token glow, shine and hover lift use transform/opacity. Hidden views
  pause animation; reduced motion disables it. Logos themselves never animate,
  recolour or distort. Four columns respond to two on smaller windows.
- FACEIT client and anti-cheat launch/start-with-CS2 reuse existing endpoints
  and tagged companions. Custom paths can be saved while automatic launch is
  off. Match alerts expose enable, sound and always-on-top settings. Sound and
  topmost options apply to the next alert window; existing acceptance remains.
- Discord: installed/running status, launch, executable picker, start with CS2.
  Reuses stable/PTB/Canary discovery and watches Discord instead of Update.exe.
  Deep links to overlay, acceleration and voice settings include manual page
  names as fallback. Optional close-after-CS2 is omitted under the explicit
  start/watch/open-URLs safety rule; the UI says Discord remains open.
- TeamSpeak: launch, status, start with CS2, executable picker and auto-join.
  Host/port/nickname are saved in this app's per-account preferences. Validated,
  encoded ts3server://HOST?port=PORT&nickname=NAME URLs open via os.startfile,
  without a shell, during Play or Join saved server. IPv6 is bracketed.
- Crosshair X retains Steam start/discovery, start with CS2, and CS2 crosshair
  safeguards. Wake overlay opens ms-gamebar:. Removed the old Win+G/focus
  automation, including on automatic launch, to obey section 6's no-input rule.
  The player now controls/closes Game Bar and its widgets.
- Polls update status without replacing forms. Failed new toggles roll back
  with local errors. No other app's files are edited, no injection, new CDN,
  dependencies, helper jobs or elevation paths. Existing FACEIT AC launch
  elevation behavior remains unchanged.

## Assets and design

Used built-in ImageGen for sec6-concept.png. Prompt direction: dark charcoal
Apps section, four equal violet-glow tiles, neutral app-window icons with names
(no invented logos), companion action below and TeamSpeak settings example.
Extracted equal proportions, fine outlines, generous spacing, subtle glow and
row-based details, then implemented using existing themes. Concept is not UI art.

FACEIT uses the existing official faceit-mark.svg unchanged. HTTPS download
probe failed in this sandbox. The other three logos are intentionally neutral
placeholders: generic application window plus app name. The assets/apps/README.md
lists exact replacement filenames and official publisher sources.

## Files touched

- cs2cfg/web/index.html: tile/detail markup, Crosshair integration, companion
  filtering, startup and polling. The unrelated Apply explanation is hidden
  only while Apps is selected, to fit the tiles better on laptops.
- cs2cfg/web/assets/apps/apps.css and apps.js: theme layout, motion and actions.
- cs2cfg/web/assets/apps/discord-logo.svg, teamspeak-logo.svg, crosshairx-logo.svg,
  README.md: named neutral placeholders and official replacement instructions.
- cs2cfg/apps.py: discovery, status, configuration and validated URLs.
- cs2cfg/webui.py: named app routes, TeamSpeak startup URL and alert options.
- cs2cfg/launcher.py: URL companions and correct named-process waiting.
- cs2cfg/crosshairx.py: safe URL wake replaces keyboard/focus automation.
- cs2cfg/faceit_apps.py: persist chosen paths with auto-start disabled.
- cs2cfg/desktop.py: alert sound/topmost options.
- cs2cfg.spec: bundle new assets/apps folder.
- tests/test_crosshairx.py: replaced obsolete synthetic-input/Game Bar probe
  tests with URL wake/cancellation/failure checks; existing discovery, config
  and markup/watch assertions retained.
- tests/test_apps_tiles.py: URL validation/encoding, safe dispatch, missing
  handlers, URL launch, process status, configuration and FACEIT path tests.
- tools/check_apps_tiles.cjs: offline production-renderer checks and captures.
- This note and sec6-*.png previews.

Searched tests including ignored files for changed markup/behavior. No other
existing Python markup assertions needed changes. New Python tests are prepared
for the caller and were not executed here.

## Validation

- node tools/check_apps_tiles.cjs: 37 passed.
- node tools/check_home_launcher.cjs: 193 passed.
- node tools/check_setup_wizard.cjs: 162 passed; full-page boot ordering and
  inline script compilation also passed.
- node tools/check_fixit_toolbox.cjs: 97 passed.
- node tools/check_graphics_workspace.cjs: 61 passed.
- node tools/check_connection_startup.cjs: 8 passed.
- node tools/check_faceit_dashboard.cjs: 83 passed.
- node tools/check_keyboard_workspace.cjs: 2845 passed.
- Total: 3486 Node browser checks passed. git diff --check passed.
- Python deliberately not run; caller runs python -m unittest. No Python pass
  count claimed. Real installed apps and URLs were not launched in these checks.

Apps checks cover four pages, launch and startup toggle payloads, alert options,
server saving, focus/Escape, all ten themes, narrow layouts, logo loading and
unmodified presentation, generic companions, rollback/errors, polling form
preservation, hidden pausing and reduced motion.

## Screenshots

sec6-before-apps.png was captured before edits. After captures:
sec6-after-apps.png, sec6-after-faceit.png, sec6-after-discord.png,
sec6-after-teamspeak.png, sec6-after-crosshairx.png, sec6-after-paper.png,
sec6-after-narrow.png. All are in this folder; fixtures stub process/API data.
After captures scroll to the Apps subtab to show relevant controls.

## Open questions for Edy

1. Replace the three neutral logo files using exact filenames and official
   sources in assets/apps/README.md; confirm licensing and clear space.
2. Verify Discord deep links on the installed version; some versions open Home.
   Manual settings page names are provided as fallback.
3. Verify TS3/TS5/TS6 protocol registration, install paths and joining with
   Edy's host/nickname. Auto-join follows Play here, not independent Steam launches.
4. Verify Game Bar URL wake and Crosshair X's widget on Edy's PC. The URL-only
   wake intentionally leaves widget control to the player under the safety rule.
5. Run python -m unittest and smoke-test FACEIT AC, Discord launch and alert
   sound/topmost options on Windows.

## Caller correction (after review)

The removal of the Crosshair X Win+G / focus overlay wake described above was reverted before commit:
`cs2cfg/crosshairx.py`, `tests/test_crosshairx.py` and the Play step 5 block in `cs2cfg/launcher.py`
are back to their pre-section-6 state, so Play still runs the full overlay-broker wake Edy relies on.
The brief's "never send input" rule covers the companion apps themselves, not this existing Windows
Game Bar fix. The Crosshair X page's manual "Wake overlay" button still only opens `ms-gamebar:`.
Tests after the revert: 1319 passed.
