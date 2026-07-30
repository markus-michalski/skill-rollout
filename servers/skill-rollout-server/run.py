#!/usr/bin/env python3
"""Entry point for the skill-rollout MCP server (stdio transport)."""

from __future__ import annotations

import sys
from pathlib import Path

# Add plugin root to path so tools/ can be imported.
plugin_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(plugin_root))


def stale_venv_message(module_name: str | None) -> str | None:
    """Return the actionable stale-venv message for a failed mcp-related
    import, or None if the import failure is unrelated to mcp.

    Covers both a fully-missing module (ModuleNotFoundError, pre-2.x venv
    doesn't have mcp.server.mcpserver at all) and a renamed symbol in an
    existing module (plain ImportError, e.g. an old mcp.types import)."""
    if module_name and module_name.startswith("mcp"):
        return (
            "skill-rollout: the venv at ~/.skill-rollout/venv has an incompatible "
            "mcp SDK (needs >=2.0.0,<3.0.0). Run /skill-rollout:setup to sync it."
        )
    return None


try:
    from server import mcp  # noqa: E402
except ImportError as exc:
    message = stale_venv_message(exc.name)
    if message is not None:
        sys.exit(message)
    raise

if __name__ == "__main__":
    mcp.run(transport="stdio")
