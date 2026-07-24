# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `reference/eval-schema.md`, `workflows/skill-rollout.js`, `reference/prompt-self-improving-skill-
  playbook.md`: new 🟩 READ-ONLY tier in the STATUS.md Live-column legend, between 🟦 N/A and 🟥
  BLOCKED. The previous BLOCKED default conflated any real MCP domain-tool surface with "needs
  sandbox design", regardless of whether that surface could actually mutate data — confirmed
  concrete case: mm-skills' `socialcraft` (read-only `wikijs`/`mm-dev-toolkit` lookups) was blocked
  alongside `shopware-produkt-wizard` (genuinely creates/updates real shop products). Stage A now
  greps each skill's OWN domain-tool surface against a read-verb allowlist (`get_`/`list_`/
  `search_`/`resolve_`/`read_`) BEFORE the sandbox-design hard gate; verified zero write-verb calls
  (`create_`/`update_`/`delete_`/`write_`/`move_`/`append_`) anywhere bypasses the plugin-level
  sandbox-design requirement entirely and runs Prompt 3 directly against the real system (no reset
  needed — a read cannot mutate shared state). One write-capable call anywhere disqualifies the
  bypass — no partial credit, falls through to the existing BLOCKED gate. Also fixes a pre-existing
  inconsistency found while implementing this: the hard-gate text said to leave a blocked skill's
  Live column at a bare ⬜, but the actually-used convention (confirmed in mm-skills' real
  STATUS.md) is 🟥 BLOCKED, matching eval-schema.md's own legend (issue #24).
- `reference/self-improving-skills.md`, `reference/eval-schema.md`, `reference/prompt-self-improving-
  skill-playbook.md`, `workflows/skill-rollout.js`: new per-plugin MCP Surface Register
  (`{skillEvalsDir}/{plugin}/mcp-surface-register.md`), closing issues #26 and #27. Previously,
  onboarding only made a one-time, binary, plugin-level judgment ("does a safe sandbox strategy exist
  at all?") — it kept no structural inventory of which specific MCP tools are per-entity vs.
  global-singleton, or which fixture states the shared sandbox actually contains, so every skill's
  rollout re-discovered the same gaps from scratch (confirmed duplication: `chapter-writer`'s
  `sandbox.md` independently re-derived almost the same explanation `start-session`'s `sandbox.md`
  already had). The register is now created at onboarding (or lazily, existence-based, for an
  already-onboarded plugin) and consulted/updated by every skill's Stage A run before Prompt 3: (1) a
  fixture-completeness pre-check auto-creates a missing, known enum-permutation fixture state via the
  plugin's own real creation tool, or names a specific gap and blocks only that one case if it can't
  be safely auto-created (issue #27); (2) a singleton-tool decision key — does anything read the
  value after the call, this case's own assertions, a later step, or another skill's future live case
  — classifies each global-singleton MCP write as `no-restore-accepted-drift` (no restore attempted,
  case not downgraded) or `best-effort-snapshot-restore` (the call itself is the system under test);
  a new mandatory Rule 1 requires capturing the prior value before ANY singleton write regardless of
  classification, closing the specific failure mode that left `chapter-writer`'s live case unable to
  restore `update_session()`'s prior value (issue #26). New `↺ no-restore-accepted-drift` Notes-column
  symbol in `eval-schema.md`, distinct from 🟨 NEEDS-HUMAN-REVIEW (this one is an expected, resolved
  outcome, not an open question for a human).
- `README.md`, `skills/run/SKILL.md`: documented that Claude Code's Auto Mode must be ON before
  invoking `/skill-rollout:run` — without it, every routine tool call inside the batch (including
  unattended subagent calls) prompts for individual approval, defeating the point of an unattended
  batch runner. Confirmed real-world gotcha: entering Plan Mode mid-session silently turns Auto Mode
  off, and a batch that previously ran cleanly starts prompting again with no other cause.

### Changed
- Nothing yet

### Deprecated
- Nothing yet

### Removed
- Nothing yet

### Fixed
- `reference/self-improving-skills.md`, `reference/eval-schema.md`, `reference/prompt-self-improving-
  skill-playbook.md`: reconcile the "Beispielprompt für Skill Self-Improvement"'s per-iteration
  `git commit`/`git reset` instruction with Stage A's no-commit boundary (`workflows/skill-rollout.js`,
  from #13). Confirmed hitting production twice independently (`mm-skills/prompt-generator` and
  `storyforge/backfill-style-principles` loop-logs) before this fix, each session re-deriving its
  own workaround. The example prompt now explicitly distinguishes standalone runs (real `git
  commit`/`git reset`, unchanged) from pipeline (Stage A) runs: "keep" leaves the edit applied
  uncommitted (`"commit": null` + explanatory `"note"` in loop-state.json — documented as the
  correct, expected shape, not an anomaly); "discard" restores content captured just before the
  edit (a plain Read/Edit, never a git operation) rather than a git-based revert, which would be
  unsafe once any earlier iteration in the same run was kept (Stage A never commits, so HEAD is
  always the pre-loop baseline — a git-based discard after a keep would silently wipe the kept edit
  too, not just the current iteration's). Not yet observed in production but a real,
  waiting-to-happen bug this fix closes before it manifests. Also adds a "do not lose this to
  paraphrasing" hard requirement to the onboarding meta-prompt template's Prompt 2 section (mirroring
  issue #20's git-safety hard requirement), so a future onboarding can't silently regenerate a
  playbook missing this reconciliation. The two already-onboarded plugins' generated playbooks
  (`~/projekte/skill-evals/{mm-skills,storyforge}/self-improving-skill-*.md`) — the exact two files
  that produced the production workarounds above — are backfilled with the same fix in a companion
  change to the separate `skill-evals` repo, so this closes for real, not just for future
  onboardings (issue #22).

### Security
- Nothing yet

## [1.0.3] - 2026-07-23

### Fixed
- mandate scoped commit + safe push-retry for skill-evals writes (#21)

## [1.0.2] - 2026-07-23

### Fixed
- live-verify PR merge state instead of trusting stale prose (#19)

## [1.0.1] - 2026-07-23

### Added
- restructure per-skill rollout as sibling pipeline stages (#17)

### Fixed
- prohibit subagent-spawn in generated live-tier Prompt 3 (#15) (#16)
- replace unavailable Task/Agent reviewer with manual review criteria (#12) (#14)
- write loop-log.md per iteration during Prompt 2, not only at skill-end (#11)

## [1.0.0] - 2026-07-22

### Added
- migrate generic docs into the plugin (reference/) (#5)
- add setup, configure, status, and help skills (#4)
- add the run skill (batch rollout entry point) (#3)
- bring the batch workflow in-plugin (#2)

### Changed
- add Unreleased comparison link to CHANGELOG
- colocate per-plugin playbook with its eval state (#7)
- add smoke-test suite and CI matrix (#1)
- Initial plugin scaffold

### Fixed
- actually invoke code-reviewer subagent in autonomous mode (#9)
- bind referenceDir/skillEvalsDir for target-repo Onboard agent (#8)
- remove private-doc dependency, make onboarding self-contained (#6)

[1.0.0]: https://github.com/markus-michalski/skill-rollout/releases/tag/v1.0.0
[1.0.1]: https://github.com/markus-michalski/skill-rollout/releases/tag/v1.0.1
[1.0.2]: https://github.com/markus-michalski/skill-rollout/releases/tag/v1.0.2
[1.0.3]: https://github.com/markus-michalski/skill-rollout/releases/tag/v1.0.3
