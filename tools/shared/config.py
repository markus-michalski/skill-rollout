"""Configuration + path resolution for skill-rollout.

The single source of truth for machine-specific paths. Everything else (skills,
parsers) resolves paths through here so there is exactly one place that knows
where the docs and eval state live on this machine.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

CONFIG_ROOT = Path.home() / ".skill-rollout"
CONFIG_FILE = CONFIG_ROOT / "config.yaml"

# Fallbacks used when no config.yaml exists (Markus' main-PC paths). Documented
# in config/config.example.yaml — copy it to CONFIG_FILE to override per machine.
DEFAULT_DOCS_BASE = (
    "~/SeaDrive/Meine Bibliotheken/002-Development/Claude_Code/docs/self_improving_skill"  # noqa: E501
)
DEFAULT_SKILL_EVALS = "~/projekte/skill-evals"


def get_plugin_root() -> Path:
    """Return the plugin root directory (parent of tools/)."""
    return Path(__file__).parent.parent.parent


def _abs_posix(path_str: str) -> str:
    """Expand ~ and return an absolute, forward-slash path.

    Forward-slash absolute form works in both Git Bash (where a literal backslash
    is an escape char) and the file tools (which don't expand ~), so this is the
    shape the Workflow tool and every downstream agent should receive.
    """
    return Path(os.path.expanduser(path_str)).as_posix()


def load_config() -> dict[str, Any]:
    """Load user config from ~/.skill-rollout/config.yaml.

    Tolerant by contract: a missing or malformed config falls back to an empty
    dict (→ documented defaults in resolve_config) rather than throwing and
    taking down every downstream tool.
    """
    if not CONFIG_FILE.exists():
        return {}
    try:
        with CONFIG_FILE.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return {}
    return data or {}


def resolve_config() -> dict[str, str]:
    """Resolve all machine-specific paths for a rollout run.

    Returns absolute, forward-slash paths ready to hand to the Workflow tool and
    the file tools. workflowScriptPath points at the workflow.js shipped inside
    this plugin — no separate deploy/copy step.
    """
    cfg = load_config()
    paths = cfg.get("paths", {}) if isinstance(cfg, dict) else {}

    docs_base = paths.get("self_improving_docs") or DEFAULT_DOCS_BASE
    skill_evals = paths.get("skill_evals") or DEFAULT_SKILL_EVALS

    plugin_root = get_plugin_root()
    workflow_script = plugin_root / "workflows" / "skill-rollout.js"

    return {
        "docsBase": _abs_posix(docs_base),
        "skillEvalsDir": _abs_posix(skill_evals),
        "workflowScriptPath": workflow_script.as_posix(),
        "pluginRoot": plugin_root.as_posix(),
        "configFile": CONFIG_FILE.as_posix(),
        "configExists": "true" if CONFIG_FILE.exists() else "false",
    }
