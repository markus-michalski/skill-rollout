# Eval Schema Reference

One `evals.json` file per skill, one `skill_name` + `evals[]` array. Each eval case carries a `mode` field — `"simulated"` (default, omit the field) or `"live"` — that determines which of the two shapes below it follows. Both modes can coexist in the same file (see `storyforge/author-check/evals.json` for a worked example: cases 1-20 simulated, 21-24 live).

## 1. Simulated (mode omitted, or `"simulated"`)

Skill-creator's standard eval format. No real tool calls — an executor subagent plays both the skill-following assistant and a plausible user, entirely in one self-contained prompt. Fast, free of side effects, tests the skill's *decision logic*.

```json
{
  "id": 1,
  "prompt": "Turn 1 - User: \"...\" (fixture context described in prose, e.g. 'Author X's profile has field Y set to Z')",
  "expected_output": "One-sentence description of the correct behavior, citing the specific SKILL.md phase/rule it exercises.",
  "files": [],
  "expectations": [
    "True/false-checkable statement about what the transcript should show.",
    "..."
  ]
}
```

**Fields:**
- `id` — unique integer.
- `prompt` — the user's opening message(s), turn-labeled if multi-turn. Any external state the skill would normally read via a tool call (an author profile field, a file's contents) is described in prose directly in the prompt — the executor treats it as ground truth without calling a real tool.
- `expected_output` — human-readable summary of correct behavior, should name the exact SKILL.md phase/rule being tested.
- `files` — input file paths, if any (rarely used for MCP-tool skills; more relevant for skills that process user-supplied documents).
- `expectations` — list of independently gradable true/false statements, each grounded in the SKILL.md's exact wording.

