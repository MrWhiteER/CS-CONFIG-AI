# Round 3, section 3b: real download speed

Implemented on existing codex/r3-5. No branch changes, git writes, commits, pushes, PRs, merges or releases.

## What changed

- Extended /api/net/start + /api/net with download Mbps, bytes, elapsed seconds, source and generic errors.
- One streaming HTTPS GET to https://speed.cloudflare.com/__down?bytes=25000000. No account, cookies, credentials, device information or user identifiers; generic Mozilla/5.0 User-Agent. No redirects, proxy discovery or telemetry. As with any HTTPS request, the endpoint sees the connecting public IP.
- Caps received payload at 25,000,000 bytes or four seconds including setup; reads at most 64 KiB at once. A daemon transport and bounded wait handle DNS/TLS/header/read stalls. Socket shutdown interrupts pending reads. An OS DNS call may outlive the deadline on its daemon but cannot send a late GET or publish late results. No extra retry downloads.
- Mbps is received payload bits divided by elapsed wall time, including setup. A deadline with data is a valid short sample. Empty/truncated/error, non-200, compressed and offline responses produce unknown. This short single-stream sample can understate fast lines due to setup time/byte cap; it is not a full multi-stream benchmark.
- Runs inside the existing background startup job after the first-run gate. Download finishes before ICMP, so it cannot inflate ping/jitter. Existing serialization excludes server-region probes. Existing 12-second UI deadline and 15-second startup fallback remain; request/startup threads do not synchronously wait on network I/O.
- Chip uses real download Mbps + internet ping. Link speed stays in details beside download and sample limits. Download failures retain independently measured ping; speed stays unknown. Re-test repeats both, preserving deduplication, polling, timeout recovery, keyboard/focus behavior.
- Reuses existing theme tokens and SVG icon/motion rules. No new animation, dependency, CDN, helper action or UAC prompt.

## Files touched

- cs2cfg/netcheck.py: bounded download, job integration, snapshot.
- cs2cfg/web/index.html: chip, tooltip, details and progress wording.
- tests/test_netcheck.py: 14 new mocked unittest methods.
- tools/check_home_launcher.cjs: download fixtures/assertions and offline view.
- docs/redesign/round3/preview/sec3b-*.png and this file.

## Validation and tests updated

- node tools/check_home_launcher.cjs: 193 checks passed. Covers download versus link speed, fractional Mbps, invalid/failed downloads, retained ping, retry, duplicate jobs, polling/timeout, focus, popover placement and all existing themes/features exercised by this harness.
- Paper, 1366x768 reduced-motion and offline screenshot reruns: 193 checks passed each.
- node tools/check_connection_startup.cjs: 8 checks passed.
- node tools/check_setup_wizard.cjs: 162 checks passed; all five inline scripts compile; full-page first-run ordering passed.
- 363 checks across those three distinct suites; screenshot reruns also pass.
- Python coverage: byte cap and rate, generic headers, offline/timeout/thread-start failures, HTTP failures/redirects, compression, empty/truncated streams, read errors and cleanup, bounded DNS and partial-stream deadlines, socket shutdown, snapshot isolation, download-before-ping, deduplication and Re-test. All network is mocked.
- Searched tests/ including ignored files for changed connection labels/markup; no existing Python markup assertions needed replacement.
- git diff --check passed. Python intentionally not executed because supplied sandbox blocks python.exe; caller runs python -m unittest (supplied baseline: 1294 passing). No Python pass result claimed.

## Screenshots

Production UI/function extraction in existing Node Chrome harness; deterministic offline fixtures, not live speed results. Assertions and captures share the browser session; motion freezes after checks. Visually reviewed dark, paper and laptop.

- sec3b-before-connection.png: current branch baseline using adapter speed.
- sec3b-after-connection.png: measured download chip and details.
- sec3b-after-paper.png: light theme.
- sec3b-after-laptop.png: 1366x768 reduced motion.
- sec3b-after-offline.png: download unknown, ping retained, Re-test available.
- sec3b-concept.png: built-in imagegen concept only, not a runtime asset.

## Concept prompt

Built-in imagegen via imagegen skill; saved sec3b-concept.png. Prompt:

> Use case: ui-mockup. Concept only for existing CS2 desktop utility. Tight close-up of charcoal toolbar with purple accents, compact network chip reading '245 Mbps · 18 ms', simple anchored details panel below. Reuse thin outline network SVG style. Panel text: 'Connection', small 'Re-test', 'Download 245 Mbps', 'Short sample · Cloudflare · up to 25 MB', 'Ethernet · Link speed: 1 Gbps', two quiet ping columns 'Router 1 ms' and 'Internet 18 ms'. Crisp restrained minimal interface, no illustration, no nested cards. Save concept only, implementation uses existing theme tokens.

## Open questions for Edy

- Run full Python unittest suite; 14 new methods have not been executed here.
- Verify live startup/Re-test on Edy's Windows PC, including offline behavior and Cloudflare availability. No live speed test performed here. No unresolved product/design decisions.
