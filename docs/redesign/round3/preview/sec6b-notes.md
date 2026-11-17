# R3-7 item 1: Apps logos on light themes

Paper and Daylight are the only light backgrounds in the production ten-theme
list. CSS theme tokens now show the official dark-text TeamSpeak variant there;
the original white wordmark remains visible on every dark theme. Crosshair X
keeps its original image, with a rounded plate using the theme's dark ink colour
and 8px vertical / 12px horizontal clear space on light themes. Tile title
alignment and logo dimensions stay the same. Detail headers follow the same
treatment, including theme changes while the detail page stays open.

No logo files were edited, recoloured, filtered, cropped or traced. Existing
transform/opacity animations and reduced-motion rules are unchanged. Compared
tile/logo computed styles and geometry with a baseline captured before edits:
all eight dark themes match.

Files changed:

- `cs2cfg/web/index.html`: paired TeamSpeak images and logo wrappers.
- `cs2cfg/web/assets/apps/apps.css`: theme tokens, image visibility and plate.
- `cs2cfg/web/assets/apps/apps.js`: identify the selected detail-header logo.
- `cs2cfg/web/assets/apps/README.md`: document the wired variants and plate.
- `tools/check_apps_tiles.cjs`: use the production theme list/switcher; check
  visible variants, loading, unchanged dimensions, alignment, plate clear space,
  at least 7:1 white-to-plate contrast, live detail changes and narrow layout.
- `tools/check_home_launcher.cjs`, `tools/check_connection_startup.cjs`: normalize
  CRLF before extracting source sections; existing LF-only markers failed on
  this Windows checkout. No application behavior changed for these fixes.
- This note and the four `sec6b-*.png` screenshots below.

Validation (all passed):

| Node suite in `tools/` | Checks |
| --- | ---: |
| `check_apps_tiles.cjs` | 108 |
| `check_home_launcher.cjs` | 193 |
| `check_setup_wizard.cjs` | 162 |
| `check_fixit_toolbox.cjs` | 97 |
| `check_graphics_workspace.cjs` | 61 |
| `check_connection_startup.cjs` | 8 |
| `check_faceit_dashboard.cjs` | 83 |
| `check_keyboard_workspace.cjs` | 2845 |
| `check_server_ping_widget.cjs` | 535 |
| **Total** | **4092** |

Setup also passed all five inline-script syntax checks and full-page boot
ordering. `node --check tools/check_apps_tiles.cjs` and `git diff --check` passed.

Screenshots use the offline production-renderer fixture at 1366 x 768:

- `sec6b-before-paper.png`: captured before any edits, with animation playback
  frozen; shows the original white wordmarks on the light tiles.
- `sec6b-after-paper.png`, `sec6b-after-daylight.png`: readable official logos.
- `sec6b-after-violet.png`: original dark-theme logo presentation.

Historical `sec6-*.png` files were preserved. Screenshot animation states vary;
dark-theme preservation was additionally checked through computed styles and
geometry, rather than claiming identical full-page screenshot pixels.

Python was not run; the caller runs `python -m unittest`. Browser checks use
stubbed API/process data. No remaining uncertainty about this visual fix; real
companion launches were outside these checks. No git write commands were run.
