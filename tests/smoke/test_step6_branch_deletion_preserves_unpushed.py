"""Smoke: `run`'s Step 6 must not force-delete a local `skill-eval-*` branch that was
never confirmed pushed to origin (issue #64 follow-up).

Regression guard for a code-review finding on issue #64's own fix: `prePushExistenceCheck`
(workflows/skill-rollout.js) can leave a skill's commit sitting purely LOCAL — deliberately
unpushed — with an explicit `needsHumanReview` entry promising a human that commit is still
there to reconcile. Step 6's teardown used to force-delete EVERY local `skill-eval-*`
branch unconditionally (`for-each-ref ... | xargs ... branch -D`), which would silently
destroy exactly that promised, unpushed commit — the only copy of it — turning a "sitting
locally, pending reconciliation" flag into permanent data loss with no trace.

The fix compares each local branch's tip SHA against the same-named branch on origin and
only force-deletes on an exact match (confirmed pushed); anything else is kept and
reported. It also guards the no-`origin`-remote case (a flat, non-GitHub skill-collection
repo — mm-skills is the reference case) so that structural absence doesn't get reported as
N individual reconciliation warnings, one per branch, every single run.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN_SKILL = ROOT / "skills" / "run" / "SKILL.md"
WORKFLOW_JS = ROOT / "workflows" / "skill-rollout.js"


def _normalize(text):
    return re.sub(r"\s+", " ", text)


def _step6_source():
    src = RUN_SKILL.read_text(encoding="utf-8")
    idx = src.find("## Step 6:")
    assert idx != -1, "expected to find '## Step 6:' in skills/run/SKILL.md"
    return src[idx:]


def test_step6_has_no_unconditional_branch_delete_of_all_skill_eval_branches():
    """The old bug: every local skill-eval-* branch was force-deleted with no check at
    all — regardless of whether it was ever pushed."""
    section = _step6_source()
    assert "xargs -r git" not in section and "branch -D\"" not in section, (
        "expected the old unconditional `for-each-ref | xargs ... branch -D` pipeline to "
        "be gone — it deleted every local skill-eval-* branch with no pushed-confirmation "
        "check at all"
    )


def test_step6_only_deletes_a_branch_confirmed_matching_origin():
    section = _normalize(_step6_source())
    assert "ls-remote --heads origin" in section, (
        "expected the deletion loop to query origin directly per branch via `ls-remote`"
    )
    assert 'local_sha" = "$remote_sha' in section, (
        "expected the deletion to be gated on the local tip SHA matching the remote tip "
        "SHA exactly — anything else means the branch isn't confirmed pushed"
    )


def test_step6_guards_the_no_origin_remote_case():
    """A flat skill-collection repo (mm-skills is the reference case, per this plugin's
    own CLAUDE.md) legitimately has no GitHub remote — without this guard, every
    `ls-remote` call would fail for that structural reason alone, and every local
    skill-eval-* branch would be reported as an individual reconciliation warning, every
    single run, which is noise rather than signal."""
    section = _step6_source()
    assert "remote get-url origin" in section, (
        "expected an upfront check for whether an origin remote exists at all, before "
        "looping per-branch"
    )
    assert "expected for a flat, non-github" in section.lower() or "expected for a flat" in section.lower(), (
        "expected the no-origin case to be reported as one honest structural note, not as "
        "N per-branch reconciliation warnings"
    )


def test_step6_kept_branches_are_reported_not_silently_left():
    section = _step6_source()
    assert "KEEPING" in section, (
        "expected a kept (not-confirmed-pushed) branch to be explicitly reported, not "
        "just silently skipped"
    )
    assert "add it to this step's own report" in section.lower(), (
        "expected an explicit instruction to surface kept branches to the operator, same "
        "as a teardown-time rescue branch"
    )


def test_deletion_loop_defaults_to_keep_not_delete_on_missing_data():
    """Regression guard: the comparison must degrade toward safety. An empty
    `remote_sha` (ls-remote failed, no matching branch, or no origin at all) must fail the
    `-n` check and land in the KEEPING branch, never in the deletion branch — a bug here
    would flip an "I couldn't verify" state into "confirmed safe to delete", the exact
    failure class this fix exists to prevent."""
    section = _normalize(_step6_source())
    delete_pos = section.find('branch -D "$b"')
    keeping_pos = section.find("KEEPING $b")
    guard_pos = section.find('[ -n "$remote_sha" ]')
    assert delete_pos != -1 and keeping_pos != -1 and guard_pos != -1
    assert guard_pos < delete_pos < keeping_pos, (
        "expected the non-empty-remote_sha guard to gate the delete branch, with the "
        "KEEPING branch as the else/fallback"
    )


def test_is_valid_skill_slug_defined_once():
    src = WORKFLOW_JS.read_text(encoding="utf-8")
    definitions = re.findall(r"function isValidSkillSlug\(", src)
    assert len(definitions) == 1, (
        f"expected exactly one isValidSkillSlug definition, found {len(definitions)}"
    )


def test_is_valid_skill_slug_wired_into_the_dedupe_filter():
    """Regression guard: defining isValidSkillSlug is not the fix — it must actually gate
    what reaches skillsToProcess (and from there, shell-interpolated agent prompts), not
    sit unused alongside the filter."""
    src = WORKFLOW_JS.read_text(encoding="utf-8")
    filter_start = src.find("skillsToProcess = skillsToProcess.filter(")
    assert filter_start != -1, "expected to find the skillsToProcess dedupe filter"
    filter_section = src[filter_start:filter_start + 500]
    assert "isValidSkillSlug(" in filter_section, (
        "expected isValidSkillSlug(...) to be called inside the dedupe filter, not just "
        "defined and left unused"
    )
    assert "batchNotes.push" in filter_section, (
        "expected an invalid name to be recorded in batchNotes, not silently dropped with "
        "no trace"
    )
