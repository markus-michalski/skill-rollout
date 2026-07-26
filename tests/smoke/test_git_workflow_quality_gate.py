"""Smoke: workflows/skill-rollout.js's 3-stage per-skill pipeline (issue #13)
must actually wire an independent reviewer between staging and committing —
not just promise that "code review findings get fixed".

History: the original single-agent design (pre-#12) never actually invoked
`git-pr-workflows:git-workflow`, and its "autonomous mode" section never told
the agent HOW to produce a review in the first place (mm-skills batch,
PRs #23-25, 2026-07-22, see memory project_skill_rollout_git_workflow_bypass).
Issue #12 replaced the aspirational prose with a rigorous MANUAL self-review
procedure, since the Task/Agent tool is unavailable from within a workflow
agent() call (nested agent-spawning refused by the Workflow tool boundary).

Issue #13 (this file's current target) supersedes that manual-self-review
design with a REAL independent reviewer: the per-skill rollout is now three
sibling agent() calls — Stage A (evalAndEditPrompt: eval + edit, stages but
never commits), Stage B (reviewPrompt: independent review of the staged
diff, run via `agentType: 'git-pr-workflows:code-reviewer'`), Stage C
(commitPrompt: applies non-security findings, commits, pushes, opens the PR,
and does the loop-log/STATUS.md/batch-digest bookkeeping). Stage B's
agentType call is a TOP-LEVEL sibling call in the workflow script, not a
nested spawn from inside another agent — the harness constraint that broke
issue #12's original design does not apply to this shape.

The tests below guard the new 3-stage pipeline's invariants.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_JS = ROOT / "workflows" / "skill-rollout.js"


def _normalize(text):
    # Prompt text wraps across lines for readability — collapse whitespace so
    # a line-wrap alone (as opposed to a semantic reword) never breaks a
    # substring/sequence assertion below.
    return re.sub(r"\s+", " ", text)


def _source():
    return WORKFLOW_JS.read_text(encoding="utf-8")


def _slice_between(src, start_marker, end_marker):
    start = src.find(start_marker)
    end = src.find(end_marker)
    assert start != -1, (
        f"expected to find {start_marker!r} in workflows/skill-rollout.js"
    )
    assert end != -1 and end > start, (
        f"expected to find {end_marker!r} after {start_marker!r} "
        "in workflows/skill-rollout.js"
    )
    return src[start:end]


def _stage_a_source():
    return _normalize(
        _slice_between(
            _source(), "function evalAndEditPrompt(", "function reviewPrompt("
        )
    )


def _stage_b_source():
    return _normalize(
        _slice_between(_source(), "function reviewPrompt(", "function commitPrompt(")
    )


def _stage_c_source():
    return _normalize(
        _slice_between(_source(), "function commitPrompt(", "phase('Select')")
    )


def _rollout_loop_source():
    return _normalize(_slice_between(_source(), "phase('Rollout')", "phase('Digest')"))


def test_review_stage_uses_a_real_independent_reviewer_agenttype():
    """Regression guard for the core issue #13 fix: Stage B must actually spawn
    an independent `git-pr-workflows:code-reviewer` agent via the Workflow
    tool's own top-level `agentType` fan-out — not a nested Task/Agent spawn
    (the mechanism issue #12 proved broken), and not a manual self-review
    prose substitute (issue #12's interim fix, now superseded)."""
    loop = _rollout_loop_source()
    assert "agentType: 'git-pr-workflows:code-reviewer'" in loop, (
        "expected the review stage's agent() call to use "
        "agentType: 'git-pr-workflows:code-reviewer' — a top-level sibling "
        "call, not a nested spawn from inside another agent"
    )
    review_call_idx = loop.find("agentType: 'git-pr-workflows:code-reviewer'")
    review_prompt_idx = loop.find("reviewPrompt(")
    assert review_prompt_idx != -1 and review_prompt_idx < review_call_idx, (
        "agentType: 'git-pr-workflows:code-reviewer' must be attached to the "
        "reviewPrompt(...) agent() call, not some other stage"
    )


def test_stage_b_runs_before_stage_c_in_actual_control_flow():
    """Stronger than a prose-order check: Stage B (review) must be invoked
    before Stage C (commit) in the real control flow of the rollout loop, not
    just described in that order in a comment — a future edit that reordered
    the two calls would still pass a pure string-order-in-prose check."""
    loop = _rollout_loop_source()
    review_idx = loop.find("await agent(reviewPrompt(")
    commit_call_idx = loop.find("commitPrompt(")
    assert review_idx != -1, (
        "expected Stage B's `await agent(reviewPrompt(...))` call in the rollout loop"
    )
    assert commit_call_idx != -1, (
        "expected Stage C's commitPrompt(...) call in the rollout loop"
    )
    assert review_idx < commit_call_idx, (
        "Stage B (review) must be invoked before Stage C (commit) in the "
        "actual control flow — review must gate the commit, not follow it"
    )


def test_review_stage_is_skipped_only_when_nothing_was_staged():
    """Stage B must be conditional on Stage A actually having staged
    something — an unconditional Stage B call would burn an agent call
    reviewing an empty diff on every early-exit skill."""
    loop = _rollout_loop_source()
    assert "editResult.hasChanges && !editResult.stoppedEarly" in loop, (
        "expected the review stage to be gated on "
        "'editResult.hasChanges && !editResult.stoppedEarly'"
    )


def test_stage_c_always_runs_even_on_early_exit():
    """Regression guard for a deliberate deviation from issue #13's literal
    pseudocode: Stage C (which also does loop-log/STATUS.md/batch-digest
    bookkeeping) must run for EVERY skill, including early-exits — skipping
    it entirely on early-exit would silently drop that bookkeeping write."""
    loop = _rollout_loop_source()
    edit_call_idx = loop.find("editResult = await agent(")
    commit_call_idx = loop.find("commitPrompt(")
    assert edit_call_idx != -1 and commit_call_idx != -1
    assert edit_call_idx < commit_call_idx
    between = loop[edit_call_idx:commit_call_idx]
    assert "continue" not in between, (
        "found a `continue` between Stage A and Stage C's call — Stage C "
        "must always run (it owns the bookkeeping write), branching "
        "internally on editResult.hasChanges instead of being skipped"
    )


def test_stage_a_stages_but_never_commits():
    section = _stage_a_source()
    assert "git add -A" in section, "Stage A must stage changes via `git add -A`"
    assert "do NOT commit" in section, (
        "Stage A must explicitly instruct not to commit — that is Stage C's job"
    )


def test_stage_b_mandates_concrete_review_criteria():
    """Regression guard for the original aspirational-prose failure mode: the
    review step must list explicit, concrete categories to check — not just
    say 'do a review' and let the agent decide what that means."""
    section = _stage_b_source()
    for category in (
        "Logic/correctness",
        "SKILL.md structural compliance",
        "Eval design quality",
        "Data hygiene",
        "Cross-file consistency",
    ):
        assert category in section, (
            f"Stage B's prompt must list '{category}' as an explicit category "
            "to check — vague 'do a review' instructions reproduce the "
            "original aspirational-prose failure"
        )


def test_stage_b_is_read_only():
    section = _stage_b_source()
    assert "Do NOT edit any files" in section
    assert "Do NOT run" in section and "git add" in section and "git commit" in section


def test_stage_b_checks_untracked_files_not_just_git_diff():
    """Regression guard for the 'blind review of new files' failure mode:
    git diff HEAD alone misses brand-new untracked files, which this rollout
    routinely creates (fixtures, eval docs, tests)."""
    section = _stage_b_source()
    assert "git diff HEAD" in section
    assert "git status --porcelain" in section, (
        "expected Stage B to also check `git status --porcelain` — `git diff "
        "HEAD` alone misses brand-new untracked files"
    )


def test_stage_c_requires_fixing_all_severities_before_commit():
    section = _stage_c_source()
    # Word-boundary-safe regex, not a bare substring — matches the original
    # test's intent of guarding against silently dropped severity language.
    assert re.search(r"critical/high/medium/low", section), (
        "Stage C must still require fixing every severity (critical..low)"
    )
    fix_idx = section.find("Fix every non-security finding")
    commit_idx = section.find("git commit")
    assert fix_idx != -1 and commit_idx != -1 and fix_idx < commit_idx, (
        "fixing findings must be instructed before the commit step"
    )


def test_stage_c_requires_a_second_pass_after_fixes():
    """A future edit that deletes the re-read/re-confirm step entirely must
    fail here — a single-pass review with no post-fix verification lets
    fix-induced regressions through."""
    section = _stage_c_source()
    assert "Re-read every file your fixes touched" in section, (
        "expected an explicit second-pass verification step after applying "
        "fixes — a single-pass review lets fix-induced regressions through"
    )


def test_stage_c_scopes_the_defer_allowance_to_the_re_review_pass():
    """Regression guard: the 'note remaining low-severity items instead of
    chasing further' allowance must be scoped to NEW findings surfaced by the
    re-review pass, never to Stage B's original findings."""
    section = _stage_c_source()
    assert "ONLY to items surfaced by THIS re-review pass" in section, (
        "the defer-allowance must be explicitly scoped to the re-review pass, "
        "not left ambiguous between Stage B's findings and second-round ones"
    )


def test_stage_c_never_forwards_security_findings_for_self_fix():
    """Regression guard: security/credential/data-loss findings must never
    reach the 'fix these' instruction. This is now a STRUCTURAL guarantee
    (filtered out of the findings list in JS before the prompt is even
    built) rather than a prose EXCEPT clause an agent has to correctly
    parse — stronger than the original design."""
    section = _stage_c_source()
    assert "isSecurityRisk" in section, (
        "Stage C must filter review findings on isSecurityRisk before "
        "building the 'fix these' instruction"
    )
    assert "do NOT self-fix" in section, (
        "Stage C must explicitly instruct that flagged security findings are "
        "not to be self-fixed"
    )
    assert "needsHumanReview" in section


def test_stage_c_never_self_merge_limit_present():
    """Cheap regression guard for a pre-existing, safety-critical invariant:
    an unattended agent must never self-approve or self-merge a PR, no
    matter how autonomous everything upstream of it is."""
    section = _stage_c_source()
    assert "never self-approve or self-merge a PR" in section, (
        "the hard 'never self-merge' limit must remain present in Stage C's prompt"
    )


def test_stage_c_step_order_fix_then_reread_then_commit():
    """Regression guard beyond the pairwise checks above: the three steps
    must appear in this exact relative order — fix findings, second-pass
    re-read, commit. A future edit that swapped the fix and re-read steps
    would pass every pairwise 'before commit' check individually while
    still being wrong."""
    section = _stage_c_source()
    fix_idx = section.find("Fix every non-security finding")
    re_review_idx = section.find("Re-read every file your fixes touched")
    commit_idx = section.find("git commit")
    assert -1 not in (fix_idx, re_review_idx, commit_idx), (
        f"expected all three step markers present: fix={fix_idx}, "
        f"re-read={re_review_idx}, commit={commit_idx}"
    )
    assert fix_idx < re_review_idx < commit_idx, (
        f"expected order fix({fix_idx}) < re-read({re_review_idx}) < "
        f"commit({commit_idx}), got a different relative order"
    )


def test_stage_c_falls_back_to_manual_review_if_stage_b_failed():
    """Regression guard: if Stage B's agent() call itself throws (harness or
    transient error, distinct from Stage B running successfully and finding
    nothing), Stage C must NOT silently commit an unreviewed diff — that
    would be worse than the pre-#13 manual-self-review design. It must fall
    back to performing the same review itself before committing."""
    section = _stage_c_source()
    assert "reviewFailed" in section, (
        "Stage C's prompt builder must branch on a reviewFailed flag"
    )
    assert "Do NOT commit on an unreviewed diff" in section, (
        "expected an explicit instruction not to commit when the independent "
        "review never ran"
    )
    # The fallback path must reuse the same five review categories as Stage B,
    # not a watered-down ad hoc check.
    for category in (
        "Logic/correctness",
        "SKILL.md structural compliance",
        "Eval design quality",
        "Data hygiene",
        "Cross-file consistency",
    ):
        assert category in section, (
            f"Stage C's manual-review fallback must cover '{category}', same "
            "as Stage B's own criteria"
        )


def test_rollout_loop_tracks_review_failure_and_passes_it_to_stage_c():
    loop = _rollout_loop_source()
    assert "reviewFailed = true" in loop, (
        "expected the loop to set reviewFailed=true in Stage B's catch block"
    )
    commit_call_idx = loop.find("commitPrompt(")
    args_marker = loop.find("editResult, reviewResult, reviewFailed")
    commit_call_end = loop.find(")", args_marker)
    assert "reviewFailed" in loop[commit_call_idx : commit_call_end + 1], (
        "expected the commitPrompt(...) call to pass reviewFailed through"
    )


def test_stage_c_never_commits_a_diff_stage_b_did_not_review():
    """Regression guard for code-review finding H1: Stage C used to gate its
    commit branch on `editResult.hasChanges` alone, while Stage B's review
    gate was `hasChanges && !stoppedEarly` — so a `hasChanges: true,
    stoppedEarly: true` result skipped review but still auto-committed,
    silently defeating the whole point of this pipeline. Stage C must
    recognize this exact combination as a distinct case and commit (if at
    all) only with an explicit unreviewed-diff flag, never silently folded
    into the normal reviewed-and-clean commit path."""
    section = _stage_c_source()
    assert "editResult.hasChanges && !editResult.stoppedEarly" in section, (
        "expected Stage C's normal (reviewed) commit branch to be gated on "
        "the SAME condition as Stage B's review gate"
    )
    assert "commit AS-IS, unreviewed, and flag it loudly" in section, (
        "expected a distinct branch for hasChanges && stoppedEarly that "
        "commits unreviewed work only with an explicit, loud flag — not "
        "silently treated as reviewed"
    )
    stopped_branch_idx = section.find("commit AS-IS, unreviewed, and flag it loudly")
    normal_branch_idx = section.find("Apply the review's findings, then commit")
    assert -1 not in (stopped_branch_idx, normal_branch_idx), (
        "expected both the normal and the stopped-early commit branches to "
        "be present as distinct sections"
    )
