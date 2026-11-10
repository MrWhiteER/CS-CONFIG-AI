# Redesign brief for Codex

The goal is a full visual redesign of the CS CONFIG AI desktop app. It covers buttons, icons,
text style, colours, animations, loading screens and the sign-in page. Behaviour stays exactly
as it is: this is a reskin, not a rewrite.

References: [Gaming UI design references](https://claude.ai/artifact/E8wR7dHVSQBtGiYv43rJBB)
(Razer Synapse, HyperX NGENUITY, Logitech G HUB, FACEIT, Leetify, Riot Client, and Dribbble shots
such as [GamerVerse](https://dribbble.com/shots/26443606-GamerVerse-Game-Dashboard-Design)).

## What exists today (read this first)

- The entire interface is one file: `cs2cfg/web/index.html` (~15,000 lines of HTML, CSS and JS).
  `cs2cfg/webui.py` serves it, and `cs2cfg/window.py` hosts it in a native Windows window.
- Styling is token-based. The default theme's tokens sit in `:root` around line 2160 (`--bg`,
  `--panel`, `--panel-2`, `--ink`, `--muted`, `--line`, `--accent`, `--good`, `--warn`, `--bad`,
  `--neon-*`, `--cat-*`). Alternate themes override them through `:root[data-theme="…"]`:
  `ember`, `carbon`, `acid`, `daylight`, `pro`.
- Fonts (around line 4584): `--display` is Bahnschrift/Oswald, `--body` is Segoe UI Variable,
  and `--mono` is Cascadia Mono.
- Brand (`docs/brand/README.md`): violet `#A78BFA`, dark tile `#130C1F`, background `#07050D`,
  text `#ECE8F7`. The default accent is `#8B5CF6`. `cs2cfg/appicon.py` draws the app icon and
  is pinned by `tests/test_appicon.py`. **Do not change the icon.**
- Navigation is a `.tabs` tablist (around line 5022) with these tabs: cs2, faceit, files, fix, gpu,
  inventory, keyboard, launcher, scripts, settings, skins.
- Sign-in is cloud login: a CSS block around line 1091, markup around line 5639, and JS around
  lines 11960 to 12110 (email/password plus other providers, ending in Steam).
- There are 19 `@keyframes` and about 42 inline SVG icons.

## Direction

Keep the violet brand as the default theme. It already matches the GamerVerse and Dribbble neon
look. Push it toward a modern esports dashboard:

- **Layout:** replace the top tab strip with a slim left icon rail (icon + label on hover, active
  item gets a violet bar and a glow), with the content canvas on the right. Use one header row
  for the version, a CS2 "detected" status pill and the account.
- **Colour:** base `#07050D`, cards `#130C1F` with glass (semi-transparent fill +
  `backdrop-filter: blur`), violet `#8B5CF6` to `#A78BFA` accent, and an optional violet-to-pink
  `#EC4899` gradient for hero elements only. Keep `--good`/`--warn`/`--bad` for ratings,
  Leetify-style. Every existing `data-theme` must keep working with the new components.
- **Typography:** condensed uppercase headings (keep Bahnschrift, with Rajdhani or Oxanium as an
  option) at 0.05 to 0.1em tracking. Body text in Segoe UI Variable at 13 to 14px. All numbers use
  tabular figures.
- **Buttons:** primary is a solid accent fill with a 8px radius, and a glow plus a 1px lift on
  hover. Secondary is a 1px outline that turns accent on hover. The main "Apply config" action is a
  wide, uppercase hero button, like Battle.net's Play button.
- **Icons:** one consistent outline set at 1.5 to 2px stroke (Lucide/Tabler style), inlined as
  SVG. Keep custom glyphs for game-specific things (crosshair, sensitivity, FPS).
- **Cards:** 12 to 16px radius, 1px `--line` border, soft shadow, and a subtle accent glow on hover.
  Stat chips use the ratings colours.
- **Motion:** 150 to 250ms ease-out on hovers and tab changes, a sliding active indicator on the
  rail, and cards fading and rising 8px on load, staggered 30 to 50ms. A pulse on live states
  (CS2 running, syncing). Honour `prefers-reduced-motion`.
- **Loading screen:** black screen with the logo mark glowing in, a thin violet progress bar and a
  rotating CS2 tip. Inside the app, use skeleton shimmer cards instead of spinners.
- **Sign-in page:** a Riot Client-style split layout. The form is on the left (logo, provider
  buttons, email/password, big accent "Sign in" button). On the right is full-bleed animated
  artwork with a dark violet gradient. Keep every existing provider, flow and message.

## Rules

1. Don't change any element `id`, `data-*` attribute, API call or JS behaviour. Restyle and
   restructure markup only where the JS does not depend on it.
2. Work through the tokens first, then the components (buttons, cards, rail, inputs, toggles,
   sliders), then the screens.
3. No external CDNs: the app must work offline. Bundle fonts and icons inline, or use system
   fonts.
4. All tests in `tests/` must still pass (`python -m pytest`).
5. Ship in small PRs: tokens and type first, then navigation, then components, then the loading
   screen and sign-in page.
