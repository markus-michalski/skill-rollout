"""Smoke: `run`'s Step 3 must not silently discard a dirty rollout worktree
left behind by an interrupted prior batch (issue #57).

Step 3 unconditionally ran `git worktree remove --force` on any stale
`{plugin}-rollout-wt` before creating a fresh one. If a previous batch left a
real, already-verified diff staged-but-uncommitted there — e.g. because Stage
C received a wrong `hasChanges:false` handoff and skipped committing — that
diff was destroyed with no warning and no recovery path. This happened for
real on 2026-07-28 against mm-dev-toolkit; the diff was only recoverable by
luck via `git fsck --dangling` because it happened to already be staged.

Regression guard for skills/run/SKILL.md Step 3.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN_SKILL = ROOT / "skills" / "run" / "SKILL.md"


def _normalize(text):
    return re.sub(r"\s+", " ", text)


def _slice(src, start_marker, end_marker):
    start = src.find(start_marker)
    end = src.find(end_marker, start)
    assert start != -1, f"expected to find {start_marker!r}"
    assert end != -1 and end > start, (
        f"expected to find {end_marker!r} after {start_marker!r}"
    )
    return src[start:end]


def _step3_source():
    src = RUN_SKILL.read_text(encoding="utf-8")
    return _normalize(_slice(src, "## Step 3:", "## Step 4:"))


def _step6_source():
    src = RUN_SKILL.read_text(encoding="utf-8")
    idx = src.find("## Step 6:")
    assert idx != -1, "expected to find '## Step 6:' in skills/run/SKILL.md"
    return _normalize(src[idx:])


def _step6_source_raw():
    src = RUN_SKILL.read_text(encoding="utf-8")
    idx = src.find("## Step 6:")
    assert idx != -1, "expected to find '## Step 6:' in skills/run/SKILL.md"
    return src[idx:]


def test_step3_checks_worktree_dirtiness_before_force_removing():
    text = _step3_source()
    assert "status --porcelain" in text, (
        "expected Step 3 to check the existing worktree for uncommitted "
        "changes with `status --porcelain` before removing it"
    )


def test_step3_does_not_unconditionally_force_remove_without_a_dirty_check():
    """The old bug: `worktree remove --force` ran unconditionally, with no
    branch for a dirty vs. clean worktree. Guard that the force-remove now
    only fires after (or gated by) the dirtiness check, not before it."""
    text = _step3_source()
    dirty_check_pos = text.find("status --porcelain")
    force_remove_pos = text.find("worktree remove --force")
    assert dirty_check_pos != -1 and force_remove_pos != -1
    assert dirty_check_pos < force_remove_pos, (
        "expected the dirtiness check to run BEFORE the force-remove, not after"
    )


def test_step3_preserves_dirty_worktree_via_rescue_branch_instead_of_discarding():
    text = _step3_source()
    assert 'RESCUE_NAME="rescue/{plugin}-' in text, (
        "expected an explicit `RESCUE_NAME=\"rescue/{plugin}-...\"` capture, "
        "not just prose describing a rescue mechanism — a vague description "
        "can't be regression-guarded"
    )
    assert 'branch "$RESCUE_NAME"' in text, (
        "expected the branch-create command to use the captured $RESCUE_NAME "
        "variable rather than re-expanding `$(date ...)` inline"
    )


def test_step3_rescue_branch_created_before_worktree_is_removed():
    text = _step3_source()
    branch_pos = text.find('branch "$RESCUE_NAME"')
    remove_pos = text.rfind("worktree remove --force")
    assert branch_pos != -1 and remove_pos != -1
    assert branch_pos < remove_pos, (
        "expected the rescue branch to be created BEFORE the worktree is "
        "removed, not after — otherwise there's nothing left to branch from"
    )


def test_step3_rescue_commit_bypasses_hooks():
    """Regression guard for a code-review HIGH finding: an interrupted
    batch's WIP diff is exactly what a pre-commit/lint hook in the target
    repo is likely to reject. If the rescue commit is blocked by a hook, a
    naive 'commit, then unconditionally branch' sequence still creates the
    rescue branch pointing at the OLD HEAD — empty of the actual diff — and
    then removes the worktree, silently destroying the data while reporting
    a rescue succeeded. The rescue commit must bypass hooks: it is a
    data-preservation snapshot, not a real commit subject to quality gates."""
    text = _step3_source()
    assert "commit --no-verify" in text, (
        "expected the rescue commit to use `--no-verify` so a pre-commit/"
        "lint hook in the target repo can't silently block the rescue"
    )


def test_step3_verifies_rescue_before_removing_worktree():
    """Regression guard for a code-review HIGH finding: `git branch` doesn't
    fail just because the preceding `git commit` failed — it happily creates
    a branch pointing at the unchanged HEAD. Without an explicit
    verification gate, the worktree gets removed either way and the
    diff is gone while the operator is told a rescue branch exists."""
    text = _step3_source()
    assert "STOP" in text and "leave the worktree in place" in text.lower(), (
        "expected an explicit STOP-and-leave-worktree-in-place instruction "
        "for when the rescue can't be verified, so the destructive "
        "worktree-remove never runs on an unverified rescue"
    )


def test_step3_treats_status_check_errors_as_dirty_not_clean():
    """Regression guard for a code-review MEDIUM finding: `git status
    --porcelain` against a broken worktree (missing .git, index.lock
    contention, permission error) can exit non-zero with empty stdout —
    indistinguishable from 'clean' by output alone. An agent that only
    checks for empty output fails OPEN onto the destructive path."""
    text = _step3_source()
    assert "exit code" in text.lower(), (
        "expected Step 3 to explicitly require checking the exit code of "
        "the status check, not just its (possibly empty-on-error) output"
    )


def test_step3_reports_rescue_branch_to_operator():
    """A silent rescue is still a silent discard from the operator's point of
    view — Step 5's report must surface it."""
    src = RUN_SKILL.read_text(encoding="utf-8")
    step5 = _normalize(_slice(src, "## Step 5:", "## Step 6:"))
    assert "rescue" in step5.lower(), (
        "expected Step 5 (Report) to explicitly mention surfacing a rescued "
        "worktree branch to the operator, not just Step 3 handling it silently"
    )


