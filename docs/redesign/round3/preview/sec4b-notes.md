# R3-7 item 2: count the three system settings

Implemented in the supplied `codex/r3-7` worktree. No git write commands, Python execution, live Apply, helper calls, or UAC prompts.

## What changed

- NVIDIA profile, Windows power, and Windows graphics now each contribute one check to “Your PC is set: N/N verified.” Both the Play badge and Apply checklist use the same server counts. Live N still varies with the individual video/file checks recorded by Apply.
- Green means the current read matches; an ordinary recommendation mismatch is amber **Not set**, with a button opening the existing settings surface. Unreadable values are **Not checked**, remain in N, and prevent full confirmation. A missing NVIDIA GPU/driver is neutral **Not applicable** and leaves N. Existing failed Apply writes remain red.
- New Apply receipts include all three read specifications. GET upgrades old receipts’ excluded placeholder rows in memory, so existing users do not need another Apply to see the corrected count. GET does not save or mutate the receipt.
- Expanded the checklist’s scroll allowance so the nine-row preview shows all three system checks together. Added bottom space for the existing reveal animation, avoiding a transient scrollbar. Existing theme tokens, hidden-window pausing, and reduced motion still apply.
- **Caller live check:** On the caller’s real PC (NVIDIA GPU and driver installed, CS2 absent), `nvidia.read_recommended()` returned `available: False` with `reading the effective application setting: NVAPI_SETTING_NOT_FOUND`. An unset setting is inherited, so the reader now tries the app, current global, and base profiles in order, then NVIDIA’s documented default when none stores a value. Missing applications/profiles follow the same inheritance path. Ordinary defaults now yield a readable comparison (normally amber **Not set** for power management), while access failures remain **Not checked**. Caller must rerun the live read after this fix; no post-fix hardware result is claimed here.

## Expected values, including items never applied

These three rows compare current state with recommendations rather than taking the first observed value as “expected.” A first read must not turn an unconfigured PC green. Matching settings also count when the user set them outside this app. A later mismatch stays amber Not set; it does not claim an Apply write failed.

| Row | Target and read | Existing control |
| --- | --- | --- |
| NVIDIA profile | Effective `cs2.exe` power management = Prefer maximum performance (`0x1057EB71 = 1`); Vertical sync = application-controlled or Off (`0x00A879CF = 0x60925292` or `0x08416747`). Uses the existing NVAPI `_Session` and read-only `DRS_GetSetting`: app → current global → base → documented driver default. Missing app/profile or unset setting inherits. No catalogue scan, driver write, or profile creation. | Review NVIDIA settings opens Graphics. The row gives NVIDIA Control Panel > Manage 3D settings > Program Settings > cs2.exe instructions. See the limitation below. |
| Windows power | Active High performance GUID, Ultimate template GUID, the app’s recorded active `changed_to` GUID (including a renamed Ultimate clone), or an Ultimate Performance GUID discovered by the existing fix’s name rule. Reuses `_powercfg` and GUID parsing with `/getactivescheme` and, when needed, `/list`, each with a five-second timeout. | Open power control opens Fix It, where the existing performance-power switch lives. |
| Windows graphics | Reads the actual installed `game/bin/win64/cs2.exe` value in HKCU `Software\Microsoft\DirectX\UserGpuPreferences`, comparing `read(..., strict=True)` with `wanted(current)`: `GpuPreference=2` and `SwapEffectUpgradeEnable=1`. Unrelated fields such as AppStatus do not affect the result. Missing registry value = Not set; denied access or missing executable = Not checked. | Open Windows graphics opens Settings > Apply > Machine and focuses Set for performance when present. |

The NVIDIA controls in this repository are read-only; there is no existing profile writer or stored desired 3D preset to reuse. I therefore chose the two explicit recommendations above: maximum performance and no driver-forced VSync on. Application-controlled VSync allows CS2’s existing video setting to take effect. Image quality, Reflex, driver defaults for unrelated settings, G-SYNC, and global settings are outside this row’s target. No NVIDIA writer was added. The UI explains the manual control instead of offering a nonfunctional Apply button.

