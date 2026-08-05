"""Smoke: the Select phase's done-check must treat a source-verified,
permanently-blocked Live cell as done — not re-select it forever (issue #67).

🟥 BLOCKED bundles two structurally different situations under one symbol:
1. Pending sandbox convention (issue #35 not yet implemented for this
   plugin) — genuinely non-terminal, a future batch may unblock it.
2. Permanent read-exposure — the skill's real, non-sandbox reads would
   surface sensitive personal/legal/medical/business data by design. No
   sandbox convention can ever fix this (a read has nothing to
   snapshot/restore against), so it can never resolve to ✅ either. This
   is independent of write-capability: a skill can have write-capable
   calls covered normally by the sandbox convention AND a separate,
   unscopable sensitive-read call that stays permanently blocked
   regardless (confirmed concrete case: life-hub's `new-case`/`resume`,
   both write-capable, both still permanently blocked on an unrelated
   unscoped `tool_list_persons`/`tool_list_shared_contacts` read).

Before this fix, the Select phase's done-check only accepted Simulated ✅ AND
(Live ✅ OR verified 🟦 N/A) as done — flavor 2 has no way to ever satisfy
that, so a skill correctly, permanently blocked for read-exposure reasons
gets re-selected into every future batch forever, producing zero-value
no-op re-confirmation work each time.

Regression guard for the fix in workflows/skill-rollout.js's Select-phase
prompt (~line 1374), the new stand-alone Read-exposure check (which runs
BEFORE the read-only bypass, independent of write-capability), the hard-gate
branch, and reference/eval-schema.md's BLOCKED row.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_JS = ROOT / "workflows" / "skill-rollout.js"
EVAL_SCHEMA = ROOT / "reference" / "eval-schema.md"

PERMANENT_ANNOTATION = "🟥 BLOCKED (read-exposure, permanent)"

READ_EXPOSURE_CHECK_MARKER = (
    "Read-exposure check, run this FIRST for every skill's own MCP surface"
)
READ_ONLY_BYPASS_MARKER = "Read-only bypass, check this FIRST among the mutation-risk"
HARD_GATE_MARKER = "Hard gate, check this if the read-only bypass above did NOT apply"
MCP_REGISTER_MARKER = "MCP Surface Register pre-check"


def _normalize(text):
    return re.sub(r"\s+", " ", text)


def _workflow_text():
    return _normalize(WORKFLOW_JS.read_text(encoding="utf-8"))


def _workflow_raw():
    return WORKFLOW_JS.read_text(encoding="utf-8")


def _eval_schema_text():
    return _normalize(EVAL_SCHEMA.read_text(encoding="utf-8"))


def _slice(text, start_marker, end_marker):
    start = text.find(start_marker)
    assert start != -1, f"expected to find {start_marker!r} in workflow.js"
    end = text.find(end_marker, start)
    assert end != -1 and end > start, (
        f"expected to find {end_marker!r} after {start_marker!r} in workflow.js"
    )
    return text[start:end]


def _read_exposure_check_section():
    return _slice(_workflow_text(), READ_EXPOSURE_CHECK_MARKER, READ_ONLY_BYPASS_MARKER)


def _hard_gate_section():
    return _slice(_workflow_text(), HARD_GATE_MARKER, MCP_REGISTER_MARKER)


def _select_phase_slice():
    src = _workflow_raw()
    start_marker = "Determine the batch selection for plugin"
    end_marker = "{ schema: SELECTION_SCHEMA, phase: 'Select' }"
    start = src.find(start_marker)
    assert start != -1, f"expected to find {start_marker!r} in workflow.js"
    end = src.find(end_marker, start)
    assert end != -1 and end > start, (
        f"expected to find {end_marker!r} after {start_marker!r} in workflow.js"
    )
    return _normalize(src[start:end])


def test_eval_schema_blocked_row_documents_two_flavors():
    text = _eval_schema_text()
    assert "Pending sandbox convention" in text, (
        "expected the BLOCKED row to name the non-terminal 'pending sandbox "
        "convention' flavor explicitly"
    )
    assert "Permanent read-exposure" in text, (
        "expected the BLOCKED row to name the terminal 'permanent "
        "read-exposure' flavor explicitly"
    )


def test_eval_schema_blocked_row_documents_permanent_annotation_string():
    text = _eval_schema_text()
    assert PERMANENT_ANNOTATION in text, (
        f"expected the BLOCKED row to document the exact annotation string "
        f"{PERMANENT_ANNOTATION!r} used in STATUS.md cells"
    )


def test_eval_schema_blocked_row_states_permanent_flavor_is_terminal_for_scheduling():
    text = _eval_schema_text()
    assert "stops re-selecting the skill" in text, (
        "expected the BLOCKED row to state that the permanent flavor stops "
        "the Select phase from re-selecting the skill"
    )


def test_eval_schema_blocked_row_states_permanent_flavor_independent_of_write_calls():
    """Regression guard for the original fix's critical gap: flavor 2 must be
    documented as reachable regardless of whether the skill also has
    write-capable calls elsewhere — otherwise it's unreachable for the exact
    confirmed real-world cases (new-case/resume) the issue names."""
    text = _eval_schema_text()
    assert "independent of" in text and "write-capable calls elsewhere" in text, (
        "expected the BLOCKED row to state flavor 2 applies independent of "
        "write-capable calls elsewhere in the same skill"
    )


def test_eval_schema_blocked_row_bare_symbol_flavor_1_is_specific_not_tautological():
    """A bare 🟥 must default to flavor 1 — assert on the actual defaulting
    statement, not just the presence of the words 'bare' and '🟥' anywhere in
    the file (both already existed pre-fix and would pass trivially)."""
    text = _eval_schema_text()
    assert "the default meaning of a bare" in text, (
        "expected an explicit statement that a bare, un-annotated 🟥 defaults "
        "to the non-terminal 'pending sandbox convention' flavor"
    )


def test_eval_schema_blocked_table_still_parses_as_one_table():
    """Regression guard: a blank line or an un-escaped line break inside a
    markdown table cell silently truncates the table at that point — the
    NEEDS-HUMAN-REVIEW and no-restore-accepted-drift rows below BLOCKED would
    render as stray text with literal pipes instead of table rows. The
    BLOCKED cell's internal structure must use <br>, never a literal
    paragraph break, and the row must stay on one physical line."""
    text = EVAL_SCHEMA.read_text(encoding="utf-8")
    start = text.find("| 🟥 BLOCKED |")
    assert start != -1, "expected the BLOCKED row to exist"
    line_end = text.find("\n", start)
    assert line_end != -1
    blocked_row_line = text[start:line_end]
    assert blocked_row_line.rstrip().endswith("|"), (
        "expected the entire BLOCKED row to stay on one physical line "
        "(use <br> for internal breaks, not a real newline) so it doesn't "
        "truncate the markdown table"
    )
    next_row_start = text.find("| 🟨 NEEDS-HUMAN-REVIEW |", line_end)
    assert next_row_start != -1, (
        "expected the NEEDS-HUMAN-REVIEW row to immediately follow as a real "
        "table row, not fall out of the table due to a broken BLOCKED cell"
    )


def test_select_phase_done_check_accepts_permanent_blocked_annotation():
    """The Select phase's own done-predicate prose must recognize the exact
    permanent-block annotation as done, not just ✅/🟦 N/A."""
    section = _select_phase_slice()
    assert PERMANENT_ANNOTATION in section, (
        f"expected the Select phase's done-check to explicitly recognize "
        f"{PERMANENT_ANNOTATION!r} as a done state"
    )


def test_select_phase_done_check_keeps_bare_blocked_non_terminal():
    """A bare/pending-sandbox 🟥 BLOCKED must NOT count as done — the fix
    must not accidentally make ALL BLOCKED skills terminal."""
    section = _select_phase_slice()
    assert "fail open" in section.lower(), (
        "expected the Select phase's done-check to explicitly say the "
        "pending-sandbox flavor stays non-terminal / fails open toward "
        "re-checking"
    )


def test_select_phase_done_check_still_rejects_plain_square():
    """Regression guard: the existing 'never treat plain ⬜ as done' rule
    must survive this edit."""
    section = _select_phase_slice()
    assert "never treat plain ⬜ as done" in section.lower(), (
        "expected the pre-existing 'never treat plain ⬜ as done' rule to "
        "still be present after extending the done-check"
    )


def test_reselect_prompt_uses_same_extended_done_rule_as_select_phase():
    """The post-onboarding reselect prompt claims to apply 'the same fully
    done rule as the Select phase above' — it must actually match, not
    silently cite the pre-fix two-state rule."""
    reselect_section = _slice(
        _workflow_text(),
        "just completed. Read the newly-created",
        "Deliberately no issue #65 live-PR-check",
    )
    assert PERMANENT_ANNOTATION in reselect_section, (
        "expected the reselect prompt's own done-rule restatement to include "
        "the permanent-block annotation, matching the Select phase above"
    )


def test_workflow_js_read_exposure_check_exists_before_read_only_bypass():
    """The read-exposure check must run BEFORE the read-only bypass and be
    reachable independent of it — a future edit that nested it back inside
    the bypass's zero-write branch would make it unreachable for any skill
    that also has write-capable calls (the exact bug this test guards)."""
    text = _workflow_text()
    exposure_idx = text.find(READ_EXPOSURE_CHECK_MARKER)
    bypass_idx = text.find(READ_ONLY_BYPASS_MARKER)
    assert exposure_idx != -1, "expected the read-exposure check section to exist"
    assert bypass_idx != -1, "expected the read-only bypass section to exist"
    assert exposure_idx < bypass_idx, (
        "expected the read-exposure check to appear BEFORE the read-only bypass"
    )


def test_workflow_js_read_exposure_check_marks_permanent_annotation():
    """The read-exposure check's own outcome instruction — scoped strictly to
    its own section, not the whole file — must mark the permanent
    annotation. This is the ONLY place the permanent annotation should be
    emitted, and it must be reachable regardless of write-capability."""
    section = _read_exposure_check_section()
    assert PERMANENT_ANNOTATION in section, (
        f"expected {PERMANENT_ANNOTATION!r} to appear within the read-exposure "
        f"check's own section (not just somewhere later in the file)"
    )


def test_workflow_js_read_exposure_check_independent_of_write_capability():
    """Regression guard for the original fix's critical gap: the check must
    explicitly state it applies regardless of whether the skill also has
    write-capable calls — otherwise it's structurally unreachable for the
    exact confirmed cases (new-case/resume) the issue is about."""
    section = _read_exposure_check_section()
    marker = "regardless of whether the skill also has write-capable calls"
    assert marker in section, (
        "expected the read-exposure check to explicitly apply independent of "
        "write-capability elsewhere in the skill's surface"
    )


def test_workflow_js_read_exposure_check_excludes_only_dependent_cases():
    """A single sensitive-unscopable-read must not blanket-block the whole
    skill's live tier if other cases don't depend on it — only cases that
    actually need the flagged call should be excluded (matching the real
    life-hub precedent: 4/4 non-dependent cases still executed and passed)."""
    section = _read_exposure_check_section()
    marker = "Every OTHER live case that does NOT depend on one still runs normally"
    assert marker in section, (
        "expected the read-exposure check to only exclude cases that "
        "actually depend on the sensitive-unscopable-read, not the whole skill"
    )


def test_workflow_js_hard_gate_stays_non_terminal_pending_sandbox_flavor():
    """The hard gate (plugin-wide convention not yet implemented) must be
    explicitly tied to the non-terminal, pending-sandbox flavor — it must
    NOT write the permanent annotation, since it doesn't know anything
    about read-exposure, only about the missing convention."""
    hard_gate_section = _hard_gate_section()
    assert PERMANENT_ANNOTATION not in hard_gate_section, (
        "the hard gate (missing-convention path) must not write the "
        "permanent read-exposure annotation — it doesn't verify read-exposure"
    )
    assert "mark the Live column 🟥 BLOCKED" in hard_gate_section, (
        "expected the hard gate to still explicitly mark a bare 🟥 BLOCKED "
        "(regression guard for test_readonly_tier.py's own assertion, which "
        "this section must keep satisfying)"
    )
    assert "non-terminal" in hard_gate_section.lower(), (
        "expected the hard gate to explicitly state its BLOCKED outcome is "
        "non-terminal (pending-sandbox flavor)"
    )


def test_edit_result_schema_livescore_documents_blocked_annotations():
    """Stage A's structured result (EDIT_RESULT_SCHEMA) is the ONLY channel
    that carries a Live-column conclusion to Stage C — Stage A itself is
    forbidden from writing STATUS.md (stage boundary). Before this test, the
    schema's own liveScore description only documented "N/A" and pass/total,
    with no slot for a BLOCKED annotation — an agent reading the schema
    literally had no documented way to signal a permanent block downstream."""
    text = _workflow_text()
    schema_idx = text.find("const EDIT_RESULT_SCHEMA")
    next_schema_idx = text.find("const SKILL_RESULT_SCHEMA", schema_idx)
    assert schema_idx != -1 and next_schema_idx != -1 and next_schema_idx > schema_idx
    schema_section = text[schema_idx:next_schema_idx]
    assert PERMANENT_ANNOTATION in schema_section, (
        "expected EDIT_RESULT_SCHEMA's liveScore description to document the "
        "permanent read-exposure annotation as a valid value"
    )
    assert "never write STATUS.md" in schema_section, (
        "expected the schema to state that liveScore, not a direct write, is "
        "how Stage A hands its Live-column conclusion to Stage C"
    )


def test_skill_result_schema_livescore_echoes_blocked_annotation_verbatim():
    """Stage C's own final result schema must document the same BLOCKED
    annotation shape and instruct echoing it verbatim, not paraphrasing a
    partial live-case pass rate into a plain score."""
    schema_section = _slice(
        _workflow_text(), "const SKILL_RESULT_SCHEMA", "const DIGEST_SCHEMA"
    )
    assert PERMANENT_ANNOTATION in schema_section, (
        "expected SKILL_RESULT_SCHEMA's liveScore description to document "
        "the permanent read-exposure annotation as a valid value"
    )
    assert "never paraphrase" in schema_section, (
        "expected an explicit instruction to echo the BLOCKED annotation "
        "verbatim rather than paraphrasing it into a bare score"
    )


def test_stage_c_bookkeeping_writes_livescore_annotation_verbatim_to_status_md():
    """Stage C's bookkeeping instructions (where STATUS.md actually gets
    written) must explicitly say to copy a BLOCKED annotation from Stage A's
    evalScores.liveScore into the Live cell verbatim — otherwise Stage C, a
    fresh agent with no memory of Stage A's reasoning, has no documented
    reason not to paraphrase "4/6 executed, 2 blocked" into a plain "✅ 4/6"."""
    text = _workflow_text()
    bookkeeping_idx = text.find("## Bookkeeping — do this regardless of whether")
    assert bookkeeping_idx != -1, "expected Stage C's bookkeeping section to exist"
    bookkeeping_section = text[bookkeeping_idx : bookkeeping_idx + 1200]
    assert "stageAResultsBlock" in bookkeeping_section, (
        "expected the bookkeeping instruction to reference stageAResultsBlock "
        "as the source of the Live cell content"
    )
    marker = "do NOT paraphrase it into a plain pass/total score"
    assert marker in bookkeeping_section, (
        "expected an explicit anti-paraphrase instruction for the BLOCKED "
        "annotation in Stage C's own bookkeeping section"
    )


def test_digest_merge_prefers_blocked_annotation_over_stage_c_echo():
    """The batch-digest merge (JS, not prompt text) must not just fill in a
    missing liveScore — a 🟥 BLOCKED annotation from Stage A's evalScores
    must overwrite even a NON-empty result.liveScore, in case Stage C
    paraphrased the annotation away despite being told not to. A simple
    'only fill when empty' merge would silently accept that paraphrase."""
    text = _workflow_text()
    marker = "a 🟥 BLOCKED annotation from Stage A always wins over Stage C's own echo"
    assert marker in text, (
        "expected the digest merge to explicitly override result.liveScore "
        "with a BLOCKED annotation, not just fill it in when empty"
    )
    assert "editLiveScore.indexOf('🟥 BLOCKED')" in _workflow_raw(), (
        "expected the merge to actually check for the BLOCKED marker before "
        "overriding, not unconditionally prefer editResult's liveScore"
    )
