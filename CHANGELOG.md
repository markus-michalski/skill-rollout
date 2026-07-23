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
- `workflows/skill-rollout.js`, `reference/self-improving-skills.md`,
  `reference/prompt-self-improving-skill-playbook.md`: mandate scoped `git add` AND scoped
  `git commit -- <path>` (never `-A`/bare `.`, never a plain `git commit`) plus safe
  push-retry-via-rebase (never `--force`) at every point the rollout commits inside
  `~/projekte/skill-evals` — evals.json, loop-log.md, loop-state.json, STATUS.md,
  batch-digest.md, self-improving-skill-{plugin}.md. Unlike the target plugin's own repo
  (isolated per-batch via `preIsolated`), `skill-evals` is a single repo SHARED across every
  rollout-target plugin with no worktree isolation — running two rollout sessions concurrently
  against different plugins (e.g. mm-skills + storyforge) risked a blind `git add -A` (or even
  a *scoped* add followed by a *plain* `git commit`, which still snapshots the whole shared
  index) sweeping up the other session's uncommitted, unrelated-plugin files. Also distinguishes
  a rebase *refusal* (another session's in-flight uncommitted work sitting in the shared working
  tree — retry, never "clean up" with stash/checkout/reset) from a real content *conflict* (stop,
  flag `needsHumanReview`) — a code-review pass on the first draft found both the scoped-add-only
  approach and the "rebase is always safe here" reasoning were incomplete. New shared
  `skillEvalsGitSafety()` helper keeps the rule consistent across all touch points (Stage A,
  Stage C, Onboard, plus an explicit commit-deferral note on the Select phase's batch-digest.md
  write) rather than risking copy-paste drift (issue #20).

### Security
- Nothing yet

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
