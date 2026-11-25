# Audit hardening and tools

Owner authorized implementation of all audit fixes and additions on November
24, 2026, then explicitly authorized GUPDATE after this batch is completed
and checked. Publication approval applies to this batch, not unrelated work.

Branch: codex/audit-hardening-and-tools, based on origin/main bec72dd (1.26.8).
Codex owns this batch. Existing other worktrees must be preserved.

## Work inventory

- [x] Atomic, pre-encoded config writes and revision-checked editor saves.
- [x] Failed cloud pull accounting and Home/Work sync comparison/conflict UI.
- [x] Reachable script release/cycle checks and documented input-rule coverage.
- [x] Interactive script key-down/key-up debugger.
- [x] Restore known map baseline values and report unavailable values and serialized map state.
- [x] Updater quoting, Settings overflow, truthful status and missing defaults.
- [x] Repair four browser harnesses and add a required verification command/CI.
- [x] Repeatable measured preset A/B comparison.
- [x] Winning-config source trace with a safe undo path.
- [x] Redacted diagnostic package export with preview.
- [x] Guided practice using existing maps/lineups and verified restoration.
- [x] Regression tests, full test suite, browser verification, Windows build.
- [ ] Publish the approved batch and verify the release. Claude acknowledgement remains pending.

## Coordination

Read AGENTS.md before work. Update this inventory and docs/AGENT_UPDATES.md at
meaningful milestones. Existing Claude session acknowledgement is pending.
Review current task ownership and local handoff notes before continuing.

## Verification limits

Use isolated data for tests. Do not apply disruptive repairs, change security
settings or modify live game files merely to test the implementation. Record
real game/hardware checks that cannot be completed on this PC explicitly.
