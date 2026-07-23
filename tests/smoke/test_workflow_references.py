"""Smoke: workflows/skill-rollout.js references real, existing reference/ docs.

Regression guard for the exact bug class found by an adversarial post-merge
review: a prompt document claiming a file reference was fully retired while
dead references silently survived elsewhere, and a resolved path (referenceDir)
never actually reaching the agent prompt that needed it.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_JS = ROOT / "workflows" / "skill-rollout.js"
ONBOARD_PLAYBOOK = ROOT / "reference" / "prompt-self-improving-skill-playbook.md"
REFERENCE_DIR = ROOT / "reference"

# Filenames workflow.js itself hardcodes into referenceDir-relative paths
# (evalSchemaPath, onboardPlaybookPath). self-improving-skills.md is NOT
# hardcoded here — it's referenced only from within the onboarding playbook
# document itself (checked separately below).
_WORKFLOW_HARDCODED_FILENAMES = [
    "eval-schema.md",
    "prompt-self-improving-skill-playbook.md",
]
_ALL_REFERENCED_FILENAMES = _WORKFLOW_HARDCODED_FILENAMES + ["self-improving-skills.md"]


def _workflow_source():
    return WORKFLOW_JS.read_text(encoding="utf-8")


def test_workflow_hardcoded_reference_filenames_exist():
    """Every reference/*.md filename workflow.js builds a path to must be real."""
    src = _workflow_source()
    for filename in _WORKFLOW_HARDCODED_FILENAMES:
        assert filename in src, (
            f"workflow.js no longer mentions {filename} — check for a silent removal"
        )
        assert (REFERENCE_DIR / filename).is_file(), (
            f"reference/{filename} does not exist on disk"
        )


def test_all_referenced_docs_exist_on_disk():
    """Every doc mentioned anywhere across workflow.js + the onboarding playbook
    must be real — catches the bug class regardless of which file mentions it."""
    combined = _workflow_source() + ONBOARD_PLAYBOOK.read_text(encoding="utf-8")
    for filename in _ALL_REFERENCED_FILENAMES:
        assert filename in combined, (
            f"neither workflow.js nor the onboarding playbook mentions {filename}"
        )
        assert (REFERENCE_DIR / filename).is_file(), (
            f"reference/{filename} does not exist on disk"
        )


def test_evalschemapath_has_both_referencedir_and_fallback_branches():
    """Guards against silently collapsing the referenceDir-present/absent branch.

    The referenceDir-present branch must build an in-plugin path; the absent
    branch must build the (intentionally dead, documented-as-dead) fallback —
    both template shapes must survive future edits, not just one."""
    src = _workflow_source()
    assert "${referenceDir}/eval-schema.md" in src, (
        "referenceDir-present evalSchemaPath branch missing"
    )
    assert "${skillEvalsDir}/schema.md" in src, (
        "referenceDir-absent (fallback) evalSchemaPath branch missing"
    )
    assert "${referenceDir}/prompt-self-improving-skill-playbook.md" in src, (
        "referenceDir-present onboardPlaybookPath branch missing"
    )


def test_no_bare_functional_schema_md_references_remain():
    """Every per-skill/selection prompt must use the resolved ${evalSchemaPath},
    not a bare 'schema.md' string that resolves nowhere from an agent's cwd."""
    src = _workflow_source()
    # A bare "schema.md" not part of the intentional dead-fallback path
    # construction (or its accompanying warning) is a regression.
    bare_mentions = re.findall(r"(?<!eval-)schema\.md", src)
    # Exactly 2 intentional literal occurrences are allowed: the fallback path
    # construction itself and its accompanying warning text.
    assert len(bare_mentions) <= 2, (
        f"found {len(bare_mentions)} bare 'schema.md' mentions in workflow.js — "
        "expected at most 2 (dead-fallback construction + its warning); "
        "anything more is likely a dangling reference needing ${evalSchemaPath}"
    )


def test_onboard_agent_prompt_receives_referencedir_explicitly():
    """The Onboard agent's prompt must explicitly bind {referenceDir} to a real
    value — the bug this guards against: an onboarding agent running with its
    cwd in a DIFFERENT target repo had no absolute path to the plugin's docs."""
    src = _workflow_source()
    assert "{referenceDir} =" in src, (
        "Onboard agent prompt does not explicitly bind {referenceDir} to a value"
    )


def test_mcp_surface_register_filename_spelled_consistently():
    """mcp-surface-register.md is a runtime-generated per-plugin file (lives at
    {skillEvalsDir}/{plugin}/..., never on disk in this repo, so it can't be
    existence-checked like the reference/ docs above) — this guards against the
    4 files that mention it by literal string drifting apart on the name
    (skill-rollout issue #26/#27)."""
    combined = (
        _workflow_source()
        + ONBOARD_PLAYBOOK.read_text(encoding="utf-8")
        + (REFERENCE_DIR / "self-improving-skills.md").read_text(encoding="utf-8")
        + (REFERENCE_DIR / "eval-schema.md").read_text(encoding="utf-8")
    )
    assert combined.count("mcp-surface-register.md") >= 4, (
        "expected all 4 files that describe the MCP Surface Register to spell "
        "its filename identically as 'mcp-surface-register.md'"
    )


def test_onboarding_playbook_placeholders_are_absolute_not_bare_relative():
    """The onboarding playbook must instruct the agent to use {referenceDir}-style
    absolute paths, not bare `reference/...` paths that would resolve against
    the target repo's cwd instead of skill-rollout's own."""
    body = ONBOARD_PLAYBOOK.read_text(encoding="utf-8")
    assert "{referenceDir}" in body, (
        "onboarding playbook doesn't use the {referenceDir} placeholder at all"
    )
    # A bare `reference/` mention that isn't part of an explicit absolute-path
    # instruction or a descriptive mention of the NEW playbook's own text is
    # exactly the regression class this test guards against.
    bare_relative = re.findall(
        r"(?<!\{)reference/(?:eval-schema|self-improving-skills)\.md", body
    )
    assert len(bare_relative) <= 1, (
        f"found {len(bare_relative)} bare relative 'reference/*.md' mentions — "
        "expected at most 1 (the 'write this string into the new playbook' "
        "description); anything more suggests a path needing {referenceDir}"
    )
