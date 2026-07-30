"""skill-rollout MCP Server.

Read-only surface over the skill-rollout process: resolves machine-specific
paths from ~/.skill-rollout/config.yaml and exposes the per-plugin eval state
(STATUS.md, batch-digest.md, loop-state/loop-log) so skills don't have to
re-derive paths or hand-parse markdown.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from tools.shared.config import resolve_config
from tools.state.parsers import get_batch_status, get_eval_state, list_evals

mcp = MCPServer("skill-rollout-mcp")


def _read_only() -> ToolAnnotations:
    """Fresh ToolAnnotations per tool — instances are mutable, so tools must
    not share one, even though every tool here happens to be read-only."""
    return ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )


@mcp.tool(annotations=_read_only())
def tool_resolve_config() -> dict[str, Any]:
    """Resolve machine-specific paths for a rollout run.

    Returns skillEvalsDir, workflowScriptPath (the workflow.js shipped inside
    this plugin), referenceDir, pluginRoot, and config-file metadata. All paths
    are absolute, forward-slash form — ready to hand to the Workflow tool and
    the file tools on both Windows and POSIX.
    """
    return resolve_config()


@mcp.tool(annotations=_read_only())
def tool_list_evals(plugin: str) -> dict[str, Any]:
    """List the eval status of every skill for a plugin.

    Parses {skillEvalsDir}/{plugin}/STATUS.md. Returns one row per skill with
    its simulated/live cells, notes, and a derived fullyDone flag (simulated ✅
    AND live ✅-or-N/A). Returns exists=false if the plugin was never onboarded.

    Args:
        plugin: Plugin slug (lowercase letters/digits/hyphens).
    """
    return list_evals(plugin)


@mcp.tool(annotations=_read_only())
def tool_get_batch_status(plugin: str) -> dict[str, Any]:
    """Return the running batch digest for a plugin.

    Reads {skillEvalsDir}/{plugin}/batch-digest.md verbatim — the file each
    skill appends to as it finishes, so a human checking on a long batch mid-run
    sees progress without waiting for the whole batch.

    Args:
        plugin: Plugin slug (lowercase letters/digits/hyphens).
    """
    return get_batch_status(plugin)


@mcp.tool(annotations=_read_only())
def tool_get_eval_state(plugin: str, skill: str) -> dict[str, Any]:
    """Return the per-skill loop state for resuming a rollout.

    Reads loop-state.json (parsed) and the tail of loop-log.md for one skill, so
    a rerun continues from where a prior run left off instead of redoing work.

    Args:
        plugin: Plugin slug (lowercase letters/digits/hyphens).
        skill: Skill name (its directory under the plugin's skills).
    """
    return get_eval_state(plugin, skill)


if __name__ == "__main__":
    mcp.run(transport="stdio")
