# Overlay redesign: Steam-style modular shell

Edy, 2026-11-15: "I need the overlay to be similar to Steam, so we can have
multiple things plugged in inside, and in case we need to do anything in the
future, we can add additionally whatever we need."

Codex owns the design. This brief gives the shape, the facts and the limits.
Base: branch `codex/overlay` (PR #17, now a draft). Work on a new branch
`codex/overlay-shell` from it. The data layer, HUD, PresentMon, GSI, capture
exclusion and permissions all stay. This replaces the panel's look and
structure.

## What Steam's overlay does (the reference)

- Shift+Tab dims the whole game behind a dark translucent layer.
- A bar along the bottom (or top) holds launcher buttons for each tool:
  friends, achievements, browser, notes, guides, settings, performance.
- Each tool opens as its own floating window inside the overlay. Windows can
  be moved, resized and closed, and several can be open at once.
- Any window can be **pinned**: it stays visible, click-through, over the game
  after the overlay closes (Steam's pin, Game Bar's pinned widgets).
- Closing the overlay returns straight to the game.

Xbox Game Bar is the other reference: same idea, widgets in a top bar,
pinnable, and a widget store to add more.

## What to build

### 1. The shell
- Hotkey (default Ctrl+Alt+P, setting) opens a full-monitor shell on the
  monitor CS2 is on. It dims the game with a translucent layer, shows a clock
  and a tool bar (dock), and puts the open tool windows on top.
- Click on the dimmed area or press the hotkey/Esc to close. Focus goes back
  to CS2 (existing `panel.return_to_game`).
- Tool windows: drag to move, resize from the corner, close, pin. Layout
  (position, size, open, pinned) is saved per tool and restored next time.
- Smooth: open/close fade of about 120 ms, no layout jank. It must feel instant
  because the window is created once and only shown/hidden.

### 2. Tool plug-in system (the important part for the future)
Each tool is one self-contained module, registered in one place, so adding a
tool later means adding one file on each side and nothing else.

- Python side: `cs2cfg/overlay/tools/<id>.py` defines
  `TOOL = Tool(id, title, icon, data=callable, actions={name: callable},
  refresh_hz=..., default_size=..., pinnable=True)`.
  `cs2cfg/overlay/tools/__init__.py` holds the registry (an explicit list, no
  dynamic import of arbitrary files). Endpoints: `GET /api/overlay/tools`
  (list), `POST /api/overlay/tool` with `{id, action, args}`. Same token
  auth as the existing panel endpoint.
- Web side: one renderer per tool, registered by id, given
  `(root, data, call(action, args))`. A tool never polls on its own; the
  shell asks for data at that tool's `refresh_hz`, only while the tool is
  visible.
- Settings: the user can turn tools on or off and reorder them in the dock.

### 3. Tools to ship now (move the existing panel content into these)
1. **Performance**: live FPS, 1% low, frame time, 2/5/10 min graph.
2. **Hardware**: CPU/GPU load, GPU temp, VRAM/RAM if available.
3. **Stutters and freezes**: the event list.
4. **Profiles**: setups and keyboard/mouse layout profiles, with the
   "press <apply key> in game" hint.
5. **Server lock**: the region lock (adapter `overlay/regionlock.py`; the real
   `cs2cfg.serverlock` is now on main, so use it; keep the guarded import).
6. **Settings**: overlay settings in the shell itself (hotkeys, HUD fields,
   auto hide, hide from capture, which tools are in the dock).

Leave room in the dock design for future tools (FACEIT match info, notes,
crosshair, match alert), but don't build them now.

### 4. Pinned widgets
- A pinned tool stays on screen after the shell closes, as a small,
  click-through, never-focused widget (same window styles as the HUD:
  WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW |
  WS_EX_NOACTIVATE), with the hide-from-capture setting applied.
- The existing HUD becomes the pinned form of Performance and Hardware, so
  there is one system rather than two.
- Pinned widgets update at most 2 Hz and redraw only on change. Prefer the
  native GDI renderer (hud.py) for pinned widgets; a WebView per pinned
  widget is too heavy. If a tool can't be drawn natively, it isn't pinnable.
- Auto hide during live rounds (GSI) applies to pinned widgets.

## Limits (unchanged, non-negotiable)

- All hard safety rules from OVERLAY_STEP0_BRIEF.md: no hooks or injection,
  no SendInput or input hooks, no game memory access (OpenProcess 0x1000
  only), no drivers, hotkeys only via RegisterHotKey, no UAC prompts from
  overlay code, region lock only through `cs2cfg.serverlock`.
- Load: shell closed = no WebView work (suspended or all timers stopped),
  no data requests. Shell open = each visible tool at its own rate, max 10 Hz
  for graphs. One WebView for the whole shell, never one per tool.
- Overlay stays off by default.
- Style through the app's theme tokens so every theme works.

## Done means

- unittest only. Tests for the registry, the tool endpoint (auth, unknown
  tool, unknown action), layout save/restore, pin state, and each tool's
  `data()` with mocked sources. The full suite passes.
- Safety grep clean.
- Screenshots in docs/overlay/preview/ (not committed): the shell with 2 or 3
  tools open, the dock, a pinned widget over a dark background, and the
  settings tool.
- Push `codex/overlay-shell`. No PR and no release: Claude retargets PR #17
  once Edy approves the look.
