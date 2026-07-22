---
name: setup
description: "First-time setup for skill-rollout. Creates the venv, installs dependencies, copies the config template. Use when: (1) Plugin just installed, (2) MCP server not responding, (3) User says 'setup' or 'einrichten'."
model: claude-sonnet-5
user-invocable: true
---

# Skill Rollout Setup

First-time setup and repair for the skill-rollout plugin: creates the dedicated
venv at `~/.skill-rollout/venv`, installs dependencies, and seeds the config.

## Workflow

**Multi-line Python scripts — write a file, don't inline them.** Several steps
below need multi-line Python. Never pass multi-line content via
`<PY> -c "<script>"` — a `-c` argument containing literal newlines parses
differently across bash, PowerShell, and cmd, and reliably breaks under
PowerShell. Instead, for any script longer than one line: write it to a file
(reuse `~/.skill-rollout/_setup_scratch.py` from Step 2 onward; for Step 1,
before that dir exists, use the OS temp dir — resolve it with the single-line
`<PY> -c "import tempfile; print(tempfile.gettempdir())"`), then run it as
`<PY> <path>` — a plain file-path argument, portable across every shell.

Single-line `<PY> -c "..."` commands are unaffected and can stay as shown.

### Step 0: Detect Platform and Resolve a Working Python Interpreter

Try each of the following in order and use the **first one that actually runs**
(prints a platform string, doesn't error):

```bash
python3 -c "import sys; print(sys.platform)"
python -c "import sys; print(sys.platform)"
py -3 -c "import sys; print(sys.platform)"
```

**Do not stop at the first failure.** On Windows, `python3`/`python` frequently
fail with **exit code 49 and no output** even when Python is installed — this is
the Microsoft Store app-execution-alias stub, not a missing-Python error, common
on Intune/SCCM-managed devices. `py` (the Python Launcher) always lives in
`C:\Windows\`, on `PATH` regardless of how Python was installed — so try it
before concluding Python is missing.

If all three fail, check known install locations as a last resort (Windows,
PowerShell): `$env:ProgramFiles\Python3*\python.exe`,
`${env:ProgramFiles(x86)}\Python3*\python.exe`,
`$env:LocalAppData\Programs\Python\Python3*\python.exe` — first one that exists.

Call whichever succeeded `<PY>` — use it verbatim for every system-level Python
invocation below (Steps 1–3, 5), until the venv exists in Step 3. From Step 4 on
the venv's own interpreter is used instead.

**Windows quoting note:** `python3`/`python`/`py -3` need no special handling, but
a full-path `<PY>` from the fallback may contain spaces (e.g. `C:\Program
Files\Python313\python.exe`) — on Windows invoke via `& "<PY>" -c "..."`, not
bare `<PY>`.

Output `win32` means Windows (venv layout: `venv\Scripts\python.exe`,
`venv\Scripts\pip.exe`); any other output means POSIX (venv layout:
`venv/bin/python3`, `venv/bin/pip`). Use this for every OS choice below.

### Step 1: Check Current State

Multi-line — write-then-run as `<tmp>/skill-rollout-setup-step1.py`, then
`<PY> <tmp>/skill-rollout-setup-step1.py`:

```python
from pathlib import Path
base = Path.home() / '.skill-rollout'
print('data-dir:', 'OK' if base.is_dir() else 'MISSING')
print('venv:', 'OK' if (base / 'venv').is_dir() else 'MISSING')
print('config:', 'OK' if (base / 'config.yaml').is_file() else 'MISSING')
```

### Step 2: Create Data Directory (if missing)

```bash
<PY> -c "from pathlib import Path; Path.home().joinpath('.skill-rollout').mkdir(parents=True, exist_ok=True)"
```

### Step 3: Create Venv (if missing)

Use `<PY>` — the interpreter resolved in Step 0, not a hardcoded `python`/`python3`
(on a managed device where only `py -3` worked, hardcoding `python` re-hits the
Store-alias failure).

- POSIX: `<PY> -m venv ~/.skill-rollout/venv`
- Windows: `<PY> -m venv "$env:USERPROFILE\.skill-rollout\venv"`

### Step 4: Sync Dependencies (always)

Always run — `pip` is idempotent and fast on a warm cache, so new deps in later
releases are never silently skipped.

- POSIX: `~/.skill-rollout/venv/bin/pip install -r ${CLAUDE_PLUGIN_ROOT}/requirements.txt -q`
- Windows: `& "$env:USERPROFILE\.skill-rollout\venv\Scripts\pip.exe" install -r ${CLAUDE_PLUGIN_ROOT}/requirements.txt -q`

### Step 5: Copy Config (if missing)

Single-line, uses `<PY>` (no venv needed):

```bash
<PY> -c "import shutil; from pathlib import Path; cfg = Path.home() / '.skill-rollout' / 'config.yaml'; cfg.parent.mkdir(parents=True, exist_ok=True) or None; (not cfg.exists()) and shutil.copy2(r'${CLAUDE_PLUGIN_ROOT}/config/config.example.yaml', cfg)"
```

Then tell the user the config was copied to `~/.skill-rollout/config.yaml` and
that they should set the two paths for this machine (run `/skill-rollout:configure`
or edit directly):
- `paths.self_improving_docs` — where per-plugin playbooks
  (`self-improving-skill-{plugin}.md`) live
- `paths.skill_evals` — where per-plugin eval state lives (default `~/projekte/skill-evals`)

### Step 6: Verify MCP Server

Multi-line — write-then-run via the **venv's** Python (POSIX:
`~/.skill-rollout/venv/bin/python3 <path>`, Windows:
`& "$env:USERPROFILE\.skill-rollout\venv\Scripts\python.exe" <path>`). Wrap the
`${CLAUDE_PLUGIN_ROOT}` substitution in a raw string — on Windows the interpolated
value contains backslashes and a plain literal can hit an invalid `\U`/`\u`/`\N`
escape `SyntaxError`:

```python
import sys
sys.path.insert(0, r'${CLAUDE_PLUGIN_ROOT}/servers/skill-rollout-server')
sys.path.insert(0, r'${CLAUDE_PLUGIN_ROOT}')
import mcp  # noqa: F401
import yaml  # noqa: F401
from server import mcp as srv  # noqa: F401
print('MCP: OK')
```

### Step 7: Report

```
Setup abgeschlossen:
- Daten-Verzeichnis: OK/ERSTELLT  (~/.skill-rollout)
- Venv:              OK/ERSTELLT  (~/.skill-rollout/venv)
- Dependencies:      SYNCHRONISIERT
- Config:            OK/ERSTELLT  (~/.skill-rollout/config.yaml)
- MCP:               OK

Starte Claude Code neu, damit der MCP Server geladen wird.
```

## Error Handling

- `python3` not found (POSIX) and no other interpreter in Step 0's chain works →
  Python genuinely not installed. Tell the user to install Python 3.11+.
- On Windows, `python`/`python3` exiting with code 49 and no output is **not**
  "Python not found" — it's the Store app-execution-alias stub. Do not tell the
  user to install Python; fall through Step 0's chain (`py -3`, then install paths).
- `pip install` fails → check the network and that `requirements.txt` exists at
  `${CLAUDE_PLUGIN_ROOT}`.
