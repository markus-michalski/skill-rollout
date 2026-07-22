"""Smoke: MCP server loads and registers all read-only tools."""

import asyncio
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP_JSON = ROOT / ".mcp.json"
SERVER_NAME = "skill-rollout-mcp"

EXPECTED_TOOLS = {
    "tool_resolve_config",
    "tool_list_evals",
    "tool_get_batch_status",
    "tool_get_eval_state",
}


def test_mcp_json_is_valid_json():
    json.loads(MCP_JSON.read_text(encoding="utf-8"))


def test_mcp_json_schema():
    """A dropped/typo'd field here silently breaks the MCP server for every user."""
    config = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    server = config["mcpServers"][SERVER_NAME]
    assert server["type"] == "stdio"
    assert isinstance(server["args"], list) and len(server["args"]) == 1
    assert server["args"][0].endswith("servers/skill-rollout-server/run.py")
    assert "CLAUDE_PLUGIN_ROOT" in server["env"]


def test_server_imports_and_names_itself():
    import server

    assert server.mcp.name == SERVER_NAME


def test_registered_tools_match_expected_exactly():
    """Exact-set, not subset: a new tool must be added to EXPECTED_TOOLS
    deliberately — that forces a contributor to also confirm it is read-only
    (see test_all_tools_are_marked_read_only), instead of silently appearing."""
    import server

    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS, (
        f"registered tools {sorted(names)} != expected {sorted(EXPECTED_TOOLS)}"
    )


def test_all_tools_are_marked_read_only():
    """EVERY registered tool must be read-only — this server is a read-only
    surface. Iterates all tools (not just the known ones) so a future write tool
    cannot sneak in past the annotation guard."""
    import server

    tools = asyncio.run(server.mcp.list_tools())
    assert tools, "server registered no tools"
    for t in tools:
        ann = t.annotations
        assert ann is not None, f"{t.name}: missing annotations"
        assert ann.readOnlyHint is True, f"{t.name}: not marked readOnlyHint"
