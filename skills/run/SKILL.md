---
name: run
description: |
  Run the self-improvement rollout (Prompt 1/2/3 from the self_improving_skill playbook) over N
  skills of a target Claude plugin, sequentially, fully autonomously within one batch. Stops after
  `count` skills or `max_duration`, whichever comes first — never auto-chains into a next batch,
  the next batch is always a fresh manual invocation. Use when: (1) User says "skill rollout",
  "lass N Skills laufen", "starte einen Batch für {plugin}", "run the rollout", (2)
  `/skill-rollout:run {plugin} {count} [max_duration]`.
model: claude-sonnet-5
user-invocable: true
argument-hint: "{plugin} {count} [max_duration]"
---

# Skill Rollout — run

Unattended, sequential, single-batch runner for the self-improvement-loop process (born out of the
storyforge rollout, generalized for any Claude plugin). The one-batch-no-auto-chaining design is
deliberate: after a batch stops, the operator reviews and merges the resulting PRs/issues before the
next batch is manually invoked — see Step 4 below for how that boundary is enforced.

**This skill is a thin entry point.** All real logic lives in the Workflow script that ships inside
this plugin at `workflows/skill-rollout.js`. This file only resolves arguments, launches that
script, and enforces the wall-clock cutoff the workflow script itself structurally cannot (Workflow
scripts have no access to real time — `Date.now()`/`new Date()` are unavailable there by design).

**No manual deploy, no sync.** Both this `SKILL.md` and `workflows/skill-rollout.js` ship together in
the plugin. The script is launched by its in-plugin path (`workflowScriptPath` from Step 1), not from
`~/.claude/workflows/` — there is nothing to copy or keep in sync, and the repo's `.gitattributes`
guarantees the script is checked out LF-only (the Workflow tool rejects a script containing CR).

## Step 1: Resolve arguments

- **Paths (machine-specific).** Call the MCP tool **`tool_resolve_config`** (server
  `skill-rollout-mcp`). It returns, as absolute forward-slash paths ready to use on any OS:
  - `docsBase` — where the per-plugin playbooks (`self-improving-skill-{plugin}.md`) live
  - `skillEvalsDir` — per-plugin eval state (`STATUS.md`, `loop-log.md`, `batch-digest.md`, ...)
  - `workflowScriptPath` — the in-plugin `workflows/skill-rollout.js` to launch in Step 2
  - `referenceDir` — the plugin's own versioned generic docs (eval schema + onboarding
    meta-prompt); the workflow reads the schema and onboarding playbook from here
  - `pluginRoot`, `configFile`, `configExists`

  If `configExists` is `false`, the neutral defaults are in effect — that is fine for a first run,
  but if `docsBase`/`skillEvalsDir` don't match this machine, tell the user to run
  `/skill-rollout:configure` (or copy `config/config.example.yaml` to `~/.skill-rollout/config.yaml`)
  and adjust the paths, then re-invoke. Do NOT hand-guess paths — `tool_resolve_config` is the only
  source of truth here.
- `{plugin}` — a slug (lowercase letters/digits/hyphens) that must resolve to a real, existing repo
  path. If ambiguous, not given, or doesn't look like a valid slug, ask — this is not something to
  guess. The workflow script re-validates both the slug format and the repo path's existence itself
  before doing anything else, but don't rely on that as the only check — resolve it properly here
  first. Despite the name, this isn't limited to packaged Claude Code plugins (`.claude-plugin/`,
  nested `skills/{name}/SKILL.md`) — a private flat skill-collection repo works too (skills directly
  at `{repo}/{name}/SKILL.md`, no `skills/` subfolder, no MCP server — mm-skills is the reference
  case, and is a valid `{plugin}` target, including running the rollout against this plugin's own
  skills). The Select/Onboard phases in the workflow script auto-detect which layout applies per repo.
- `{count}` (number of skills) and/or `{max_duration}` (wall-clock, e.g. "8h", "10 hours") — at
  least one must be given. If both are missing, ask which stop condition to use. Realistic values
  per the concept doc: `count: 3-5` for a daytime batch, `count: 8-10` / `max_duration: ~8-10h` for
  an overnight batch. Don't accept `count: "all"` without an explicit confirmation — it's supported
  by the workflow but was never actually the intended usage pattern.

## Step 2: Create an isolated worktree, then launch

