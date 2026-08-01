"""Smoke: preIsolated Stage A must VERIFY the shared worktree actually advanced to
this skill's own branch before touching a single file (issue #63).

Regression guard for a confirmed incident: during a life-hub skill-rollout batch
(2026-07-31, preIsolated mode), the shared rollout worktree was found parked on the
PREVIOUS skill's branch with the NEXT skill's diff staged on top of it, instead of
having been advanced to its own fresh `skill-eval-{skillName}` branch off origin/main
first. The rollout agent for that skill caught it and recovered by hand, but nothing
in the prompt told it to check in the first place — `git checkout -f -B
skill-eval-{skillName} origin/main` was trusted to have worked just because it exited
0, with no verification that HEAD actually landed on the expected branch before any
file was read or edited.

The fix adds an explicit `git branch --show-current` check immediately after the
branch reset, with a STOP-and-flag path (not a self-guessed recovery) if it doesn't
match.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_JS = ROOT / "workflows" / "skill-rollout.js"


def _normalize(text):
    return re.sub(r"\s+", " ", text)


def _workflow_source():
    return WORKFLOW_JS.read_text(encoding="utf-8")


def _preisolated_create_section():
    # 'Start this skill from a PRISTINE base' only appears in isolationSection's
    # preIsolated + role==='create' branch (used by Stage A). 'Do ALL
    # reads/edits/reviews' is common text right after the role-specific ternary
    # closes, so it safely bounds the slice without needing to worry about
    # isolationSection's other role/preIsolated branches (resume, non-preIsolated)
    # which use entirely different wording.
    src = _workflow_source()
    start_marker = "Start this skill from a PRISTINE base"
    end_marker = (
        "Do ALL reads/edits/reviews/git-workflow steps directly in this worktree"
    )
    start = src.find(start_marker)
    assert start != -1, f"expected to find {start_marker!r} in workflow.js"
    end = src.find(end_marker, start)
    assert end != -1 and end > start, (
        f"expected to find {end_marker!r} after {start_marker!r} in workflow.js"
    )
    return _normalize(src[start:end])


def test_branch_reset_is_followed_by_a_show_current_check():
    section = _preisolated_create_section()
    assert "git branch --show-current" in section, (
        "expected an explicit `git branch --show-current` verification right after "
        "the branch-reset command, not just trust that `git checkout -B` worked"
    )


def test_verification_runs_after_the_reset_command():
    section = _preisolated_create_section()
    reset_pos = section.find("git checkout -f -B skill-eval-")
    verify_pos = section.find("git branch --show-current")
    assert reset_pos != -1 and verify_pos != -1
    assert reset_pos < verify_pos, (
        "expected the verification to run AFTER the branch-reset command, not before"
    )


def test_stops_before_touching_any_file_on_mismatch():
    section = _preisolated_create_section()
    assert "STOP" in section, (
        "expected an explicit STOP instruction for when the branch doesn't match"
    )
    assert "not read, edit, or stage a single file" in section.lower(), (
        "expected the STOP to explicitly forbid touching any file in "
        "pluginRepoPath, not just vaguely 'be careful' — a prior skill's diff "
        "could already be sitting there"
    )


def test_stop_precedes_the_subsequent_stage_handoff():
    section = _preisolated_create_section()
    stop_pos = section.find("STOP")
    handoff_pos = section.find("Every subsequent stage for this skill")
    assert stop_pos != -1 and handoff_pos != -1
    assert stop_pos < handoff_pos, (
        "expected the STOP-on-mismatch instruction to appear before the "
        "'every subsequent stage runs on this branch' handoff text"
    )


def test_mismatch_is_flagged_to_needs_human_review_not_self_fixed():
    section = _preisolated_create_section()
    assert "needsHumanReview" in section, (
        "expected a mismatch to produce a needsHumanReview entry, not just a "
        "silent stop"
    )
    assert "do not attempt to fix the branch mismatch yourself" in section.lower(), (
        "expected an explicit prohibition on the agent guessing its way out of "
        "an unexpected branch state on a SHARED worktree — that risks silently "
        "mixing two skills' diffs, the exact failure this check exists to prevent"
    )


def test_mismatch_sets_stopped_early_so_the_circuit_breaker_can_trip():
    """Regression guard for a code-review finding: without an explicit
    `stoppedEarly: true`, the batch's only systemic-failure guard
    (FAILURE_CIRCUIT_BREAKER, which counts skills that self-report stoppedEarly)
    never trips on a worktree that's stuck on the wrong branch for every remaining
    skill in the batch — it would silently grind through the whole batch producing
    the same failure per skill instead of stopping after 3."""
    section = _preisolated_create_section()
    assert (
        "stoppedEarly: true" in section and "stopReason: 'branch_mismatch'" in section
    ), (
        "expected the STOP path to explicitly set stoppedEarly: true and a "
        "distinct stopReason, so the batch's circuit breaker can actually trip "
        "on a systemic fault"
    )


def test_mismatch_does_not_claim_evals_are_unaffected():
    """Regression guard for a code-review finding: an earlier draft of this fix
    said 'evals/grading are unaffected — only the git-workflow portion is
    blocked' right next to forbidding all file reads — but Stage A's entire job
    IS reading files to run evals, so that claim was self-contradictory and
    actively wrong (the mismatch corrupts eval results FIRST, not last)."""
    section = _preisolated_create_section()
    assert "evals/grading are unaffected" not in section.lower(), (
        "expected the STOP path to NOT claim evals are unaffected by a branch "
        "mismatch — Stage A's whole job is reading files to run evals, so a "
        "mismatch corrupts exactly that first"
    )


def test_mismatch_forbids_advancing_status_md_symbols():
    """Regression guard for a code-review finding: without this, Stage C's
    'nothing was staged' bookkeeping branch could still write STATUS.md's
    completion symbols for a skill that was never actually evaluated (its eval
    never ran, due to the branch mismatch), permanently hiding it from every
    future batch's selection."""
    section = _preisolated_create_section()
    assert (
        "do not advance this skill's simulated/live symbols in status.md"
        in section.lower()
    ), (
        "expected an explicit prohibition on marking this skill done in "
        "STATUS.md when its eval was never actually run due to the branch "
        "mismatch"
    )


def test_verification_checks_exact_match_not_a_prefix():
    section = _preisolated_create_section()
    assert "exactly" in section.lower(), (
        "expected the check to require an EXACT match against the expected "
        "branch name, not a loose 'looks right' comparison"
    )
