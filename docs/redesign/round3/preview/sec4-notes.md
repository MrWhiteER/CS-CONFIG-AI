# Round 3, section 4: applied and verified

Implemented on the existing codex/r3-4 branch in this worktree. Section 4 plus the two requested section 3 fixes only. No branch switches, commits, pushes, PRs, merges or releases.

## What changed

- Removed mode-card estimates and estimate fetching, assessment tier/headroom/ceiling figures, title-bar score promises, Machine FPS figures and limit comparison, and target copy promising to hold/clear a frame rate. Removed the same estimates from first-run preset cards. Target input, preset choices, settings preview and internal backend calculations remain.
- Preserved useful advisories while suppressing estimate/tier/headroom diagnoses in the UI. Kept Worth knowing and Settings arrangement for section 5.
- Apply records intended values and immediately reads them back: individual video keys, exact generated cfg/reference text, parsed executable autoexec link, Steam launch options and the applied display's scaling value. Generated text is captured once and reused from the writer, avoiding timestamp rollover mismatches.
- Added an animated checklist above Apply's write report in Settings. The same results appear in an expandable Play badge: Your PC is set: N/N verified, with checked time, applied time, preset and account. Green means matching; amber means changed/missing or not checked; red means failed write. Partial results say Review settings.
- Receipts persist in the app's existing data directory as applied-verification.json. Reload checks actual values again. Visible-session checks run every 15 seconds, on foreground return and via Read again. Pending edits, account/selection changes, failed reads and timeouts cannot retain green confirmation. Startup waits for the existing first-run gate and initial scan. A response predating Apply cannot overwrite its new receipt.
- Verification reads only. It calls no write/repair/elevation/helper function and asks for no new rights. Permission failures become Not checked. Only Apply saves the app's receipt; GET does not save or modify anything.
- Apply does not write NVIDIA profiles or Windows power/graphics settings in this codebase. Their rows explicitly say Not checked - not written by this Apply, outside the attempted-value denominator. Requested writes skipped while Steam/CS2 is running remain in the denominator and prevent full confirmation. Existing Windows graphics controls remain functional and unchanged.
- Config/launch/video write failures are retained as failed steps so completed writes can still be read back and reported.
- Fixed connection whitespace before wired/Wi-Fi. Ping dial and AVG MS both use the average; the sample-history plot still shows individual replies.
- Theme-token SVG shield/check/status icons; opacity/transform animations. Hidden tabs/background windows pause motion; reduced motion disables it. No runtime image, CDN or dependency added.

## Files touched

- cs2cfg/web/index.html: promise removal, confirmation UI, read-only refresh, connection fixes; two-column Machine parts after removing the center estimate comparison.
- cs2cfg/webui.py: Apply receipt creation, failure reporting and GET /api/verification.
- cs2cfg/verification.py: receipt persistence and read-only comparisons.
- tests/test_verification.py: 17 new tests for actual reads, overwritten/missing/denied files, executable links vs comments, failed/skipped writes, exact generated expectations, persisted receipts and display selection.
- tests/test_apply_partial.py: mock the receipt boundary in existing isolated write-routing tests.
- tools/check_home_launcher.cjs: replace estimate assertions, test production confirmation/render code, connection regressions, themes, reduced motion, startup gating, changed selections, timeout/retry and shared Apply/Play reports; section screenshot routes.
- tools/check_setup_wizard.cjs: replace estimate/countup assertions with absence-of-estimates checks; preset choices work without FPS data.
- This note and sec4-*.png previews.

## Validation

- node tools/check_home_launcher.cjs: 128 browser checks passed.
- Same suite at 1366x768 with reduced motion: 130 checks passed.
- node tools/check_connection_startup.cjs: 8 checks passed.
- node tools/check_setup_wizard.cjs: 162 checks passed; all five inline scripts compile; full-page first-run boot ordering passed.
- node tools/check_graphics_workspace.cjs: 61 checks passed.
- node tools/check_fixit_toolbox.cjs: 93 checks passed.
- node tools/check_keyboard_workspace.cjs: 2845 checks passed.
- Six primary suites: 3297 checks passed; reduced-motion rerun adds 130. Screenshot reruns also pass.
- Node syntax checks and git diff --check passed.
- Searched tracked and ignored Python tests for replaced markup/estimate strings. No Python markup assertion depended on the removed elements. Updated the partial-Apply fixture and added backend coverage above.
- Python deliberately not run, per supplied sandbox restriction. Caller runs python -m unittest (reported baseline 1277). No Python pass count claimed.

## Screenshots

All paths below are relative to this directory. Deterministic offline fixtures, not measured hardware or a live Apply. Badge fixture uses six attempted groups and three explicitly unwritten categories; live video settings are checked individually, so live N varies. Production render functions are used. Motion freezes after assertions for capture.

- sec4-before-play.png: unchanged HEAD mode estimates.
- sec4-before-connection.png: unchanged HEAD spacing/dial mismatch.
- sec4-after-play.png: estimate-free cards and persistent badge.
- sec4-after-verified.png: expanded checklist.
- sec4-after-changed.png: amber overwritten value and red failed write.
- sec4-after-connection.png: spaced link label; router dial matches AVG MS.
- sec4-after-machine.png: CPU/GPU information without estimated FPS.
- sec4-after-target.png: target retained as settings input without a performance promise.
- sec4-after-paper-laptop.png: 1366x768, light theme, reduced motion.
- sec4-concept.png: generated reference, not shipped in app.

## Design references and concept

Read ROUND3_BRIEF.md in full and inspected refs/04-current-target-fps-promise.png. Reused the existing theme/icon system. Borrowed status semantics from [Windows Security](https://support.microsoft.com/en-us/windows/security/windows-security/windows-security-app-overview) and checked [NVIDIA optimization status guidance](https://nvidia.custhelp.com/app/answers/detail/a_id/3180/). No web code or assets imported.

Built-in imagegen concept prompt:

> Use case: ui-mockup. A single close-up desktop utility confirmation strip and expanded checklist, dark charcoal existing CS2 Auto Config interface, violet accent, themeable outline shield check icon in green. Concise headline exactly 'Your PC is set: 14/14 verified', subdued timestamp 'Checked at 18:42', small chevron. Expanded below on same flat panel, title 'Applied and verified', rows with green check circles: CS2 video settings, Config files, Steam launch options, NVIDIA profile, Windows power, Windows graphics. Each row has muted 'Matches' on right. Thin dividers, simple sans serif 16px, no nested cards, restrained rounded corners 12px, generous horizontal spacing. Concept only. No FPS, tiers, performance numbers or promises.

The flat strip, shield, typography hierarchy and divided rows informed implementation. Existing app spacing and condensed section headings remain. Actual status/counts follow backend evidence, including unchecked categories, rather than illustrative concept values. Saved concept: sec4-concept.png, generated using the built-in tool.

## Open questions for Edy

- Run Python unittest and exercise live Apply, restart persistence, Steam/CS2 file rewrites, denied file reads and display scaling on Windows. This environment cannot verify those live interactions. No new UAC/helper job was added.
- Confirm whether a later section should integrate previously applied Windows graphics settings into the receipt across separate controls. This section verifies Apply's own writes and labels NVIDIA/power/Windows graphics as not written by Apply; it adds no new optimization writes.
