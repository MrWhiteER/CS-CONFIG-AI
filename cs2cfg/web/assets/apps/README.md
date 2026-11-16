# Apps tile assets

All logos here are the publishers' official files, copied byte-for-byte. Do not trace,
recolour, crop or distort them; only the surrounding tile is animated (`object-fit: contain`).
FACEIT uses `../faceit/faceit-mark.svg`; its provenance is in `../faceit/README.txt`.

| File | Official source (fetched 2026-11-15) |
| --- | --- |
| `discord-logo.svg` | Discord brand page https://discord.com/branding, "Symbol, blurple, SVG" download: https://cdn.discordapp.com/assets/content/a736b95923ddbc155e828651c92471292e40727655d770a06cec89c48ba0b41f.zip, file `Discord_Symbol_Color/Discord-Symbol-Blurple.svg` |
| `teamspeak-logo.svg` | TeamSpeak media kit https://teamspeak.com/en/mediakit/, SVG kit https://files.teamspeak-services.com/media/teamspeak-mediakit/TeamSpeak_MediaKit_SVG.zip, file `TS_InLine_BlueLight.svg` (variant for dark backgrounds) |
| `teamspeak-logo-dark.svg` | Same TeamSpeak SVG kit, file `TS_InLine_BlueDark.svg` (dark-text variant, wired up for light themes) |
| `crosshairx-logo.png` | CenterPoint Gaming's official Steam store logo for Crosshair X (app 1366800): https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/1366800/logo.png. centerpointgaming.com has no public press kit (the product page returned 403). |

TeamSpeak uses `teamspeak-logo.svg` on dark themes and the official dark-text
`teamspeak-logo-dark.svg` on light themes (Paper and Daylight). CSS theme tokens
switch the visible image immediately when the theme changes. Crosshair X keeps
its original white logo and sits on a rounded dark plate with clear space on
those light themes. Tiles and app detail headers share this treatment; dark
themes retain their original presentation. No logo file is modified or filtered.

Discord settings links are best-effort client routes (`discord://-/settings/...`).
Client versions may route to Home instead; the UI also states the exact page names
for manual navigation.
