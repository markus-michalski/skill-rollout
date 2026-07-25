"""Smoke: the Select phase discovers skills added mid-rollout, every batch.

Regression guard for the workflow script's own documented failure mode: a
plugin/repo can gain a brand-new skill directory between rollout batches (the
concept doc's own example: storyforge's `delete-author` appeared because
`create-author`'s live tier found a missing MCP tool and the fix added a
whole new skill alongside it). If the Select phase only ever read existing
STATUS.md rows, that new skill would stay invisible to every future batch
forever, since selection only ever looks at existing rows (workflow.js's own
wording) — nothing else in the pipeline ever looks at the raw directory
listing.

This does NOT need an equivalent "new MCP tool" discovery step: the rollout
evaluates skills, not MCP tools directly, and an MCP tool without a wrapping
skill was never a rollout target in the first place — it only ever surfaces
via the skill that wraps it, which this scan already catches.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_JS = ROOT / "workflows" / "skill-rollout.js"


def _normalize(text):
    # Prompt text wraps across lines for readability — collapse whitespace so
    # a line-wrap alone (as opposed to a semantic reword) never breaks a
    # substring/phrase assertion below.
    return re.sub(r"\s+", " ", text)


def _workflow_raw():
    return WORKFLOW_JS.read_text(encoding="utf-8")


def _select_phase_slice():
    src = _workflow_raw()
    # Anchored to the prompt's own content (its opening sentence, and the
    # schema/phase binding that closes the agent() call it belongs to)
    # rather than the phase('Select')/phase('Onboard') labels — those labels
    # are just progress-display grouping and can be renamed (e.g. 'Onboard'
    # -> 'Onboarding') without touching the guarded prompt text at all,
    # which would otherwise fail every test in this file with a misleading
    # "marker not found" error instead of a real regression.
    start_marker = 'Determine the batch selection for plugin'
    end_marker = "{ schema: SELECTION_SCHEMA, phase: 'Select' }"
    start = src.find(start_marker)
    assert start != -1, f"expected to find {start_marker!r} in workflow.js"
    end = src.find(end_marker, start)
    assert end != -1 and end > start, (
        f"expected to find {end_marker!r} after {start_marker!r} in workflow.js"
    )
    return _normalize(src[start:end])


def test_select_phase_cross_checks_status_against_real_directory_listing():
    """The Select agent must diff STATUS.md's rows against the actual
    current skill directory listing before selecting anything — not just
    trust STATUS.md as if it were always complete."""
    section = _select_phase_slice()
    assert "cross-check" in section.lower(), (
        "expected the Select phase prompt to instruct a cross-check between "
        "STATUS.md and the real skill directory listing"
    )
    assert "actual current skill directory listing" in section, (
        "expected the cross-check to reference the actual current skill "
        "directory listing specifically, not just directories in general"
    )


def test_select_phase_detects_both_repo_layouts():
    """Plugin-type repos (skills/{name}/SKILL.md) and flat-collection repos
    (mm-skills-style, {name}/SKILL.md) are structurally different — the scan
    must branch on which layout this repo actually uses, not assume one."""
    section = _select_phase_slice()
    assert "Plugin layout" in section, (
        "expected the Select phase to name-check the plugin-type layout branch"
    )
    assert "Flat-collection layout" in section, (
        "expected the Select phase to name-check the flat-collection layout branch"
    )
    assert ".claude-plugin/plugin.json" in section, (
        "expected the layout branch to key off .claude-plugin/plugin.json presence"
    )


def test_select_phase_adds_missing_rows_now_before_selection():
    """A directory with no matching STATUS.md row must get one added NOW,
    before the batch's skill selection happens — deferring this to 'a future
    batch' would mean it never gets picked up on its own, since selection
    only ever reads existing rows. The word NOW carries the load here: a
    rewording that keeps 'before selection' but drops the immediacy (e.g.
    'can be added later, before selection in some future batch') must fail
    this test even though 'before selection' alone would still match."""
    section = _select_phase_slice()
    assert "NOW, before selection" in section, (
        "expected missing rows to be added NOW, before selection — not "
        "merely 'before selection' at some unspecified future point"
    )
    assert (
        "stays invisible to every future batch forever, since selection "
        "only ever looks at existing rows"
    ) in section, (
        "expected the prompt to state the concrete consequence of skipping "
        "this: permanent invisibility to every future batch, because "
        "selection never re-scans anything beyond existing rows"
    )


def test_select_phase_new_skill_can_join_current_batch():
    """A skill discovered mid-scan must be eligible for the batch that
    discovered it, not just recorded for some future run."""
    section = _select_phase_slice()
    assert "actual work now includes a newly-added skill" in section, (
        "expected the Select phase to allow a newly-discovered skill into "
        "the current batch's work, not only log it for later"
    )


def test_select_phase_corrects_footer_count_on_new_row():
    """STATUS.md's total-skill-count footer must stay in sync when a row is
    added — a stale footer is a silent drift bug of its own."""
    section = _select_phase_slice()
    assert "total-skill-count footer" in section, (
        "expected the Select phase to correct STATUS.md's footer count when "
        "adding a newly-discovered skill's row"
    )