def test_step6_has_no_standalone_unconditional_force_remove():
    """Regression guard for a code-review HIGH finding: Step 6's teardown
    used to force-remove the SAME worktree unconditionally — the identical
    bug, ~60 lines further down in the same file. A first-round fix that
    only ADDED a reminder sentence above the original bare command left the
    bare, copy-pasteable `worktree remove --force` bullet sitting right
    there — an agent (or a future edit) can trivially skip the reminder and
    run the bullet directly. There must be no standalone force-remove
    command left in Step 6 at all; the only removal that may fire here is
    whichever one item 3's procedure itself produces."""
    text = _step6_source_raw()
    bare_command_lines = re.findall(
        r"^\s*-\s*`[^`]*worktree remove --force[^`]*`", text, re.MULTILINE
    )
    assert not bare_command_lines, (
        "expected Step 6 to contain NO bare `- `...worktree remove --force...`` "
        f"bullet of its own (found {bare_command_lines!r}) — the removal must "
        "come from re-running item 3's dirty-check-and-rescue procedure, not "
        "a separate copy-pasteable unconditional command bullet"
    )


def test_step6_points_at_item_3_specifically_not_item_4():
    """Step 3's numbered list has item 3 (dirty-check-and-rescue) and item 4
    (fetch + create fresh worktree). Step 6 must re-run only item 3's
    check-and-remove — re-running item 4 at teardown time would recreate
    the worktree it just tore down."""
    text = _step6_source()
    assert "item 3" in text.lower(), (
        "expected Step 6 to point at item 3 specifically (not just 'Step 3' "
        "in general), since Step 3 also contains item 4 (fetch/create), "
        "which must NOT be re-run at teardown"
    )
    assert "not item 4" in text.lower(), (
        "expected Step 6 to explicitly exclude item 4 (fetch/create) from "
        "what gets re-run at teardown, via the literal phrase 'NOT item 4' — "
        "a bare 'not' anywhere in Step 6's prose doesn't pin the exclusion"
    )


def test_step6_aborts_entirely_if_item3_stops():
    """Regression guard for a code-review HIGH finding, reproduced with real
    git: git's protection against deleting a branch checked out in a
    worktree only applies while that worktree is still REGISTERED — exactly
    the state item 3's STOP branch refuses to disturb. Without an explicit
    'abort Step 6 entirely' instruction, the `worktree prune` /
    `skill-eval-*` branch-deletion bullets that follow can still run after a
    STOP and silently delete the very branch item 3 just decided not to
    touch — the #57 failure class reintroduced at the other end of the
    file."""
    text = _step6_source()
    assert "stop this whole step too" in text.lower(), (
        "expected Step 6 to explicitly abort ITSELF (not just skip the "
        "removal) if item 3's procedure ends in a STOP, so the prune/"
        "branch-deletion bullets that follow never run against a worktree "
        "item 3 refused to touch"
    )


