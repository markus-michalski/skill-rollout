"""Smoke: 🟩 READ-ONLY tier bypasses the sandbox-design gate for verified
read-only MCP domain surfaces (issue #24).

The Live-tier BLOCKED default previously conflated any real MCP domain-tool
surface with "needs sandbox design", regardless of whether that surface
could actually mutate data. Confirmed concrete case: mm-skills'
`socialcraft` calls only read-verb MCP tools (wikijs search/get,
mm-dev-toolkit's tool_get_project) yet was BLOCKED alongside
`shopware-produkt-wizard`, which genuinely creates/updates real shop
products — a whole class of zero-mutation-risk skills was stuck behind
sandbox-design work that doesn't apply to them.

Regression guard for the fix in workflows/skill-rollout.js's Stage A
(`evalAndEditPrompt`) and reference/eval-schema.md's STATUS.md legend.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_JS = ROOT / "workflows" / "skill-rollout.js"
EVAL_SCHEMA = ROOT / "reference" / "eval-schema.md"
ONBOARD_PLAYBOOK = ROOT / "reference" / "prompt-self-improving-skill-playbook.md"


def _normalize(text):
    return re.sub(r"\s+", " ", text)


def _workflow_text():
    return _normalize(WORKFLOW_JS.read_text(encoding="utf-8"))


def _eval_schema_text():
    return _normalize(EVAL_SCHEMA.read_text(encoding="utf-8"))


def test_eval_schema_defines_readonly_tier():
    text = _eval_schema_text()
    assert "🟩 READ-ONLY" in text, (
        "expected a distinct 🟩 READ-ONLY entry in the STATUS.md legend table"
    )


def test_eval_schema_readonly_tier_requires_verified_zero_write_calls():
    text = _eval_schema_text()
    no_partial_credit = (
        "One confirmed write-capable call anywhere disqualifies it entirely"
    )
    assert no_partial_credit in text, (
        "expected an explicit no-partial-credit rule — one write call anywhere "
        "disqualifies the whole skill from this tier"
    )


def test_eval_schema_readonly_classification_is_behavior_based_not_name_based():
    """Regression guard for a code-review MEDIUM finding: classifying a
    tool as read-only purely by name prefix is unsafe (e.g. a hypothetical
    search_and_replace_X would match the search_ prefix while mutating).
    The legend must require confirming real behavior, not just a name
    pattern."""
    text = _eval_schema_text()
    assert "never inferred from name alone" in text, (
        "expected the legend to explicitly forbid name-only classification"
    )
    assert "search_and_replace_X" in text, (
        "expected the concrete false-positive example to be documented, "
        "not just an abstract warning"
    )


def test_eval_schema_readonly_tier_addresses_mutation_risk_only():
    """Regression guard for a code-review HIGH finding: the first draft's
    read-only bypass reasoned only about mutation risk, ignoring that a
    read of sensitive real data (personal/legal/medical/business) still
    exposes that data — e.g. into loop-log.md, which gets committed and
    pushed to the skill-evals git repo."""
    text = _eval_schema_text()
    assert "This tier addresses MUTATION risk only, not read-exposure risk" in text, (
        "expected an explicit statement that READ-ONLY clearance does not "
        "generalize to a blanket 'safe to read anything real' clearance"
    )
    assert "sensitive personal/legal/medical/business data" in text, (
        "expected the specific sensitive-data categories to be named, not "
        "just a vague 'be careful' caveat"
    )


def test_eval_schema_readonly_bypasses_sandbox_conversation():
    text = _eval_schema_text()
    assert "does NOT need the plugin-level sandbox-design conversation" in text, (
        "expected the READ-ONLY tier to explicitly bypass the sandbox-design "
        "requirement, not just exist as a label"
    )


def test_workflow_js_has_readonly_bypass_before_hard_gate():
    """The read-only bypass check must run BEFORE the hard gate — a future
    edit that reordered them would silently re-block read-only skills."""
    text = _workflow_text()
    bypass_idx = text.find("Read-only bypass, check this FIRST")
    hard_gate_marker = (
        "Hard gate, check this if the read-only bypass above did NOT apply"
    )
    hard_gate_idx = text.find(hard_gate_marker)
    assert bypass_idx != -1, "expected the read-only bypass section to exist"
    assert hard_gate_idx != -1, (
        "expected the hard gate to explicitly reference the bypass above it"
    )
    assert bypass_idx < hard_gate_idx, (
        "expected the read-only bypass check to appear BEFORE the hard gate"
    )


def test_workflow_js_readonly_bypass_greps_this_skills_own_surface():
    text = _workflow_text()
    own_surface = (
        "this skill's own SKILL.md actually makes" in text
        or "this specific skill's own surface" in text
    )
    assert own_surface, (
        "expected the bypass check to grep THIS skill's own domain-tool "
        "calls, not a plugin-wide sample"
    )


def test_workflow_js_readonly_bypass_requires_zero_write_verbs():
    text = _workflow_text()
    assert "Zero write-capable calls anywhere in this skill's surface" in text, (
        "expected the bypass to require verified zero write-capable calls"
    )
    assert "One write-capable call anywhere disqualifies the whole skill" in text, (
        "expected the no-partial-credit rule restated in the workflow script itself"
    )


def test_workflow_js_readonly_classification_is_behavior_based():
    """Regression guard for a code-review MEDIUM finding: the bypass must
    not let an LLM agent classify a tool as read-only purely because its
    name matches a prefix — it must confirm the tool's actual documented
    behavior, and fall through to the hard gate on any doubt."""
    text = _workflow_text()
    assert "Classify by what each tool DOES, not by its name" in text, (
        "expected an explicit behavior-based classification instruction"
    )
    assert "search_and_replace_X" in text, (
        "expected the concrete false-positive example naming a tool whose "
        "name looks read-only but would mutate"
    )
    assert "fall through to the hard gate, do not guess it's safe" in text, (
        "expected an explicit fail-closed instruction for low-confidence "
        "classifications"
    )


def test_workflow_js_readonly_bypass_has_sensitive_data_carveout():
    """Regression guard for a code-review HIGH finding: reasoning only
    about mutation risk misses that a READ of sensitive real data
    (personal/legal/medical/business) still exposes it — e.g. into
    loop-log.md, which Stage C commits and pushes. The bypass must
    explicitly NOT treat "read-only" as "safe to read anything real"."""
    text = _workflow_text()
    mutation_only = (
        "this bypass addresses MUTATION risk only — it is not a read-anything clearance"
    )
    assert mutation_only in text, (
        "expected an explicit statement that read-only clearance does not "
        "cover sensitive-data-exposure risk"
    )
    assert "personal, legal, medical, or business/customer data" in text, (
        "expected the specific sensitive-data categories named explicitly"
    )


def test_workflow_js_readonly_path_skips_sandbox_reset_instructions():
    """A read-only-cleared skill has nothing to reset — it's not mutating
    shared state, so sandbox reset/teardown instructions must not apply
    to it (that would be meaningless busywork, or worse, confuse the
    agent into thinking a sandbox is required after all)."""
    text = _workflow_text()
    assert "Read-only-cleared skill:" in text and "no sandbox needed" in text, (
        "expected an explicit branch stating no sandbox/reset is needed "
        "for a read-only-cleared skill"
    )


def test_workflow_js_status_column_uses_blocked_symbol_not_bare_square():
    """Regression guard for a pre-existing inconsistency found while fixing
    issue #24: the hard-gate text said to leave the Live column as a bare
    ⬜ ("not attempted"), which is indistinguishable from a skill nobody has
    looked at yet — the actually-used convention (confirmed in mm-skills'
    real STATUS.md) is 🟥 BLOCKED, matching eval-schema.md's own legend."""
    text = _workflow_text()
    assert "mark the Live column 🟥 BLOCKED" in text, (
        "expected the hard-gate outcome to explicitly mark 🟥 BLOCKED, not "
        "leave the column at a bare ⬜"
    )


def test_onboard_playbook_mentions_per_skill_readonly_override():
    """A future onboarding must know the plugin-level blocked-placeholder
    decision (case 3) isn't the final word per-skill — the rollout-time
    read-only bypass can still apply to an individual skill regardless.

    Regression guard for a code-review finding: an earlier version of this
    test accepted the bare substring "read-only" anywhere in the file,
    which is near-tautological (the word appears throughout the doc
    regardless of whether the OVERRIDE semantics survive an edit). Assert
    on override-specific wording instead."""
    text = _normalize(ONBOARD_PLAYBOOK.read_text(encoding="utf-8"))
    assert "not necessarily final per-skill" in text, (
        "expected the onboarding playbook's blocked-placeholder case to "
        "state the per-skill override explicitly, not just mention the "
        "word 'read-only' somewhere in the file"
    )
