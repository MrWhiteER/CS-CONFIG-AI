# Round 3, section 3: This PC and connection chip

Implemented only section 3 on codex/r3-3. No branch changes, git writes, commits, pushes, PRs or releases. Sections 1-2 retained; sections 4-8 untouched.

## What changed

- Moved Detected, hardware inventory and assessment together into Settings > This PC. Reused section 2 display/hardware icons. IDs and render paths remain intact. Assessment/FPS content stays for section 4.
- Removed the large Connection card/button from Play. A network chip alongside CPU/GPU/RAM uses the same styling and shared animated SVG; it shows adapter link speed and average internet ping.
- Click opens router/internet dials, reply history, jitter, loss, adapter details and findings. Small Re-test in the header. Native keyboard activation, expanded state, Escape/focus restoration, outside-click dismissal, resize positioning and viewport scrolling.
- Test starts after the first-run gate, alongside startup and before scan/preferences. Registered with the loading coordinator; loading awaits the entire measurement.
- Serialized polling shares one bounded job. Duplicate starts reuse it; start/poll failures and a 12-second deadline settle with an explanation and restore Re-test. Late timed-out responses cannot replace newer results. Existing 15-second global loading fallback retained.
- Theme-token colours, transform-based progress; existing shared icons handle hidden/background/reduced-motion states. No new animation loop, dependency, backend endpoint, permission or UAC action.

## Files touched

- cs2cfg/web/index.html: markup relocation, This PC navigation, connection chip/details, startup and polling.
- tools/check_home_launcher.cjs: production connection/navigation extraction, relocation/polling/error/timeout/focus/paint-order/theme checks, screenshot views, captures same Chrome session as assertions.
- tools/check_connection_startup.cjs: production startup coordinator with deferred connection; registration/boot placement checks. Deterministic timers stand in for paint-grace frames because virtual-time Chrome may skip frames.
- docs/redesign/round3/preview/sec3-*.png and this file.

## Validation and tests updated

- node tools/check_home_launcher.cjs: 99 browser checks passed.
- HOME_REDUCED=1, 1366x768: 100 browser checks passed.
- node tools/check_connection_startup.cjs: 8 checks passed.
- node tools/check_setup_wizard.cjs: 162 browser checks passed; inline compilation and full-page first-run ordering passed. No connection work starts under first-run setup.
- node tools/check_graphics_workspace.cjs: 61 checks passed.
- node tools/check_fixit_toolbox.cjs: 93 checks passed.
- node tools/check_keyboard_workspace.cjs: 2845 checks passed.
- Six primary suites: 3268 checks passed. Reduced-motion rerun adds 100; screenshot reruns also passed.
- node tools/check_server_ping_widget.cjs fails the Ember theme-colour assertion: computed panel text stays violet while expected text is Ember. Reproduced IDENTICAL failure with that test reading unchanged HEAD:cs2cfg/web/index.html via read-only git show. No server-region code/test changes made.
- git diff --check and Node syntax checks passed. Inline application scripts compile in browser harnesses.
- Searched tests/ including ignored files for Detected, hw-card, net-card, net-run, Measure my connection, pollNet, settings-subtabs: no matching Python markup assertions, so no Python tests changed.
- Python intentionally not run due supplied sandbox restriction. Caller runs python -m unittest (reported baseline 1277 passing); no Python pass claimed.

## Screenshots

All in docs/redesign/round3/preview/:

- sec3-before-play.png, sec3-before-system.png: section 2 baseline. System uses source/harness read from HEAD without changing the worktree.
- sec3-after-this-pc.png: inventory/assessment under selected This PC.
- sec3-after-system.png: full-width Play system chart after removing Detected.
- sec3-after-connection.png: chip and open diagnostics.
- sec3-after-paper.png: light theme diagnostics.
- sec3-after-laptop.png: 1366x768, reduced motion, diagnostics.
- sec3-concept.png: built-in imagegen concept, not shipped at runtime.

Deterministic offline fixtures, not live hardware/network. This PC fixture selects production sub-pane markup/function; rail selection and segment thumb positioning are not driven by the full router. Motion/transitions freeze after assertions for captures.

## Concept prompt

Built-in imagegen via imagegen skill, saved as sec3-concept.png. Prompt (middle dot between speed and ping in original):

> Use case: ui-mockup. Compact desktop CS2 utility interface concept, charcoal theme with restrained purple accent. Close-up top toolbar with four small matching rectangular chips: CPU 7%, GPU 28%, RAM 52%, network icon 245 Mbps / 18 ms. Under the network chip an anchored simple details popover: Connection, Download 245 Mbps, Ping 18 ms, Jitter 2 ms, small circular-arrow Re-test action. Below a Settings pane with This PC selected and a single hardware inventory panel of crisp CPU GPU RAM monitor power outline icons beside device names. Spacious practical desktop interface, no illustrations or extra cards. Concept only; final implementation reuses existing themeable SVG icons.

Implementation labels the existing adapter reading as link speed rather than adopting the concept's illustrative download label.

## Open questions for Edy

- Is true internet download throughput wanted later? Existing /api/net reports adapter link speed, not download Mbps. This section uses that actual reading, labels it in details, and adds no bandwidth-heavy external service.
- Run Python unittest and verify real adapter speed, ICMP availability and startup duration on Edy's PC. Offline readings stay unknown; slow tests time out after 12 seconds with Re-test available.
- Existing server-region widget Ember colour assertion fails identically on unchanged HEAD; investigate separately if revising that widget.
