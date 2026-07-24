# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `reference/prompt-self-improving-skill-playbook.md`, `reference/self-improving-skills.md`: new
  onboarding step 3c — after the create-testdata/reset-testdata/delete-testdata discovery, static,
  and live-verification checks all pass, actually run `create-testdata` for real (not the synthetic
  safety-check call from step 3a) and record what it created in `mcp-surface-register.md`'s Fixture
  Inventory. Closes issue #37: the live verification alone only ever tests the refuse path against a
  synthetic slug, it never provisions anything — without this step, a newly-onboarded plugin's
  sandbox stayed empty, leaving whichever skill got selected first to improvise fixture creation via
  the older, more generic PR #30 fixture-completeness pre-check instead of the canonical
  `create-testdata` path.

### Changed
- Nothing yet

### Deprecated
- Nothing yet

### Removed
- Nothing yet

### Fixed
- Nothing yet

### Security
- Nothing yet

## [1.1.0] - 2026-07-24

### Added
- replace sandbox-conversation gate with testdata skills (#36)
- add shared-mutable-per-entity scope category (#34)
- add per-plugin MCP Surface Register (#26, #27) (#30)
- define fixed PR/commit/issue title convention for target-repo work (#29)
- add 🟩 READ-ONLY tier to bypass sandbox gate for read-only skills (#25)

### Changed
- document Auto Mode requirement for unattended batches (#32)
- track .claude/settings.json permission allowlist (#31)

### Fixed
- reconcile keep/discard mechanics with Stage A's no-commit boundary (#23)

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
[1.1.0]: https://github.com/markus-michalski/skill-rollout/releases/tag/v1.1.0
