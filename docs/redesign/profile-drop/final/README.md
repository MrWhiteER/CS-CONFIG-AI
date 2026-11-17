# Finished Profile Rail

The app implementation is in `cs2cfg/web/index.html`. These captures load that page directly; neither prototype code nor screenshot fixtures are imported. The static server blocks all `/api/*` calls, so verification honestly reads **Not checked** and hardware readings remain unavailable.

## Captures

`profile-rail-{idle,hover,shelf}-{dark,daylight}.png` are the six requested 1440×900 captures. `theme-*.png` records shelf review for all ten theme-picker choices, including Paper and Pro. The Pro surface uses its existing opaque `--glass-3` token. Text and icons use theme ink tokens; profile identity uses the tinted seat and its border.

## Reproduction and validation

Run `node docs/redesign/profile-drop/final/render.mjs` from the worktree. The renderer uses installed Edge and native CDP without dependencies. Its temporary browser profile lives in the OS temporary directory and is removed on exit. `--serve` serves the real app page with the desktop API disabled.

`render-report.json` records the 26 passing browser checks, all screenshot dimensions, ten theme contrast measurements, and zero page JavaScript errors. Checks cover manual arrow/End exploration, native Enter/Space activation, native Tab dismissal, Escape focus restoration, outside dismissal, delayed hover, off-Home selection and undo with background plans, Home preview, real verification observation, Apply request success/failure lifetimes, reduced motion, hidden-control/window cancellation, and 860px fit. Controlled request fixtures are confined to the interaction checks and discarded by reloading before screenshots. Finite rail animations are finished before captures to show settled states.

`tests/test_profile_rail_web.py` adds three unittest cases. Its Node harness exercises the actual selection/plan/motion functions, including stale-plan rejection and failed-preview handling. That harness passed directly in Node, and the entire app script passed Node syntax parsing.

The full-suite command `py -3 -m unittest discover -s tests` was attempted but could not start: `py` is not available on PATH in this session. The installed launcher and Python 3.13 executable also return **Access is denied** when invoked by absolute path. Consequently **0 Python tests ran; failure/error counts are unavailable**, and a passing full suite cannot be claimed. No tests were ignored.
