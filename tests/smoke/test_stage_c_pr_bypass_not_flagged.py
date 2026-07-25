"""Smoke: Stage C's PR-creation bypass must not self-flag as needsHumanReview.

Regression guard for a confirmed noise bug: Stage C never invokes the
interactive `git-pr-workflows:git-workflow` skill directly — its
AskUserQuestion checkpoints and Task-tool subagent phases are unavailable
inside an unattended Stage C subagent context, so Stage C always runs the
equivalent commit/push/PR steps itself instead. That bypass is the intended,
universal design for every skill's Stage C, not a per-skill anomaly — before
this fix, nothing told the agent that, and it kept re-deriving and logging
the same justification as a `needsHumanReview` entry. Confirmed on 2 of 14
`loop-state.json` files across `~/projekte/skill-evals/` that carry a
`needs_human_review` field at all (both from the same project-hub batch) — a
small sample, but structurally guaranteed to recur on every skill's Stage C
in every batch from here on, since nothing told the agent otherwise.

The rule itself now lives in reference/eval-schema.md §7 (single source of
truth for commit/PR/issue conventions, per that section's own stated
purpose) — workflows/skill-rollout.js only references it, from BOTH of Stage
C's commit branches (the normal reviewed-and-committed path, and the "Stage
A stopped early, commit AS-IS" path). The two-branch coverage matters: an
earlier version of this fix only touched the normal branch, leaving the
stopped-early branch's own — genuinely mandatory — "committed WITHOUT
independent review" needsHumanReview entry exposed to the same noise it was
meant to escape scrutiny for.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_JS = ROOT / "workflows" / "skill-rollout.js"
EVAL_SCHEMA = ROOT / "reference" / "eval-schema.md"


def _normalize(text):
    # Prompt text wraps across lines for readability — collapse whitespace so
    # a line-wrap alone (as opposed to a semantic reword) never breaks a
    # substring assertion below. Same convention as
    # test_git_workflow_quality_gate.py.
    return re.sub(r"\s+", " ", text)


def _workflow_source():
    return WORKFLOW_JS.read_text(encoding="utf-8")


def _eval_schema_source():
    return EVAL_SCHEMA.read_text(encoding="utf-8")


def _slice_between(src, start_marker, end_marker):
    start = src.find(start_marker)
    end = src.find(end_marker, start)
    assert start != -1, f"expected to find {start_marker!r}"
    assert end != -1 and end > start, (
        f"expected to find {end_marker!r} after {start_marker!r}"
    )
    return src[start:end]


def _stage_c_source():
    # Same marker pair as test_git_workflow_quality_gate.py's
    # _stage_c_source() — deliberately mirrored rather than inventing new
    # prose-anchored markers, so the two files can't silently disagree about
    # where Stage C's prompt begins and ends.
    return _normalize(
        _slice_between(
            _workflow_source(), "function commitPrompt(", "phase('Select')"
        )
    )


def _eval_schema_bypass_section():
    # The bypass paragraph is eval-schema.md's final paragraph (end of §7,
    # end of file) — slice from its start marker to end-of-string rather
    # than hunting for a fragile "next section" marker that may not exist.
    src = _eval_schema_source()
    start = src.find("**PR-creation bypasses the interactive")
    assert start != -1, "expected the PR-creation bypass note in eval-schema.md"
    return _normalize(src[start:])


def test_both_commit_branches_reference_the_eval_schema_bypass_rule():
    """Both of Stage C's commit branches (normal review-then-commit, and
    Stage-A-stopped-early-commit-AS-IS) must point at eval-schema.md §7's
    bypass rule — not just one of them. This is the exact gap an earlier
    version of this fix left: only the normal branch got the exception, so
    the stopped-early branch's own mandatory needsHumanReview entry stayed
    exposed to the same noise."""
    section = _stage_c_source()
    marker = "PR-creation bypasses the interactive git-workflow skill"
    occurrences = section.count(marker)
    assert occurrences >= 2, (
        f"expected at least 2 references to the eval-schema.md bypass note "
        f"(one per commit branch), found {occurrences}"
    )


def test_stage_c_does_not_inline_the_bypass_rationale():
    """The rationale (AskUserQuestion/Task-tool unavailability) must live in
    eval-schema.md §7, not be re-derived inline in the JS prompt —
    eval-schema.md §7 explicitly positions itself as the single source of
    truth for these conventions specifically so this text has one place to
    drift from, not two."""
    section = _stage_c_source()
    assert "AskUserQuestion" not in section, (
        "expected the AskUserQuestion rationale to live only in "
        "eval-schema.md §7, not be duplicated inline in workflow.js"
    )


def test_stopped_early_branch_bypass_note_does_not_touch_its_mandatory_entry():
    """The stopped-early branch's own mandatory 'committed WITHOUT
    independent review' needsHumanReview entry must stay mandatory — the
    bypass exception is scoped narrowly enough that it cannot be read as
    covering that entry too."""
    section = _stage_c_source()
    stopped_early_start = section.find("Staged, but Stage A stopped early")
    assert stopped_early_start != -1, "expected to find the stopped-early branch"
    stopped_early_section = section[stopped_early_start:]
    assert "unrelated to" in stopped_early_section, (
        "expected the stopped-early branch to explicitly disclaim that the "
        "bypass exception reduces its own mandatory needsHumanReview "
        "requirement"
    )
    assert "Mandatory" in stopped_early_section, (
        "expected the stopped-early branch's own needsHumanReview entry to "
        "remain explicitly mandatory"
    )


def test_eval_schema_names_the_bypassed_skill_and_the_reason():
    """eval-schema.md §7's bypass note must name the specific skill being
    bypassed and the specific structural reason — a vague 'this is expected'
    would let a future maintainer's paraphrase drift away from the actual
    constraint."""
    section = _eval_schema_bypass_section()
    assert "git-pr-workflows:git-workflow" in section, (
        "expected the bypassed skill to be named explicitly"
    )
    assert "AskUserQuestion" in section and "Task-tool" in section, (
        "expected the structural reason (AskUserQuestion checkpoints, "
        "Task-tool subagent phases unavailable) to be named, not just "
        "asserted"
    )


def test_eval_schema_reserves_needs_human_review_for_real_deviations():
    """The fix must narrow the flag, not eliminate it — a genuine deviation
    from the documented PR-creation convention (guessing the mechanism, a
    failed `gh` call) must remain flaggable, named concretely rather than
    left implicit."""
    section = _eval_schema_bypass_section()
    assert "guessing at the PR-creation mechanism" in section, (
        "expected a concrete example of what still warrants needsHumanReview"
    )
    assert "call itself failing" in section, (
        "expected a second concrete example (a failed gh call) alongside "
        "the first"
    )


def test_eval_schema_covers_both_needs_human_review_field_names():
    """The two confirmed noisy entries landed in loop-state.json's
    snake_case `needs_human_review` field, not the structured camelCase
    `needsHumanReview` return value — the rule must name both, or an agent
    could reasonably assume only the structured field is covered and keep
    polluting the file on disk."""
    section = _eval_schema_bypass_section()
    assert "needs_human_review" in section, (
        "expected the rule to explicitly cover loop-state.json's snake_case "
        "field, not just the structured needsHumanReview return value"
    )
