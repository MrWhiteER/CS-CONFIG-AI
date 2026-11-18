# Status bar redesign brief (for Codex)

Edy's words (2026-11-18):

> When we are changing any setting or loading something, on the bottom left it shows the loading
> bar of anything that was loading, or what is coming, any notifications. It comes from the left
> bottom as a bar. With different themes the bar is not visible enough, and the text is not
> visible enough. Plus the bar itself is not looking nice. I don't like it. Make it with
> animation, as a GIF. Make it nice, and it should proceed with the loading bar as well: what is
> it loading, what error is it showing, anything related to notifications from the software. And
> it should be highlighted properly with different themes, because each theme has a different
> colour pattern and it may be hard to read.

You (Codex) own the design and the engineering. This brief is facts plus the bar to clear.

---

## What exists today (all in `cs2cfg/web/index.html`)

- Markup: `<div id="status">` (around line 6253, inside the stage).
- Styles: `#status` around line 3265 (an older copy at ~1917 and ~2156 is overridden).
  - Background is **hardcoded** `rgba(10, 6, 20, .92)`; text is `var(--ink-dim)`.
  - On **Daylight** and **Paper** the ink tokens are near-black, so it is dark text on a dark
    chip: basically unreadable. On the dark themes `--ink-dim` at 12px is weak too.
  - Error state only changes the border (`#status.err`).
- JS: `function status(text, isError)` and `function busy(text)` (around line 7060).
  - `busy()` prefixes a text glyph `<span class="spin">◐</span>` that rotates. That is the
    whole "loader". There is no progress bar at all.
  - Plain messages hide after 6 s; errors stay until replaced; a message containing `spin`
    never auto-hides.
  - `text` is inserted with `innerHTML`, and callers sometimes pass HTML.
- About **165 call sites** (`grep -n "status(\|busy(" cs2cfg/web/index.html`). Many errors pass
  the raw exception: `status("Apply failed: " + esc(e.message), true)`,
  `status(String(err && err.message || err), true)`, `status(r.error, true)`. Those can surface
  things like `HTTP 500`, `response was not JSON`, `Failed to fetch`, Python exception text,
  Windows error codes or internal ids. Edy wants **plain explanations, never code**.
- Real progress already exists in places that do not use the bar:
  - Startup: `--boot-progress` on the loading veil (~line 6051), counts settled loads.
  - Demo download: `demoData.job.seen / job.total` (~lines 12492, 12674).
  - Setup wizard steps (`setup-progress`).
- Related surface: the update toast `.upd-toast` (bottom-right, ~line 3799) also has a
  hardcoded dark background `rgba(18, 18, 26, .93)` in its first rule (a later token rule at
  ~5470 partly fixes it). Make it the same family so the two do not look like different apps.
- 10 themes: `THEMES` (~line 13669): violet (default, no attribute), ember, carbon, acid,
  crimson, frost, neon, daylight, paper, pro. Theme tokens are at ~2400 to 2660
  (`--ink`, `--ink-dim`, `--muted`, `--panel-2`, `--glass-3`, `--accent`, `--good`, `--warn`,
  `--bad`, `--lift`). Pro is flat and square (`--r: 4px`, `--glow: 0`).

## What to build

A proper notification dock that slides in from the bottom-left.

1. **Look.** A solid, readable card (not see-through glass over busy art). Icon or loader on
   the left, a short bold title plus a plain sentence, and a progress bar along the bottom edge.
   Styled only through theme tokens, so each theme gets its own colours; add a few tokens
   (for example `--status-bg`, `--status-ink`, `--status-track`) per theme where the existing
   ones are not enough. Pro stays flat and square.
2. **States**, each clearly different at a glance:
   - **Working** (busy): an animated loader that feels like a GIF but is drawn in SVG/CSS
     (no image files needed, scales crisply, follows `--accent`). Indeterminate bar: a smooth
     travelling shimmer.
   - **Progress**: a determinate bar with a percent or "3 of 8" when the app really knows it.
     Animate the width smoothly (tween, never jumps). Never fake a percentage.
   - **Done**: a short success animation (for example the loader morphs into a tick), then the
     bar drains as the auto-hide timer (about 6 s), and pauses while hovered.
   - **Error**: `--bad` colour, an error icon, stays until dismissed or replaced, with a close
     button. Optional "Details" toggle for the raw text, collapsed by default.
   - **Notice / warning**: for messages like "New match: ..." or "Steam is back".
3. **Motion.** Slide and fade in from the bottom-left, settle with a slight spring, slide out.
   Changing from busy to done morphs in place instead of popping. Transform/opacity only,
   60 fps, nothing running while hidden, and `prefers-reduced-motion` gets a simple fade.
4. **Readable in every theme.** Text at least 4.5:1 contrast against the card and the bar at
   least 3:1 against its track, in all 10 themes, for every state. Please check it
   programmatically (compute the contrast from the resolved colours) and include the numbers.
5. **Plain language.** Add one `friendlyError()` (or similar) used by `status()` for errors, so
   network failures, HTTP codes, "not JSON", permission denied, file not found, timeouts and
   Python/Windows error strings become a short human sentence ("The app's background service
   did not answer. Try again in a moment."). Keep useful specifics a player understands (a
   file name the user exported to, a device name). No stack traces, exception class names,
   status codes or internal ids in the main text. Sweep the call sites and fix any message that
   reads like code.
6. **API.** Keep `status(text, isError)` and `busy(text)` working for every existing caller.
   Add what you need on top, for example `busy(text, {progress: 0.4, detail: "3 of 8"})`,
   `status.progress(...)`, `status(text, {kind: "warn"})`. Wire real progress where it exists:
   startup loads, demo download, Apply / Restore (if the plan knows how many writes), config
   scans. Everything else uses the indeterminate bar.
7. **Several things at once.** If two jobs overlap, do not let one silently wipe the other's
   error. Your call: a small stack (max 3) or a queue.
8. **Accessibility.** `role="status"` / `aria-live="polite"` for normal messages, `role="alert"`
   for errors, close button reachable by keyboard.

## Rules

1. Every feature keeps working; same API calls and behaviour. Use `esc()` for anything that
   comes from the backend now that text is richer.
2. Theme tokens only; all 10 themes must work.
3. App works offline: no CDNs, no external fonts or images.
4. Tests: add a web test (pattern: `tests/test_profile_rail_web.py`, Node harness) covering the
   status helper states, the auto-hide timing, error persistence and `friendlyError`. Run the
   suite **module by module** (`python -m pytest tests/test_x.py`), not all at once. If a test
   asserted old markup you replaced on purpose, update it and say so.
5. Do not touch the elevated helper or add anything that needs admin rights.

## Deliverables

- Branch `claude/project-thread-gy5mzy` (this brief is already on it). Commit and push there.
- Screenshots in `docs/redesign/status-bar/preview/`:
  - `before-<theme>.png` for each of the 10 themes (current bar, busy message).
  - `after-<theme>.png` for each of the 10 themes, showing all states on one image
    (working, progress at ~60 %, done, error, notice), real app page behind it.
  - `loader-strip.png`: 6 to 8 frames of the loader and bar animation side by side.
  - `contrast.md`: the contrast numbers per theme and state.
- A short summary of what changed and which tests ran.
