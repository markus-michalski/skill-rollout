# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- high-level `log()` heartbeats at phase transitions during autonomous batch runs (onboarding start/end, per-skill eval/review/commit stages) so an operator can tell "still running" from "silently stopped" (#39)

### Changed
- Nothing yet

### Deprecated
- Nothing yet

### Removed
- Nothing yet

### Fixed
- write the `## Batch started` batch-digest.md header on a plugin's first-ever onboarding run too, not only when STATUS.md already exists — previously batch-digest.md didn't exist at all until the first selected skill finished, leaving a first onboarding run indistinguishable from a silent stall (#40)

### Security
- Nothing yet

## [1.1.1] - 2026-07-24

### Added
- provision sandbox for real after guard verification (#37) (#38)

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
[1.1.1]: https://github.com/markus-michalski/skill-rollout/releases/tag/v1.1.1
