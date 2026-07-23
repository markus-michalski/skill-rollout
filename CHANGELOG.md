# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nothing yet

### Changed
- `skills/status/SKILL.md`: live-verify PR merge state via `gh pr view` before presenting a status
  summary, instead of trusting STATUS.md/batch-digest.md's free-form prose (written once when a
  skill's rollout stage finished, never revisited afterward). Confirmed in production against
  storyforge (9 batch-digest PRs of unknown actual state) and mm-skills (several PRs reported open
  that were long since merged). Presentation-time correction only — the skill's pre-existing
  "strictly read-only" contract is unchanged, nothing is written back to either file. Explicitly
  out of scope: NEEDS-HUMAN-REVIEW notes describing a structural harness limitation that a later
  plugin version has since fixed — not GitHub-API-verifiable, left as an accurate historical record
  (issue #18).

### Deprecated
- Nothing yet

### Removed
- Nothing yet

### Fixed
- Nothing yet

### Security
- Nothing yet

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
