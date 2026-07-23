# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nothing yet

### Changed
- `workflows/skill-rollout.js`: restructure the per-skill rollout from one monolithic `agent()` call
  into three sibling pipeline stages — Stage A (eval + edit, stages changes but does not commit),
  Stage B (independent `git-pr-workflows:code-reviewer` review of the staged diff via the Workflow
  tool's `agentType` option), Stage C (applies non-security findings, commits, pushes, opens the PR,
  and does the loop-log/STATUS.md/batch-digest bookkeeping). Supersedes the manual self-review
  procedure introduced by the issue #12 fix above with a real independent reviewer, now that the
  review runs as a top-level sibling `agent()` call instead of a nested spawn from inside another
  agent (issue #13). Stage C always runs, even when Stage A stopped early or made no changes, so the
  bookkeeping write is never silently skipped; only Stage B is conditional on there being a diff to
  review.

### Deprecated
- Nothing yet

### Removed
- Nothing yet

### Fixed
- `workflows/skill-rollout.js`: remove broken "Use Task/Agent tool to spawn code-reviewer subagent" instruction — the Task/Agent tool is unavailable from within a workflow `agent()` call (same harness constraint as `EnterWorktree`). Replace with a rigorous manual self-review procedure covering logic/correctness, SKILL.md structural compliance, eval design quality, data hygiene, and cross-file consistency; limitation recorded per-skill in `needsHumanReview` as `issue #12`. JS-level comment added documenting the constraint and the correct Option 2 path if harness ever lifts it.
- `reference/prompt-self-improving-skill-playbook.md`: prohibit generating a Prompt 3 (live-MCP tier) that instructs spawning a subagent for MCP tool execution — the Task/Agent tool is unavailable inside the skill-rollout Workflow's per-skill agent context (same constraint as `EnterWorktree`), confirmed via repeated silent substitution in real rollout runs (issue #15). New guidance mandates direct MCP tool execution with a TOOL CALL LOG and independent post-write verification instead.

### Security
- Nothing yet

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
