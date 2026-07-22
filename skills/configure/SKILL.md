---
name: configure
description: |
  Interactive configuration for skill-rollout — set the eval-state path in
  ~/.skill-rollout/config.yaml. Use when: (1) User says "skill-rollout configure",
  "konfigurieren", "Pfad anpassen", (2) resolve_config reports configExists=false
  and the default doesn't match this machine.
model: claude-sonnet-5
user-invocable: true
---

# Configure

Interactive editor for `~/.skill-rollout/config.yaml` — the one machine-specific
path the rollout needs.

## Workflow

### 1. Read Current Config

Call the MCP tool `tool_resolve_config` to show what is currently in effect
(`skillEvalsDir`, `configExists`). If `configExists` is `false`, no config file
exists yet and the neutral default is being used — say so.

### 2. Ask What to Change

Use AskUserQuestion for the one path:
- **skill_evals** — where per-plugin rollout state lives (default `~/projekte/skill-evals`).
  Everything for one target plugin lives at `{skill_evals}/{plugin}/`: `STATUS.md`,
  `batch-digest.md`, the per-plugin playbook (`self-improving-skill-{plugin}.md`), and
  per-skill `loop-log.md`/`loop-state.json`/`evals.json`. The generic docs (schema,
  onboarding meta-prompt) ship inside this plugin, not here.

Accepts an absolute path or `~`. No trailing slash.

### 3. Apply Changes

Detect the platform first (see `skills/setup/SKILL.md` Step 0 for the `<PY>`
resolution). Write the config with the write-then-run pattern — save a short
Python script to `~/.skill-rollout/_configure_scratch.py` with the new value
substituted directly into the file, then run it via the venv's Python (POSIX:
`~/.skill-rollout/venv/bin/python3 <path>`, Windows:
`& "$env:USERPROFILE\.skill-rollout\venv\Scripts\python.exe" <path>`). Never pass
multi-line content via `-c "<script>"` — it breaks under PowerShell.

The script should write valid YAML to `~/.skill-rollout/config.yaml`:

```yaml
paths:
  skill_evals: "<value>"
```

Use `open(..., encoding="utf-8")` when writing (paths may contain non-ASCII, e.g.
"Meine Bibliotheken") so Windows doesn't fall back to cp1252.

### 4. Confirm

Call `tool_resolve_config` again and show the resolved paths so the user sees the
change took effect. Point out that a running MCP server already picked up the new
config on its next tool call (no restart needed for a pure config edit).

## First-Time Setup

If `~/.skill-rollout/config.yaml` doesn't exist yet, copy it from
`${CLAUDE_PLUGIN_ROOT}/config/config.example.yaml` first (or run
`/skill-rollout:setup`), then walk through steps 2–4.

## MCP-Tools

- `tool_resolve_config` — read the currently-resolved paths (before + after).
