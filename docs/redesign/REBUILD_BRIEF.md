# Rebuild brief, round 2 (for Codex)

Round 1 (PRs #6 to #10) was a reskin: same layout, new paint. Edy's verdict: it still looks
unprofessional and "dead". This round is a **real rebuild** of the screens below. You may change
layout, markup, rendering code and add new visuals. The rules at the end still protect the
features.

Edy's screenshots of the current app are in `docs/redesign/feedback/` (01 to 06). His words are
quoted where they matter.

Targets: Razer Synapse 4 and Logitech G HUB (keyboard and mouse tools), FACEIT client, and
Leetify (https://leetify.com/@mrwhiteer) for stats. "Don't go too crazy. Leetify is made for
stats; our software is something different."

---

## 1. Home / Play tab (screenshots 04, 05)

> "the main page, its DEAD! no animation nothing nice, the graph animation is shit, the system
> circle bars are pinging not even animating, same with the temperature icon which I don't like."

- **Hero.** An illustrated soldier (a CS-style operator, original art) sitting at a desk in
  front of a PC, playing. His monitor shows a still "booting" screen in the spirit of CS2's
  startup screen. Make it original art, not Valve's assets. Draw it as layered SVG with subtle
  idle motion: screen glow flicker, a breathing posture, RGB light on the desk.
- **App mark.** "Everywhere you can see CS2 text but nowhere a logo." Design an original logo
  for this app, inspired by the CS2 look but clearly our own. Don't alter Valve's actual CS2
  logo; it's their trademark. Use it in the rail header, loading screen and hero.
- **Gauges.** Replace the static rings (CPU, GPU, RAM, VRAM). The arcs must animate smoothly
  between readings (tweened, not jumping), with a glow that intensifies with load and numbers
  that count up.
- **Temperatures.** Replace the thermometer icons with something better, such as a heat bar
  with a colour gradient and the animated value.
- **Live graphs.** The CPU and GPU load lines need real motion: a scrolling area chart with
  gradient fill, smoothed curves and a glowing leading point.
- **Optimise for (screenshot 05).** Remove the gliding sphere on a line. Use **three sharp,
  angle-cut cards side by side: Competitive (FPS), Balanced, Quality.** Each card shows an
  animated scene that makes the trade-off obvious to a player, for example the same CS-style
  scene rendered three ways:
  - Competitive: flat, clean, high-contrast and very smooth. Show a high FPS counter ticking.
  - Balanced: the middle ground.
  - Quality: rich lighting, shadows and detail, with a lower FPS counter.

  The selected card glows and lifts, and the estimated FPS shows on each. Make the scenes in
  SVG, canvas or WebGL. No photos needed.

## 2. Keyboard and mouse tab (screenshots 01, 02)

> "it looks so unprofessional made. I want a nice keyboard like Razer has, almost a real
> keyboard. The mouse a proper mouse like Razer. The way you use the tools, how you grab
> everything, what comes with Razer or Logitech."

- **Keyboard.** A near-photoreal keyboard: 3D keycaps with depth, bevels and legends, a
  slight perspective tilt, an aluminium or plastic case, and per-key RGB lighting. Key state
  colours (your script / changed / CS2 default / free) are shown as the key's backlight, not as
  flat fills. Keys press down on hover and click.
- **Mouse.** A real gaming mouse render, in the style of Razer or G HUB (original design, not a
  copy of a specific product). Buttons are hotspots on the body with leader lines to labelled
  callouts for M1 to M5, the wheel and DPI.
- **Interaction, Synapse/G HUB style.** Pick a key, then a side panel slides in with the
  assignment. Commands can be **dragged from the command library onto a key**, and clicking
  still works. Add smooth transitions, a hover preview of what a key runs, and a clear
  "assigned" animation.
- Profiles (Default / Warmup / ...) become proper profile tabs with icons.
- Keep every existing function: profiles, the legend counts, "Not set in ...", search,
  categories, back to default, open the file.

## 3. FACEIT tab (screenshot 03)

> "no proper GUI. Nothing like inside FACEIT. Nothing even close to the FACEIT GUI."

- **Tab icon.** Use the FACEIT logo for the FACEIT tab. Use FACEIT's official mark as provided
  in their brand assets, and don't redraw or alter it. Also show it large, faded and in orange
  behind the FACEIT page as a background stamp. Before release, check FACEIT's brand guidelines
  for this use.
- **Leetify-style stats** (use only the data the app already has, or can get from the same
  FACEIT data):
  - A player header: avatar, nickname, level badge, ELO with a trend sparkline.
  - Headline stat cards: K/D, ADR, HS %, win rate, recent form (W/L pills).
  - Charts: ELO over the last N matches, performance by map (bars or a radar), and a K/D/ADR
    trend.
  - The match list becomes rich cards: map thumbnail art, score, K/D/A, ADR and ELO change in
    green or red, and the time. Clicking a card expands it for detail.
  - The demo list becomes styled cards with clear Watch and Choose actions.

## 4. Graphics tab (screenshot 06)

> "I come here and even I don't understand what this is. Only text, no pictures, no proper
> visualisation of what it actually changes."

- Every setting gets a short plain-English line on what it does in game, plus a visual: a
  before/after or a small illustration, such as a monitor showing a refresh-rate motion blur
  comparison or black bars vs stretched for resolution.
- Displays become monitor cards with a drawn screen, resolution, Hz and the primary badge.
- Group the NVIDIA driver profile into collapsible sections with explanations. Hide raw hex
  values behind a "details" toggle.

---

## Assets: what you can and can't do

You (Codex) can build art and motion with SVG, CSS, canvas and WebGL. If you use a 3D library
(e.g. three.js), it must be vendored into the repo, because the app has to work offline with no
CDNs. You can't fetch photos or copyrighted game art. Where a real image would be better (map
thumbnails, the soldier), draw original illustrations and leave a clear slot (a file path) where
Edy can drop in his own image later.

## Rules that still apply

1. Every feature keeps working: the same API calls and the same behaviour of Apply, Play, Fix,
   profiles, binds and sign-in. You may change markup and rendering code, but update or extend
   the JS hooks so nothing breaks, and keep the tests passing (`python -m pytest`). If a test
   asserts old markup that you deliberately replaced, update the test to assert the new
   equivalent and say so in the PR.
2. Theme tokens: all 10 themes must still work. New art takes its accent from `--accent`.
3. Performance: animations use transform and opacity, run at 60 fps, pause when the window or tab
   is hidden, and respect `prefers-reduced-motion`.
4. Work in the order above, one branch and PR per section, stacked on `codex/redesign-5`.

## Practical notes (verified in the codebase)

- **Themes:** this branch line (`codex/redesign-5`) has the 7 themes in `const THEMES`.
  Crimson, Frost and Neon arrive with PR #5. Style everything through tokens and all of them
  will work.
- **Where assets go:** `cs2cfg/web/assets/`. `webui.py` serves any file under the web root,
  including subfolders. The PyInstaller spec (`cs2cfg.spec`) only bundles `cs2cfg/web/*`, so
  add `("cs2cfg/web/assets/*", "cs2cfg/web/assets")` (and any deeper folders) to `datas`, or
  the built .exe will be missing them.
- **Generated raster art is allowed.** Codex can generate images (gpt-image). For the hero
  soldier, the three optimise scenes and the map thumbnails, a generated, web-optimised
  image (WebP, a few hundred KB at most) plus CSS/canvas motion on top is fine and often
  better than hand-drawn SVG. Keep each one at a stable file path so Edy can swap in his own.
- **FACEIT logo:** the official asset can't be downloaded from inside the sandbox. Reference
  `cs2cfg/web/assets/faceit/faceit-logo.svg` and ship a clearly marked placeholder there,
  then tell us. Edy or Claude will drop in the official file from FACEIT's brand kit.
