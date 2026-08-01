"""Smoke: the Select phase must live-verify against GitHub before re-selecting a skill,
not just trust STATUS.md's ✅/⬜ symbol (issue #65).

Regression guard for a confirmed, recurring incident: `compose` (a life-hub skill) was
already fully complete — Simulated 24/24, an open/mergeable PR (#32) — from an earlier
batch run the same day, but was selected again as the 10th skill in a later batch run.
Stage A/C caught it and stopped rather than force-pushing over a divergent branch, so no
PR was corrupted — but this is at least the second time this exact pattern has shown up
(mm-dev-toolkit's own batch-digest.md, 2026-07-28: `dashboard`/`next-step` both re-selected
despite already having open PRs), attributed both times to STATUS.md showing a stale
transient symbol instead of the ✅ resting state.

The fix adds an explicit live `gh pr list --head skill-eval-{name} --state open` check for
every candidate skill before the Select phase finalizes its batch list, and excludes any
skill that already has an open PR regardless of what STATUS.md's symbols say. A code
review of the first draft found two follow-up gaps, both fixed here:

1. The exclusion instruction said to "note the exclusion... in this call's own summary",
   but SELECTION_SCHEMA had no field for that — an unenforceable instruction. The fix adds
   an `excludedOpenPrSkills` array field to the schema and wires it into the workflow's
   batchNotes so an exclusion is actually visible in the final digest.
2. The check introduces a hard new dependency on `gh` being installed/authenticated in a
   phase that previously did none of that — with no failure-handling instruction, a broken
   `gh` could silently no-op the check OR abort the entire batch before any skill work
   starts. The fix adds an explicit fail-open-with-a-note instruction, mirroring the
   established precedent in this exact plugin (skills/status/SKILL.md's own live-PR check).
   It also bounds the check to a walk-and-backfill over the table (continue past the
   original cutoff to replace each exclusion) so excluding a skill can't silently shrink
   the batch below the requested count while eligible rows remain further down the table.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_JS = ROOT / "workflows" / "skill-rollout.js"


def _normalize(text):
    # Prompt text wraps across lines for readability — collapse whitespace so a
    # line-wrap alone never breaks a substring/phrase assertion below. Same convention as
    # test_select_phase_skill_discovery.py.
    return re.sub(r"\s+", " ", text)


def _workflow_raw():
    return WORKFLOW_JS.read_text(encoding="utf-8")


def _select_phase_slice():
    # Same marker pair as test_select_phase_skill_discovery.py's _select_phase_slice() —
    # deliberately mirrored so the two files can't silently disagree about where the
    # Select phase's prompt begins and ends.
    src = _workflow_raw()
    start_marker = 'Determine the batch selection for plugin'
    end_marker = "{ schema: SELECTION_SCHEMA, phase: 'Select' }"
    start = src.find(start_marker)
    assert start != -1, f"expected to find {start_marker!r} in workflow.js"
    end = src.find(end_marker, start)
    assert end != -1 and end > start, (
        f"expected to find {end_marker!r} after {start_marker!r} in workflow.js"
    )
    return _normalize(src[start:end])


def test_selection_schema_has_a_field_for_excluded_skills():
    """Regression guard for a code-review finding: the exclusion instruction told the
    agent to 'note the exclusion in this call's own summary', but SELECTION_SCHEMA had no
    summary/notes field at all — an unenforceable instruction whose output had nowhere to
    land. Check the schema definition itself, not just the prompt text."""
    src = _workflow_raw()
    schema_start = src.find("const SELECTION_SCHEMA")
    schema_end = src.find("const ONBOARD_SCHEMA")
    assert schema_start != -1 and schema_end != -1 and schema_start < schema_end
    schema_section = src[schema_start:schema_end]
    assert "excludedOpenPrSkills" in schema_section, (
        "expected SELECTION_SCHEMA to define an excludedOpenPrSkills field the exclusion "
        "instruction can actually write to"
    )


def test_select_phase_runs_a_live_gh_pr_check_per_candidate():
    section = _select_phase_slice()
    assert "gh pr list" in section, (
        "expected the Select phase to live-verify each candidate skill via `gh pr list`, "
        "not trust STATUS.md's symbol alone"
    )
    assert "--head" in section and "skill-eval-" in section, (
        "expected the check to target the skill's own skill-eval-{name} branch via --head"
    )
    assert "--state open" in section, (
        "expected the check to filter for OPEN PRs specifically"
    )


def test_select_phase_names_status_symbol_as_untrusted():
    section = _select_phase_slice()
    assert "stale" in section.lower(), (
        "expected the Select phase to explicitly call out that STATUS.md's symbols can go "
        "stale, per the confirmed incident this check exists to catch"
    )


def test_select_phase_drops_skill_with_open_pr_regardless_of_symbols():
    section = _select_phase_slice()
    assert "drop it from the list" in section.lower(), (
        "expected an explicit instruction to DROP a candidate skill that already has an "
        "open PR from this batch's selection"
    )
    assert "regardless of what status.md" in section.lower(), (
        "expected the exclusion to explicitly override STATUS.md's symbols, not just note "
        "the open PR as a side fact"
    )


def test_select_phase_writes_exclusion_to_the_schema_field():
    section = _select_phase_slice()
    assert "excludedOpenPrSkills" in section, (
        "expected the exclusion instruction to write to the excludedOpenPrSkills schema "
        "field specifically, not an unspecified 'summary'"
    )


def test_select_phase_backfills_instead_of_shrinking_the_batch():
    """Regression guard for a code-review finding: the original instruction said to
    exclude open-PR skills with no reconciliation against the 'return the first N skills'
    rule right next to it — two unstitched instructions that, taken together, could
    silently return a batch smaller than what was actually requested."""
    section = _select_phase_slice()
    assert "backfill" in section.lower(), (
        "expected an explicit backfill instruction: continue past the original cutoff to "
        "replace each excluded skill, so the batch doesn't silently shrink below `count`"
    )


def test_select_phase_check_never_passes_repo_flag():
    """Same gh-resolution convention as needsReviewTriagePrompt and the rest of this
    script: never pass --repo, resolve from cwd's own git remote."""
    section = _select_phase_slice()
    assert "never pass \\`--repo\\`" in section or "never pass `--repo`" in section, (
        "expected the live PR check to explicitly forbid `--repo`, resolving against "
        "whatever repo pluginRepoPath's git remote points at instead — same convention as "
        "every other gh call in this script"
    )


