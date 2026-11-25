# Agent updates

## 2026-11-24 | IMPLEMENT-001 | Codex -> Claude

- Owner authorized all audit fixes and additions, followed by GUPDATE after
  completion/checks. This is explicit publication approval for this batch.
- Codex owns branch codex/audit-hardening-and-tools from origin/main bec72dd,
  release 1.26.8. Other dirty worktrees are preserved.
- Scope and checklist: docs/IMPLEMENTATION.md. Start with file integrity,
  sync acknowledgement, script semantics and map restoration, then new tools.
- Intended files: affected cs2cfg modules, web UI, tests, verification/release
  tooling, shared rules and handoff docs. No overlap with other worktrees.
- Existing Claude session acknowledgement is pending. Shared notes travel
  with the approved batch when it is published.

## 2026-11-25 | IMPLEMENT-002 | Codex → Claude

- Implemented the audit fixes and the six additions. Settings → Tools holds
  sync comparison, benchmarks, config tracing, diagnostic export and practice.
  Script Builder has a read-only debugger.
- Local verification covers Windows file writes, sync recovery and conflicts,
  script semantics, map restoration, browser workflows and both updater
  templates. Installer and portable packages were built for version 1.27.0.
- Live CS2 and production multi-PC sync require verification on the owner's
  game PC. The current worktree did not supply those environments.
- GUPDATE was granted for this batch. The owner’s existing Claude session
  has not acknowledged the handoff.

## 2026-11-25 | STATS-PROFILE-001 | Codex -> Claude

- Owner requested bundled offline map thumbnails for Stats and inline profile
  change animation inside the selected Launcher card. Working locally on
  codex/offline-map-art-inline-profile, based on main de0bdb0.
- Scope: Stats artwork and lookup, Launcher profile apply presentation and tests.
  Prior 1.27.1 publication approval was for a different batch.

## 2026-11-25 | STATS-PROFILE-002 | Codex → Claude

- Completed both tasks locally on codex/offline-map-art-inline-profile.
  Stats uses 48 original WebP illustrations and a bundled unknown-map
  fallback. Launcher shows each confirmed change in the selected card on a
  transparent background, with skipped work and errors called out separately.
- Affected files: Stats renderer and stylesheet, map assets and generator,
  Launcher HTML, apply receipts in webui.py, and their regression checks.
  Full Python and browser verification passed (2,174 Python tests, one
  skipped), including additional narrow Stats and reduced-motion Launcher
  runs. The Windows build includes all 49 map assets. Live CS2 was not used.
- The batch is local and needs its own GUPDATE. Existing Claude session
  acknowledgement is pending. Recheck delivery after the reported
  November 25 10 PM Dubai reset during active work. Keep work in these files
  coordinated with this branch until the batch is merged.

## 2026-11-25 | STATS-PROFILE-003 | Codex → Claude

- Removed the obsolete Launcher “Review settings” banner and checklist per
  the owner. The apply animation stays inside the selected card; the
  existing profile selector still uses the read-back state.
- Base implementation is local commit `32ee6b5`. The banner removal changes
  Launcher HTML and regression coverage on the same branch. The complete
  batch remains local pending GUPDATE and Claude acknowledgement.

## 2026-11-25 | INVENTORY-001 | Codex → Claude

- Working on `codex/inventory-workspace` from local `8171136`. Scope is
  inventory refresh and filters, shared item previews, sticker lighting
  preview, and multi-item preparation with a Steam Market handoff.
- Intended files: inventory and web UI modules, browser assets and tests.
  Existing Claude session acknowledgement is pending.

## 2026-11-25 | INVENTORY-002 | Codex → Claude

- Inventory now checks Steam while visible, paginates, preserves the last
  good list on temporary errors, and supports search, filters and newest
  ordering. A read of the current PC's Steam inventory succeeded.
- Inventory reuses All Skins previews and music playback. Both views use the
  interactive sticker preview with approximate map lighting. Marketable
  items can be selected as a batch, with price notes and a link for each
  exact asset in Steam. Steam itself handles listing and confirmation.
- Added pagination and browser regressions. No real listing was submitted.
  Leave this batch local pending GUPDATE. Claude acknowledgement remains
  pending; recheck the existing session after its reported reset during work.

## 2026-11-25 | LAUNCHER-SCENE-001 | Codex → Claude

- Owner requested a sharper animated gamer scene, genuine CS2 footage on
  the monitor, automatic pause while playing CS2, and varied agents.
- Worked on `codex/launcher-gameplay-scene` from local Inventory commit
  `a315d6b`, which fixes the Apps browser fixture boundary. Added two
  original gamer variations and support for the owner's local video. No
  exported CS2 recording was available in the local capture folders.
- Affected files: Launcher HTML, home assets and scene script, the native
  picker, local media handlers, and their tests. Launch begins by unloading
  video and pausing the character. The external Steam process check also
  stops playback. Browser coverage checks reduced motion and resume.
- Remains local pending GUPDATE. Claude acknowledgement is pending, with
  delivery to be checked after the reported reset during active work.
