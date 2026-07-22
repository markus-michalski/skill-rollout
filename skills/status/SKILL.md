---
name: status
description: |
  Show rollout progress for a plugin — the running batch digest plus per-skill
  eval status. Use when: (1) User says "skill rollout status", "wie weit ist der
  Batch", "was ist bisher passiert", "batch status {plugin}", (2)
  `/skill-rollout:status {plugin}`, (3) checking on a long batch mid-run without
  waiting for its completion notification.
model: claude-sonnet-5
user-invocable: true
argument-hint: "{plugin}"
---

# Skill Rollout — status

Read-only progress view for a plugin's rollout. The whole point is that nobody
has to wait for a batch to finish or dig through individual `loop-log.md` files
to see how far it has gotten.

## Workflow

### 1. Resolve the plugin

`{plugin}` is a slug (lowercase letters/digits/hyphens). If not given, ask — or,
if a batch was launched earlier in this session, default to that plugin.

### 2. Read the state (MCP, read-only)

- **`tool_list_evals(plugin)`** — per-skill status parsed from
  `{skillEvalsDir}/{plugin}/STATUS.md`: each skill's simulated/live cells, notes,
  and a derived `fullyDone` flag, plus `counts` (total / fullyDone / notDone). If
  `exists` is `false`, the plugin was never onboarded — say so and stop.
- **`tool_get_batch_status(plugin)`** — the running `batch-digest.md` verbatim
  (each skill appends its result as it finishes). If `exists` is `false`, no batch
  has run yet.

Optionally, for a specific in-flight skill, **`tool_get_eval_state(plugin, skill)`**
returns its `loop-state.json` + the tail of `loop-log.md`.

### 3. Present

Summarize concisely:
- **Overall:** `X/Y skills fully done` (from `counts`).
- **Per skill:** a compact table — name, simulated, live, and a one-line note.
  Surface any `NEEDS-HUMAN-REVIEW` (🟨) prominently — those are the things a human
  actually has to act on.
- **This batch:** the tail of the batch digest (most recent entries first) so the
  user sees what the currently-running or last batch did.

Do not modify anything — this skill is strictly read-only.

## MCP-Tools

- `tool_list_evals(plugin)` — per-skill status from STATUS.md
- `tool_get_batch_status(plugin)` — the running batch-digest.md
- `tool_get_eval_state(plugin, skill)` — one skill's loop-state + log tail
