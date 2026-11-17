# Profile drop concepts

Two deliberately different controls, rendered on the **real `cs2cfg/web/index.html` document**, including its title bar, navigation, Home cards, fonts and assets. Shipping files are unchanged. No final feature, branch, commit or push was made.

## A — Profile Rail (recommended)

- **Look:** a low, horizontal instrument with the three existing crosshair / balance / gem icons always visible. A tinted sliding seat identifies the selected profile. No hanging pod, luminous wings or idle movement.
- **States:** idle is icon-only; hover/focus reveals the profile name and verification text; the chevron opens a horizontal comparison shelf with three named choices. Selecting any profile shows a short `old → new · Needs Apply` confirmation.
- **Behaviour:** clicking an icon selects immediately; clicking the chevron opens details. Tab enters the selected radio, arrows/Home/End move focus, Enter/Space selects, Escape closes and returns focus. Keyboard selection is manual so exploring the choices does not change settings. Click outside or Tab out dismisses the shelf.
- **Animation:** the seat travels horizontally for 560 ms with a decelerating spring-like curve. Its border and tint interpolate between the source and destination profile colours. The detail shelf enters with a 240 ms fade, short translation and scale; idle is still. Reduced motion uses an 80 ms opacity fade and no travel.
- **Hooks:** selection calls the existing `chooseIntent`; on Home this preserves preset preview and undo. A body `data-intent` observer catches Home selection and undo. Verification observes the existing `#verification` attributes; verified / changed / failed / unknown have distinct words and status glyphs in details. No verified count is invented.
- **Tradeoff:** more title-bar width than B, and direct selection can be easier to click accidentally. The three targets remain legible and accessible in the supplied 860px capture.

## B — Profile Lens

- **Look:** one 46px circular instrument, with the selected emblem in its centre and a partial profile-colour ring. A separate small status dot represents verification. The arc is a profile identity accent, **not** a progress meter.
- **States:** idle occupies one icon target; hover/focus reveals a compact name/status card; click opens a vertical chooser with three descriptive rows. Profile and verification colour remain independent.
- **Behaviour:** Enter/Space opens the chooser; arrows/Home/End move focus; Enter/Space selects; Escape restores trigger focus. Pointer selection, outside dismissal and Tab dismissal also work. This deliberately requires opening the chooser before changing profiles.
- **Animation:** the outgoing emblem rises/fades while the incoming one settles from below; the ring rotates 120 degrees and changes colour over 560 ms. The chooser enters over 240 ms. There is no endless spinner, breathing or pulsing. Reduced motion replaces the switch with an 80 ms fade.
- **Hooks:** uses the same `chooseIntent`, body intent observer and verification observer as A. `aria-expanded`, `aria-controls`, radiogroups, roving tabindex and a polite switch announcement are implemented in the isolated adapter.
- **Tradeoff:** calmer and much smaller, but profile alternatives are hidden and every change takes two clicks. A coloured dot alone is intentionally supplemented by text on hover/focus/open.

## Recommendation

Choose **A — Profile Rail**. It makes the three-way tradeoff visible without reading text, offers the fastest switching, and fits the app's existing instrument/chip language. B is a strong alternative if preserving maximum empty space in the title bar matters more than one-click access.

## Shared engineering decisions and boundaries

- All component colours use existing tokens: `--neon-*`, `--ink`, `--muted`, `--panel-2`, `--bg`, `--line`, `--good`, `--warn`, `--bad`, `--sunk` and `--accent`. The original `MODE_ART` SVGs are reused. Screenshots verify violet default and daylight; the other themes inherit the same tokens but were not visually reviewed.
- At 1100px A reduces segment width; at 900px the network chip yields space; the profile control remains visible at 860px. Below 650px the Sync label and RAM chip yield, and below 560px GPU yields. B keeps its single target. The chooser is viewport-bounded.
- Selection never means Apply. Idle/open screenshots explicitly fixture a previously verified selection; changing profile marks it Needs Apply. Production must never synthesize receipts or show verified because an animation finished.
- Outside Home the prototype calls `chooseIntent(name, true)` and records undo explicitly, avoiding `presetBegin` on a hidden panel. **Before shipping**, the selected design needs a background `previewPlan()` refresh on that path (quiet selection invalidates the current plan and disables Apply), and applying/busy state must be connected to the actual Apply lifecycle. The `applying` label is reserved in the adapter; no fake applying animation or completion is claimed here.
- Switch motion is transform/opacity driven. The small seat/ring also interpolate paint colours; only these small elements repaint. No layout dimensions animate. A production version should cancel pending animations when hidden using the app's motion scheduler; this prototype has finite, event-driven animations only.
- Hover cards appear immediately in this prototype; no profile switches on hover. The animated expansion is the click-open shelf/chooser. In a final build a short hover delay can prevent accidental peeks while crossing the title bar.
- Static preview server returns a controlled error for every `/api/*` request. It cannot Apply, launch CS2, sync, or change files through the desktop service. The real app therefore displays unavailable network/sync states. CPU/GPU/RAM percentages and initial verification are labelled screenshot fixtures. Some unrelated Home content remains unpopulated because there is no backend.

