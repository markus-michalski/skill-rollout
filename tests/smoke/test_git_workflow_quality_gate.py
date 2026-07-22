"""Smoke: workflows/skill-rollout.js's inline git-workflow section must
concretely require a real code-review pass with defined criteria, not just
promise that "code review findings get fixed".

Regression guard for a journal-verified incident (mm-skills batch, PRs #23-25,
2026-07-22, see memory project_skill_rollout_git_workflow_bypass): the rollout
agent never actually invoked `git-pr-workflows:git-workflow`, and the inline
"autonomous mode" section that was supposed to replace it never told the agent
HOW to produce a code review in the first place — "Any code-review finding ...
gets fixed without asking" presupposes a review that no instruction ever
causes to happen. Zero code-reviewer subagent calls were made; the whole
quality gate was aspirational prose with nothing behind it.

NOTE (issue #12): the Task/Agent tool is unavailable from within a workflow
agent() call, so the review step mandates a rigorous manual self-review with
explicit criteria (logic, SKILL.md structure, eval design, data hygiene,
cross-file consistency) rather than a subagent spawn. The tests below guard
the new manual-review invariants. Option 2 (sibling pipeline stages) is tracked
in issue #13 as the correct long-term fix.
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


def _git_workflow_section():
    src = WORKFLOW_JS.read_text(encoding="utf-8")
    start = src.find("## git-workflow")
    end = src.find("## Stop-and-flag conditions")
    assert start != -1, (
        "expected a '## git-workflow' header in workflows/skill-rollout.js"
    )
    assert end != -1 and end > start, (
        "expected a '## Stop-and-flag conditions' header after '## git-workflow' "
        "in workflows/skill-rollout.js"
    )
    return _normalize(src[start:end])


def _stop_and_flag_section():
    src = WORKFLOW_JS.read_text(encoding="utf-8")
    start = src.find("## Stop-and-flag conditions")
    end = src.find("## Before you finish")
    assert start != -1 and end != -1 and end > start, (
        "expected '## Stop-and-flag conditions' ... '## Before you finish' in "
        "workflows/skill-rollout.js"
    )
    return _normalize(src[start:end])


def test_git_workflow_section_documents_review_limitation_and_reason():
    """The section must document WHY a subagent reviewer is not used (harness
    constraint, not a policy choice) so a future editor knows not to restore
    the broken instruction, and knows the correct fix path (issue #13)."""
    section = _git_workflow_section()
    # Must acknowledge the tool is unavailable (not silently skip, not just do manual
    # review)
    assert "Task/Agent tool" in section, (
        "git-workflow section must mention the Task/Agent tool and explain why it "
        "cannot be used — not silently omit it, which would suggest the review gap "
        "is intentional rather than a harness constraint"
    )
    assert "unavailable" in section, (
        "git-workflow section must state the tool is unavailable, not omit the "
        "explanation — future editors need to know this is a constraint, not a "
        "policy choice to drop independent review"
    )


def test_git_workflow_section_mandates_concrete_review_criteria():
    """Regression guard for aspirational-prose failure mode: the review step
    must list explicit, concrete categories to check — not just say 'do a
    review' and let the agent decide what that means."""
    section = _git_workflow_section()
    # All five mandatory review categories must be present
    for category in ("Logic/correctness", "SKILL.md structural compliance",
                     "Eval design quality", "Data hygiene", "Cross-file consistency"):
        assert category in section, (
            f"review step must list '{category}' as an explicit category to "
            "check — vague 'do a review' instructions reproduce the original "
            "aspirational-prose failure"
        )


def _final_commit_step_idx(section):
    # The actual "now go commit" action step, not just any incidental use of
    # the word "commit" earlier in the prose (e.g. "before any commit:").
    idx = section.find("Only then:")
    assert idx != -1, "expected an explicit final 'Only then: commit/push/PR' step"
    return idx


def test_git_workflow_section_requires_review_before_commit():
    """The review pass (whether subagent or manual) must be instructed BEFORE
    the final commit step — the review must gate the commit, not follow it."""
    section = _git_workflow_section()
    # Use the manual review instruction as the review marker (issue #12: subagent
    # unavailable)
    review_idx = section.find("rigorous manual code-review pass")
    commit_idx = _final_commit_step_idx(section)
    assert review_idx != -1 and review_idx < commit_idx, (
        "the review instruction ('rigorous manual code-review pass') must appear "
        "BEFORE the final commit step — review must gate the commit, not follow it"
    )


def test_git_workflow_section_requires_fixing_all_severities_before_commit():
    section = _git_workflow_section()
    # Word-boundary regex, not a bare substring check — "low" as a substring
    # is trivially satisfied by unrelated words like "follow-up" or "below",
    # which would let this assertion pass even with all severity language
    # stripped out.
    assert re.search(r"critical/high/medium/low", section), (
        "section must still require fixing every severity (critical..low), "
        "not just the review call itself"
    )
    fix_idx = section.find("Fix every finding")
    commit_idx = _final_commit_step_idx(section)
    assert fix_idx != -1 and fix_idx < commit_idx, (
        "fixing findings must be instructed before the final commit step"
    )


def test_git_workflow_section_requires_a_second_pass_after_fixes():
    """A future edit that deletes the re-read/re-confirm step entirely must fail
    here — a single-pass review with no post-fix verification lets fix-induced
    regressions through (a fix for finding X could introduce finding Y in the
    same file or an adjacent one)."""
    section = _git_workflow_section()
    # The re-read step must be instructed (issue #12: re-run of a subagent replaced
    # with re-read of touched files — the invariant is a SECOND verification pass,
    # not the mechanism used to perform it)
    assert "Re-read all files your fixes touched" in section, (
        "expected an explicit second-pass verification step after applying fixes — "
        "a single-pass review lets fix-induced regressions through"
    )


def test_git_workflow_section_carves_out_security_findings_to_stop_and_flag():
    """Regression guard: Step 2's 'fix every finding, do not defer' rule must
    not silently override the Stop-and-flag rule that security/credential/
    data-loss findings get flagged for human review, not self-fixed-and-shipped
    by an unattended agent."""
    section = _git_workflow_section()
    assert "Stop-and-flag conditions" in section, (
        "the fix-everything step must explicitly reference the Stop-and-flag "
        "carve-out, otherwise the two sections silently contradict each other "
        "for a security/credential finding"
    )
    stop_and_flag = _stop_and_flag_section()
    assert "security/credential/data-loss" in stop_and_flag, (
        "expected the security/credential/data-loss category to still exist in "
        "Stop-and-flag conditions for the git-workflow section's carve-out to "
        "actually point at something real"
    )


def test_git_workflow_section_scopes_the_defer_allowance_to_the_re_review_pass():
    """Regression guard: the 'note remaining low-severity items instead of
    chasing further' allowance must be scoped to NEW findings surfaced by the
    re-review pass, never to the first-round findings from Step 2 — otherwise
    an agent can quietly relabel an unfixed first-round finding as 'chose not
    to chase' and reintroduce the original bug in miniature."""
    section = _git_workflow_section()
    assert "ONLY to low-severity items surfaced by THIS re-review pass" in section, (
        "the defer-allowance must be explicitly scoped to the re-review pass, "
        "not left ambiguous between first-round and second-round findings"
    )


def test_git_workflow_section_full_chain_step_order():
    """Regression guard beyond the pairwise review-before-commit and
    fix-before-commit checks above: the four steps must appear in this exact
    relative order — initial review, fix, second pass, commit. A future edit
    that swapped step 2 and 3 (fix findings AFTER the confirmation re-read,
    instead of before it) would pass every pairwise "before commit" check
    individually while still being wrong."""
    section = _git_workflow_section()
    # issue #12: "git-pr-workflows:code-reviewer" replaced by "rigorous manual
    # code-review pass"
    initial_review_idx = section.find("rigorous manual code-review pass")
    fix_idx = section.find("Fix every finding")
    # issue #12: "Re-run" (subagent) replaced by "Re-read all files your fixes touched"
    re_review_idx = section.find("Re-read all files your fixes touched")
    commit_idx = _final_commit_step_idx(section)
    assert -1 not in (initial_review_idx, fix_idx, re_review_idx, commit_idx), (
        "expected all four step markers to be present in the section: "
        f"initial-review={initial_review_idx}, fix={fix_idx}, "
        f"re-read={re_review_idx}, commit={commit_idx}"
    )
    assert initial_review_idx < fix_idx < re_review_idx < commit_idx, (
        f"expected step order initial-review({initial_review_idx}) < "
        f"fix({fix_idx}) < re-read({re_review_idx}) < commit({commit_idx}), "
        "got a different relative order"
    )


def test_git_workflow_section_except_clause_is_syntactically_attached_to_fix_step():
    """Regression guard: the security/credential/data-loss carve-out must be
    grammatically attached to the fix-everything instruction via an explicit
    'EXCEPT', not just have both halves exist as independent substrings
    somewhere in the section — a degenerate edit that merged the two clauses
    with ', but ALSO' instead of 'EXCEPT' would invert the meaning while still
    satisfying test_..._carves_out_security_findings_to_stop_and_flag above."""
    section = _git_workflow_section()
    assert re.search(
        r"EXCEPT the categories listed under \"Stop-and-flag conditions\"", section
    ), (
        "expected the fix-everything step to say 'EXCEPT the categories listed "
        "under \"Stop-and-flag conditions\"' verbatim — not just have both "
        "phrases appear independently somewhere in the section"
    )


def test_git_workflow_section_never_self_merge_limit_present():
    """Cheap regression guard for a pre-existing, safety-critical invariant
    that sits in the same section this bugfix touches and had zero test
    coverage: an unattended agent must never self-approve or self-merge a PR,
    no matter how autonomous everything upstream of it is."""
    section = _git_workflow_section()
    assert "never self-approve or self-merge a PR" in section, (
        "the hard 'never self-merge' limit must remain present in the "
        "git-workflow section"
    )


def test_git_workflow_section_requires_staging_untracked_files_before_review():
    """Regression guard for the 'blind review of new files' failure mode
    fixed during code review: git diff HEAD alone misses brand-new untracked
    files, which this rollout routinely creates (fixtures, eval docs, tests)."""
    section = _git_workflow_section()
    assert "git add -A && git diff HEAD" in section, (
        "expected the review step to stage untracked files first (or "
        "otherwise ensure new files aren't invisible to the code-reviewer "
        "subagent) — git diff HEAD alone misses brand-new files"
    )
