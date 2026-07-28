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
3. **The Step 3 dirty-check-and-rescue procedure (issue #57), also required by Step 6 below — this
   item ONLY, not item 4 next.** This procedure needs a POSIX-compatible shell (Git Bash on
   Windows, per the same Git Bash already relied on above) — it uses `test -e`, `rm -rf`,
   `$(date ...)`, and shell variable assignment/capture, none of which are valid PowerShell or
   `cmd.exe` syntax. If the Bash tool resolves to PowerShell in this environment, do not attempt a
   literal PowerShell translation on the fly — stop and tell the operator this procedure needs a
   POSIX shell, the same requirement the rest of this skill already has for worktree paths. Before
   removing any stale worktree, check whether it's dirty. A
   prior batch may have left staged-but-uncommitted (or working-tree-modified) changes there — e.g.
   because Stage C received a wrong `hasChanges:false` handoff and skipped committing a real,
   already-verified diff. Force-removing that worktree unconditionally destroys it silently, with no
   recovery path. This item ends either with the worktree removed (clean, or dirty-and-rescued-and-verified),
   with nothing to do at all, or with an explicit STOP — item 4's fetch/create only runs after item 3
   ends in an actual removal or a confirmed nothing-to-remove, never after a STOP.
   - **Confirm `{worktreePath}` is actually a registered worktree first**, not just a same-named
     leftover directory (an aborted `worktree add`, a `prune`-orphaned folder, or anything with its
     own `.git` missing would make git's repo-discovery walk up to a PARENT repo instead, and any
     command below would then silently operate on the wrong repository). Run
     `git -C "{pluginRepoPath}" worktree list --porcelain` and note whether `{worktreePath}` is
     listed, and if so whether its entry is tagged `prunable` (git's own signal that the worktree
     directory is already gone from disk). Then run `git -C "{pluginRepoPath}" worktree prune`
     unconditionally (safe, only forgets already-gone worktrees) — but branch below on what the
     LIST said, not on a fresh list taken after pruning.
     Also check for a `.git` **file** (a linked worktree's `.git` is a file pointing at the main
     repo's `.git/worktrees/...`, never a directory — `test -d` would wrongly say "no .git" for a
     real worktree): `test -e "{worktreePath}/.git"`.
     - **Not in the list at all, and `{worktreePath}` doesn't exist on disk:** nothing to do — skip
       straight to item 4.
     - **In the list but tagged `prunable` (or listed yet `{worktreePath}` doesn't exist on disk):**
       the prune above already cleaned this up — there is nothing on disk to check or rescue. Skip
       straight to item 4. (Without this branch, a worktree whose directory was deleted by hand
       falls through to the registered-worktree status check below, which then errors, is
       misread as "dirty", and dead-ends the whole batch on a STOP over nothing.)
     - **Not in the list, `{worktreePath}` DOES exist on disk, and `test -e "{worktreePath}/.git"`
       fails (no `.git`):** a stray, non-worktree directory (e.g. an interrupted `worktree add`) — it
       cannot be a real git worktree without a `.git` entry, so there is nothing to rescue and no
       repo-discovery risk. **Before deleting, sanity-check the path itself**: confirm
       `{worktreePath}` is non-empty, is an absolute path, ends in the `-rollout-wt` suffix chosen in
       item 1, and is NOT equal to `{pluginRepoPath}`. If any of those checks fail, **STOP** instead —
       do not guess at a path that doesn't look like the one this skill created. Otherwise remove it
       directly, then proceed to item 4: `rm -rf "{worktreePath}"`.
     - **Not in the list, but `test -e "{worktreePath}/.git"` succeeds:** an unusual, likely-corrupted
       state (something with a `.git` that git itself no longer recognizes as a registered worktree)
       — do not guess, and do NOT `rm -rf` it. **STOP.** Leave it in place and tell the operator it
       needs manual inspection before this skill can proceed for `{plugin}`.
   - **If it IS in the list and NOT tagged `prunable`** (a real, on-disk registered worktree), run
     `git -C "{worktreePath}" status --porcelain` and check **both its exit code and its output** —
     do not judge cleanliness from output alone. A non-zero exit code (broken `.git`, `index.lock`
     contention, permission error) is NOT the same as clean; an agent that only looks at stdout can't
     tell them apart, since both can print nothing, and failing to distinguish them means failing
     OPEN onto the destructive remove path.
   - **Clean (exit code `0` AND empty output):** remove it —
     `git -C "{pluginRepoPath}" worktree remove --force "{worktreePath}"`. Check this command's own
     exit code too: if it fails (e.g. the worktree is locked), **STOP** here rather than silently
     continuing to item 4, which would otherwise fail on "already exists" with no context.
   - **Dirty (exit code `0`, non-empty output) OR the status check itself errored:** do NOT discard
     it. Rescue, then verify the rescue actually worked BEFORE removing anything:
     - Create the branch AND capture its exact name in the SAME command, since its output is the
       only place the literal timestamp is ever visible to the agent — later steps and Step 5/6's
       report both need this exact name, not a guess at "the newest one":
       `git -C "{worktreePath}" add -A`, then
       `git -C "{worktreePath}" commit --no-verify -m "rescue: uncommitted changes from interrupted batch"`
       — `--no-verify` is required: an interrupted batch's WIP diff is exactly the kind of
       not-yet-lint-clean state a pre-commit/lint hook in the target repo is likely to reject, and
       this is a data-preservation snapshot, not a real commit that should be gated by the repo's own
       quality gates — then in one call:
       `RESCUE_NAME="rescue/{plugin}-$(date +%Y%m%d-%H%M%S)"; git -C "{worktreePath}" branch
       "$RESCUE_NAME"; echo "$RESCUE_NAME"`. Record the echoed value verbatim — this is the exact
       branch name to report later, not the pattern.
     - **Verify before removing anything, do not just assume the commit succeeded**: `git branch`
       creates a ref at current HEAD regardless of whether the preceding commit actually landed, so
       re-check `git -C "{worktreePath}" status --porcelain` is now exit `0` AND empty, AND that
       `git -C "{pluginRepoPath}" branch --list "rescue/{plugin}-*"` includes the exact
       `$RESCUE_NAME` captured above. (The `--list` glob is used here only because the create and
       verify are separate tool calls with no shared shell state across them — a second
       `$(date ...)` expansion in a fresh verify command would not reliably reproduce the first
       one's literal timestamp; the actual identity check is against the captured, echoed name.)
     - If **either** verification fails: **STOP. Leave the worktree in place, untouched** — do not
       remove it, do not proceed to item 4. Tell the operator the rescue could not be verified (e.g.
       a hook or lock issue) and the worktree needs manual attention. A worktree left on disk is
       harmless clutter; a worktree removed on an unverified rescue is data loss with a false
       all-clear.
     - Only once both verifications pass:
       `git -C "{pluginRepoPath}" worktree remove --force "{worktreePath}"`.
     Report `$RESCUE_NAME` to the operator (Step 5, or Step 6's addendum if this ran during
     teardown) — including a note that `status --porcelain` also picks up untracked files, so the
     operator should confirm the branch holds a real diff and not just incidental build artifacts
     before acting on it.
4. **Only once item 3 above ended in an actual removal or a confirmed nothing-to-remove (never after
   its STOP branch), create the fresh worktree:**
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

If Step 3 found a dirty stale worktree and created a rescue branch, say so explicitly here — name
the branch and tell the operator it holds an interrupted prior batch's uncommitted diff and needs
manual review (cherry-pick, re-run, or discard), since nothing in this skill's own machinery does
that for a rescue branch. Tell them to inspect it with `git show <rescue-branch>` (the tip commit is
always exactly the rescued diff) rather than diffing against the default branch — in `preIsolated`
mode the worktree runs on a per-skill `skill-eval-{skillName}` branch, not detached, so the rescue
branch may carry other in-progress history from that same skill run underneath the rescue commit.
Also note these branches are never auto-deleted (unlike the `skill-eval-*` cleanup below) — that's
intentional, but it means they accumulate across runs until the operator clears the ones they've
already handled.

## Step 6: Remove the isolated worktree

Once the workflow has finished (or was stopped in Step 4), tear down the dedicated worktree created in
Step 3. Normally every skill branch was already pushed to the remote as an open PR, so nothing on
disk needs to survive — but **run Step 3 item 3's full dirty-check-and-rescue procedure (registered-worktree
check, `status --porcelain` exit-code-and-output check, clean-vs-dirty branch, rescue + verify,
STOP-if-unverified) against `{worktreePath}` again, right here, before removing it (issue #57) — NOT
item 4's fetch/create, just item 3's check-and-remove.** This is not optional just because
this is the end of a normal run: Step 4 already acknowledges a `TaskStop`-cut batch can leave a skill
"in a partially-processed state", which is precisely the case this teardown must not blindly discard.
**There is no separate bare `worktree remove --force` command for this step** — the removal that
fires is whichever one item 3's procedure produces (its clean-path command, or its post-rescue
command after verification passes); do not substitute an unconditional remove in its place.

**If item 3's procedure ends in a STOP here, stop this whole step too** — do not run the
`worktree prune` or `skill-eval-*` branch-deletion bullets below. Both operate on the same worktree
and its branches; git's own protections against deleting a branch checked out in a worktree only
apply while that worktree is still *registered* (exactly the state item 3 refused to disturb), so
running them anyway can silently delete the very branch item 3 just decided not to touch. Report the
STOP to the operator and leave everything else in this step undone.

If item 3's procedure creates a rescue branch during THIS run of it (as opposed to during Step 3's
own launch-time run), report that rescue branch to the operator as an addendum here too — Step 5's
report was already delivered before this teardown ran, so a teardown-time rescue has no other
reporting path, and a `TaskStop`-cut batch (the case this step's own opening paragraph calls out) is
if anything the MORE likely time for one to happen.

- `git -C "{pluginRepoPath}" worktree prune`
- Optionally delete the local `skill-eval-*` branches the run created (the real artifacts are the
  pushed PRs, so these are just local clutter; they'd otherwise accumulate across runs):
  `git -C "{pluginRepoPath}" for-each-ref --format='%(refname:short)' refs/heads/skill-eval-* | xargs -r git -C "{pluginRepoPath}" branch -D`

Do this even after a time-cut or error stop, subject to the dirty-check-and-rescue procedure above —
a leftover CLEAN worktree is just clutter, but the next run's Step 3 will now rescue rather than get
confused by a leftover DIRTY one either way. (Skipped automatically if you launched without
`preIsolated`, i.e. the legacy self-isolating mode, since then no launcher-side worktree exists.)
