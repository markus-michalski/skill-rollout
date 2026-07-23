# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nothing yet

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
