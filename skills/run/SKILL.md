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
next batch is manually invoked — see Step 5 below for how that boundary is enforced.

**Before launching — check Auto Mode is ON.** Without it, individual Bash/MCP tool calls inside the
batch (including subagent calls made unattended, away from the keyboard) prompt for approval one by
one, defeating the point of an unattended run. If unsure, ask the operator to confirm before
proceeding — do not launch a long batch expecting it to run hands-off if this hasn't been checked.
A known gotcha: entering Plan Mode during a session turns Auto Mode off as a side effect; if a batch
that previously ran cleanly suddenly starts prompting again, this is the first thing to check.

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
  - `skillEvalsDir` — per-plugin eval state AND the per-plugin playbook: everything for one
    target plugin lives at `skillEvalsDir/{plugin}/` — `STATUS.md`, `batch-digest.md`,
    `self-improving-skill-{plugin}.md`, and per-skill `loop-log.md`/`loop-state.json`
  - `workflowScriptPath` — the in-plugin `workflows/skill-rollout.js` to launch in Step 3
  - `referenceDir` — the plugin's own versioned generic docs (eval schema + onboarding
    meta-prompt); the workflow reads the schema and onboarding playbook from here
  - `pluginRoot`, `configFile`, `configExists`

  If `configExists` is `false`, the neutral default is in effect — that is fine for a first run,
  but if `skillEvalsDir` doesn't match this machine, tell the user to run
  `/skill-rollout:configure` (or copy `config/config.example.yaml` to `~/.skill-rollout/config.yaml`)
  and adjust the path, then re-invoke. Do NOT hand-guess paths — `tool_resolve_config` is the only
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

## Step 2: MCP connectivity pre-flight (issue #51)

**Before creating any worktree or spending any agent budget**, confirm the target plugin's MCP
server (if it has one) is actually connected in THIS session — `enabledPlugins: true` in
`settings.json` is not proof of that. Toggling a plugin on mid-session does not retroactively
connect its MCP server; that needs a fresh session (or a `/plugin-toggle` off→on cycle). Skipping
this check means an entire batch can run its live tier silently as simulated-only, with the gap
buried in each skill's own `needsHumanReview` note instead of stopping the batch before it starts —
this happened for real on 2026-07-25 (a 10-skill storyforge batch, stopped by the operator after 4
skills once the pattern became visible by eye across separate digest entries; all 4 PRs were closed
and reverted since none of the live-tier claims in them were backed by a real MCP call).

1. Check whether `{pluginRepoPath}/.mcp.json` exists. If it does **not**, also check
   `{pluginRepoPath}/.claude-plugin/plugin.json`'s `mcpServers` field — it may point somewhere else
   entirely, or hold the server config inline, rather than defaulting to `./.mcp.json`. Only treat
   this plugin as MCP-free (skip this whole step) once **both** are confirmed absent — flat
   skill-collection repos (mm-skills is the reference case) legitimately have neither, but a missing
   `.mcp.json` alone is not proof of that; don't let this step silently no-op just because the file
   happened to not be at the default path.
2. Read whichever of the two actually holds the config and note the declared server name(s) under
   `mcpServers` — these become the expected tool-name prefix `mcp__plugin_{plugin}_{server-name}__*`
   (or the equivalent for a project-scoped, non-plugin `.mcp.json`).
3. Call `ToolSearch` for that server's tools (e.g. a query built from the plugin/server name) in
   **this session** — the launcher's own, not a subagent's. Check the returned tool **names**
   actually match the expected prefix from step 2 — `ToolSearch` returns best-effort keyword matches,
   so a query can return a different plugin's tools that happen to share vocabulary; a schema coming
   back is not proof it's the right server's schema.
4. **Schemas matching by name is necessary but not sufficient — the server can be registered but its
   process already dead** (e.g. a missing venv, or a stale entry in
   `~/.claude/mcp-needs-auth-cache.json`), in which case its tool schemas are still present in the
   registry even though nothing responds. Make **one real read-only call** to one of the matched
   tools (a `list_*`/`get_*`) and confirm it actually returns data, not just that `ToolSearch` found
   its schema. This is the same check step 5 below already asks the *operator* to do by hand after a
   failure — doing it here, once, up front, is what actually prevents the failure instead of just
   detecting it after the fact.
5. If step 3 found no name-matching tools, OR step 4's real call errors/hangs/fails: **STOP here.**
   Do not create the worktree, do not launch the Workflow. Tell the operator the target plugin's MCP
   server isn't connected (or isn't responding) in this session, and that they need to either start a
   fresh session or run `/plugin-toggle` off→on for the target plugin — then confirm connectivity
   themselves with one real read-only call before retrying this skill. Do not attempt to work around
   it (e.g. by proceeding simulated-tier-only without saying so) — that's exactly the silent failure
   this check exists to prevent.
6. If the real call in step 4 succeeded: proceed to Step 3.

This is a pre-flight only — it does not replace the workflow script's own per-skill defense-in-depth
(if a skill's own Stage A independently discovers the server missing from its tool surface, e.g.
because this check was skipped or the environment changed mid-batch, that surfaces as a loud
batch-level note in the digest, not just a per-skill aside).

## Step 3: Create an isolated worktree, then launch

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
max_duration was given}, skillEvalsDir: "{resolved skillEvalsDir}",
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

## Step 4: Enforce `max_duration` from outside the workflow

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

## Step 5: Report

Relay the workflow's digest (or the "stopped by time limit" note from Step 4) to the user directly —
**do not start a new batch afterward.** The whole point of this skill, per the concept doc, is
stopping cleanly at one batch's boundary: the user reviews and merges the resulting PRs/issues
before the next batch is manually invoked. Never chain into a second `Workflow` call in the same
invocation.

## Step 6: Remove the isolated worktree

Once the workflow has finished (or was stopped in Step 4), tear down the dedicated worktree created in
Step 3 — every skill branch was already pushed to the remote as an open PR, so nothing on disk needs
to survive:

- `git -C "{pluginRepoPath}" worktree remove --force "{worktreePath}"`
- `git -C "{pluginRepoPath}" worktree prune`
- Optionally delete the local `skill-eval-*` branches the run created (the real artifacts are the
  pushed PRs, so these are just local clutter; they'd otherwise accumulate across runs):
  `git -C "{pluginRepoPath}" for-each-ref --format='%(refname:short)' refs/heads/skill-eval-* | xargs -r git -C "{pluginRepoPath}" branch -D`

Do this even after a time-cut or error stop; a leftover worktree is just clutter and can confuse the
next run's stale-worktree check in Step 3. (Skipped automatically if you launched without
`preIsolated`, i.e. the legacy self-isolating mode, since then no launcher-side worktree exists.)
