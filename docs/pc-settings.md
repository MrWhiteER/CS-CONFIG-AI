# PC settings are only on while the app runs

Edy's rule (Nov 21): the hardware/system settings the app changes go back to the
player's own when the app is not running. Game configs and picture settings stay.

Code: `cs2cfg/pcstate.py`. Tests: `tests/test_pcstate.py`.

## What is covered

| Setting | Put back with |
|---|---|
| Steam launch options for CS2 | `localconfig.vdf` line, once Steam is closed |
| CS2 window mode (`setting.fullscreen`, `nowindowborder`, `fullscreen_min_on_focus_loss`, `monitor_index` in `cs2_video.txt`) | once CS2 is closed |
| Windows graphics setting for cs2.exe (`UserGpuPreferences`) | HKCU registry |
| Fullscreen optimisations for cs2.exe (`AppCompatFlags\Layers`) | HKCU registry |
| Power plan | `powercfg`, then the helper's existing `power.set` job |
| Windows Security exclusion of the CS2 folder | the helper's existing `defender.cs2` job |
| NVIDIA scaling | NVAPI, once CS2 is closed |
| NVIDIA 3D settings for CS2 (`nvidia_3d`) | NVAPI or the helper's `nvidia.set`, once CS2 is closed |
| Refresh rate | display API, once CS2 is closed |
| Desktop resolution while stretched | `deskmode` (already existed) |

NVIDIA 3D settings in CS2's own program profile (Settings → NVIDIA, and each
Launcher mode) are kind `nvidia_3d`, one part per setting id, put back with
`nvidia.write_cs2` once CS2 is closed. They save through the helper's
`nvidia.set` job (helper version 3, one more prompt per PC); without the helper
the put-back reports a plain error and never prompts.

## How

* Every writer calls `pcstate.note(kind, ident, before, after)`. The first
  change keeps `before` as the original. A first-run snapshot of everything is
  saved too (`pc-originals.json`, key `first_run`).
* Put back only touches a setting that still holds the app's value. If the
  player changed it, it is left alone and forgotten.
* Region lock stays on while the app is closed (the player turns it off in the
  app; uninstall removes it), so its `+mm_dedicated_search_maxping` stays in the
  launch options with it. Uninstall removes both.

## Triggers

* **App start**: snapshot (once), set the app's values again, start the watcher
  (`CS2 Launcher.exe pc-guard --pid N`, hidden, no console).
* **Quit, crash, Task Manager**: the watcher sees the process end and puts
  everything back. Screen settings wait for CS2 to close. It stops if the app
  is opened again.
* **Update**: `/api/update/install` writes `pc-updating.flag`; the watcher exits
  at once (the updater waits for every process in the install folder) and the
  new version sets everything again.
* **Windows shutdown with the app open**: a HKCU RunOnce entry
  (`CS2 Launcher - put PC settings back`) runs `pc-restore` at next sign-in.
* **Uninstall**: `uninstall-cleanup` puts everything back before the helper
  removes itself.
* Steam's and CS2's own files are rewritten by those programs on exit, so when
  they are open the change is handed to a small PowerShell script in
  `%LOCALAPPDATA%\cs2-autoconfig-restore` that waits for them to close, edits
  only lines that still hold the app's value, and deletes itself.
* While the app runs and Steam was open at start, the app's launch options are
  handed to the game through `steam.exe -applaunch` on Play instead.
