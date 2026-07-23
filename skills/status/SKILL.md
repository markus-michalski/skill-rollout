---
name: status
description: |
  Show rollout progress for a plugin — the running batch digest plus per-skill
  eval status. Use when: (1) User says "skill rollout status", "wie weit ist der
  Batch", "was ist bisher passiert", "batch status {plugin}", (2)
  `/skill-rollout:status {plugin}`, (3) checking on a long batch mid-run without
  waiting for its completion notification.
model: claude-sonnet-5
user-invocable: true
argument-hint: "{plugin}"
---

# Skill Rollout — status

Read-only progress view for a plugin's rollout. The whole point is that nobody
has to wait for a batch to finish or dig through individual `loop-log.md` files
to see how far it has gotten.

## Workflow

### 1. Resolve the plugin

`{plugin}` is a slug (lowercase letters/digits/hyphens). If not given, ask — or,
if a batch was launched earlier in this session, default to that plugin.

### 2. Read the state (MCP, read-only)

- **`tool_list_evals(plugin)`** — per-skill status parsed from
  `{skillEvalsDir}/{plugin}/STATUS.md`: each skill's simulated/live cells, notes,
  and a derived `fullyDone` flag, plus `counts` (total / fullyDone / notDone). If
  `exists` is `false`, the plugin was never onboarded — say so and stop.
- **`tool_get_batch_status(plugin)`** — the running `batch-digest.md` verbatim
  (each skill appends its result as it finishes). If `exists` is `false`, no batch
  has run yet.

Optionally, for a specific in-flight skill, **`tool_get_eval_state(plugin, skill)`**
returns its `loop-state.json` + the tail of `loop-log.md`.

### 2.5: Live-verify PR merge state (does not modify files)

The text from Step 2 records PR state as free-form prose, written once at the moment each skill's
rollout stage finished — never revisited after that. A PR the text calls "open"/"not merged" may
have been merged since, by a human, entirely outside the rollout process (confirmed in production:
storyforge's batch-digest.md alone has 9 such entries of unknown actual current state; mm-skills'
STATUS.md reported several PRs as open that were long since merged). Trust GitHub for that specific
fact, not old prose.

1. From the combined text of `tool_list_evals`'s per-skill notes and `tool_get_batch_status`'s
   batch-digest content, find every GitHub PR URL (`https://github.com/OWNER/REPO/pull/N`) that
   appears in a context **affirmatively describing it as open/unmerged** — real examples from
   production digests: `"PR #375 open (not merged)"`, `"PR: https://github.com/.../pull/387 (open,
   not merged)"`. Watch for the substring trap: `"not merged"` CONTAINS the word `"merged"` — a
   naive check for the bare word `merged` would wrongly skip exactly the PRs that need checking.
   "Already recorded as merged" means an affirmative statement like `"PR #N merged"` or `"[PR
   #N](...) merged"`, never a negated one. Dedupe by PR URL first (the same PR commonly appears in
   both STATUS.md and batch-digest.md) — check each unique PR at most once.
2. For each unique PR, run `gh pr view N --repo OWNER/REPO --json state,mergedAt` (the number+repo
   form — not the raw URL — so there's no URL string interpolated into the shell call). If the call
   fails (repo inaccessible, PR deleted, `gh` not authenticated for that org): do not fail the whole
   status check over it — keep the stored (possibly stale) text for that one PR and note that live
   verification failed for it.
3. Note, per PR, only the ones where live state actually DIFFERS from the stored text (e.g. stored
   "open", live "MERGED") — that's the only thing Step 3 needs to flag.

**Do not modify any files.** Those files stay exactly as Step 2 read them — an accurate historical
log of what was true when each note was written. This step only changes what gets PRESENTED in
Step 3, never what gets persisted; the skill's read-only contract (see below) is unchanged.

**Out of scope, do not attempt:** a 🟨 NEEDS-HUMAN-REVIEW note can also go stale in a completely
different way — describing a structural harness limitation (e.g. "code-reviewer subagent could not
run") that a LATER version of this very plugin has since fixed. That is not a GitHub-API-verifiable
fact and this step cannot detect it — leave those notes as an accurate historical record, do not
try to guess whether they still apply.

### 3. Present

Summarize concisely:
- **Overall:** `X/Y skills fully done` (from `counts`).
- **Per skill:** a compact table — name, simulated, live, and a one-line note. Where Step 2.5 found
  a live state different from the stored text, show the correction visibly rather than silently
  swapping it in (e.g. "PR #375 — stored: open, **live: MERGED** ✅") — the user should see that
  stale info was caught, not just a different number than they remembered. Surface any
  `NEEDS-HUMAN-REVIEW` (🟨) prominently — those are the things a human actually has to act on.
- **This batch:** the tail of the batch digest (most recent entries first) so the user sees what
  the currently-running or last batch did, with the same PR-state correction applied.

Do not modify any files — this skill remains strictly read-only, exactly as before this step existed.
In particular, never write the live-checked PR state back to STATUS.md or batch-digest.md — Step
2.5 is a presentation-time correction only; nothing gets persisted back to either file.

## MCP-Tools

- `tool_list_evals(plugin)` — per-skill status from STATUS.md
- `tool_get_batch_status(plugin)` — the running batch-digest.md
- `tool_get_eval_state(plugin, skill)` — one skill's loop-state + log tail
