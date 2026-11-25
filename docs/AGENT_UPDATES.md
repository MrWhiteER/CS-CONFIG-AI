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

## 2026-11-25 | LAUNCHER-SCENE-002 | Codex → Claude

- Owner clarified that the monitor is a static gameplay screenshot and only
  the keyboard hand should move. They require the exact Valve agents and
  rejected original substitutes. The Launcher now uses an empty workstation
  until ready-made frames are supplied. It supports separate CT and T
  sheets and freezes them as soon as CS2 launches.
- Branch `codex/launcher-static-ace-scene`, based on `727c998`. Files:
  Launcher HTML and home assets, media API, picker and regression checks.
- The local Launcher uses the owner's actual Dust II screenshot. The image
  is not bundled. An authentic ace screenshot and ready-made keyboard poses
  remain outstanding. GUPDATE and Claude acknowledgement remain pending.

## 2026-11-25 | LAUNCHER-SCENE-003 | Codex → Claude

- Removed the monitor's letterboxing and anchored the screenshot crop to
  the top right to preserve the kill feed. Added preferred stock agent
  filenames `ct-default.png` and `t-default.png` for supplied frames.
- The local CS2 config and Steam inventory response do not establish which
  agent is equipped. The stock files are the Launcher default when
  present. The exact seated stock artwork remains outstanding.
- Scope: Launcher styling, agent asset resolution and regression checks.
  Pending GUPDATE and existing Claude acknowledgement.

## 2026-11-25 | LAUNCHER-SCENE-004 | Codex → Claude

- Owner supplied the stock SAS CT archive. Posed the supplied rig for
  the Launcher, then adjusted the seating, wrist alignment and finger
  placement after feedback. The editable scene and the two-frame PNG
  are local to the owner's PC. The supplied mesh and textures stay outside
  Git. Credit: gettan on Sketchfab; source credit Valve.
- The local asset renders with the real Dust II screenshot and passes
  the Launcher browser checks. No stock T model was supplied, so pose
  transfer across variants remains unverified. Claude acknowledgement
  and GUPDATE remain pending.

## 2026-11-25 | LAUNCHER-SCENE-005 | Codex → Claude

- Owner asked to put the chair in front of the desk, preserve the SAS
  body pose, straighten the hands, and add gaming peripherals with
  theme and keybind lighting. The new workstation includes a handheld,
  fader mixer, and microphone. The SAS placement and rendered hand
  frames were adjusted locally to match it.
- The Launcher uses the existing CS2 HID color palette for its
  photographed keyboard. Desk lighting follows the theme and pauses
  during launch or play. Affected files: Launcher home art, HTML,
  scene script, media tests, and web UI. The supplied SAS asset remains
  local. No GUPDATE or existing Claude acknowledgement.

## 2026-11-25 | LAUNCHER-SCENE-006 | Codex -> Claude

- Starting the owner's Launcher art revision in codex/launcher-static-ace-scene at 2cf2639. In scope: home asset art, monitor image, Launcher scene HTML/JS and obsolete Launcher-specific lighting/media hooks. Replace the exact SAS with original seated CT/T variants, remove keyboard and handheld lighting, and use the linked Steam news banner on the screen.
- Checking the official banner and preparing local artwork. Delivery to the existing Claude session is pending; retry after the last reported reset if the session is available. No GUPDATE for this batch.

### Style direction update | Codex -> Claude

- Owner supplied a visual reference for the character and lighting. Final direction is a fitted knit balaclava covering the face, worn desk, cool industrial shadows and grounded original CT/T gear, with the official static CS2 Steam banner on the monitor. Supersedes the visible-profile trial and the oversized hood trial. Keyboard and handheld remain unlit. The old gameplay picker and exact SAS sheet are no longer part of the Launcher scene.
- Restored the physical RGB frame helper after the early suite caught its internal sync caller. All 31 targeted RGB tests now pass. Existing Claude acknowledgement remains pending; last reported reset is 22:00 Asia/Dubai.

### Local verification and handoff | Codex -> Claude

- Final artwork uses original navy CT and olive/rust T in the reference-inspired worn workshop. Each has a fitted knit balaclava, a close hood and smoked goggles covering the entire eye opening. The static monitor uses the exact PNG from the requested Steam post. Dark keyboard and handheld, with quiet accents on the existing microphone, monitor and mixer.
- Latest normal browser previews checked both sides (202 each), with 198 reduced-motion checks. Full Python and browser gate ran successfully (2,176 Python tests, one skipped) before the final art swap; the completed artwork passed the targeted preview runs. The CLI RGB tests also passed (31).
- Existing Claude session acknowledgement is pending. Next retry is after 22:00 Asia/Dubai if the owner’s session is available. The prepared batch is local pending GUPDATE.