**Normalize every path first.** Resolve each path argument to an **absolute, forward-slash** form
before launching — expand `~` to the real home directory and convert any Windows `\` to `/`. The
paths from `tool_resolve_config` are already in this form; apply the same normalization to
`{pluginRepoPath}` and `{worktreePath}`. Forward-slash absolute paths work in both Git Bash (where a
literal `\` is an escape char and silently mangles the path) and the file tools (which do not expand
`~`), so this is what stops the workflow's agents from operating on a broken or wrong path on Windows.

**Isolate up front — the launcher does this, the workflow's agents cannot.** The per-skill agents run
inside a Workflow-subagent context where `EnterWorktree` is refused (the cwd override is unavailable
there — confirmed on Windows), so they cannot self-isolate. Instead YOU (the launcher, top-level)
create **one** dedicated, single-use git worktree with plain git — which works on every OS — and hand
it to the workflow via `preIsolated: true`. All sequential skills share this one worktree, each
branching off the remote default branch, so they never collide with each other or with the operator's
main checkout:

Note the two distinct paths below: `{pluginRepoPath}` is the operator's ORIGINAL repo (the `git -C`
target for every worktree command), and `{worktreePath}` is the new sibling worktree you create and
then pass as the `pluginRepoPath` *argument* to the workflow.

1. Pick a worktree path as a **sibling** of the repo (never nested inside it), e.g.
   `{pluginRepoPath}-rollout-wt`.
2. Resolve the repo's default branch — do not assume `main`:
   `git -C "{pluginRepoPath}" symbolic-ref --short refs/remotes/origin/HEAD` yields `origin/<branch>`;
   strip the `origin/` prefix and call the result `{defaultBranch}`.
3. Create the worktree detached at that remote default branch. If a stale one from a prior run
   exists, remove it first:
   - `git -C "{pluginRepoPath}" worktree remove --force "{worktreePath}" 2>/dev/null; true`
   - `git -C "{pluginRepoPath}" fetch origin`
   - `git -C "{pluginRepoPath}" worktree add --detach "{worktreePath}" origin/{defaultBranch}`

Then call the `Workflow` tool with **`scriptPath: {workflowScriptPath}`** (the in-plugin path from
Step 1 — do NOT hardcode any `~/.claude/workflows/` path), args: `{ plugin: "{plugin-name}",
pluginRepoPath: "{worktreePath}", preIsolated: true, count: {count or a large number like 999 if only
max_duration was given}, docsBase: "{resolved docsBase}", skillEvalsDir: "{resolved skillEvalsDir}",
referenceDir: "{resolved referenceDir}" }`. Note **`pluginRepoPath` points at the WORKTREE**, and
`preIsolated: true` tells the agents to work
directly in it (branch per skill off origin/{defaultBranch}) instead of calling `EnterWorktree`. Runs
in the background — let it.

(The workflow still supports the legacy self-isolating mode when launched WITHOUT `preIsolated` — on a
harness where subagent `EnterWorktree` works, that path is fine too — but the worktree-up-front
approach above is the reliable default on all OSes, and the only one that works on Windows.)

**Mid-run visibility:** each skill appends its result to
`{skillEvalsDir}/{plugin-name}/batch-digest.md` as it finishes — the whole point being that nobody has
to wait for the full batch to complete or dig through individual `loop-log.md` files to see progress
so far. If asked "what's happened so far" while a batch is still running, use the `/skill-rollout:status
{plugin}` skill (or read that file directly) instead of waiting for the workflow's own completion
notification.

## Step 3: Enforce `max_duration` from outside the workflow

If `max_duration` was given: call `ScheduleWakeup` for that duration with a reason describing the
batch being watched. When it fires, check the workflow task's status (`TaskOutput` / the notification
you'll receive if it already finished on its own).

- If the workflow already completed on its own (hit `count` first): nothing to do, just relay its
  digest when it arrives.
- If it's still running when the wakeup fires: call `TaskStop` on it. This ends the batch at the
  time limit instead of mid-skill-count. Note explicitly in your report to the user that the batch
  was cut short by time, not by reaching `count` — and that whatever skill was mid-flight when
  stopped may be in a partially-processed state (check its `loop-state.json`/`loop-log.md` next time
  before assuming it's untouched).

## Step 4: Report

Relay the workflow's digest (or the "stopped by time limit" note from Step 3) to the user directly —
**do not start a new batch afterward.** The whole point of this skill, per the concept doc, is
stopping cleanly at one batch's boundary: the user reviews and merges the resulting PRs/issues
before the next batch is manually invoked. Never chain into a second `Workflow` call in the same
invocation.

## Step 5: Remove the isolated worktree

Once the workflow has finished (or was stopped in Step 3), tear down the dedicated worktree created in
Step 2 — every skill branch was already pushed to the remote as an open PR, so nothing on disk needs
to survive:

- `git -C "{pluginRepoPath}" worktree remove --force "{worktreePath}"`
- `git -C "{pluginRepoPath}" worktree prune`
- Optionally delete the local `skill-eval-*` branches the run created (the real artifacts are the
  pushed PRs, so these are just local clutter; they'd otherwise accumulate across runs):
  `git -C "{pluginRepoPath}" for-each-ref --format='%(refname:short)' refs/heads/skill-eval-* | xargs -r git -C "{pluginRepoPath}" branch -D`

Do this even after a time-cut or error stop; a leftover worktree is just clutter and can confuse the
next run's stale-worktree check in Step 2. (Skipped automatically if you launched without
`preIsolated`, i.e. the legacy self-isolating mode, since then no launcher-side worktree exists.)
