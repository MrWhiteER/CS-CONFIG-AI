# Round 3, section 1: combined hardware graph

Implemented only section 1 on codex/r3-1. Sections 2-8 remain outside this change.

## What changed

- Replaced the CPU/GPU sparklines with one overlaid SVG area chart for CPU, GPU, RAM and VRAM, using the existing /api/monitor history.
- Smooth curves, translucent gradients, shared grid, percent axis and roughly two-minute window. All series appear by default.
- Click a legend chip or a line to isolate it; others fade. Repeat the click or use All to restore every series. Wide transparent stroke targets make lines easier to click. Fills do not intercept clicks.
- Shared crosshair and tooltip show every series at the inspected sample. Arrow keys, Home/End and Escape support keyboard inspection; legend controls retain focus through polling.
- Simple inline SVG glyphs are isolated in series metadata for replacement in section 2. Theme tokens supply every series color. Acid, Ember, Carbon and Paper have token-based adjustments to distinguish similar colors.
- Celsius toggle for available CPU/GPU/System thermal sources. Temperature history accumulates in this page; usage history remains backend-owned. Existing thermal strips, unavailable-sensor messages, unlock action, alarms, gauges and session stats remain in place.
- Replaced per-frame path rebuilding with requestAnimationFrame translation. Retain the sample leaving the left edge until translation finishes; preserve the current offset when another sample arrives. Stop animation when the page or Play panel is hidden; reduced motion updates immediately. Hover content changes only when the inspected sample changes.
- No dependencies, network assets, backend changes, new privileges or new elevation behavior.

## Files touched

- cs2cfg/web/index.html: graph markup, styles, interaction, motion and monitor polling integration.
- tools/check_home_launcher.cjs: updated removed-sparkline assertions, added graph checks and screenshot options (HOME_HASH, HOME_SCREENSHOT; existing HOME_VIEWPORT retained).
- docs/redesign/round3/preview/sec1-*.png: before/after screenshots and generated concept.
- This notes file.

## Validation and tests updated

- node tools/check_home_launcher.cjs: **53 browser checks passed**, including existing launcher controls, gauge persistence, sensor unlock, backend mode estimates, all ten themes, chip/line selection and reset, tooltip values, keyboard inspection, focus retention, sensor gaps, scrolling boundary, half-step translation, hidden state and reduced motion.
- Deliberately replaced the old separate-chart assertion with a combined smooth-area assertion. The image check now ignores images with no src; the original check falsely failed on the unpopulated match-map image before changes.
- All inline application scripts compile through vm.Script in the browser harness.
- git diff --check: passed.
- Required full-suite command attempted from the repository root using the exact supplied Python313/python.exe path and -m unittest. **Blocked before execution: Windows returned "Access is denied" for python.exe.** No Python test result or 1277-test pass is claimed. No Python tests were modified.
- Screenshots use the existing offline Chrome fixture approach with deterministic samples, not live readings from Edy's machine. Reviewed dark/light, isolated GPU and 1366x768 laptop layouts. The fixture's gauge values and chart samples are independent test inputs.

## Screenshots

- sec1-before-play.png, sec1-before-system.png: original branch UI, Play and System views.
- sec1-after-play.png, sec1-after-system.png: combined graph in context and shared tooltip.
- sec1-after-paper.png: light Paper theme.
- sec1-after-gpu.png: isolated GPU.
- sec1-after-laptop.png: 1366x768 laptop layout.
- sec1-concept.png: built-in image generation concept, design reference only, not shipped in the app.

## Concept prompt

Built-in image generation was used with this prompt:

> Use case: ui-mockup. Create a single close-up concept for a CS2 desktop utility System hardware chart, landscape. Dark charcoal panel, restrained purple accent, clean readable typography. Header Hardware activity, right small All and temperature toggle. Four compact legend chips CPU 24%, GPU 58%, RAM 52%, VRAM 25%, simple placeholder glyphs. A wide overlaid smooth area chart, four distinctly colored theme-friendly lines purple, teal, amber, blue, translucent gradient fills, subtle dark horizontal grid, 0 to 100 percent left axis, last 60 seconds horizontal axis. Shared hover crosshair and small floating tooltip listing four series at same moment. Precise practical UI, no decoration, no other app sections. Concept only, no photos.

The implementation retains the actual roughly two-minute history and app theme colors rather than the concept's illustrative 60-second scale.

## Open questions for Edy

- Run the full Python unittest suite in an environment allowed to execute the supplied interpreter; this sandbox could not launch it.
- Verify real sensor availability and long-running live scrolling on Edy's PC. The Celsius toggle uses reported readings only; it does not infer a CPU temperature from System.
- Time labels are approximate, based on the existing two-second sampling interval. The backend has no per-sample timestamps; temperature history starts with this page. Is backend timestamped thermal history wanted in a later run?

## Commit status

Attempted the requested git add -A and local commit after browser validation. Git could not create G:/Projects/cs2-autoconfig/.git/worktrees/cs2-redesign3/index.lock: Permission denied. No commit was created; all work remains in this worktree. No push was attempted.