NVIDIA IDs, allowed values, read function IDs, and error distinctions were checked against NVIDIA’s primary sources: [published setting enums](https://github.com/NVIDIA/nvapi/blob/main/NvApiDriverSettings.h), [function IDs](https://github.com/NVIDIA/nvapi/blob/main/nvapi_interface.h), [DRS API declarations](https://github.com/NVIDIA/nvapi/blob/main/nvapi.h), and [status codes](https://github.com/NVIDIA/nvapi/blob/main/nvapi_lite_common.h). Unset setting (`-160`), missing profile (`-163`), and missing application (`-166`) permit inheritance. `DRS_GetCurrentGlobalProfile` precedes `DRS_GetBaseProfile`; handles are opened only when a setting needs fallback and reused within that read. If both lack the setting, the published defaults are `PREFERRED_PSTATE_DEFAULT = OPTIMAL_POWER` (`5`) and `VSYNCMODE_DEFAULT = PASSIVE` (`0x60925292`). These differ from the power recommendation and do not make an unconfigured PC green. Access denied (`-175`) never falls back to a default. Missing NVIDIA device (`-6`) is not applicable. Unsupported calls, unreadable settings, incompatible DLLs, and other driver errors remain Not checked.

## Read-only boundary / Needs admin

- **Needs admin: none of the three verification reads.** No helper job was added or used, and verification does not call `elevated.ready()` or `elevated.run()`.
- If local policy or driver access prevents a read, show Not checked and keep it in the denominator. There is no new elevation fallback. No admin-only value was discovered by source review; NVIDIA and registry reads still need live validation by the caller.
- Verification never calls power create/setactive/toggle, Windows graphics apply, or a driver save/set function. Navigation buttons do not activate the controls they open. The existing controls retain their own behavior when the user deliberately operates them.
- Power-record reads use the data directory already resolved at app startup. Verification does not call the quickfix path resolver / `user_data_dir()`, which could otherwise create a directory and write a storage probe on first resolution.
- Native `powercfg /getactivescheme` was run once read-only during this task. It returned the standard High performance GUID with the expected output format. No live NVIDIA or registry read was executed through Python.

## Files

- `cs2cfg/verification.py`: system check specifications, old-receipt upgrade, unelevated comparisons, counts/actions.
- `cs2cfg/nvidia.py`: published target enums, targeted effective-setting reads through the existing session, missing-driver versus read-error distinction.
- `cs2cfg/wingraphics.py`: opt-in strict read errors; default callers retain the previous forgiving behavior.
- `cs2cfg/webui.py`: records system checks and upgrades old receipts during GET using the already resolved storage directory.
- `cs2cfg/web/index.html`: Not set / Not applicable states, existing-control navigation, checklist sizing.
- `tests/test_verification.py`: 52 test methods total, covering actual ctypes read plumbing with fake NVAPI functions, powercfg subprocess results/timeouts, fake winreg reads, match/mismatch/unavailable counts, old receipts, and read-only guards. The NVIDIA regression cases now distinguish app/global/base handles and cover explicit app precedence, per-setting inheritance, global/base fallback, documented defaults, missing CS2/profile, and errors that must stay Not checked. Every test class stubs `elevated.ready/run`; system tests also reject repair, helper, and UAC paths. No real helper code is invoked.
- `tools/check_home_launcher.cjs`: counted system fixtures, 9/9 and 8/8 behavior, amber recommendations and navigation, unreadable counts, text/action escaping, shared Apply results, and preview routes.
- This note and the four `sec4b-*.png` previews.

## Validation

| Node suite | Passed checks |
| --- | ---: |
| check_home_launcher.cjs | 202 |
| check_apps_tiles.cjs | 108 |
| check_connection_startup.cjs | 8 |
| check_faceit_dashboard.cjs | 83 |
| check_fixit_toolbox.cjs | 97 |
| check_graphics_workspace.cjs | 61 |
| check_keyboard_workspace.cjs | 2845 |
| check_server_ping_widget.cjs | 535 |
| check_setup_wizard.cjs | 162 |
| **Nine-suite total** | **4101** |

- Home also passed 202 checks at 1366×768 with reduced motion; screenshot runs for verified, not applicable, and Paper also passed.
- All five inline scripts compile; setup’s full-page first-run ordering passed. `node --check tools/check_home_launcher.cjs` and `git diff --check` passed.
- The Apps suite regenerates its section 6 previews. Those unrelated regenerated files were restored byte-for-byte from read-only `git show HEAD:<path>` output, keeping this change scoped to item 2.
- **Python was not run**, as requested. Caller should run `python -m unittest`; no Python pass result is claimed.
- For the unset-NVIDIA-setting follow-up, reran Home (202 checks) and Graphics (61 checks): both passed. Node source checks also confirmed the read-only function table, absence of saving code, preserved caller DLL-error text, and unique Python test names; `git diff --check` passed. The new Python regression cases and post-fix live NVIDIA read remain for the caller.

## Screenshots

Deterministic offline fixtures using production rendering, at 1440×1100. These are not a live Apply or measured hardware confirmation. The six existing groups plus three system rows illustrate the denominator; live N varies.

- [sec4b-before-verified.png](sec4b-before-verified.png): captured before any editing; 6/6 with excluded unchecked system rows.
- [sec4b-after-verified.png](sec4b-after-verified.png): expanded checklist, all nine rows counted and matching, 9/9.
- [sec4b-after-notapplicable.png](sec4b-after-notapplicable.png): non-NVIDIA fixture, neutral excluded row, 8/8.
- [sec4b-after-paper.png](sec4b-after-paper.png): expanded 9/9 checklist in Paper.

Reproduce with `HOME_HASH=#verification`, `#verification-notapplicable`, or `#verification-paper`, plus `HOME_SCREENSHOT=<path>`, when running `node tools/check_home_launcher.cjs`. `#verification-notset` shows the three amber recommendations and their review buttons.

## Open questions for Edy

- Confirm the NVIDIA recommendation choice: Prefer maximum performance plus application-controlled/Off VSync. The current app has no NVIDIA profile writer; this change intentionally exposes the existing manual path. Any future writer is separate work.
- Caller: run the Python suite and validate live NVAPI inheritance, HKCU reads, and old-receipt reload on Windows. Access failures must remain Not checked without a prompt. No implementation work is waiting on a new helper/admin job.