**Grading — mandatory methodology, not optional:** a naive "faithful reading" grading pass — an agent plays a perfectly compliant skill-following assistant, simulates the transcript, then grades its own idealized simulation — trivially converges toward 100%, because the expectations were derived from the same SKILL.md text a faithful reader is asked to follow. A perfect (or near-perfect) score on the very first baseline run, before any fix, is a red flag that this happened, not evidence the skill is bug-free (`backfill-promises` hit exactly this: a naive pass scored 61/61 on baseline; `book-conceptualizer`'s loop-log re-discovered the same failure mode independently by reaching 68/68 on baseline with plain self-grading).

Use **adversarial-realistic** grading instead, whether the grader is an independent pass or (for cost reasons) the same agent self-grading: instruct the grader to simulate a *realistic, competent-but-imperfect* assistant — limited context, plausible shortcuts, ambiguity-prone reading — and to actively hunt for spec gaps, not to demonstrate perfect compliance. This is what actually finds real gaps; it is not an optional refinement for when self-grading is used, it applies regardless of whether grading is independent or self-graded.

**Avoid narration-dependent expectations.** Don't phrase an expectation as "the skill's reasoning explicitly notes/cites/narrates X" — a simulated transcript's verbosity isn't controlled by the SKILL.md, so this tests how chatty that particular run happened to be, not the skill's actual behavior. It also tends to fail even after a targeted fix, because there's often no real output slot to narrate into once the skill's own format is terse (see `storyforge/backfill-style-principles/loop-log.md`'s "eval-design revision" section for a worked example — three assertions of this shape were removed/replaced after chronic false failures/passes across 5 loop iterations). Test the *outcome* instead: what got written (or not written), what field is empty vs. populated, what message text appears — anything checkable from the transcript's tool calls and final output, not from whether an internal reasoning step was spelled out in prose.

## 2. Live (`mode: "live"`)

Real MCP tool calls against a disposable sandbox instead of prose-embedded fixtures. Catches what simulation structurally cannot: wrong tool name/parameters, schema drift between the skill's assumptions and the tool's actual response, unhandled error paths, and whether a claimed side effect (file write, DB update) actually happened.

```json
{
  "id": 21,
  "mode": "live",
  "sandbox": { "author_slug": "zz-sandbox-author", "book_slug": "zz-sandbox-book", "chapter_slug": "01-test-chapter" },
  "setup": "Reset sandbox to baseline (see <plugin>/<skill>/sandbox.md). Any case-specific precondition beyond baseline (e.g. 'write a review.md with a known findings count') goes here too.",
  "prompt": "Turn 1 - User: \"...\" — no fixture data embedded; the executor calls real tools to discover everything.",
  "expected_output": "One-sentence description, same style as the simulated schema.",
  "files": [],
  "expectations": [
    "The transcript shows an actual MCP tool_use block calling <tool> with <real parameters> — not narrated.",
    "A separate, independent Read/tool call after the run confirms <claimed side effect> actually happened on disk/in the DB — not just the transcript's claim."
  ],
  "teardown": "Reset sandbox to baseline again, so the next case starts clean."
}
```

**Additional fields beyond the simulated schema:**
- `sandbox` — the disposable fixture identifiers (author/book/chapter slugs, or whatever the skill's domain uses) the live case runs against. Never a real user's data.
- `setup` — precondition to establish before running: usually "reset to baseline" plus any case-specific state (a specific file present/absent, a specific DB value).
- `teardown` — how to restore baseline afterward, so cases stay isolated from each other.

**Grading requirement, stricter than simulated:** expectations must be phrased so they can only be satisfied by real evidence — an actual `tool_use` block in the transcript, or an independent post-run read of real state — never by the executor's prose claim alone. See `storyforge/author-check/sandbox.md` for the concrete reset mechanics (including the important isolated-vs-shared-storage distinction — some state lives in files/DBs isolated per entity, safely git-restorable; some lives in a store shared across many real entities, where a git-level restore would roll back real data too, and the reset must go through the domain's own tools instead, scoped by ID).

## How many live cases does a skill need?

Not a 1:1 mirror of every simulated case. 4-6 live cases covering: one per distinct MCP tool call path the skill makes, the side-effect case (anything the skill writes), and whichever case depends most on real data structure (e.g. a filter that reads real nested fields). The rest of the skill's decision logic stays covered by the cheap simulated tier.

## Scoring

Report simulated-tier and live-tier pass rates **separately**. Never average them into one number — a perfect simulated score says nothing about live-tool-call correctness (concretely: `author-check` was 61/61 simulated while two of its underlying MCP-tool assumptions were completely broken in production — see `storyforge/author-check/loop-log.md`).

## 3. Loop state (`loop-state.json`, companion to `loop-log.md`)

`loop-log.md` is the narrative record (what was tried, why, what the grader said) — good for understanding a specific iteration, bad for a quick "where does this skill stand right now" glance across 49 skills. `loop-state.json` is the machine-readable twin: same information, structured for a one-glance read (or for a resumed/interrupted loop to pick up its own state) without parsing prose. Maintain both, one per skill, updated after every iteration — not a replacement for `loop-log.md`, a companion.

```json
{
  "iteration": 4,
  "best_score": 1.0,
  "best_score_pass_total": [71, 71],
  "best_score_history": [
    {"iteration": 0, "label": "baseline", "score": 0.9296, "pass": 66, "total": 71},
    {"iteration": 1, "label": "keep", "score": 0.9577, "pass": 68, "total": 71, "commit": "29e038f"},
    {"iteration": 2, "label": "discard", "score": 0.9577, "pass": 68, "total": 71},
    {"iteration": 3, "label": "keep", "score": 1.0, "pass": 71, "total": 71, "commit": "0a7e6c2"},
    {"iteration": 4, "label": "keep", "score": 1.0, "pass": 71, "total": 71, "commit": "44a1d1d", "source": "code-review finding, not the eval loop itself"}
  ],
  "consecutive_non_improvements": 0,
  "assertion_streaks": {},
  "stopped": true,
  "stop_reason": "perfect_score"
}
```

**Fields:**
- `iteration` — the last iteration number run (0 = baseline).
- `best_score` / `best_score_pass_total` — the best pass rate reached so far and its raw `[pass, total]`.
- `best_score_history` — one entry per iteration, in order: `label` is `"baseline"`, `"keep"`, or `"discard"`; `commit` only present on `"keep"` entries; `source` is optional free text for entries that didn't come from the loop's own propose-a-fix step (e.g. a PR-review-driven fix applied and re-scored afterward, same as `backfill-promises`'/`backfill-style-principles`'s code-review-hardening commits).
- `consecutive_non_improvements` — current stall streak (0-2); the loop stops when this hits 2.
- `assertion_streaks` — map of assertion id → consecutive-fail count, only for assertions currently mid-streak (empty object once nothing is streaking, e.g. after a perfect score). Feeds the same "flag as eval-design candidate after 2 failed targeted attempts" rule `loop-log.md` documents in prose.
- `stopped` / `stop_reason` — whether the loop has stopped and why: `"perfect_score"`, `"stalled_2_consecutive"`, `"manual_interruption"`, or a specific variant like `"perfect_score_reconfirmed_after_code_review_cleanup"` when a post-loop review commit needed a re-score.

Update this file after every iteration (not just at the end) — its main value is being readable mid-run, including by a resumed/continued session that needs to know where a previous run left off without re-reading the whole log.

## 4. STATUS.md conventions

Each plugin's `~/projekte/skill-evals/{plugin}/STATUS.md` tracks per-skill progress with a
Simulated and a Live column. Five states, not two:

| Symbol | Meaning |
|---|---|
| ⬜ | not attempted yet |
| ✅ | done — put the score in the cell (e.g. `✅ 68/68`) |
| 🟦 N/A | **verified**, not guessed, that this doesn't apply — almost always a Live-column state for a skill with no real MCP domain-tool surface. Verify by actually grepping the SKILL.md for MCP tool calls (`get_`/`create_`/`update_`/`write_`/`list_`/`resolve_path`/etc.) — don't mark N/A on a vague "probably doesn't need it" impression. storyforge's `configure` was wrongly assumed N/A this way at one point; it actually calls `list_authors()`/`get_author()`/`update_author()`. A skill that only mentions MCP as an install/bootstrap sanity check (no domain tool call against real data) is a legitimate N/A — storyforge's `setup` is the precedent. |
| 🟥 BLOCKED | Live column only, and different from N/A: the skill DOES have an MCP domain-tool surface, but the *plugin* has no verified-safe sandbox isolation strategy yet — per the onboarding meta-prompt's step 3a. **Not** about whether the plugin's subject matter is fictional (storyforge's own shared `~/.storyforge/authors/` holds a real, non-sandbox author, `ethan-cole`, right alongside `zz-sandbox-author` — a "fictional domain" is not inherently safe). What actually makes a plugin unblocked is concrete, already-done design work: a positive naming convention marking test entities apart from anything real, path-scoped resets, a shared-vs-isolated-storage reset distinction — exactly what storyforge's `sandbox.md` files document. Default is BLOCKED for every plugin until that design work has actually happened and been verified, regardless of how low-stakes its domain sounds. Stays ⬜/🟥 until a human sandbox-design conversation happens; never auto-resolved, never guessed past. |
| 🟨 NEEDS-HUMAN-REVIEW | in the Notes column, not its own column — flags a specific eval-design ambiguity that an autonomous run correctly declined to guess at or silently resolve. Doesn't block further work on other skills; it's a marker for a human to look at when convenient, not a stop condition. |

Without the N/A state, a skill with no live-tier surface stays ⬜ forever and any automation reading
this file for "what's left to do" can never treat it as complete. Without the distinct BLOCKED
state, a real-world-data plugin's live tier would either get silently skipped (N/A is wrong — it
IS applicable, just gated) or, worse, an autonomous run might attempt to design a sandbox on its
own for something touching real personal/legal/business data.

## 5. When a skill's SKILL.md changes after it was already marked ✅

This will keep happening: an out-of-scope finding gets filed as a GitHub issue during a skill's own
rollout (per the "file, don't fix inline" rule), then gets fixed LATER, and the fix lands back in
that same skill's SKILL.md — after STATUS.md already recorded it as done. Concrete case:
`book-conceptualizer` scored 68/68, then storyforge PR #373/#374 fixed issue #371 (a memoir craft
doc it referenced was wrongly marked fiction+memoir-applicable) by changing what
`book-conceptualizer`'s own Prerequisites section loads — after its ✅ was already recorded.

