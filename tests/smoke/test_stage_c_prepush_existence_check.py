"""Smoke: Stage C must check for a pre-existing remote branch before its own first push
of `skill-eval-{skillName}` (issue #64).

Regression guard for a confirmed incident: during a life-hub skill-rollout batch
(2026-07-31), the `add-person` skill's PR needed a manual merge-commit reconciliation
before it could be pushed cleanly — `origin/skill-eval-add-person` already had an
unreviewed commit on it (likely a duplicate/interrupted earlier Stage C dispatch for the
same skill) before this run's own Stage C tried to push. The reconciliation happened to
land on the correct (fully-reviewed) version, but it was ad hoc and undocumented — nothing
told the agent to check for this in the first place, or what to do if it found it.

The fix adds a shared `prePushExistenceCheck(skillName, preIsolated)` helper (same
one-shared-function precedent as skillEvalsGitSafety/deploySyncGuardrail, see
test_skill_evals_git_safety.py) interpolated at BOTH of Stage C's commit branches that
push. Two revisions happened before this landed, both caught by an independent code
review of the first draft:

1. The first draft used `git fetch origin && git rev-parse --verify --quiet
   origin/skill-eval-{name}` — a LOCAL remote-tracking-ref lookup. `git fetch` without
   `--prune` never removes stale tracking refs, so a branch merged-and-deleted on GitHub in
   an earlier batch would still false-positive this check on the very next legitimate
   live-tier-only re-run of the same skill (a normal, expected case per the Select phase's
   own "Simulated ✅ but Live ⬜ ... should be included" rule). The fix switched to `git
   ls-remote --exit-code --heads origin skill-eval-{name}`, which queries the server
   directly and has no staleness class, with explicit three-way exit-code handling (2 =
   absent/expected, 0 = found/STOP, anything else = check itself failed/STOP, never treat
   an unverifiable state as safe-to-push).
2. The check is only meaningful in preIsolated mode, where Stage A's own branch-reset
   guarantees the literal `skill-eval-{name}` branch name — non-preIsolated mode isolates
   via a bare `EnterWorktree` call with an auto-generated branch name this script never
   learns, so the same check there would silently no-op against a ref that was never going
   to exist regardless of what actually happened upstream. The helper takes `preIsolated`
   as a second parameter and states this explicitly rather than shipping a check that reads
   as universal but is only ever load-bearing in one of the two modes.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_JS = ROOT / "workflows" / "skill-rollout.js"


def _normalize(text):
    return re.sub(r"\s+", " ", text)


def _workflow_source():
    return WORKFLOW_JS.read_text(encoding="utf-8")


def _slice_between(src, start_marker, end_marker):
    start = src.find(start_marker)
    end = src.find(end_marker, start)
    assert start != -1, f"expected to find {start_marker!r}"
    assert end != -1 and end > start, (
        f"expected to find {end_marker!r} after {start_marker!r}"
    )
    return src[start:end]


def _stage_c_source():
    # Same marker pair as test_stage_c_pr_bypass_not_flagged.py's _stage_c_source() —
    # deliberately mirrored so the files can't silently disagree about where Stage C's
    # prompt begins and ends.
    return _normalize(
        _slice_between(_workflow_source(), "function commitPrompt(", "phase('Select')")
    )


def test_prepush_existence_check_helper_defined_once():
    """Must be a single shared function, not copy-pasted per call site — copy-paste
    invites the two copies drifting apart, same rationale as skillEvalsGitSafety."""
    src = _workflow_source()
    definitions = re.findall(r"function prePushExistenceCheck\(", src)
    assert len(definitions) == 1, (
        f"expected exactly one prePushExistenceCheck definition, found {len(definitions)}"
    )


def _helper_source():
    src = _workflow_source()
    return _normalize(_slice_between(src, "function prePushExistenceCheck(", "\n}\n"))


def test_helper_takes_preisolated_and_is_a_noop_otherwise():
    """The literal skill-eval-{name} branch name is only guaranteed in preIsolated mode
    (Stage A's own branch-reset creates it) — non-preIsolated mode isolates via a bare
    EnterWorktree call with an auto-generated branch name this script never learns, so the
    same check there would silently no-op against a ref that was never real to begin with.
    A code-review finding on the first draft caught this being interpolated unconditionally
    with mode-specific justification baked in regardless of mode."""
    src = _workflow_source()
    definition_start = src.find("function prePushExistenceCheck(")
    assert definition_start != -1
    signature_end = src.find(")", definition_start)
    signature = src[definition_start:signature_end]
    assert "preIsolated" in signature, (
        "expected prePushExistenceCheck to take preIsolated as a parameter"
    )
    section = _helper_source()
    assert "if (!preIsolated)" in section, (
        "expected an explicit early branch for the non-preIsolated case, not a check that "
        "silently reads as universal"
    )


def test_helper_uses_ls_remote_not_a_local_tracking_ref():
    """Regression guard for the H1/F2 code-review finding: `git fetch` (no `--prune`) never
    drops stale local remote-tracking refs, so `git rev-parse --verify origin/{branch}`
    would false-positive against a branch merged-and-deleted in an earlier batch. `git
    ls-remote` queries the server directly and has no such staleness class."""
    section = _helper_source()
    assert "ls-remote --exit-code --heads origin" in section, (
        "expected the check to use `git ls-remote --exit-code --heads origin`, not a local "
        "remote-tracking-ref lookup"
    )
    assert "rev-parse --verify" not in section, (
        "expected the stale-ref-prone `git rev-parse --verify origin/...` form to be gone "
        "entirely, not left alongside the new ls-remote check"
    )
    assert "skill-eval-" in section


def test_helper_handles_all_three_exit_codes_distinctly():
    """`git ls-remote --exit-code` is a three-way result (0 = found, 2 = not found, other =
    real failure), not a boolean — a naive 'if it found nothing, proceed' reading conflates
    'confirmed absent' with 'could not check', which silently defeats the check exactly
    when the remote is unreachable."""
    section = _helper_source()
    assert "exit 2" in section.lower() and "exit 0" in section.lower(), (
        "expected the two defined exit codes (0 and 2) to be handled explicitly and "
        "distinctly"
    )
    assert "any other exit code" in section.lower(), (
        "expected a third, explicit branch for any other exit code (network/auth failure) "
        "— an unverifiable state must not be read as safe"
    )
    assert "not a pass" in section.lower(), (
        "expected an explicit statement that an incomplete check does not count as a pass"
    )


def test_helper_stops_without_guessing_a_reconciliation():
    section = _helper_source()
    assert "STOP" in section, (
        "expected an explicit STOP instruction when the branch already exists on origin"
    )
    assert "no merge, no rebase, no force-push" in section.lower(), (
        "expected an explicit prohibition on guessing a reconciliation strategy — the "
        "confirmed incident was an undocumented, ad hoc merge-commit reconciliation; the "
        "fix must not just replace that with a different unguided freelance recovery"
    )


def test_helper_sets_stopped_early_with_a_distinct_reason():
    """Regression guard for a code-review finding: without stoppedEarly, the batch's
    circuit breaker (which counts skills that self-report stoppedEarly) never trips on a
    systemic fault (e.g. a concurrent duplicate batch) that will recur for every remaining
    skill — the batch grinds through all of them producing the same STOP each time."""
    section = _helper_source()
    assert "stoppedEarly: true" in section, (
        "expected the STOP path(s) to set stoppedEarly: true so the circuit breaker works"
    )
    assert "stopReason: 'remote_branch_exists'" in section, (
        "expected a distinct, named stopReason for the branch-already-exists case"
    )


def test_helper_flags_needs_human_review_not_a_silent_stop():
    section = _helper_source()
    assert "needsHumanReview" in section, (
        "expected the STOP to produce a needsHumanReview entry naming the unexpected "
        "pre-existing branch, not just abort silently"
    )


def test_helper_forbids_advancing_status_md_on_a_blocked_push():
    """Regression guard for a code-review finding: without this, Stage C's bookkeeping
    step could still mark this skill's Simulated/Live symbols done in STATUS.md even though
    no PR exists — making it permanently unreselectable by any future batch (STATUS.md says
    done, but there's nothing to review or merge)."""
    section = _helper_source()
    assert "do not advance this skill's simulated/live symbols in status.md" in section.lower(), (
        "expected an explicit prohibition on marking this skill's STATUS.md row done when "
        "the push itself was blocked"
    )


def test_helper_states_the_expected_case_proceeds_normally():
    section = _helper_source()
    assert "proceed with the push" in section.lower(), (
        "expected an explicit statement that finding nothing is the expected case and "
        "the push proceeds normally, so the check doesn't read as blocking every push"
    )


def test_prepush_check_interpolated_in_both_commit_branches():
    """Both branches push (the normal reviewed path, and the stopped-early AS-IS path) —
    the check must guard both, not just one, the same gap issue #64's sibling fix
    (test_stage_c_pr_bypass_not_flagged.py) already found and fixed for the bypass note."""
    section = _stage_c_source()
    occurrences = section.count("prePushExistenceCheck(skillName, preIsolated)")
    assert occurrences >= 2, (
        f"expected at least 2 interpolations of prePushExistenceCheck(skillName, "
        f"preIsolated) (one per commit branch that pushes), found {occurrences}"
    )


def test_check_runs_after_commit_before_push_in_normal_branch():
    section = _stage_c_source()
    commit_pos = section.find("git add -A\\` again")
    assert commit_pos != -1, "expected to find the normal branch's re-add-then-commit step"
    check_pos = section.find("prePushExistenceCheck(skillName, preIsolated)", commit_pos)
    push_pos = section.find(
        "Use the PR-creation mechanism the plugin playbook's repo facts specify", commit_pos
    )
    assert check_pos != -1 and push_pos != -1
    assert commit_pos < check_pos < push_pos, (
        "expected commit -> pre-push check -> push/PR ordering in the normal branch"
    )


def test_check_runs_after_commit_before_push_in_stopped_early_branch():
    section = _stage_c_source()
    stopped_early_start = section.find("Staged, but Stage A stopped early")
    assert stopped_early_start != -1
    check_pos = section.find("prePushExistenceCheck(skillName, preIsolated)", stopped_early_start)
    mandatory_pos = section.find("**Mandatory:**", stopped_early_start)
    assert check_pos != -1 and mandatory_pos != -1
    assert stopped_early_start < check_pos < mandatory_pos, (
        "expected the stopped-early branch's own push to also run the pre-push check, "
        "before the closing mandatory needsHumanReview bookkeeping step"
    )
