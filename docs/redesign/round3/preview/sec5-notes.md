# Round 3, section 5

Implemented only section 5 on the existing codex/r3-5 branch. Read the full brief and inspected both section 5 references; built on sections 1-4. No branch switches, commits, pushes, PRs, merges or releases.

## What changed

- Every Settings pane uses the same two-column grid, 16px gutters, 20px card padding and stretched row alignment. Below 900px it becomes one column. Existing large workspaces (configuration studio, themes, account and history) span this grid. Apply puts Machine beside Write, then Setups beside Picture quality. Preview output participates in that grid. Removed the Settings height tween; pane entrances use transform/opacity.
- All three Play presets reveal actual changes from the same plan response as Picture quality: hardware icon, setting name, old -> new, one row at a time. Equal display labels include raw values. Rows scroll inside the chosen card; unchanged plans say everything matches. The surrounding page dims. Clicking again, clicking elsewhere, Escape, hiding the window or leaving Play clears the reveal/timer. Other presets remain clickable. Reduced motion shows all rows immediately. A cutout keeps the chosen card visible through the existing glass-panel stacking contexts.
- A preview revision guard prevents late responses from overwriting the latest preset. Failed previews release the dimmer. Apply stays disabled until a valid current preview arrives.
- Settings > Steam is the single home for the launch-options comparison/Apply checkbox, Steam account selector/follow control, detected Steam/CS2 paths, client status and three Steam repairs (restart, end leftover CS2, verify files). Original handlers and controls were moved, with no second instance. Steam tools/category were removed from Fix It. Existing confirmations, running-game restrictions, restart-then-play choice, payloads and results remain. Failed Steam surveys have local retry; restoring Steam at startup loads the tools.
- Settings > Account remains separate on the shared grid, with the full-width #account-card for app sign-in, linking, subscription information and cloud handlers. Steam/Google/email sign-in belongs here; the local Steam account selector belongs in Steam. Saved account-subtab preferences restore to Account without remapping. Selecting Account refreshes cloud state. App-wide sync, first-run setup, inventory and the main Play flow keep their contextual entrypoints.
- Removed Worth knowing, its advisory filtering/rendering and heading-icon registration. Backend profile/launch generation and the optimization settings it described remain unchanged.
- Machine reuses section 2 animated CPU/GPU SVGs, short model names and compact Windows graphics controls. Automatic / Lean on GPU / Lean on CPU has a sliding highlight and concise explanation tooltips. The existing preference/preview behavior and focus remain. Hidden/background motion pauses; reduced motion disables the slide. No new app raster assets, CDN, dependency or helper/UAC job.

## Files touched

- cs2cfg/web/index.html: shared grid, Steam moves, plan reveal/revision guard, compact Machine, advisory-render removal.
- cs2cfg/webui.py: adds already-detected Steam root as read-only steam_path in the scan payload.
- tests/test_cloud_web.py: restores test_it_has_its_own_place_rather_than_being_wedged_in, asserting the Account tab and card, plus the Steam tab; provider assertions remain.
- tools/check_home_launcher.cjs: tests production Machine handlers/preview coordinator, real preset data and sequencing, raw values, races/errors, cleanup, themes, reduced motion, shared grids and unique controls; checks separate Steam/Account placement and Account preference restoration; Steam and Account capture routes use production renderers.
- tools/check_fixit_toolbox.cjs: asserts Steam tools moved once, scopes toolbox filtering, tests local survey failure/recovery, retains every repair/payload check and adds a Steam capture route.
- This note and sec5-*.png previews.

## Validation

Account separation correction:
- node tools/check_home_launcher.cjs: 190 passed on both Steam and Account screenshot runs, including separate pane ownership, saved Account selection and its shared grid.
- node tools/check_fixit_toolbox.cjs: 97 passed.
- Refreshed sec5-after-steam.png and added sec5-after-account.png; visually inspected both.
- Python and git were not run for this correction, per caller restriction.

Initial section 5 validation, before the Account separation correction:

- node tools/check_home_launcher.cjs: 188 passed.
- Same suite at 1366x768 with reduced motion: 188 passed.
- Same suite at 820x1100: 188 passed.
- node tools/check_fixit_toolbox.cjs: 97 passed, including all 16 original repair endpoints and Steam payload/launch behavior.
- node tools/check_setup_wizard.cjs: 162 passed; full-page boot ordering passed; inline scripts compile.
- node tools/check_graphics_workspace.cjs: 61 passed.
- node tools/check_keyboard_workspace.cjs: 2845 passed.
- node tools/check_connection_startup.cjs: 8 passed.
- Six primary suites: 3361 checks passed; additional reduced-motion/narrow runs: 376 passed. Screenshot reruns also passed.
- git diff --check passed. Searched Python tests, including ignored files, for replaced labels/IDs/subtab markup; updated the affected cloud-panel assertion.
- Python deliberately not run per supplied sandbox restriction. Caller runs python -m unittest against the reported 1294-test baseline. No Python pass count claimed.

## Screenshots

Offline fixtures rendered with production UI code, not measured hardware or live Steam actions. Checks precede capture; home captures freeze motion. Steam overview and repair images use separate fixtures, so their account/path/launch data differs. Repair capture intentionally shows the no-stuck-process disabled state.

- sec5-before-settings.png, sec5-before-machine.png, sec5-before-play.png: before section 5 edits.
- sec5-after-settings.png: shared Apply grid.
- sec5-after-machine.png: compact Machine/switch.
- sec5-after-preset.png: plan-backed Balanced reveal; identical production renderer tested for all three presets.
- sec5-after-steam.png: client, Steam account selector, paths and launch preview; no app Account card.
- sec5-after-account.png: separate Account tab with the production Steam/Google/email sign-in UI, using an offline signed-out fixture with Google enabled.
- sec5-after-steam-tools.png: all three moved repairs.
- sec5-after-paper-laptop.png: paper theme, 1366x768, reduced motion.
- sec5-after-narrow.png: one-column grid at 820x1100.
- sec5-concept.png: generated concept only, no app dependency.

## Concept

Built-in imagegen, saved as sec5-concept.png. Equal columns and compact Machine switch informed implementation; final controls and values follow the real app.

Prompt: Use case: ui-mockup. Concept for existing CS2 Auto Config desktop Settings UI, dark charcoal and violet accent. Consistent two-column equal-width grid, 16px gutters, flat panels. Subtabs Apply, This PC, Steam, Account, Apps, Look, Sound, Config files, Editing, Logs. Apply view has compact Machine panel with outline CPU and GPU hardware icons and short hardware model names, segmented sliding switch Automatic / Lean on GPU / Lean on CPU. Adjacent Write panel with checkbox rows. Bottom row Setups and Picture quality. Minimal text, readable desktop typography, no FPS promises. Small inset Play preset card showing icon Shadows Low -> High, icon Textures Low -> Medium appearing sequentially, dimmed backdrop. No nested cards, no decorative art. Concept only.

## Open questions for Edy

- Run python -m unittest; Python execution is blocked in this sandbox.
- Verify live Steam account switching/following, browser sign-in/linking/sync, restart/sign-in/then-play, file verification, actual detected paths and Apply/read-back on Windows. Browser checks used offline APIs and invoked no real Steam actions or configuration writes.
- No unresolved design decision blocks this section. The app Account tab stays separate from Steam; full-width workspace spans remain deliberate choices.
