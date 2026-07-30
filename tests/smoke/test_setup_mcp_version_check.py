"""Smoke: `setup`'s Step 6 must actually verify the installed mcp SDK version,
not just that `import mcp` succeeds (issue #59).

A bare `import mcp` succeeds against ANY installed version, including a stale
1.x venv that Step 4's dependency sync failed to upgrade (offline, cached
index, a swallowed pip error). On such a venv, Step 6 used to report
"MCP: OK" while the actual MCP server (run.py) would fail to start with a
raw ModuleNotFoundError traceback — silent success masking a broken install.

Regression guard for skills/setup/SKILL.md Step 6.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETUP_SKILL = ROOT / "skills" / "setup" / "SKILL.md"


def _step6_source():
    src = SETUP_SKILL.read_text(encoding="utf-8")
    start = src.find("### Step 6:")
    end = src.find("### Step 7:", start)
    assert start != -1, "expected to find '### Step 6:' in skills/setup/SKILL.md"
    assert end != -1 and end > start, (
        "expected to find '### Step 7:' after Step 6 in skills/setup/SKILL.md"
    )
    return src[start:end]


def test_step6_checks_the_installed_mcp_version_explicitly():
    text = _step6_source()
    assert 'version("mcp")' in text, (
        "expected Step 6 to explicitly read the installed mcp version via "
        "importlib.metadata.version(\"mcp\"), not just `import mcp`"
    )


def test_step6_rejects_a_pre_2x_mcp_install():
    text = _step6_source()
    assert 'startswith("2.")' in text, (
        "expected Step 6 to explicitly gate on the mcp major version "
        "starting with '2.', matching this repo's mcp>=2.0.0,<3.0.0 pin"
    )


def test_step6_version_check_runs_before_importing_server():
    """The version check must gate the `from server import mcp as srv` import
    — checking after would already have hit the raw traceback it's meant to
    prevent."""
    text = _step6_source()
    version_check_pos = text.find('version("mcp")')
    server_import_pos = text.find("from server import mcp as srv")
    assert version_check_pos != -1 and server_import_pos != -1
    assert version_check_pos < server_import_pos, (
        "expected the mcp version check to run BEFORE importing `server`, "
        "not after"
    )


def test_step6_stale_message_is_actionable():
    text = _step6_source()
    assert "MCP: STALE" in text, (
        "expected an explicit STALE status distinct from the OK status, so "
        "a stale venv can't be silently reported as MCP: OK"
    )
