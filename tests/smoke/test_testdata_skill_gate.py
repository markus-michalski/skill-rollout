"""Smoke: create-testdata/reset-testdata/delete-testdata convention replaces the
former "human sandbox-design conversation" gate (issue #35).

That gate was never actually honored in practice: a grep across every
storyforge loop-log.md turned up zero documented human-Claude design
discussion, even though it was the one plugin that went through onboarding.
Replaced with a concrete, checkable artifact — three fixed-name skills whose
existence, static implementation, and live refuse-behavior onboarding
verifies directly, instead of trusting an undefined conversation happened.

Regression guard for the fix across reference/prompt-self-improving-skill-playbook.md,
reference/self-improving-skills.md, reference/eval-schema.md, and
workflows/skill-rollout.js.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_JS = ROOT / "workflows" / "skill-rollout.js"
EVAL_SCHEMA = ROOT / "reference" / "eval-schema.md"
ONBOARD_PLAYBOOK = ROOT / "reference" / "prompt-self-improving-skill-playbook.md"
SELF_IMPROVING = ROOT / "reference" / "self-improving-skills.md"


def _normalize(text):
    return re.sub(r"\s+", " ", text)


def _workflow_text():
    return _normalize(WORKFLOW_JS.read_text(encoding="utf-8"))


def _eval_schema_text():
    return _normalize(EVAL_SCHEMA.read_text(encoding="utf-8"))


def _onboard_text():
    return _normalize(ONBOARD_PLAYBOOK.read_text(encoding="utf-8"))


def _self_improving_text():
    return _normalize(SELF_IMPROVING.read_text(encoding="utf-8"))


# --- The old gate must actually be gone, not just supplemented ---------------


def test_old_human_conversation_gate_removed_from_onboard_playbook():
    text = _onboard_text()
    assert "human conversation" not in text, (
        "expected the old undefined 'human conversation' unblock step to be "
        "fully replaced, not left alongside the new mechanism"
    )
    assert "blocked pending a human conversation to actually design it" not in text


def test_old_human_sandbox_design_conversation_removed_from_eval_schema():
    """Regression guard for a code-review finding: the first version of this
    test only checked the exact phrase 'human sandbox-design conversation',
    which the BLOCKED row rewrite did remove — but missed a stale copy of the
    same retired framing sitting in the neighboring READ-ONLY row ('...does
    NOT need the plugin-level sandbox-design conversation', '...once a human
    designs a sandbox'), different exact wording, same retired concept.
    Assert on the narrower substrings so a partial replacement can't hide."""
    text = _eval_schema_text()
    assert "sandbox-design conversation" not in text, (
        "expected every occurrence of the retired 'sandbox-design "
        "conversation' framing to be gone, including in rows other than "
        "the one this PR's diff directly touched"
    )
    assert "designs a sandbox" not in text, (
        "expected the READ-ONLY row's 'once a human designs a sandbox' "
        "phrasing to be gone too, not just the BLOCKED row's copy"
    )


def test_old_human_sandbox_design_conversation_removed_from_workflow_js():
    text = _workflow_text()
    assert "sandbox-design conversation" not in text, (
        "expected the hard-gate needsHumanReview text to point at the "
        "three-skill convention's buildable unblock path, not the retired "
        "conversation step"
    )
    assert "designs a sandbox" not in text


# --- Onboard playbook step 3a: discovery + static + live checks --------------


def test_onboard_playbook_names_the_three_fixed_skills():
    text = _onboard_text()
    for name in ("create-testdata", "reset-testdata", "delete-testdata"):
        assert name in text, f"expected step 3a to name {name}"


def test_onboard_playbook_requires_all_three_not_a_subset():
    text = _onboard_text()
    assert "All three, not a subset" in text, (
        "expected an explicit requirement that all three skills exist, not "
        "just one or two of them"
    )


def test_onboard_playbook_has_discovery_static_and_live_check_steps():
    text = _onboard_text()
    assert "**Discovery.**" in text
    assert "**Static check.**" in text
    assert "**Live verification" in text


def test_onboard_playbook_static_check_reads_actual_instruction_text():
    text = _onboard_text()
    assert "actual instruction text (not their" in text, (
        "expected the static check to require reading the SKILL.md's real "
        "instructions, not trusting its prose claims about itself"
    )


def test_onboard_playbook_live_verification_uses_provably_nonexistent_slug():
    """Regression guard for the corrected methodology (issue #35 design
    refinement): the original proposal used a merely 'non-matching' slug,
    which could accidentally collide with real data if the guard was broken
    — making the verification attempt itself the data loss. The fix requires
    a synthetic, provably-nonexistent slug instead."""
    text = _onboard_text()
    assert "provably-nonexistent" in text or "provably nonexistent" in text
    assert "cannot coincide with any real entity even if" in text


def test_onboard_playbook_documents_both_zero_risk_live_outcomes():
    text = _onboard_text()
    assert "guard confirmed working" in text
    assert '"not found"' in text or "fails with “not found”" in text


def test_onboard_playbook_explains_why_original_check_was_flawed():
    text = _onboard_text()
    assert (
        "the verification attempt itself would have been the data loss, the "
        "test and the damage the same event" in text
    ), "expected the flaw in the original (non-synthetic-slug) proposal to be documented"


def test_onboard_playbook_unblock_path_is_buildable_not_a_conversation():
    text = _onboard_text()
    assert "buildable unblock path instead of an undefined" in text
    assert "file a per-plugin GitHub issue for this if one does not already exist" in text


def test_onboard_playbook_prompt3_outcomes_reference_three_checks():
    """Phase 2's Prompt 3 outcome list must match step 3a's actual mechanism,
    not the retired 'confirmed disposable/fictional domain' framing."""
    text = _onboard_text()
    assert "confirmed disposable/fictional" not in text, (
        "expected the retired fictional-domain framing to be gone from the "
        "Prompt 3 outcome list"
    )
    assert "discovery + static + live checks ALL passed" in text


def test_onboard_playbook_phase3_selfcheck_covers_live_verification():
    text = _onboard_text()
    assert "was actually constructed to be provably-nonexistent" in text


def test_onboard_playbook_per_skill_readonly_override_still_intact():
    """Pre-existing regression guard (test_readonly_tier.py) depends on this
    exact phrase surviving step 3a's rewrite."""
    text = _onboard_text()
    assert "not necessarily final per-skill" in text


# --- self-improving-skills.md: convention documented as primary path ---------


def test_self_improving_skills_documents_three_skill_convention_section():
    text = _self_improving_text()
    assert "create-testdata / reset-testdata / delete-testdata Convention" in text


def test_self_improving_skills_names_all_three_skills_with_purpose():
    text = _self_improving_text()
    assert "legt frische, wegwerfbare Test-Entities" in text  # create-testdata
    assert "OHNE sie zu löschen" in text  # reset-testdata never deletes
    assert "vollständiges Teardown" in text  # delete-testdata


def test_self_improving_skills_requires_delete_testdata_idempotent():
    text = _self_improving_text()
    assert "idempotent" in text and "no-op-safe" in text


def test_self_improving_skills_documents_prefix_decision():
    text = _self_improving_text()
    assert "zz-sandbox-" in text
    assert "NICHT auf `zzzz-` umgestellt" in text or "NICHT auf `zzzz`" in text


def test_self_improving_skills_documents_staged_option_a_and_b():
    text = _self_improving_text()
    assert "Option A (jetzt lieferbar" in text
    assert "Option B (stärker, größerer Scope" in text


def test_self_improving_skills_hand_designed_material_reframed_as_implementation_guidance():
    """Issue #35's explicit ask: the pre-existing git-tag-baseline /
    isolated-vs-shared-storage material must become implementation guidance
    FOR the three skills, not something onboarding itself designs."""
    text = _self_improving_text()
    assert "Implementierungs-Leitlinien" in text or "Implementierungsleitlinie" in text
    assert "nicht etwas, das das Onboarding selbst entwirft" in text


def test_self_improving_skills_notes_testdata_skills_are_rollout_targets():
    text = _self_improving_text()
    assert "sind selbst Rollout-Ziele" in text


# --- eval-schema.md: BLOCKED tier points at the concrete artifact ------------


def test_eval_schema_blocked_tier_names_three_skill_convention():
    text = _eval_schema_text()
    assert "create-testdata" in text and "reset-testdata" in text and "delete-testdata" in text
    assert "checkable artifact, not a design conversation" in text


def test_eval_schema_blocked_tier_still_distinguishes_from_na_and_bare_square():
    """Regression guard: the rewrite must not lose the pre-existing
    N/A-vs-BLOCKED-vs-not-attempted distinction this row already documented."""
    text = _eval_schema_text()
    assert "never a bare ⬜" in text
    assert '"not attempted yet"' in text


def test_workflow_js_hard_gate_still_distinguishes_applicable_but_blocked():
    """Companion regression guard for the workflow.js copy of the same
    N/A-vs-BLOCKED distinction (a separate location from eval-schema.md's
    STATUS.md legend row)."""
    text = _workflow_text()
    assert '"applicable but blocked"' in text


# --- workflows/skill-rollout.js: special-case fixed sequence -----------------


def test_workflow_js_defines_testdata_skill_names_constant():
    text = _workflow_text()
    assert "TESTDATA_SKILL_NAMES" in text
    assert "'create-testdata', 'reset-testdata', 'delete-testdata'" in text


def test_workflow_js_has_special_case_prompt_function():
    text = _workflow_text()
    assert "function testdataSkillEvalAndEditPrompt" in text


def test_workflow_js_rollout_loop_branches_on_testdata_skill():
    text = _workflow_text()
    assert "isTestdataSkill" in text
    assert "testdataSkillEvalAndEditPrompt(plugin, pluginRepoPath, skill.name" in text


def test_workflow_js_fixed_sequence_is_check_delete_create_reset_order():
    """The source file is a JS template literal — backticks are escaped as
    \\` in the raw text this test reads, so assertions must match that
    literal form, not a plain backtick."""
    text = _workflow_text()
    check_idx = text.find("Check whether test data already exists")
    delete_idx = text.find(r"Run \`delete-testdata\`, UNCONDITIONALLY")
    create_idx = text.find(r"Run \`create-testdata\`")
    reset_idx = text.find(r"Run \`reset-testdata\`")
    assert -1 not in (check_idx, delete_idx, create_idx, reset_idx), (
        "expected all four fixed-sequence steps to be present"
    )
    assert check_idx < delete_idx < create_idx < reset_idx, (
        "expected the fixed sequence to appear in check -> delete -> create -> "
        "reset order"
    )


def test_workflow_js_delete_testdata_step_always_runs_not_conditionally():
    """Regression guard for a code-review MEDIUM finding: the first version
    of this sequence only ran delete-testdata 'if test data already
    exists' — on a freshly-cleaned sandbox, step 1 would find nothing, step
    2 would never execute, and delete-testdata's Live column could still
    end up marked done without the tool ever having been called once (a
    false pass on the highest-blast-radius skill of the three)."""
    text = _workflow_text()
    assert "UNCONDITIONALLY, regardless of what step 1 found" in text
    assert "could reach the end of this sequence having marked" in text
    assert "a false pass, exactly the failure" in text
    assert "must be idempotent/no-op-safe on an empty sandbox" in text


def test_workflow_js_requires_delete_testdata_idempotent_on_empty_sandbox():
    text = _workflow_text()
    assert "idempotent/no-op-safe" in text
    assert 'recognizes "nothing to delete"' in text
    assert "proceeds without erroring" in text


def test_workflow_js_testdata_special_case_skips_evals_json():
    text = _workflow_text()
    assert "Do NOT create an evals.json or run a simulated-tier grading loop for this skill" in text


def test_workflow_js_hard_gate_points_at_three_skill_convention_not_conversation():
    text = _workflow_text()
    idx = text.find("Hard gate, check this if the read-only bypass above did NOT apply")
    assert idx != -1
    gate_section = text[idx:idx + 2500]
    assert "create-testdata" in gate_section
    assert "buildable engineering task, never an undefined" in gate_section
