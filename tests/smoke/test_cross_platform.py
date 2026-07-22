"""Smoke: Windows/POSIX compatibility — regression guard for the whole class of
Windows bugs (launch wrapper, LF pinning, missing encoding=, OS-branch in skills).
"""

import ast
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP_JSON = ROOT / ".mcp.json"
RUN_SERVER = ROOT / "bin" / "run-server"
RUN_SERVER_CMD = ROOT / "bin" / "run-server.cmd"
GITATTRIBUTES = ROOT / ".gitattributes"
WORKFLOW_JS = ROOT / "workflows" / "skill-rollout.js"
SKILLS_DIR = ROOT / "skills"
SERVER_NAME = "skill-rollout-mcp"

# Whole-repo encoding scan, minus vendored/generated dirs — a missing encoding=
# outside tools/servers (e.g. a future script in workflows/ or bin/) is exactly
# the silent-bypass this guard must not have.
_SCAN_EXCLUDE_DIRS = {
    ".git", "venv", ".venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "build", "dist",
}
_TEXT_IO_FUNCS = {"open", "read_text", "write_text"}


# --- MCP launch wrapper ---

def test_mcp_command_goes_through_wrapper_not_hardcoded_venv():
    config = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    command = config["mcpServers"][SERVER_NAME]["command"]
    assert "venv/bin" not in command
    assert "venv\\Scripts" not in command and "venv/Scripts" not in command
    assert command.endswith("bin/run-server")


def test_run_server_wrapper_exists_and_is_executable():
    assert RUN_SERVER.exists(), "bin/run-server not found"
    assert os.access(RUN_SERVER, os.X_OK), "bin/run-server must have the executable bit"
    first_line = RUN_SERVER.read_text(encoding="utf-8").splitlines()[0]
    assert first_line in ("#!/bin/sh", "#!/bin/bash"), (
        f"unexpected shebang: {first_line}"
    )


def test_run_server_cmd_targets_windows_venv():
    assert RUN_SERVER_CMD.exists(), "bin/run-server.cmd not found"
    content = RUN_SERVER_CMD.read_text(encoding="utf-8")
    assert "%USERPROFILE%" in content
    assert "Scripts\\python.exe" in content


# --- LF/CRLF pinning ---

def test_gitattributes_pins_line_endings():
    text = GITATTRIBUTES.read_text(encoding="utf-8")
    assert "bin/run-server text eol=lf" in text
    assert "bin/run-server.cmd text eol=crlf" in text
    # The Workflow tool rejects a script with CR — the workflow.js MUST be LF-pinned.
    assert "workflows/skill-rollout.js text eol=lf" in text


def test_run_server_wrapper_has_no_cr():
    """A CR in the POSIX shebang line breaks the wrapper on Linux/macOS."""
    raw = RUN_SERVER.read_bytes()
    assert b"\r" not in raw, "bin/run-server must have LF-only line endings"


def test_workflow_js_is_lf_if_present():
    """The Workflow tool rejects any script containing CR/control chars."""
    if WORKFLOW_JS.exists():
        assert b"\r" not in WORKFLOW_JS.read_bytes(), (
            "workflows/skill-rollout.js must be LF-only — the Workflow tool rejects CR"
        )


# --- encoding= on every file I/O (independent bug class from the launch wrapper) ---


def _iter_repo_py_files():
    for py in ROOT.rglob("*.py"):
        parts = py.relative_to(ROOT).parts
        if any(part in _SCAN_EXCLUDE_DIRS for part in parts):
            continue
        yield py


def _call_func_name(func):
    if isinstance(func, ast.Attribute):
        return func.attr  # x.open / x.read_text / x.write_text
    if isinstance(func, ast.Name):
        return func.id  # builtin open
    return None


def _is_binary_io(node):
    """True if this open/read/write is binary mode (encoding= is invalid there)."""
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            if isinstance(kw.value.value, str) and "b" in kw.value.value:
                return True
    # builtin open(path, "rb"): mode is the second positional arg.
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        val = node.args[1].value
        if isinstance(val, str) and "b" in val:
            return True
    return False


def test_all_text_file_io_passes_encoding():
    """Without encoding=, Windows falls back to the locale codepage (cp1252) and
    crashes on any non-ASCII char in a file written with ensure_ascii=False.

    AST-based, whole-repo: matches open()/.read_text()/.write_text() calls by
    function name (no line-based false positives, no self-match on string
    literals) and skips binary-mode calls."""
    offenders = []
    for py in _iter_repo_py_files():
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_func_name(node.func) not in _TEXT_IO_FUNCS:
                continue
            if _is_binary_io(node):
                continue
            if not any(kw.arg == "encoding" for kw in node.keywords):
                rel = py.relative_to(ROOT)
                offenders.append(f"{rel}:{node.lineno}: file I/O without encoding=")
    assert not offenders, "text file I/O without encoding=:\n" + "\n".join(offenders)


# --- Skill OS-branch guard (tolerant: only checks skills that shell out to a venv) ---

def test_skills_that_reference_a_venv_interpreter_document_both_platforms():
    """A skill that shells out to a venv interpreter must document BOTH OS paths.

    Triggers on a venv interpreter/pip PATH (the thing that actually needs
    OS-branching), not on the bare word "venv" — a prose mention in a help
    overview is not a shell-out and needs no OS paths."""
    if not SKILLS_DIR.is_dir():
        return
    for skill_md in SKILLS_DIR.glob("*/SKILL.md"):
        body = skill_md.read_text(encoding="utf-8")
        posix = "venv/bin/python3" in body or "venv/bin/pip" in body
        windows = "Scripts\\python.exe" in body or "Scripts\\pip.exe" in body
        if not (posix or windows):
            continue
        assert posix and windows, (
            f"{skill_md.relative_to(ROOT)}: references a venv interpreter path in one "
            "OS form but not the other — document both POSIX (venv/bin/python3) and "
            "Windows (Scripts\\python.exe)"
        )