def test_step6_reports_a_teardown_time_rescue_branch():
    """Regression guard for a code-review MEDIUM finding: Step 5 (Report)
    runs BEFORE Step 6 (teardown) and is scoped to 'if Step 3 found a dirty
    stale worktree' — a rescue branch created during THIS run of item 3 (at
    teardown time, arguably the more likely case since Step 4 already flags
    a TaskStop-cut batch) has no reporting path without an explicit
    addendum instruction in Step 6 itself."""
    text = _step6_source()
    assert "addendum" in text.lower(), (
        "expected Step 6 to explicitly instruct reporting a teardown-time "
        "rescue branch as an addendum, since Step 5's report already ran "
        "before Step 6 executes"
    )


def test_step3_dirty_check_rescue_is_a_separate_item_from_fetch_and_create():
    """Regression guard: the dirty-check-and-rescue procedure and the
    fetch+create-fresh-worktree steps must be distinct numbered items, not
    merged into one — otherwise 'apply the same procedure' (used by Step 6)
    is ambiguous about whether it includes recreating the worktree."""
    src = RUN_SKILL.read_text(encoding="utf-8")
    step3 = _slice(src, "## Step 3:", "## Step 4:")
    assert re.search(r"\n4\.\s", step3), (
        "expected the dirty-check-and-rescue procedure (item 3) and the "
        "fetch/create-worktree steps (item 4) to be separate numbered items"
    )


def test_step3_item4_explicitly_gated_on_item3_not_stopping():
    text = _step3_source()
    item4_pos = text.find("4. **Only once item 3")
    assert item4_pos != -1, (
        "expected item 4 to explicitly state it only runs once item 3 "
        "completed with an actual removal, not after item 3's STOP branch"
    )
    assert "confirmed nothing-to-remove" in text, (
        "expected item 4's gate to also cover the 'nothing at all to "
        "remove' outcomes (no worktree existed, or a prunable entry was "
        "already cleaned up), not just 'an actual removal' — otherwise "
        "those branches read as ungated by item 4's own condition"
    )


def test_step3_clean_path_remove_checks_its_own_exit_code():
    """Regression guard for a code-review LOW finding: the clean-path
    `worktree remove --force` used to swallow its own failure
    (`2>/dev/null; true`), so a locked/failed removal would silently fall
    through to item 4's `worktree add`, which then fails on 'already
    exists' with no context. The fix makes the clean path check its own
    exit code and STOP on failure — pin that explicitly, since every other
    STOP condition in this file already has a dedicated test and this one
    didn't."""
    text = _step3_source()
    clean_pos = text.find("Clean (exit code")
    assert clean_pos != -1
    clean_section = text[clean_pos:clean_pos + 400]
    assert "exit code too" in clean_section and "STOP" in clean_section, (
        "expected the clean-path removal to explicitly check its own exit "
        "code and STOP on failure, not silently fall through to item 4"
    )


def test_step3_flags_posix_shell_requirement_for_new_commands():
    """Regression guard for a code-review HIGH finding: the dirty-check-and-
    rescue procedure introduces `test -e`, `rm -rf`, `$(date ...)`, and shell
    variable assignment — none valid PowerShell/cmd.exe syntax, and none used
    anywhere else in this plugin's SKILL.md files. This repo has a from-
    scratch Windows-compatibility requirement (CLAUDE.md) and an established
    convention (skills/setup, skills/configure) of calling out shell
    portability traps explicitly rather than leaving them implicit — the
    procedure must state its POSIX-shell requirement rather than silently
    assuming Git Bash."""
    text = _step3_source()
    assert "POSIX-compatible shell" in text or "POSIX shell" in text, (
        "expected Step 3 to explicitly state that the dirty-check-and-rescue "
        "procedure requires a POSIX-compatible shell (Git Bash on Windows), "
        "given it introduces `test -e`/`rm -rf`/`$(date ...)`/shell-variable "
        "syntax with no PowerShell equivalent anywhere in the file"
    )


def test_step3_handles_unregistered_directory_without_dead_end():
    """Regression guard: a directory at {worktreePath} that ISN'T a
    registered git worktree (stray leftover, aborted `worktree add`) used to
    route to 'treat as no worktree, go to the clean-path remove' — but that
    remove targets a registered worktree and would be a no-op against a
    stray directory, then item 4's `worktree add` fails hard with 'already
    exists'. Must instead distinguish: no directory at all (skip to item 4),
    a directory with no .git (safe to rm -rf directly), or a directory WITH
    a .git that git doesn't recognize as registered (STOP, don't guess)."""
    text = _step3_source()
    assert 'test -e "{worktreePath}/.git"' in text, (
        "expected an explicit, exact command deciding the .git-presence "
        "branch — a prose-only check here gates the file's only recursive "
        "delete and is too easy to get wrong (e.g. `test -d`, which is "
        "wrong: a linked worktree's .git is a FILE, not a directory)"
    )
    assert "rm -rf" in text, (
        "expected an explicit direct removal for a stray non-worktree "
        "directory that has no .git of its own"
    )


