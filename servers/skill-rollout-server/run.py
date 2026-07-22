#!/usr/bin/env python3
"""Entry point for the skill-rollout MCP server (stdio transport)."""

import sys
from pathlib import Path

# Add plugin root to path so tools/ can be imported.
plugin_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(plugin_root))

from server import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run(transport="stdio")
