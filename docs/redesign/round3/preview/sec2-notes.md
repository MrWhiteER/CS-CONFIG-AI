# Round 3, section 2: hardware icon family

Implemented only section 2 on `codex/r3-2`. Section 1's graph remains intact, with its placeholder legend glyphs replaced. No branch changes, commits, pushes, PRs or releases.

## What changed

- Original 24px SVG family: CPU, GPU, RAM, VRAM, SSD/NVMe, HDD, motherboard, power/PSU, display, network, fan/cooling, temperature, mouse, keyboard, headset and microphone. Shared rounded 1.5px strokes inherit theme tokens. No runtime raster icons, libraries or CDN requests.
- Hardware category icons replace words in Play gauges, topbar load/score chips, Detected rows, assessment rows/bottleneck, Machine parts, graph legends, Graphics display headings and hardware settings glyphs, and Sound input/output labels. Setup hardware summaries retain model names beside icons. Shared device symbols, Keyboard command glyphs and hardware navigation glyphs use the family. Instructions, action names, model names and navigation text stay readable. Names remain available in tooltips and accessible labels.
- Topbar mirroring now identifies gauges by hardware key rather than removed caption text; live percentages, unknown values and warning classes retain their logic.
- New temperature widgets blend component/thermometer badges with a gradient ring and large value. Preserved sensor floor/hot scales, animated fill, warning states, alarms, unavailable reasons and helper unlock. Unknown is a dash, never zero. Specific sensor/model names remain visible.
- Icons breathe using transform/opacity; gauge load adjusts the pulse period. Temperature warning colour changes use theme tokens. Animations pause for hidden content/background documents and respect reduced motion.
- Redrew all 16 repair illustrations in assets/fixit/icons.js, sharing hardware geometry where applicable. Consistent circular gradient frames and restart badges replace uneven drawings. Icons pulse while repairs run. All existing targets, precautions, confirmations, states and actions remain.
- Added hardware assets to the frozen-app manifest. No backend/API/privilege changes. FPS estimate removal, Machine layout changes and the overlay remain for later sections.

## Files touched

- cs2cfg/web/index.html: integration, temperature markup, sound label associations and live topbar keys.
- cs2cfg/web/assets/hardware/icons.js and icons.css: family, names/tooltips, theme styles and motion lifecycle.
- cs2cfg/web/assets/fixit/icons.js and toolbox.css: repair artwork, frames and activity pulse.
- cs2cfg.spec: frozen-app asset inclusion.
- tools/check_home_launcher.cjs: production Detected/Machine/Sound rendering and topbar mirroring, icon/thermal checks, reduced-motion mode and screenshot views.
- tools/check_fixit_toolbox.cjs, check_graphics_workspace.cjs, check_keyboard_workspace.cjs, check_setup_wizard.cjs: load shared local artwork in extracted-script fixtures.
- docs/redesign/round3/preview/sec2-*.png and this file.

## Validation and tests updated

- node tools/check_home_launcher.cjs: 71 browser checks passed. Added distinct glyphs, names/tooltips, escaping, inherited colour, hidden/background pauses, actual Detected/Machine/Sound output, selected sound devices and associated labels, topbar values after removing caption text, persistent thermal nodes, hot state and unavailable readings. Existing graph interaction/animation and ten-theme checks pass.
- HOME_REDUCED=1 node tools/check_home_launcher.cjs: 72 checks passed, including actual browser reduced-motion CSS and 1366x768. The harness temporarily overrides the motion preference to exercise graph interpolation, then restores it for reduced-motion checks.
- node tools/check_fixit_toolbox.cjs: 93 checks passed; FIXIT_REDUCED=1: 95 passed. All 16 mocked actions, selections, confirmations, helper warnings, failures/retries and themes pass.
- node tools/check_graphics_workspace.cjs: 61 checks passed.
- node tools/check_keyboard_workspace.cjs: 2845 checks passed.
- node tools/check_setup_wizard.cjs: 162 checks passed; full-page boot ordering also passed.
- Five primary suites: 3232 browser checks passed. Reduced-motion reruns add 167 passing checks. No real fixes or Windows/device writes were invoked.
- Inline scripts compile in the harnesses; both new JS assets pass node --check. git diff --check passed.
- Searched tests/ (including ignored files) for replaced markup/category/glyph strings. No Python markup assertions require changes, so no Python tests were modified. Python unittest was intentionally not run, per the known sandbox restriction; the caller runs the 1277-test baseline suite. No Python pass is claimed.

## Screenshots

Before: sec2-before-system.png, sec2-before-fixit.png.

After: sec2-after-system.png, sec2-after-paper.png, sec2-after-laptop.png (1366x768, reduced motion), sec2-after-machine.png, sec2-after-sound.png, sec2-after-graphics.png, sec2-after-fixit.png, sec2-after-fixit-daylight.png.

sec2-after-family.png is a test-only specimen of all glyphs and sensor states. No gallery page is added to the app. sec2-concept.png is generated concept art, not a runtime asset.

Screenshots use deterministic offline fixtures, not live hardware. The home harness hides its result log and freezes transitions/animation AFTER assertions for repeatable captures; this avoids capturing half-completed dark-to-light transitions. Machine and Sound previews isolate their production cards. Gauge and graph fixture inputs are independent.

## Concept prompt

Built-in image generation (imagegen skill), saved as sec2-concept.png:

> Use case: ui-mockup. Concept sheet for a CS2 desktop hardware utility, clean vector-like line icons on charcoal background. One consistent family in purple and teal: CPU with clear socket pins, GPU with two fans, RAM, NVMe stick, HDD platter, motherboard, PSU bolt, display, network, cooling fan, mouse, keyboard, headset, microphone. Bottom row show two temperature widgets combining a small chip silhouette and thermometer badge with a circular purple-to-teal gradient frame and large 56-degree numeric reading. Fine rounded outlines, highly legible at 24px, restrained glow. No perspective, no decorative wires. Labels underneath each icon. Design concept only; final assets will be SVG.

The actual prompt used the degree symbol after 56. The SVG implementation adapts the concept to theme tokens and the existing layout.

## Open questions for Edy

- Run the Python unittest suite and verify the packaged executable; this session intentionally did not execute Python or build a release.
- Verify real sensor names/availability and long device lists on Edy's PC. Generic drive sensors use the SSD silhouette without inferring model/type; the actual sensor name remains visible. A separate HDD glyph is available when a source explicitly reports HDD.
- No design decision blocks this section. Existing helper permissions and unlock behaviour are unchanged.
