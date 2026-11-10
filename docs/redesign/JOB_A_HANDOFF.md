# Job A: Home / Play rebuild

Changed `cs2cfg/web/index.html` and `cs2cfg.spec`. Added the five assets below,
`tools/check_home_launcher.cjs`, and this handoff. No backend changes or libraries.
No commits or pushes. Other pages retain their markup and behavior.

| Asset under cs2cfg/web/assets | Bytes | Format / dimensions |
| --- | ---: | --- |
| brand/config-mark.svg | 205 | Original split-chevron SVG, 64 x 64 viewBox |
| home/hero.webp | 54,876 | Generated WebP, 1440 x 810 |
| home/mode-competitive.webp | 56,006 | Generated WebP, 800 x 450 |
| home/mode-balanced.webp | 48,682 | Generated WebP, 800 x 450 |
| home/mode-quality.webp | 82,390 | Generated WebP, 800 x 450 |

All raster art was generated with the built-in gpt-image tool and compressed with
the browser's WebP encoder at quality .79. No fallback assets. All assets are local;
the spec bundles both brand and home subfolders. Stable paths allow replacement.
The original opposing-chevron mark appears in the rail, loading screen and hero;
the generated monitor menu echoes it. No Valve assets were used.

## Behavior and motion

- Hero: original operator at a PC, still menu image, slow breathing, pointer
  parallax, monitor glow flicker and a desk strip following `--accent`. Original
  Play, Fix, display mode, Close and Stop controls and IDs remain in the hero.
- Mode cards: three native buttons with `aria-pressed`, arrow keys and Home/End.
  They call the original `chooseIntent`, including saved preferences, undo and
  preview. Images pan and receive a light sweep; selection lifts and glows.
  Counters animate toward actual backend estimates rather than simulated FPS.
  Two extra read-only `/api/plan` calls obtain the other profiles when relevant
  settings change. Request snapshots reject stale results; unavailable estimates
  remain dashes. No additional API endpoint or write action was introduced.
- System: persistent gauge elements and one requestAnimationFrame scheduler tween
  arcs and numbers from their current displayed values. Glow grows with load.
  Title-bar scores use the same renderer; CPU/GPU/RAM chips mirror animated values
  and gain a load strip and glow.
- Temperature: gradient heat strips use each sensor's floor/hot threshold.
  Values animate. Unavailable/administrator text, alarms and elevation remain.
- Graphs: real monitor history scrolls with cubic curves, gradient areas and a
  leading point. Missing readings remain gaps; no invented samples.
- Detected, Assessment, sessions/hours/alt-tab and Connection keep their content
  and actions with new spacing, icons, dividers and hierarchy.
- New motion pauses when the document or Launcher panel is hidden. Monitor polls
  skip hidden documents. Reduced motion shows final readings immediately and
  disables decorative animation. Surfaces use existing theme tokens; image text
  uses dedicated dark scrims. All images and scripts work offline.

## Validation

`node tools/check_home_launcher.cjs` passes 20 browser assertions using actual
markup/CSS and extracted production functions. Covers card click, keyboard,
save/preview behavior, persistent gauges, unavailable readings, administrator
offer, backend estimates, tween completion, curves, asset loading, overflow,
reduced motion, hidden-panel scheduling and basic checks across all seven themes.
Checked at 1440 x 1100 and 1100 x 800 and inspected rendered screenshots.
The tool syntax-checks all five inline scripts. Set `CHROME_PATH` for another
Chromium executable or `HOME_VIEWPORT` for another size. Output goes in OS temp.

No existing tests changed: none asserted the removed slider/thermometer markup.
The browser smoke test is new. `git diff --check` passes. `python -m pytest` could
not run because Python is not installed/on PATH here. Browser fixtures do not
verify Windows/Steam/backend integration or prove theme contrast compliance.

## Launch review

Run `python -m pytest`, then check real Play/Close, Fix, both display modes, saved
mode after restart, live telemetry, administrator sensor unlock and Measure my
connection. Review light themes and your normal WebView2 size. Check estimates
after changing target FPS/account. Courtyards are comparable generated
compositions rather than pixel-identical rerenders.

## Generation prompt set

Hero: premium wide launcher art; original charcoal tactical operator/headset at a
gaming PC, rear/side view, operator/monitor in right two thirds and dark negative
space at left; realistic cinematic materials, warm monitor and teal desk RGB;
original amber still boot/menu, split-chevron emblem, CONFIG AI lettering; no
Valve logo/assets or surrounding UI.

Modes: separate landscape 16:9 original Mediterranean training courtyards,
eye-level stone lane, central archway, crates on right, pale plaster/sandstone,
palm over left wall; no characters, weapons, UI, logos or copyrighted maps.
Competitive: flat matte low detail, crisp visibility, no bloom/haze. Balanced:
medium detail, subtle materials, soft natural shadows. Quality: rich stone,
reflective puddles, golden rays, foliage and deep soft shadows. A cleanup edit
removed stray upper-left text from Quality while preserving its scene.

## Questions

None blocking. Real backend and native-window verification remains for the owner.
