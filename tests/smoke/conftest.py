"""Shared path setup for smoke tests.

Puts the plugin root (for `tools`) and the MCP server dir (for `server`) on
sys.path so the tests can import them the same way run.py does at launch.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER_DIR = ROOT / "servers" / "skill-rollout-server"

for p in (ROOT, SERVER_DIR):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)
