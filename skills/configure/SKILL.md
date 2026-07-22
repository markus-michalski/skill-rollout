---
name: configure
description: |
  Interactive configuration for skill-rollout — set the docs and eval-state paths
  in ~/.skill-rollout/config.yaml. Use when: (1) User says "skill-rollout configure",
  "konfigurieren", "Pfade anpassen", (2) resolve_config reports configExists=false
  and the defaults don't match this machine.
model: claude-sonnet-5
user-invocable: true
---

# Configure

Interactive editor for `~/.skill-rollout/config.yaml` — the two machine-specific
paths the rollout needs.

## Workflow

### 1. Read Current Config

Call the MCP tool `tool_resolve_config` to show what is currently in effect
(`docsBase`, `skillEvalsDir`, `configExists`). If `configExists` is `false`, no
config file exists yet and the neutral defaults are being used — say so.

### 2. Ask What to Change

Use AskUserQuestion for the two paths:
- **self_improving_docs** — where per-plugin playbooks (`self-improving-skill-{plugin}.md`,
  one per target plugin rolled out) live on this machine. The generic docs (schema,
  onboarding meta-prompt) ship inside this plugin, not here.
- **skill_evals** — where per-plugin eval state (`STATUS.md`, `loop-log.md`,
  `batch-digest.md`) lives (default `~/projekte/skill-evals`).

Both accept absolute paths or `~`. No trailing slash.

### 3. Apply Changes

Detect the platform first (see `skills/setup/SKILL.md` Step 0 for the `<PY>`
resolution). Write the config with the write-then-run pattern — save a short
Python script to `~/.skill-rollout/_configure_scratch.py` with the new values
substituted directly into the file, then run it via the venv's Python (POSIX:
`~/.skill-rollout/venv/bin/python3 <path>`, Windows:
`& "$env:USERPROFILE\.skill-rollout\venv\Scripts\python.exe" <path>`). Never pass
multi-line content via `-c "<script>"` — it breaks under PowerShell.

The script should write valid YAML to `~/.skill-rollout/config.yaml`:

```yaml
paths:
  self_improving_docs: "<value>"
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
