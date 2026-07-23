"""Smoke: Prompt 2's commit/reset instruction is reconciled with Stage A's
no-commit boundary (issue #22).

`reference/self-improving-skills.md`'s "Beispielprompt für Skill Self-
Improvement" used to instruct an unconditional "if score improved: git
commit; if it dropped: git reset" per iteration — correct for a standalone
run, but a self-contradiction once this text is followed inside Stage A
(`evalAndEditPrompt` in workflows/skill-rollout.js), whose own boundary
rule forbids committing the plugin-repo diff at all. Confirmed hitting
production twice independently (mm-skills/prompt-generator/loop-log.md,
storyforge/backfill-style-principles/loop-log.md) before this fix — the
harder case (a git-based discard silently wiping an earlier KEPT
iteration's edit, since Stage A never commits and HEAD is always the
pre-loop baseline) was never actually exercised in production but is a
real, waiting-to-happen bug once a keep-then-discard run occurs.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SELF_IMPROVING_SKILLS = ROOT / "reference" / "self-improving-skills.md"
EVAL_SCHEMA = ROOT / "reference" / "eval-schema.md"


def _normalize(text):
    return re.sub(r"\s+", " ", text)


def _self_improving_skills_text():
    return _normalize(SELF_IMPROVING_SKILLS.read_text(encoding="utf-8"))


def _eval_schema_text():
    return _normalize(EVAL_SCHEMA.read_text(encoding="utf-8"))


def test_prompt_2_distinguishes_standalone_from_pipeline_mode():
    text = _self_improving_skills_text()
    assert "Standalone run" in text and "Pipeline run" in text, (
        "expected the example prompt to explicitly distinguish a standalone "
        "run from a pipeline (Stage A) run for the keep/commit decision"
    )


def test_prompt_2_pipeline_mode_never_commits():
    text = _self_improving_skills_text()
    assert "do NOT commit" in text and "Stage A's own boundary rule forbids" in text, (
        "expected pipeline-mode keep to explicitly forbid committing, "
        "matching Stage A's boundary rule in workflows/skill-rollout.js"
    )


def test_prompt_2_pipeline_mode_records_null_commit_with_note():
    text = _self_improving_skills_text()
    assert '"commit": null' in text, (
        "expected the null-commit convention to be stated explicitly, not "
        "left for an agent to invent on its own (as happened twice already "
        "in production before this fix)"
    )
    assert "CORRECT, expected shape in pipeline mode, not an anomaly" in text, (
        "expected explicit reassurance that commit:null+note is correct, "
        "not something to fix or apologize for"
    )


def test_prompt_2_discard_uses_content_capture_not_git():
    """Regression guard for the harder bug this issue found: a git-based
    discard (checkout/reset) is only safe when no prior iteration in the
    same run was kept, since Stage A never commits and HEAD is always the
    pre-loop baseline — a discard after a keep would silently wipe the kept
    edit too. The fix must mandate content-capture-and-restore instead."""
    text = _self_improving_skills_text()
    assert "capture the file's exact current content" in text, (
        "expected an explicit instruction to capture pre-edit content "
        "every iteration, not just on iterations expected to fail"
    )
    assert "always use it rather than a git-based revert" in text, (
        "expected an explicit instruction preferring content-restore over "
        "any git-based revert"
    )
    assert "git checkout" in text and "git reset" in text, (
        "expected git checkout/reset named explicitly as the risky alternative"
    )
    assert "silently wiping out any EARLIER kept iteration" in text, (
        "expected the specific failure mode (a git-based revert erasing an "
        "earlier keep, not just the current discard) to be named explicitly "
        "— a vaguer 'be careful' warning would not have prevented the bug"
    )


def test_prompt_2_capture_happens_before_making_the_change():
    """Regression guard for a code-review finding: an earlier version of
    this test compared capture's position against the DISCARD instruction,
    which is near-trivially true for any sane prose ordering and doesn't
    verify what its docstring claimed (capture-before-the-edit-itself).
    The actual pre-edit guarantee comes from the sentence's own wording
    ("Before making that change, capture...") — assert on that anchor
    directly, not on text position relative to an unrelated later step."""
    text = _self_improving_skills_text()
    anchor = "Before making that change, capture the file's exact current content"
    assert anchor in text, (
        "expected the capture instruction to be explicitly anchored as "
        "happening BEFORE the edit itself, not just present somewhere "
        "earlier in the text than the discard step"
    )


def test_eval_schema_documents_null_commit_as_valid_pipeline_shape():
    text = _eval_schema_text()
    assert "CORRECT, expected shape in pipeline mode" in text, (
        "expected eval-schema.md's loop-state.json field docs to state "
        "commit:null+note is a valid, expected shape for a pipeline run, "
        "not just show real-commit-hash examples that read as the only "
        "valid shape"
    )
    assert '"commit": null' in text, (
        "expected a concrete commit:null example in the schema docs"
    )
