# skill-rollout

A Claude Code plugin that runs the **self-improvement skill-rollout** process
over the skills of any target Claude plugin — unattended, sequentially, one batch
at a time, with no auto-chaining into the next batch.

Born out of a manual rollout process (StoryForge, then mm-skills) and generalized
into a proper plugin: the workflow script now ships inside the plugin (no manual
copy into `~/.claude/workflows/`), paths resolve through a single config, and the
per-plugin eval state is queryable over MCP.

## What It Does

- **Batch runner** — processes N skills of a target plugin one at a time, each
  through the self-improvement loop (Prompt 1/2/3), fully autonomously within one
  batch. Stops after `count` skills or `max_duration`, whichever comes first.
- **Isolated** — the launcher creates one dedicated git worktree up front and
  hands it to the workflow, so unattended runs never collide with a concurrent
  session in the same repo.
- **Never auto-chains** — one batch, then stop. The operator reviews and merges
  the resulting PRs before the next batch is manually invoked.
- **Queryable state** — an MCP server exposes config resolution and the running
  batch digest / per-skill loop state, so progress is visible mid-run.

## Status

Functionally complete and in active use (tested end-to-end against a real target plugin).

1. ✅ Plugin scaffold (manifest, MCP shell, config, parsers, launch wrapper)
2. ✅ Smoke tests (`tests/smoke/`), CI on ubuntu-latest + windows-latest
3. ✅ MCP server — four read-only tools (`tool_resolve_config`, `tool_list_evals`,
   `tool_get_batch_status`, `tool_get_eval_state`)
4. ✅ `workflows/skill-rollout.js` — ships in-plugin, launched via its own
   `workflowScriptPath`, no manual deploy copy
5. ✅ Skills — `run`, `status`, `setup`, `configure`, `help`
6. ✅ Generic docs migrated into `reference/` (eval schema, onboarding meta-prompt,
   methodology overview) — the only thing that stays external per-machine is
   `skill_evals` (per-plugin state + generated playbooks)
7. ⬜ Governance (PolyForm NC + CLA + branch protection) — the one remaining step

## MCP Tools

| Tool | Purpose |
|------|---------|
| `tool_resolve_config` | Resolve machine-specific paths (eval state, in-plugin docs, workflow script) |
| `tool_list_evals` | Per-skill eval status from a plugin's `STATUS.md` |
| `tool_get_batch_status` | The running `batch-digest.md` for a plugin |
| `tool_get_eval_state` | `loop-state.json` + `loop-log.md` tail for one skill |

## Configuration

Copy `config/config.example.yaml` to `~/.skill-rollout/config.yaml` and adjust
the paths. If the file is absent, `resolve_config()` falls back to documented
defaults.

## License

PolyForm Noncommercial 1.0.0.
