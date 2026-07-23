# skill-rollout — Plugin Guide

Unattended, sequential, single-batch runner for the self-improvement skill-rollout
process across any Claude plugin. This file is the routing table + the invariants
a contributor must not break.

## Routing Table

| User Intent | Skill |
|-------------|-------|
| "skill rollout", "run the rollout", "starte einen Batch für {plugin}", "lass N Skills laufen" | `/skill-rollout:run {plugin} {count} [max_duration]` |
| "was ist im Batch passiert", "batch status", "wie weit ist der rollout" | `/skill-rollout:status {plugin}` |
| Plugin just installed / MCP server not responding | `/skill-rollout:setup` |
| "skill-rollout konfigurieren", change paths | `/skill-rollout:configure` |
| "welche skill-rollout Skills gibt es", help | `/skill-rollout:help` |

## Architecture

- **Skills = logic, MCP = data.** Skills orchestrate; the MCP server only reads
  config and eval state. No skill hand-parses `STATUS.md` — it calls
  `tool_list_evals`. No skill hardcodes a docs/evals path — it calls
  `tool_resolve_config`.
- **The Workflow script ships in the plugin.** `workflows/skill-rollout.js` is
  referenced by `run`'s SKILL.md via the `workflowScriptPath` that
  `resolve_config()` returns (`${pluginRoot}/workflows/skill-rollout.js`). There
  is no copy into `~/.claude/workflows/` anymore.
- **Config lives outside the plugin** at `~/.skill-rollout/config.yaml`, so it
  survives plugin updates. Template ships as `config/config.example.yaml`.
- **Per-plugin eval state lives outside the plugin** at `{skillEvalsDir}/{plugin}/`
  (default `~/projekte/skill-evals/{plugin}/`). It is user data, never plugin
  content.

## Hard Invariants

- **One batch, no auto-chaining.** `run` never launches a second `Workflow` call
  in the same invocation. The operator merges PRs, then manually starts the next
  batch.
- **Never self-approve or self-merge a PR.** Every PR the rollout opens is left
  open for human review, regardless of how autonomous everything upstream was.
- **Launcher owns isolation.** The `run` skill (top-level) creates the dedicated
  git worktree and passes `preIsolated: true`; the workflow's subagents work
  directly in it and must NOT call `EnterWorktree` (refused in that context).
- **`workflows/skill-rollout.js` must be LF.** The Workflow tool rejects a script
  with CR/control characters. Enforced by `.gitattributes`.
- **Windows compatibility is a from-scratch requirement.** OS-agnostic
  `bin/run-server` wrapper, `encoding="utf-8"` on every file I/O, `py -3`
  interpreter fallback in skills. This plugin's own `bin/run-server(.cmd)`,
  `.gitattributes`, and `tests/smoke/test_cross_platform.py` are the reference
  implementation of the pattern — copy from here for a new plugin, not the
  other way around.
- **No manual version bump.** Leave `version` in `plugin.json` + the CHANGELOG
  header to the release process; edit `[Unreleased]` only.
- **Per-skill review expects `git-pr-workflows` enabled (soft dependency).** The
  Rollout phase's review stage spawns an independent reviewer via
  `agentType: 'git-pr-workflows:code-reviewer'` on a top-level `agent()` call in
  `workflows/skill-rollout.js`. If that plugin is disabled/unavailable and the
  call throws, the pipeline degrades gracefully to an in-prompt manual
  self-review before committing (see `commitPrompt`'s `reviewFailed` branch) —
  it never silently commits an unreviewed diff. Still, enable `git-pr-workflows`
  for full review quality on a rollout batch.

## Layout

```
.claude-plugin/plugin.json          # manifest (only file that belongs here)
.mcp.json                           # MCP server registration
bin/run-server(.cmd)                # OS-agnostic launch wrapper
config/config.example.yaml          # config template
skills/{run,status,setup,configure,help}/SKILL.md
servers/skill-rollout-server/       # FastMCP stdio server
tools/shared/config.py              # resolve_config()
tools/state/parsers.py              # STATUS.md / batch-digest / loop-state readers
workflows/skill-rollout.js          # the batch workflow (ships in-plugin)
reference/                          # design doc + eval schema
tests/smoke/                        # loadability + cross-platform regression guards
```
