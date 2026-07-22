"""skill-rollout MCP Server.

Read-only surface over the skill-rollout process: resolves machine-specific
paths from ~/.skill-rollout/config.yaml and exposes the per-plugin eval state
(STATUS.md, batch-digest.md, loop-state/loop-log) so skills don't have to
re-derive paths or hand-parse markdown.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from tools.shared.config import resolve_config
from tools.state.parsers import get_batch_status, get_eval_state, list_evals

mcp = FastMCP("skill-rollout-mcp")


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
def tool_resolve_config() -> dict:
    """Resolve machine-specific paths for a rollout run.

    Returns docsBase, skillEvalsDir, workflowScriptPath (the workflow.js shipped
    inside this plugin), pluginRoot, and config-file metadata. All paths are
    absolute, forward-slash form — ready to hand to the Workflow tool and the
    file tools on both Windows and POSIX.
    """
    return resolve_config()


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
def tool_list_evals(plugin: str) -> dict:
    """List the eval status of every skill for a plugin.

    Parses {skillEvalsDir}/{plugin}/STATUS.md. Returns one row per skill with
    its simulated/live cells, notes, and a derived fullyDone flag (simulated ✅
    AND live ✅-or-N/A). Returns exists=false if the plugin was never onboarded.

    Args:
        plugin: Plugin slug (lowercase letters/digits/hyphens).
    """
    return list_evals(plugin)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
def tool_get_batch_status(plugin: str) -> dict:
    """Return the running batch digest for a plugin.

    Reads {skillEvalsDir}/{plugin}/batch-digest.md verbatim — the file each
    skill appends to as it finishes, so a human checking on a long batch mid-run
    sees progress without waiting for the whole batch.

    Args:
        plugin: Plugin slug (lowercase letters/digits/hyphens).
    """
    return get_batch_status(plugin)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
def tool_get_eval_state(plugin: str, skill: str) -> dict:
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
