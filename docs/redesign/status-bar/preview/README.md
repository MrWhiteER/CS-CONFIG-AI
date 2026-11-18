# Notification dock preview

The original ten before captures were made before editing index.html, using git show HEAD:cs2cfg/web/index.html. Each after capture shows six illustrative states produced by the real notification helpers, over the real app page. Only screenshot staging clones all six cards; the production dock always has at most three visible cards with a FIFO queue. API requests are answered by a static local preview server and never reach a desktop backend. All browser profiles and generated artifacts stay inside this worktree.

Run the renderer with Node: node docs/redesign/status-bar/preview/render.mjs. Use --before to render the original HEAD version again. The renderer runs 13 real Edge/CDP assertions, checks all 60 resolved theme/state colour pairs, and writes the after captures, seven-frame loader strip and render-report.json. It needs the installed Microsoft Edge path used in render.mjs. The contrast table is in contrast.md.

The production JS harness runs with node tests/status_bar_harness.cjs, or via py -m unittest tests.test_status_bar_web when Python is available. The existing Profile Rail's production Node harness can also run without Python using node docs/redesign/status-bar/preview/check-regressions.cjs. No existing test assertions were changed.

Verification: notification Node harness passed; extracted existing Profile Rail Node harness passed; 13 Edge browser assertions passed; no uncaught page exceptions; all 60 contrast combinations passed; git diff --check passed. Attempts to run unittest modules tests.test_status_bar_web, tests.test_profile_rail_web and tests.test_themes were blocked: py is absent from this tool session's PATH and the installed Python313/python.exe returns Access is denied. The Python suite could not be run.

Progress is measured from settled startup loads, demo bytes (only determinate with a known total), and two actual config scan requests. The Apply plan exposes changed settings, not per-write progress; Apply and Restore are single synchronous requests without live counters. Those stay indeterminate during their requests and show returned step counts on completion. No backend, helper, game configuration or admin behaviour was changed.

The API keeps status(text, isError) and busy(text), and adds optional {id,kind,progress,detail,title}. Reusing an explicit id updates the same job. status.progress(text,fraction,options), status.dismiss(id) and status.clear() are available. Errors persist until dismissed or explicitly replaced on the same job; unrelated jobs and legacy status('') cannot erase an error. Queued cards start their six-second lifetime when displayed. Hover, focus and hidden windows pause lifetimes. Raw diagnostics are escaped inside collapsed Details.

Screenshots:

- [after-acid.png](after-acid.png) (1440 x 900)
- [after-carbon.png](after-carbon.png) (1440 x 900)
- [after-crimson.png](after-crimson.png) (1440 x 900)
- [after-daylight.png](after-daylight.png) (1440 x 900)
- [after-ember.png](after-ember.png) (1440 x 900)
- [after-frost.png](after-frost.png) (1440 x 900)
- [after-neon.png](after-neon.png) (1440 x 900)
- [after-paper.png](after-paper.png) (1440 x 900)
- [after-pro.png](after-pro.png) (1440 x 900)
- [after-violet.png](after-violet.png) (1440 x 900)
- [before-acid.png](before-acid.png) (1440 x 900)
- [before-carbon.png](before-carbon.png) (1440 x 900)
- [before-crimson.png](before-crimson.png) (1440 x 900)
- [before-daylight.png](before-daylight.png) (1440 x 900)
- [before-ember.png](before-ember.png) (1440 x 900)
- [before-frost.png](before-frost.png) (1440 x 900)
- [before-neon.png](before-neon.png) (1440 x 900)
- [before-paper.png](before-paper.png) (1440 x 900)
- [before-pro.png](before-pro.png) (1440 x 900)
- [before-violet.png](before-violet.png) (1440 x 900)
- [loader-strip.png](loader-strip.png) (2240 x 140)
