# Apps tile assets

FACEIT uses `../faceit/faceit-mark.svg` unchanged; its provenance is in
`../faceit/README.txt`. No filter, mask, recolouring or shape animation is applied
to the Apps logo. Only the surrounding tile moves.

The following files are **neutral placeholders, not official logos**. Each has
the same generic application-window icon plus its app name, with no imitation
of brand artwork. The sandbox cannot fetch files over HTTPS (curl to discord.com
failed to connect on 2026-11-15). These placeholders must be replaced before
claiming that the three tiles display official branding.

| File Edy must replace | Official artwork to drop in | Source |
| --- | --- | --- |
| `cs2cfg/web/assets/apps/discord-logo.svg` | Unmodified official Discord logo SVG, suitable for both light and dark surfaces | [Discord brand assets](https://discord.com/branding) |
| `cs2cfg/web/assets/apps/teamspeak-logo.svg` | Unmodified official TeamSpeak logo SVG from the complete SVG media kit | [TeamSpeak media kit](https://www.teamspeak.com/en/mediakit) |
| `cs2cfg/web/assets/apps/crosshairx-logo.svg` | Official Crosshair X logo SVG supplied/approved by CenterPoint Gaming | [CenterPoint Gaming](https://centerpointgaming.com/) — request the approved asset from the publisher if no downloadable SVG is provided |

Keep the exact filenames; do not trace, recolour or distort downloaded logos.
The UI uses `object-fit: contain`. Keep the publisher's artwork and viewBox intact;
check clear-space/licensing requirements before shipping. If the publisher only
supplies PNG, preserve it untouched and update both appLogo() and the tile src.
The new folder is included in `cs2cfg.spec` datas. No CDN is used at runtime.

Discord settings links are best-effort client routes (`discord://-/settings/...`).
Client versions may route to Home instead; the UI also states the exact page names
for manual navigation. Confirm these routes on Edy's installed version.