**Do not assume this either always invalidates the score or never does.** Check concretely:
1. Grep the skill's own `evals.json` for whatever the change actually touched (a filename, a tool
   call, a section name) — don't guess whether it's affected.
2. If a case's *graded expectations* still hold against the new file (even if its prose
   `expected_output` is now stale) — cosmetic fix only, not urgent, not a real problem.
3. If a case's expectation would now fail for a reason that traces to the fix being *correct*
   (the eval assumed the old, since-corrected behavior) — that's eval staleness, not a regression.
   Fix the specific expectation(s), scoped to the affected case(s) only. No need to rerun the whole
   suite — same principle as any other scoped spot-check in this rollout (e.g. re-verifying only
   the affected batch after a PR-review-driven fix).
4. Only re-run the full loop if the change plausibly affects behavior well beyond what a quick grep
   surfaces (a structural rewrite, not a narrow named-reference swap).
5. Note the correction briefly in the skill's STATUS.md row and `loop-log.md` — don't silently edit
   `evals.json` with no trace, or a future reader has no way to tell "eval was always right" from
   "eval was corrected after the fact."

## 6. A brand-new skill appears mid-rollout (not in STATUS.md at all)

Different from §5 (an existing tracked skill's file changing) — this is a plugin gaining an
entirely new skill directory that didn't exist when STATUS.md was first built, so there's no row
for it at all. Concrete case: storyforge's `create-author` live tier found no `delete_author` MCP
tool existed (documented in its own `sandbox.md`); the fix added both a real `delete_author` tool
AND a brand-new `skills/delete-author/` skill — which then had nothing tracking it, and would have
stayed invisible to any batch-selection logic reading STATUS.md forever, since Select only ever
looks at existing rows.

**Detection is structural, not something to remember to do manually each time:** the Select phase
of any automated runner (see `skill-rollout`'s `workflow.js`) should cross-check the plugin's actual
`skills/` directory listing against STATUS.md's rows on every batch, not just trust the row list is
complete. If a directory has no matching row, add one (⬜/⬜) before selecting the batch — don't wait
for a human to notice a skill count went up.

**Placement:** insert the new row at its correct pipeline-order position (check the plugin's own
CLAUDE.md/routing-table — the new skill is very likely adjacent to whatever skill's fix produced it,
`delete-author` landed right next to `create-author` in storyforge's own routing table), not appended
at the end out of laziness. Note in the row why/when it appeared and which other skill's rollout
produced it, so the connection isn't lost. Update the plugin's total skill count in STATUS.md's
footer line too — this is exactly the kind of stale count that's a recurring, easy-to-forget mistake
(storyforge's total was wrongly stuck at 49 for a
while for the same reason: nobody re-counted after the file was first built).
