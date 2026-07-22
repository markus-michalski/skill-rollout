---
name: help
description: |
  Show the available skill-rollout skills and how to use them. Use when: (1) User
  says "skill-rollout help", "welche skill-rollout Skills gibt es", "was kann das
  Plugin", (2) `/skill-rollout:help`.
model: claude-haiku-4-5-20251001
user-invocable: true
---

# Skill Rollout — help

Show what this plugin does and how to drive it. Print the overview below (adapt
wording to the user's language).

## What it does

Runs the self-improvement rollout (Prompt 1/2/3 from the self_improving_skill
playbook) over the skills of a target Claude plugin — unattended, sequentially,
one batch at a time, never auto-chaining into the next batch. The batch workflow
ships inside this plugin; per-plugin eval state and design docs are resolved via
config.

## Skills

| Skill | What it does |
|-------|--------------|
| `/skill-rollout:run {plugin} {count} [max_duration]` | Launch a batch: process N skills of `{plugin}` one at a time, stopping after `count` skills or `max_duration`. Creates an isolated worktree, runs the in-plugin workflow, then reports — and stops (never starts a second batch). |
| `/skill-rollout:status {plugin}` | Read-only progress: the running batch digest + per-skill eval status (fully-done counts, NEEDS-HUMAN-REVIEW flags). |
| `/skill-rollout:configure` | Set the machine-specific `skill_evals` path in `~/.skill-rollout/config.yaml`. |
| `/skill-rollout:setup` | First-time setup: create the venv, install dependencies, seed the config. Run once after install, or to repair a non-responding MCP server. |
| `/skill-rollout:help` | This overview. |

## Typical flow

1. `/skill-rollout:setup` (once) → then restart Claude Code so the MCP server loads.
2. `/skill-rollout:configure` → point `skill_evals` at this machine (if the default doesn't fit).
3. `/skill-rollout:run {plugin} 3` → run a small daytime batch.
4. `/skill-rollout:status {plugin}` → check progress mid-run.
5. Review + merge the PRs the batch opened, then invoke `run` again for the next batch.

## MCP tools (read-only)

`tool_resolve_config`, `tool_list_evals`, `tool_get_batch_status`,
`tool_get_eval_state` — used by the skills above; not something the user calls
directly.
