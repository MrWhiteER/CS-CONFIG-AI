# Apps tile assets

All logos here are the publishers' official files, copied byte-for-byte. Do not trace,
recolour, crop or distort them; only the surrounding tile is animated (`object-fit: contain`).
FACEIT uses `../faceit/faceit-mark.svg`; its provenance is in `../faceit/README.txt`.

| File | Official source (fetched 2026-11-15) |
| --- | --- |
| `discord-logo.svg` | Discord brand page https://discord.com/branding, "Symbol, blurple, SVG" download: https://cdn.discordapp.com/assets/content/a736b95923ddbc155e828651c92471292e40727655d770a06cec89c48ba0b41f.zip, file `Discord_Symbol_Color/Discord-Symbol-Blurple.svg` |
| `teamspeak-logo.svg` | TeamSpeak media kit https://teamspeak.com/en/mediakit/, SVG kit https://files.teamspeak-services.com/media/teamspeak-mediakit/TeamSpeak_MediaKit_SVG.zip, file `TS_InLine_BlueLight.svg` (variant for dark backgrounds) |
| `teamspeak-logo-dark.svg` | Same TeamSpeak SVG kit, file `TS_InLine_BlueDark.svg` (variant for light backgrounds; not wired up yet) |
| `crosshairx-logo.png` | CenterPoint Gaming's official Steam store logo for Crosshair X (app 1366800): https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/1366800/logo.png. centerpointgaming.com has no public press kit (the product page returned 403). |

Notes: the TeamSpeak and Crosshair X files are the light-on-dark variants (white wordmark),
chosen for the app's dark themes. On the light Paper theme the tile background must stay dark
enough for them to read; if not, swap in `TS_InLine_BlueDark.svg` from the same kit for light themes.

Discord settings links are best-effort client routes (`discord://-/settings/...`).
Client versions may route to Home instead; the UI also states the exact page names
for manual navigation.
