"""Smoke: MCP server loads and registers all read-only tools."""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[2]
MCP_JSON = ROOT / ".mcp.json"
RUN_PY = ROOT / "servers" / "skill-rollout-server" / "run.py"
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
        assert ann.read_only_hint is True, f"{t.name}: not marked read_only_hint"


def test_all_tools_have_output_schema():
    """Guards the mcp 2.x gotcha for EVERY tool: a bare `dict` return
    annotation leaves output_schema (and structured_content at call time)
    unset. Checked here on the full registered set, not just one tool —
    see test_call_tool_populates_structured_content for the end-to-end proof
    on one tool via an actual call."""
    import server

    tools = asyncio.run(server.mcp.list_tools())
    for t in tools:
        assert t.output_schema is not None, (
            f"{t.name}: bare `dict` return annotation, use `dict[str, Any]`"
        )


def test_call_tool_populates_structured_content():
    """End-to-end proof on one tool that a real call populates
    structured_content (set-wide coverage lives in
    test_all_tools_have_output_schema)."""
    import server

    async def _call():
        async with Client(server.mcp) as client:
            return await client.call_tool("tool_resolve_config", {})

    result = asyncio.run(_call())
    assert not result.is_error
    assert result.structured_content is not None
    assert "skillEvalsDir" in result.structured_content


def test_registered_tools_have_distinct_annotation_instances():
    """Regression guard for the `_read_only()` factory: ToolAnnotations is
    mutable, so a future "simplification" that hoists it to a shared module
    constant reused across all @mcp.tool(annotations=...) calls would
    silently reintroduce cross-tool mutation coupling. Every tool must get
    its own instance."""
    import server

    tools = asyncio.run(server.mcp.list_tools())
    ids = {id(t.annotations) for t in tools}
    assert len(ids) == len(tools), (
        "expected every tool to have a distinct ToolAnnotations instance, "
        "not a shared one"
    )


def test_stale_venv_message_fires_for_mcp_related_import_names():
    """Unit-level guard for run.py's except-branch: the subprocess handshake
    test below only exercises the try-branch (this venv's mcp install works),
    so the stale-venv message logic itself needs direct coverage."""
    import run

    assert run.stale_venv_message("mcp") is not None
    assert run.stale_venv_message("mcp.server.mcpserver") is not None
    assert run.stale_venv_message("mcp_types") is not None


def test_stale_venv_message_is_none_for_unrelated_import_names():
    """An unrelated missing import (e.g. tools/yaml) must re-raise rather than
    being misreported as a stale mcp venv."""
    import run

    assert run.stale_venv_message("yaml") is None
    assert run.stale_venv_message("tools.shared.config") is None
    assert run.stale_venv_message(None) is None


def test_run_py_handshake_over_real_stdio_subprocess():
    """The in-process tests above never execute run.py's own sys.path bootstrap
    or its mcp.run(transport="stdio") call — this is the actual entry point
    Claude Code launches. Spawn it for real and drive one full MCP handshake +
    tool call over stdio."""

    async def _handshake():
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(RUN_PY)],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert names == EXPECTED_TOOLS

                result = await session.call_tool("tool_resolve_config", {})
                assert not result.is_error
                assert result.structured_content is not None
                assert "skillEvalsDir" in result.structured_content

    asyncio.run(_handshake())