def test_select_phase_handles_gh_failure_without_aborting_the_batch():
    """Regression guard for a code-review finding: the Select phase previously did zero
    `gh` calls — this fix introduces a hard new dependency on `gh` being installed and
    authenticated, with no failure-handling instruction in the first draft. A broken `gh`
    could otherwise silently no-op the whole check or abort batch selection entirely,
    before any skill work starts. Mirrors the established fail-open precedent in this same
    plugin's skills/status/SKILL.md live-PR check."""
    section = _select_phase_slice()
    assert "do not fail the whole selection" in section.lower(), (
        "expected an explicit instruction that a failing `gh` call must not abort the "
        "whole batch selection"
    )
    assert "not authenticated" in section.lower() or "not installed" in section.lower(), (
        "expected concrete gh-failure modes to be named, not just a vague 'if it fails'"
    )


def test_select_phase_check_precedes_the_batch_digest_header_write():
    """The exclusion/backfill logic must be fully resolved before the batch-digest header
    is written (which records the FINAL selected skill list) — otherwise the header could
    record a pre-exclusion list that doesn't match what actually gets processed. The header
    write itself is a shared function call (batchDigestHeaderInstruction), not inline text
    — check for the call marker, not its expanded body."""
    section = _select_phase_slice()
    check_pos = section.find("gh pr list")
    header_pos = section.find("batchDigestHeaderInstruction(")
    assert check_pos != -1 and header_pos != -1
    assert check_pos < header_pos, (
        "expected the live PR check (and its backfill) to run BEFORE the batch-digest "
        "header write, so the header reflects the actually-final selected list"
    )
