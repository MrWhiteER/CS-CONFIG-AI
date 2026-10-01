# Brand

The mark is **not** stored here as a binary. `cs2cfg/appicon.py` draws it, and
what that module produces is byte-identical to the brand set's
`cs-config-ai.ico` — the tests check exactly that. Changing a number there
changes the application icon, the window icon, the notification-area icon and
the installer's icon together.

The three files beside this one are the vector originals, kept for places code
cannot reach: the project banner, a horizontal logo for a dark background, and
the square mark on its own.

| File | What it is for |
| --- | --- |
| `icon.svg` | The square mark. Also inlined into the interface as its favicon. |
| `logo.svg` | Horizontal lock-up for dark backgrounds. Live text, not outlines. |
| `banner.svg` | 1500×500, the repository banner at the top of the main README. |

Palette: violet `#A78BFA`, dark tile `#130C1F`, background `#07050D`, text
`#ECE8F7`.