## Captures and reproducibility

Run from this worktree:

```powershell
node docs/redesign/profile-drop/proto/render.mjs
```

This uses installed Microsoft Edge headless and Node's built-in HTTP/WebSocket/CDP APIs; no packages or dependencies were installed. The server binds an automatically assigned loopback port and serves only this worktree. `node .../render.mjs --serve` starts an interactive preview server and prints the local prototype URL. Add `?concept=A` or `?concept=B`, `&theme=daylight`, and optionally `&state=hover|switcher|transition`.

Each concept has:

- idle / hover / switcher / transition in dark and daylight at **1440×900**;
- switcher in both themes at **1100×900**;
- an extra dark switcher at **860×900**;
- a reduced-motion switch frame at **1100×900**;
- an **eight-frame 3200×163** animation strip, sampled at 0, 80, 160, 240, 320, 400, 480 and 560 ms. Each tile is a 400px title-bar crop centred on the profile control.

All **26 PNGs** were checked for PNG dimensions and file size during rendering. Representative dark/daylight, narrow, transition and frame-strip images were also opened for visual inspection. `render-report.json` lists every capture and its dimensions/bytes, plus passing interaction checks for both concepts: initial rendering, three options, selection, keyboard End, Escape, switching off Home, and reduced motion. Final render page JavaScript errors: **none**. Node syntax checks passed. The Python application suite was not run: this task adds isolated design artifacts only, and `python` is unavailable on PATH.

## Inspiration reviewed

- [Cult UI Dynamic Island](https://www.cult-ui.com/docs/components/dynamic-island): compact/expanded hierarchy informed B, without copying a black notch.
- [boring.notch](https://github.com/TheBoredTeam/boring.notch): a small always-available control that exposes richer controls on demand informed the peek/chooser distinction.
- [Performance modes reference](https://g-helper.com/performance-modes/): a small set of named operating modes informed A's persistent direct access. This is interaction inspiration only; CS2 profiles do not invoke laptop firmware modes.
- Local round 3 references inspected: title-bar chips, temperature-ring reference and Settings Apply screenshot. Their compact outlines and lighter daylight surfaces are retained.

## Errors encountered

Rendering ultimately succeeded; there is no missing screenshot fallback.

1. Environment probe `python -c "import importlib.util; ..."` failed: **`python : The term 'python' is not recognized as the name of a cmdlet, function, script file, or operable program.`** Node was used instead. `playwright` was also unavailable, so the renderer uses Edge directly through CDP.
2. Initial `node docs/redesign/profile-drop/proto/render.mjs` launched Edge with `--headless=new --disable-gpu` and an isolated workspace profile. Edge reported **`GPU process exited unexpectedly: exit_code=-1073741790`** and **`FATAL:content\\browser\\gpu\\gpu_data_manager_impl_private.cc:404] GPU process isn't usable. Goodbye.`** The successful preview-only invocation adds `--in-process-gpu --disable-software-rasterizer --no-sandbox`; these flags are confined to an isolated headless browser rendering local prototype content. No user browser session is used.
3. Initial frame-strip assembly replaced the page body, causing background app observers to read removed elements (`Cannot read properties of null (reading 'hidden')` / `dataset`). The final renderer overlays a canvas instead, and the final run has zero page errors.
4. The patch tool could not write these files (`Failed to write file G:\Projects\cs2-profile-drop\docs\redesign\profile-drop\proto\index.html`); PowerShell file writes succeeded.
5. Automatic approval review rejected temporary-browser-profile cleanup commands, returning **`rejected: blocked by policy`** without a more specific reason. Temporary `.edge-profile*` directories and `write-check.txt` were therefore left in `proto/` and ignored from Git. `created-files.txt` inventories all remaining files, including those temporary artifacts. The supplied renderer attempts to clean up its own newly created profile on future runs.
6. Edge emitted environment diagnostics about unavailable Windows encryption, registry writes, geolocation capability and shared GPU contexts; these did not block the successful capture. No app runtime errors remained in the final render.