def test_step3_unregistered_directory_with_git_is_never_rm_rfed():
    """Regression guard for a mutation-test finding: turning the 'STOP,
    don't guess' branch for an unrecognized-but-present .git into an
    `rm -rf` would reintroduce the exact #57 data-loss class against the
    most-likely-to-hold-real-work case. Pin that this branch is explicitly
    forbidden from deleting, not just that a STOP sentence exists somewhere
    in item 3 (which the dirty/verification branch already satisfies)."""
    text = _step3_source()
    assert "do NOT `rm -rf` it" in text or "do not `rm -rf` it" in text.replace(
        "NOT", "not"
    ), (
        "expected an explicit prohibition on `rm -rf` for the "
        "unrecognized-.git branch, not just a STOP sentence that a future "
        "edit could silently swap for a delete"
    )


def test_step3_prunable_worktree_skips_to_item4_instead_of_dead_ending():
    """Regression guard for a code-review HIGH finding, reproduced with real
    git: a worktree whose directory was deleted by hand (or by a prior
    prune) but is STILL LISTED (tagged `prunable`) by `worktree list
    --porcelain` used to fall through to the registered-worktree status
    check, which then fails against a nonexistent path, gets misread as
    'dirty', and dead-ends the whole batch on an unverifiable-rescue STOP —
    over a directory that was never even there. `prunable` must be checked
    explicitly and routed straight to item 4."""
    text = _step3_source()
    assert "prunable" in text.lower(), (
        "expected Step 3 to explicitly check for git's own `prunable` tag "
        "in `worktree list --porcelain` output and skip straight to item 4 "
        "for it, rather than routing a gone-from-disk registered worktree "
        "into the live status-check / rescue path"
    )


def test_step3_rm_rf_has_a_path_sanity_guard():
    """Regression guard for a code-review MEDIUM finding: the file's only
    recursive delete fires on a purely negative signal ('not registered,
    exists, no .git') with no positive check on the path itself. Every
    other destructive branch in item 3 is preceded by an explicit
    precondition check; this one wasn't."""
    text = _step3_source()
    assert "rollout-wt" in text and "STOP** instead" in text, (
        "expected an explicit sanity check on {worktreePath} (non-empty, "
        "absolute, ends in the expected '-rollout-wt' suffix, not equal to "
        "{pluginRepoPath}) before the stray-directory `rm -rf`, with a STOP "
        "fallback if it doesn't look like the path this skill created"
    )


def test_step3_rescue_branch_verification_runs_before_the_post_rescue_remove():
    """Regression guard for a mutation-test finding: it's not enough that
    `branch "rescue/..."` precedes SOME `worktree remove --force` in the
    text (test_step3_rescue_branch_created_before_worktree_is_removed uses
    the LAST such occurrence, which happens to be the post-rescue one today
    — but that test alone doesn't pin that the `branch --list` verification
    itself sits between the branch-create and the final remove). Moving the
    post-rescue remove to right after `branch "rescue/..."`, above the
    verification bullets, would reintroduce D1's un-gated removal while
    still passing the other ordering test."""
    text = _step3_source()
    verify_pos = text.find('branch --list "rescue/{plugin}-*"')
    final_remove_pos = text.rfind("worktree remove --force")
    assert verify_pos != -1 and final_remove_pos != -1
    assert verify_pos < final_remove_pos, (
        "expected the `branch --list` verification to run BEFORE the final "
        "(post-rescue) worktree removal, not after"
    )


def test_step3_rescue_verification_uses_glob_not_exact_timestamp():
    """Regression guard: `branch "rescue/{plugin}-$(date ...)"` and its
    verification are two SEPARATE tool calls with no shared shell state
    (Bash tool state doesn't persist variables across calls). Verifying
    against the exact same literal timestamp string would re-expand
    `$(date ...)` a second time and very likely not match the first
    expansion, causing a successful rescue to be misreported as failed."""
    text = _step3_source()
    assert 'branch --list "rescue/{plugin}-*"' in text, (
        "expected the rescue verification to use a `branch --list` glob "
        "match rather than requiring the exact same literal timestamp "
        "string produced by a separate `$(date ...)` expansion"
    )
