"""Smoke: every skill-evals commit point mandates scoped add + scoped commit
+ safe push-retry (issue #20).

`~/projekte/skill-evals` is a single git repo SHARED across every rollout-
target plugin, with no worktree isolation (unlike pluginRepoPath, which
preIsolated/EnterWorktree already protects). Two rollout sessions running
concurrently against DIFFERENT plugins still share this one repo's working
tree, index, and HEAD.

A code-review pass on the first draft of this fix (issue #20) found the
original "scoped add" rule alone was NOT sufficient: a plain `git commit`
snapshots the whole shared index, not just the paths a scoped `git add`
staged — a concurrent session's own staged files could still be swept into
your commit. The fix requires a SCOPED COMMIT too (`git commit -- <path>`),
plus explicit handling for index-lock contention and a rebase REFUSAL
(another session's in-flight uncommitted work in the shared tree) as
distinct from a rebase CONFLICT (real content overlap) — the former must
retry, never "clean up" with stash/checkout/reset, which would destroy the
other session's work.

Regression guard for the workflow script (workflows/skill-rollout.js) and
the two reference docs that generate/document per-plugin playbooks.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_JS = ROOT / "workflows" / "skill-rollout.js"
SELF_IMPROVING_SKILLS = ROOT / "reference" / "self-improving-skills.md"
ONBOARD_PLAYBOOK = ROOT / "reference" / "prompt-self-improving-skill-playbook.md"


def _normalize(text):
    return re.sub(r"\s+", " ", text)


def _workflow_raw():
    return WORKFLOW_JS.read_text(encoding="utf-8")


def _slice(src, start_marker, end_marker):
    start = src.find(start_marker)
    end = src.find(end_marker, start)
    assert start != -1, f"expected to find {start_marker!r}"
    assert end != -1 and end > start, (
        f"expected to find {end_marker!r} after {start_marker!r}"
    )
    return src[start:end]


def test_skill_evals_git_safety_helper_defined_once():
    """The rule must be a single shared function, not copy-pasted per call
    site — copy-paste invites the two copies drifting apart over time."""
    src = _workflow_raw()
    definitions = re.findall(r"function skillEvalsGitSafety\(", src)
    assert len(definitions) == 1, (
        f"expected exactly one skillEvalsGitSafety definition, found {len(definitions)}"
    )


def _helper_source():
    """Slice just skillEvalsGitSafety's own function body, so this test
    can't accidentally pass by matching one of the OTHER `git add -A`
    mentions in the file (pluginRepoPath's own staging steps)."""
    src = _workflow_raw()
    return _normalize(_slice(src, "function skillEvalsGitSafety(", "\n}\n"))


def test_skill_evals_git_safety_helper_scopes_the_commit_not_just_the_add():
    """Regression guard for a code-review HIGH finding: a scoped `git add`
    alone does NOT stop a plain `git commit` from also picking up a
    concurrent session's own staged files, since `git commit` snapshots the
    whole shared index. The commit itself must be path-scoped too."""
    text = _helper_source()
    assert "git commit --" in text, (
        "expected the pathspec-scoped commit form (`git commit -- <path>`), "
        "not a bare `git commit`, which would snapshot the whole shared index"
    )
    assert "a scoped add only controls what YOU staged" in text, (
        "expected the helper to explicitly explain WHY a scoped add alone "
        "is insufficient — this is the specific misconception the "
        "code-review pass caught in the first draft"
    )


def test_skill_evals_git_safety_helper_never_allows_blind_add():
    text = _helper_source()
    assert "git add -A" in text, (
        "expected an explicit prohibition of `git add -A` for skill-evals commits"
    )


def test_skill_evals_git_safety_helper_retries_on_index_lock():
    text = _helper_source()
    assert "index.lock" in text, (
        "expected explicit index-lock-contention handling (a concurrent "
        "session mid-operation, not a real error)"
    )


def test_skill_evals_git_safety_helper_distinguishes_rebase_refusal_from_conflict():
    """Regression guard for a code-review HIGH finding: `git pull --rebase`
    can be REFUSED because the shared working tree has another session's
    uncommitted changes sitting in it — a different, transient failure mode
    from a genuine content CONFLICT, and the two must be handled
    differently (retry vs. stop-and-flag)."""
    text = _helper_source()
    assert "refuses because the shared working tree has uncommitted" in text, (
        "expected the helper to explicitly cover the rebase-refusal case, "
        "distinct from a real conflict"
    )
    assert "reports an actual conflicting hunk" in text, (
        "expected the helper to explicitly cover the real-conflict case "
        "as a SEPARATE branch from the refusal case"
    )


def test_skill_evals_git_safety_helper_forbids_destructive_cleanup():
    """A concurrent session's uncommitted work sitting in the shared tree
    must never be "cleaned up" — that IS the other session's real work."""
    text = _helper_source()
    for forbidden in ("git stash", "git checkout -- .", "git reset --hard"):
        assert forbidden in text, (
            f"expected the helper to explicitly name-and-forbid {forbidden!r} "
            "as a destructive recovery command"
        )


def test_skill_evals_git_safety_helper_never_force_pushes():
    text = _helper_source()
    assert "git push --force" in text, "expected an explicit prohibition of force-push"


def test_skill_evals_git_safety_used_in_stage_a_eval_and_edit_prompt():
    src = _workflow_raw()
    section = _slice(src, "function evalAndEditPrompt(", "function reviewPrompt(")
    assert "skillEvalsGitSafety(" in section, (
        "expected Stage A (evalAndEditPrompt) to interpolate skillEvalsGitSafety(...) "
        "— it commits evals.json and loop-log/loop-state into skillEvalsDir"
    )


def test_skill_evals_git_safety_used_in_stage_c_commit_prompt():
    src = _workflow_raw()
    section = _slice(src, "function commitPrompt(", "phase('Select')")
    assert "skillEvalsGitSafety(" in section, (
        "expected Stage C (commitPrompt) to interpolate skillEvalsGitSafety(...) "
        "— its Bookkeeping section commits the closing skill-evals entries"
    )


def test_skill_evals_git_safety_used_in_onboard_phase():
    src = _workflow_raw()
    section = _slice(src, "phase('Onboard')", "phase('Rollout')")
    assert "skillEvalsGitSafety(" in section, (
        "expected the Onboard phase to interpolate skillEvalsGitSafety(...) "
        "— it creates and commits STATUS.md/self-improving-skill-{plugin}.md"
    )


def test_select_phase_explicitly_defers_batch_digest_commit_to_stage_c():
    """Regression guard for a code-review HIGH finding: the Select phase
    writes batch-digest.md's opening header but was given NO git-safety
    guidance at all in the first draft — not even a "don't commit here."
    An autonomous agent with no instruction could reasonably decide to
    "tidy up" with an unscoped commit. The fix is an explicit opt-out, not
    a full commit cycle (the first skill's Stage C commit picks it up)."""
    src = _workflow_raw()
    section = _normalize(_slice(src, "phase('Select')", "phase('Onboard')"))
    assert "Do NOT commit this write yourself" in section, (
        "expected the Select phase to explicitly defer the batch-digest.md "
        "commit to the first selected skill's Stage C"
    )


def test_stage_a_boundary_does_not_contradict_skill_evals_commits():
    """Regression guard for a code-review MEDIUM finding: Stage A's
    "you never commit" boundary is about the pluginRepoPath diff — it must
    not read as a blanket ban that also covers the expected evals.json/
    loop-state commits into the separate skillEvalsDir repo."""
    src = _workflow_raw()
    section = _slice(src, "function evalAndEditPrompt(", "function reviewPrompt(")
    section = _normalize(section)
    assert "does NOT apply to" in section, (
        "expected an explicit carve-out clarifying the no-commit boundary "
        "is scoped to pluginRepoPath, not skillEvalsDir"
    )


def test_self_improving_skills_doc_has_git_safety_section():
    text = _normalize(SELF_IMPROVING_SKILLS.read_text(encoding="utf-8"))
    assert "Git-Sicherheit für JEDEN Commit in skill-evals" in text, (
        "expected a dedicated git-safety section in reference/self-improving-skills.md"
    )
    assert "git commit --" in text, (
        "expected the scoped-commit form (not just scoped add) in the German doc too"
    )


def test_self_improving_skills_doc_links_loop_state_writes_to_the_rule():
    """The loop-state.json/loop-log.md example prompt text must point back
    at the git-safety section, not leave readers to infer it applies."""
    text = _normalize(SELF_IMPROVING_SKILLS.read_text(encoding="utf-8"))
    assert "use the scoped-add + scoped-commit + safe-push-retry rule" in text, (
        "expected the loop-state/loop-log section to explicitly reference "
        "the git-safety rule above it"
    )


def test_onboard_playbook_states_hard_requirement_for_prompts_1_and_2():
    """The onboarding meta-prompt template must state the rule as a HARD
    requirement, not just 'same shape as the example' — paraphrasing during
    a real onboarding run could otherwise drop safety-critical wording."""
    text = _normalize(ONBOARD_PLAYBOOK.read_text(encoding="utf-8"))
    assert "Hard requirement on Prompts 1 AND 2" in text, (
        "expected an explicit hard-requirement callout for Prompts 1/2 in "
        "the onboarding playbook template"
    )
    assert "scope BOTH the" in text and "git commit" in text, (
        "expected the scoped-commit (not just scoped-add) rule restated "
        "in the onboard playbook itself"
    )
