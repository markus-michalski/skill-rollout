"""Smoke: skills/status/SKILL.md live-verifies PR merge state (issue #18).

Regression guard for a confirmed-in-production staleness bug: STATUS.md's
per-skill notes and batch-digest.md record PR state as free-form prose,
written once when a skill's rollout stage finishes and never revisited. A PR
recorded as "open" may have been merged since, entirely outside the rollout
process — `/skill-rollout:status` used to report that stale text verbatim.

The fix adds a live `gh pr view` check as a presentation-time correction
only — it must NOT compromise the skill's pre-existing "strictly read-only"
contract (no writes back to STATUS.md/batch-digest.md).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS_SKILL = ROOT / "skills" / "status" / "SKILL.md"


def _text():
    # Prose wraps across lines for readability — collapse whitespace so a
    # line-wrap alone never breaks a substring assertion below.
    return re.sub(r"\s+", " ", STATUS_SKILL.read_text(encoding="utf-8"))


def test_live_pr_verification_step_present():
    text = _text()
    assert "gh pr view" in text, (
        "expected the status skill to live-verify PR state via `gh pr view`"
    )


def test_live_check_does_not_compromise_read_only_contract():
    """"Do not modify any files" must survive as a BLANKET prohibition — a
    code-review fix (issue #18) widened an earlier draft's narrower "do not
    modify STATUS.md or batch-digest.md" back to this, since enumerating two
    files reads as implicit permission to modify everything else."""
    text = _text()
    assert "Do not modify any files" in text, (
        "the live-check step must keep the blanket read-only prohibition, "
        "not narrow it to an enumerated file list"
    )
    disclaimer = (
        "never write the live-checked PR state back to STATUS.md or batch-digest.md"
    )
    assert disclaimer in text, (
        "expected the two tracked files named as examples alongside the "
        "blanket prohibition"
    )
    assert "strictly read-only" in text, (
        "the skill's pre-existing read-only invariant must remain stated"
    )


def test_live_check_step_precedes_present_step():
    """The live-verify step must run before Step 3 (Present) builds its
    summary — a future edit that moved verification after presentation
    would silently show stale data again."""
    text = _text()
    step_25_idx = text.find("### 2.5")
    step_3_idx = text.find("### 3. Present")
    assert step_25_idx != -1 and step_3_idx != -1 and step_25_idx < step_3_idx, (
        "expected Step 2.5 (live PR verification) to appear before Step 3 (Present)"
    )


def test_live_check_skips_already_merged_prs():
    """Merge is a one-way GitHub state — re-checking already-merged PRs on
    every status call is wasted API calls with no possible new information."""
    text = _text()
    assert "affirmatively describing it as open/unmerged" in text, (
        "expected an explicit instruction to only extract PRs affirmatively "
        "described as open/unmerged"
    )


def test_live_check_disarms_the_not_merged_substring_trap():
    """Regression guard for a code-review finding (issue #18): a naive check
    for the bare word "merged" would wrongly skip PRs described as "not
    merged", since that phrase itself contains the substring "merged". The
    instruction must explicitly disarm this trap, not just tell the agent
    to "skip merged ones" and hope it reads carefully."""
    text = _text()
    assert "CONTAINS the word" in text and "not merged" in text, (
        "expected an explicit callout of the 'not merged' substring trap"
    )


def test_live_check_avoids_raw_url_shell_interpolation():
    """Regression guard: gh pr view should take a PR number + --repo, not a
    raw URL string, so no URL is interpolated into the shell call."""
    text = _text()
    assert "gh pr view N --repo OWNER/REPO" in text, (
        "expected the number+--repo form of `gh pr view`, not raw URL interpolation"
    )


def test_live_check_dedupes_before_calling_gh():
    text = _text()
    assert "Dedupe by PR URL first" in text, (
        "expected an explicit dedupe-before-checking instruction — the same "
        "PR commonly appears in both STATUS.md and batch-digest.md"
    )


def test_live_check_handles_verification_failure_gracefully():
    text = _text()
    assert "do not fail the whole status check" in text, (
        "a single unreachable/deleted PR must not abort the entire status check"
    )


def test_needs_human_review_staleness_explicitly_out_of_scope():
    """Regression guard for scope creep: a 🟨 NEEDS-HUMAN-REVIEW note can
    describe a structural limitation that a LATER plugin version has since
    fixed — that is not GitHub-API-verifiable and must not be silently
    "fixed" by a heuristic guess."""
    text = _text()
    assert "Out of scope, do not attempt" in text, (
        "expected an explicit out-of-scope callout for NEEDS-HUMAN-REVIEW "
        "structural-limitation staleness, distinct from PR-merge staleness"
    )
