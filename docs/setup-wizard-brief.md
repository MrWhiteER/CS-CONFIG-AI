# Codex brief: first-run setup wizard + sync status (CS CONFIG AI)

Branch with the backend: `claude/project-thread-firyoa` (PR on GitHub). Build the UI on top of that branch, in `cs2cfg/web/index.html`, in the current redesign's style (same tokens, themes, cards). No backend changes should be needed. If one is, say what and why.

## When it shows

On page load, `POST /api/firstrun`. If `needed` is true, open the wizard full-window over the app before anything else. Every step has **Back**, **Skip** and **Next**. The last step has **Finish**. Closing it counts as finishing with whatever was answered, so it never shows twice on the same PC.

Also add a "Run setup again" entry in Settings that opens the same wizard. It's prefilled from `current`.

## `POST /api/firstrun` returns

```
needed, steps: ["sync","permission","sound","preset","apps","theme"],
account,                       // Steam account id this PC is playing on
cloud: { configured, signed_in, steam_id, ... }   // same as /api/cloud
sync:  { action, reason, ... } // last automatic sync round
cfg:   { path, exists, writable, reason }
sound: same shape as /api/audio (output + input device lists, current pins)
presets: [{ id: competitive|balanced|quality, label, blurb, fps, bottleneck, tier }]
apps:  [{ id, name, exe, args, with_game, integration }]   // only apps found on this PC
themes: ["violet","ember",...]
current: { intent, theme, audio_output, audio_input, cfg_write_ok, sync_auto }
```

## Steps, in this order

1. **Sync with your Steam account.** If `cloud.signed_in` is false, show a "Sign in with Steam" button using the existing cloud sign-in flow (`/api/cloud/login` with provider steam, then poll `/api/cloud/poll`, the same as the account panel). Once signed in, call `POST /api/sync/now`. If `last.action == "pull"`, show "Brought over your settings from <last.source>: N files" and say that the preset and theme steps are prefilled from the other PC. Add a toggle "Keep this PC in sync automatically" (answer `sync`, default on). If the cloud isn't configured, skip the step silently.
2. **Permission.** Explain in one sentence that the app writes its config files into `cfg.path`. Two buttons: Allow (`cfg_write: true`) and Not now (`cfg_write: false`). If `cfg.writable` is false, show `cfg.reason` and still let them continue.
3. **Sound.** Two dropdowns from `sound`: output (speakers/headset) and input (microphone). Preselect the current Windows defaults. Answer `sound: {output: id, input: id}`.
4. **Game preset.** Three big cards: Competitive / Balanced / **Visual** (id `quality`). Under each, show the big number "~`fps` FPS", or "estimate unavailable" when it's null, plus `blurb`. Optionally show the bottleneck in small print ("limited by GPU"). Preselect `current.intent` or balanced. Answer `preset: id`.
5. **Start before the game.** One toggle row per entry in `apps`, using the companion icons the rail already uses. Preselect `with_game`. If the list is empty, say "No companion apps found on this PC. You can add any program later in Companions." Answer `apps: [ids that are on]`. FACEIT shows up here automatically once PR #12 is merged.
6. **Theme.** Reuse the existing theme swatches (`THEMES` + `applyTheme`) and preview live as they're clicked. Answer `theme: id`.

**Finish**: `POST /api/firstrun/finish {answers: {...}}`. Only send keys for steps the user actually answered; a skipped step leaves things unchanged. Then reload prefs, apply the theme, and close.

## Sync status (outside the wizard)

There's a small sync indicator in the account area or title bar. Poll `POST /api/sync` (`{auto, last}`) every 30 to 60 seconds.
- `last.action` "push" → "Synced to cloud", "pull" → "Updated from <source>", "none" with `ok` → "In sync".
- `ok: false` → show `last.reason` muted (e.g. "sign in with Steam to sync").
- `last.waiting > 0` → "N config files are waiting for permission to write to CS2's cfg folder", with a button that opens step 2.
- Click → "Sync now" (`/api/sync/now`) and the auto toggle (`/api/sync/auto {on}`).

## Copy rules

Plain words, no jargon. Say "your Steam account", not "cloud account". Never show raw ids or paths except `cfg.path` in step 2.
