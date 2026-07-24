export const meta = {
  name: 'skill-rollout-runner',
  description: 'Sequentially run the self-improvement rollout (Prompt 1/2/3) over N skills of a target Claude plugin, one batch, no auto-chaining',
  phases: [
    { title: 'Select', detail: 'read STATUS.md, pick the next skills not yet fully done, in table order' },
    { title: 'Onboard', detail: 'only if this plugin has never been onboarded before' },
    { title: 'Rollout', detail: 'process each selected skill fully, one at a time, never in parallel — eval+edit, then independent review, then commit+PR' },
    { title: 'Digest', detail: 'synthesize one batch-wide summary' },
  ],
}

// This file ships INSIDE the skill-rollout plugin at workflows/skill-rollout.js and IS the single
// source of truth — the run skill launches it via the Workflow tool with
// scriptPath = resolve_config().workflowScriptPath (= ${pluginRoot}/workflows/skill-rollout.js).
// There is no separate ~/.claude/workflows/ deploy copy to keep in sync anymore.
//
// Hard constraint this script is built around: Workflow scripts have no filesystem access and
// cannot use Date.now()/Math.random()/new Date(). Every file read/write happens inside agent()
// calls (which have real tools). Wall-clock "max_duration" cutoff is NOT implemented here for the
// same reason — it's enforced by the calling skill (skills/run/SKILL.md in this plugin) via
// ScheduleWakeup + TaskStop from outside this script's sandbox.
//
// Skill-to-skill processing is a plain sequential loop, deliberately NOT pipeline()/parallel() —
// pipeline() is built for overlap (skill B starts while skill A is still finishing), which is
// exactly what must not happen here: skills share one sandbox author/book, and per the concept
// doc's own "sequential not parallel" requirement, dependency/fixture collisions must be avoided
// by strict one-at-a-time ordering, not just eventual completion.
//
// A DIFFERENT concern from the above: cross-session git races in the plugin's own working directory
// (pluginRepoPath). Documented real incidents (~/projekte/skill-evals/storyforge/*/sandbox.md,
// STATUS.md) show an unattended rollout's git-workflow steps colliding with a concurrent human/other
// session checking out branches or committing in that exact same shared checkout — moved HEAD out
// from under a running skill, overwrote another session's .git-workflow/ state file. Sequential
// skill-to-skill processing does NOT protect against this (it's about a DIFFERENT process, not
// another skill in this batch). Fixed by instructing each git-touching agent prompt to call the
// EnterWorktree/ExitWorktree tools around its own git-workflow steps — each session gets its own
// HEAD/index/working-tree files, so two sessions can no longer step on each other's git state.
//
// Note on `export const meta` + top-level `return` coexisting: this looks like it should be a
// syntax error in plain JS (a module can't have a top-level return, a function body can't have
// `export`), but it's the exact pattern the Workflow tool's own canonical example uses — the
// runtime extracts `meta` via its own parsing before wrapping the rest of the body in an implicit
// async function. Verified against the tool's own documented example, not assumed.
//
// Plugin/path arguments (args.plugin, args.pluginRepoPath) come from a human typing them into the
// skill-rollout SKILL.md's Step 1 — not from an untrusted external source — but they still get
// validated below (slug format, real directory) before being interpolated into agent prompts that
// go on to run real shell/git/gh commands, as defense in depth rather than trusting the caller.
//
// PER-SKILL PIPELINE (issue #13 — supersedes the single-agent self-review design from issue #12):
// each skill now runs as up to THREE sibling agent() calls instead of one monolithic call, so code
// review becomes a real independent reviewer instead of the skill's own agent self-approving its
// own diff:
//   Stage A (evalAndEditPrompt): runs Prompt 1/2/3, stages changes (`git add -A`), does NOT commit.
//   Stage B (reviewPrompt):      independent `git-pr-workflows:code-reviewer` agent reviews the
//                                 staged diff cold — no context on why the edits were made. Skipped
//                                 if Stage A made no changes or stopped early (nothing to review).
//   Stage C (commitPrompt):      applies Stage B's non-security findings, commits, pushes, opens the
//                                 PR, and does the loop-log/STATUS.md/batch-digest bookkeeping. Runs
//                                 for EVERY skill, including early-exits — the bookkeeping write must
//                                 not be skipped just because there was nothing to commit.
// This is a deliberate deviation from issue #13's literal pseudocode (which `continue`s straight to
// a `convertToSkillResult` helper on early-exit, skipping the final agent call entirely): the
// pre-#13 monolithic prompt always reached its "Before you finish" bookkeeping section even for a
// stopped-early skill, and skipping Stage C entirely on early-exit would silently drop that write —
// a regression, not a simplification. Stage C is therefore always invoked; only Stage B is
// conditional on there being something to review.
//
// agentType on Stage B's agent() call is a Workflow-tool-documented, top-level fan-out mechanism —
// NOT the same thing issue #12 hit. #12 failed because a subagent already running inside an agent()
// call tried to spawn ANOTHER agent via Task/Agent (nested spawning, blocked by the Workflow
// boundary). Stage B's agentType call is a sibling agent() call at the SAME level as every other
// call in this script (Select/Onboard/Digest) — no nesting involved. Documented as supported; still
// verify empirically with a real 1-skill batch before trusting it in an unattended overnight run —
// if it turns out not to work in this harness either, do NOT resurrect in-prompt "use Task/Agent"
// text (that's the exact thing #12 already proved broken); fall back to the old self-review design.

const SELECTION_SCHEMA = {
  type: 'object',
  properties: {
    pluginRepoPathExists: { type: 'boolean', description: 'true only if you actually confirmed this directory exists (ls/Bash), never assumed' },
    onboardingNeeded: { type: 'boolean', description: 'true if ~/projekte/skill-evals/{plugin}/ or its STATUS.md does not exist yet' },
    skills: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          simulatedDone: { type: 'boolean' },
          liveDone: { type: 'boolean', description: 'true if Live column is either a real done score OR a verified N/A' },
        },
        required: ['name', 'simulatedDone', 'liveDone'],
      },
    },
  },
  required: ['pluginRepoPathExists', 'onboardingNeeded', 'skills'],
}

const ONBOARD_SCHEMA = {
  type: 'object',
  properties: {
    ok: { type: 'boolean', description: 'false ONLY if something that actually gates a safe rollout (repo layout, MCP-server facts, PR-creation mechanism) could not be confirmed. A non-blocking unconfirmed fact that already has a documented fallback — e.g. branch-protection / merge-policy the GitHub API refuses (HTTP 403 on a private repo with a non-admin token) — is NOT a blocker: put it in needsHumanReview and keep ok=true.' },
    needsHumanReview: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['ok', 'summary'],
}

// Stage A result — evals + SKILL.md edits, staged but NOT committed (issue #13).
const EDIT_RESULT_SCHEMA = {
  type: 'object',
  properties: {
    skill: { type: 'string' },
    hasChanges: { type: 'boolean', description: 'true if `git add -A` staged any diff (tracked or new untracked files) for this skill in pluginRepoPath (or the resumed worktree). false if nothing changed or the stage stopped before touching pluginRepoPath at all.' },
    stoppedEarly: { type: 'boolean' },
    stopReason: { type: 'string' },
    evalScores: {
      type: 'object',
      properties: {
        simulatedScore: { type: 'string' },
        liveScore: { type: 'string', description: '"N/A" if no MCP surface, else pass/total, empty string if not attempted' },
      },
    },
    needsHumanReview: { type: 'array', items: { type: 'string' } },
    issuesFiled: { type: 'array', items: { type: 'string' } },
    worktreePath: { type: 'string', description: 'Only set when non-preIsolated AND EnterWorktree was actually called: the absolute path of the worktree this skill\'s changes are staged in (e.g. via `git rev-parse --show-toplevel` right after entering). Stage B/C must resume THIS SAME worktree via EnterWorktree({path}) rather than creating a new one or operating on the original pluginRepoPath directly. Leave empty when preIsolated (all stages share pluginRepoPath directly, no EnterWorktree involved) or when isolation failed/was skipped.' },
    summary: { type: 'string' },
  },
  required: ['skill', 'hasChanges', 'summary'],
}

// Stage B result — independent review of Stage A's staged, uncommitted diff (issue #13).
const REVIEW_RESULT_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
          file: { type: 'string' },
          line: { type: 'number' },
          description: { type: 'string' },
          isSecurityRisk: { type: 'boolean', description: 'true if this is a security/credential/data-loss risk. Stage C must NOT auto-fix these — they get flagged to needsHumanReview instead, same as the stop-and-flag convention everywhere else in this pipeline.' },
        },
        required: ['severity', 'description'],
      },
    },
    summary: { type: 'string' },
  },
  required: ['findings', 'summary'],
}

const SKILL_RESULT_SCHEMA = {
  type: 'object',
  properties: {
    skill: { type: 'string' },
    simulatedScore: { type: 'string' },
    liveScore: { type: 'string', description: '"N/A" if no MCP surface, else pass/total, empty string if not attempted' },
    prUrls: { type: 'array', items: { type: 'string' } },
    issuesFiled: { type: 'array', items: { type: 'string' } },
    needsHumanReview: { type: 'array', items: { type: 'string' } },
    stoppedEarly: { type: 'boolean' },
    stopReason: { type: 'string' },
    summary: { type: 'string' },
  },
  required: ['skill', 'summary'],
}

const DIGEST_SCHEMA = {
  type: 'object',
  properties: {
    batchSummary: { type: 'string' },
    totalPRs: { type: 'array', items: { type: 'string' } },
    totalIssues: { type: 'array', items: { type: 'string' } },
    totalNeedsHumanReview: { type: 'array', items: { type: 'string' } },
  },
  required: ['batchSummary'],
}

// Plain regex validation, no restricted API involved — fail fast before spending any agent() calls
// on a malformed plugin slug (defense in depth, per code review M2; args come from a human typing
// into the run skill's SKILL.md Step 1, but validate anyway rather than trusting the caller).
function isValidPluginSlug(name) {
  return typeof name === 'string' && /^[a-z0-9][a-z0-9-]*$/.test(name)
}

// The three fixed-name testdata-convention skills (issue #35) get a special-case Stage A instead of
// the normal Prompt 1/2/3 flow — see testdataSkillEvalAndEditPrompt below for why: they're the
// sandbox mechanism itself, and their own live cases would otherwise collide with leftover state
// from prior rollout runs of other skills (or of each other).
const TESTDATA_SKILL_NAMES = new Set(['create-testdata', 'reset-testdata', 'delete-testdata'])

// Shared git-safety rule for EVERY commit to skillEvalsDir (issue #20). skillEvalsDir is a single
// SHARED git repo across every rollout-target plugin (mm-skills, storyforge, ...) with NO isolation
// mechanism — unlike pluginRepoPath, which preIsolated/EnterWorktree already protects. Two rollout
// sessions running concurrently against DIFFERENT plugins still share this ONE repo's working tree,
// index, and HEAD. This function's text must be interpolated at every point in this script (and in
// reference/self-improving-skills.md, reference/prompt-self-improving-skill-playbook.md, and each
// already-onboarded plugin's own self-improving-skill-{plugin}.md) that instructs a commit inside
// skillEvalsDir — do not let any of them drift from this wording.
function skillEvalsGitSafety(skillEvalsDir, pluginName) {
  return `**Git safety rule for EVERY commit inside ${skillEvalsDir} (not the plugin repo — this
applies separately, in addition to whatever git discipline the plugin repo itself needs):**
${skillEvalsDir} is a single SHARED git repo across every plugin this rollout has ever touched, with
NO worktree isolation — a rollout session for a DIFFERENT plugin may be committing to its own
subtree of this exact same repo, in this exact same shared working tree/index/HEAD, at the exact
same time. The two steps below are NOT independent hygiene tips — do both, in order, every time.

1. **Scoped add AND scoped commit — a scoped add alone is not enough.** \`git add
   ${skillEvalsDir}/${pluginName}/\` (or an even more specific sub-path) — NEVER \`git add -A\`, NEVER
   a bare \`git add .\` from ${skillEvalsDir}'s root. But a scoped add only controls what YOU staged —
   a concurrent session's own \`git add\` for ITS plugin can already be sitting in this same shared
   index when you commit, and a plain \`git commit\` snapshots the WHOLE index, not just your own
   staged paths. So commit with the SAME path scope too:
   \`git commit -- ${skillEvalsDir}/${pluginName}/ -m "..."\` (the \`--\` pathspec form commits only
   matching paths regardless of anything else currently staged) — never a bare \`git commit\` here.

2. **On \`git add\`/\`git commit\` failing with an index-lock error** (\`Unable to create '.git/
   index.lock': File exists\`): this means a concurrent session is mid-operation on this same shared
   repo right now — NOT a real error. Wait a few seconds and retry, up to 5 attempts. Never delete or
   otherwise touch the lock file yourself.

3. **On \`git push\` rejection** (another session pushed first): \`git fetch origin\` then \`git
   rebase origin/main\` (or the real default branch) — do NOT run a bare \`git pull\` first, your own
   change is already committed at this point via step 1's scoped commit. Two distinct failure modes,
   handle them differently:
   - **Rebase refuses because the shared working tree has uncommitted changes** ("you have unstaged
     changes" / similar): this means the OTHER session's own in-flight write is sitting in this same
     working tree right now — it is NOT yours to touch. This is transient and should self-resolve
     once that session finishes its own add+commit cycle. Wait a few seconds and retry the whole
     fetch+rebase, up to 5 attempts. **Never** run \`git stash\`, \`git checkout -- .\`, or \`git reset
     --hard\` to "clean up" here — any of those would destroy the other session's uncommitted work,
     which is exactly the outcome this whole rule exists to prevent.
   - **Rebase reports an actual conflicting hunk** (not a refusal, a real content conflict): this
     should not happen given the scoped-commit discipline above (two sessions scoped to different
     plugin subtrees never touch the same file) — if it does anyway, stop, do NOT guess at a
     resolution, add a \`needsHumanReview\` entry naming the conflicting file(s).
   After a successful rebase: retry the push once. **Never \`git push --force\`**, under any of the
   above conditions, no exceptions.`
}

// Isolation preamble shared by all three stages. `role` is 'create' for Stage A (first to touch
// pluginRepoPath — creates the worktree in non-preIsolated mode) or 'resume' for Stage B/C (must
// re-enter the EXACT worktree Stage A created, identified by `worktreePath`, never a fresh one).
function isolationSection(pluginRepoPath, skillName, skillEvalsDir, preIsolated, role, worktreePath) {
  if (preIsolated) {
    return `## Concurrency isolation — already provided; do NOT call EnterWorktree

You are running against a DEDICATED, single-use git worktree checkout at ${pluginRepoPath}, created
by the operator specifically for this batch and used by no other session, and shared by all three
pipeline stages of this skill. Isolation is therefore already guaranteed by the path you were given.
Do NOT call \`EnterWorktree\` — it is unavailable from this workflow-subagent context on this harness
anyway, and calling it and then blocking on failure is exactly the failure this mode exists to avoid.

\`cd "${pluginRepoPath}"\` — this IS your isolated worktree; everywhere below, ${pluginRepoPath} means
this checkout.${role === 'create' ? `

**Safety assertion — do this before ANY git mutation.** Confirm ${pluginRepoPath} really is a linked
worktree and not a primary checkout: a launcher mistake could otherwise point this at the operator's
main checkout, and the branch reset below would then hijack it. Run \`git rev-parse --git-dir\` and
\`git rev-parse --git-common-dir\` — in a linked worktree they DIFFER (equivalently, \`.git\` here is a
file, not a directory). If they are the SAME, this is a primary checkout, NOT an isolated worktree:
do NOT run any state-mutating git command, add a \`needsHumanReview\` entry saying "preIsolated set
but ${pluginRepoPath} is a primary checkout, not a worktree — git-workflow skipped to avoid hijacking
it", and skip this skill's git-workflow (still report its evals/grading normally).

Start this skill from a PRISTINE base branched off the remote default branch, so sequential skills
sharing this one worktree never inherit each other's edits or leftovers (a prior skill may have
stopped mid-edit — the operator's main checkout holds the default branch, and git forbids checking
out the same branch in two worktrees, so branch off the REMOTE ref, do NOT \`git checkout main\`):
\`git fetch origin && git checkout -f -B skill-eval-${skillName} origin/main && git clean -fd\`
(resolve the real default branch with \`git symbolic-ref --short refs/remotes/origin/HEAD\` if it is
not \`main\`; \`git clean -fd\` is safe here — the eval state lives OUTSIDE this worktree). Every
subsequent stage for this skill (review, commit) runs directly on this \`skill-eval-${skillName}\`
branch — do NOT create a separate branch on top of it.` : `

This skill's changes are already staged here by the prior pipeline stage, on branch
\`skill-eval-${skillName}\` — do NOT re-branch, re-fetch, or reset anything; just inspect/build on
what is already staged.`}

Do ALL reads/edits/reviews/git-workflow steps directly in this worktree. There is NO ExitWorktree to
call — the operator owns this worktree's lifecycle across all three stages of every skill in this
batch. Never touch any other worktree or the operator's main checkout; stay entirely inside
${pluginRepoPath}.`
  }

  if (role === 'create') {
    return `## Concurrency isolation — mandatory, do this FIRST, before anything else in this prompt

This exact working directory has been the site of real concurrent-session collisions during past
unattended batches (documented in ${skillEvalsDir}/storyforge/bootstrap-book-from-series/sandbox.md
and two STATUS.md rows there): another process moved the shared HEAD out from under a running
session, and a separate incident overwrote another session's own \`.git-workflow/\` state file. This
is not a hypothetical risk — it has happened, more than once.

Do this BEFORE reading any file, running any eval, or editing anything — not just before staging.
Entering the worktree late means whatever you already read/edited in the shared checkout never makes
it into the worktree, and the staged diff ends up empty or wrong — isolation would silently fail to
isolate anything.

1. \`cd "${pluginRepoPath}"\` first. \`EnterWorktree\` isolates whatever repo your current working
   directory is inside — it does NOT take a repo path argument, so you must actually be in
   ${pluginRepoPath} (not your launch directory) before calling it, or you'll silently isolate the
   wrong repo while every real git mutation still lands in the shared, unisolated checkout.
2. Call the \`EnterWorktree\` tool (no \`name\`/\`path\` needed — a fresh worktree is created and you're
   switched into it automatically).
3. From this point on, ${pluginRepoPath} in every instruction below means the worktree you just
   entered, not the original shared path — do ALL reads, edits, and evals inside it.
4. **Do NOT call ExitWorktree.** Unlike the old single-agent design, this stage does not finish the
   skill's work — a review stage and a commit stage still need to operate in this exact worktree
   after you're done. Calling ExitWorktree here would strand your staged changes in a worktree no
   later stage can find. Instead: immediately after entering, capture the worktree's real absolute
   path (\`git rev-parse --show-toplevel\`) and return it as \`worktreePath\` in your structured result
   — that is the ONLY way the next stage knows which worktree to resume, since each stage is a fresh
   agent with no memory of this one.
5. If \`EnterWorktree\` fails or is unavailable for any reason, do NOT fall back to working directly
   in the shared checkout — add a \`needsHumanReview\` entry naming this a concurrency-isolation gap
   for this skill's run, leave \`worktreePath\` empty, set \`hasChanges: false\`, and stop before any
   git mutation (still report the rest of this skill's tiers — evals, grading — normally; only the
   git-workflow portion is blocked by this).
6. Never touch any other worktree or the operator's main checkout; stay entirely inside the worktree
   you just entered.`
  }

  // role === 'resume', non-preIsolated
  return worktreePath
    ? `## Concurrency isolation — resume the SAME worktree the prior stage created

The prior stage isolated this skill's work in a dedicated worktree and left it open (deliberately did
not call ExitWorktree) so this stage can pick up exactly where it left off. Do NOT call
\`EnterWorktree\` with a \`name\` — that would create a brand-new, EMPTY worktree containing none of the
prior stage's staged changes, which would make this stage silently operate on nothing.

1. \`cd "${pluginRepoPath}"\` first (the operator's original repo — needed for EnterWorktree's own
   repo-resolution, same as the create step).
2. Call \`EnterWorktree\` with \`path: "${worktreePath}"\` to resume that exact worktree.
3. From this point on, ${pluginRepoPath} in every instruction below means that resumed worktree.
4. Never touch any other worktree or the operator's main checkout.
5. **If this \`EnterWorktree({path: ...})\` call fails or is unavailable to you in this context:** do
   NOT fall back to the shared, unisolated checkout — you would silently inspect the wrong tree (no
   staged diff visible there) and could mistake that for "nothing to find". Stop here without
   inspecting, editing, or committing anything. If you are the review stage: return an EMPTY findings
   array with a summary that EXPLICITLY states the resume failed and no review actually happened —
   never phrase this as "diff reviewed, found nothing clean", that would misrepresent a skipped
   review as a completed one. If you are the commit stage: do NOT commit, add a \`needsHumanReview\`
   entry naming this a concurrency-isolation gap, and treat this skill the same as "nothing to
   commit" for your bookkeeping writes.`
    : `## Concurrency isolation — nothing to resume

The prior stage reported no \`worktreePath\` (isolation failed, was skipped, or nothing was staged).
Do NOT call EnterWorktree yourself — there is nothing prepared for you to resume, and creating a
fresh empty worktree here would just isolate you from the (nonexistent) staged diff. Treat this as
"nothing to review/commit for this skill" and skip straight to the bookkeeping/reporting portion of
this stage's instructions.`
}

function evalAndEditPrompt(pluginName, pluginRepoPath, skillName, skillEvalsDir, preIsolated, evalSchemaPath, referenceDir) {
  return `You are Stage A (eval + edit) of a 3-stage unattended pipeline for ONE skill, as part of an
unattended batch. No human will review anything until an independent reviewer (Stage B, a separate
agent) sees your diff — act accordingly, but DO NOT guess at anything you can verify or that
materially affects safety/correctness.

Plugin: ${pluginName} (repo: ${pluginRepoPath})
Skill: ${skillName}

(Note: the doc paths below may contain spaces — quote them in any shell command.)

${isolationSection(pluginRepoPath, skillName, skillEvalsDir, preIsolated, 'create', null)}

## Source of truth — read these first, in order, don't re-derive what they already document

1. ${skillEvalsDir}/${pluginName}/self-improving-skill-${pluginName}.md
   — the plugin-specific playbook (Prompt 1/2/3, repo facts: MCP server name/prefix if any, deploy
   sync locations, branch protection, whether a PreToolUse hook blocks \`gh pr create\`). This file
   is the authority on all plugin-specific facts — never assume storyforge's facts apply to a
   different plugin.
2. ${evalSchemaPath} — eval schema (simulated + live), the MANDATORY
   adversarial-realistic grading methodology (never plain self-grading — a perfect score on the
   first baseline run is a red flag, not a clean result), the loop-state.json format, and the
   STATUS.md N/A / NEEDS-HUMAN-REVIEW conventions.
3. ${skillEvalsDir}/${pluginName}/${skillName}/loop-log.md and loop-state.json if they exist
   — don't redo work already done; continue from where a prior run left off.

## What to actually do

**Prompt 1 (build evals.json) — only if ${skillEvalsDir}/${pluginName}/${skillName}/evals.json
doesn't exist yet.** Follow the plugin playbook's Prompt 1 exactly.

**Prompt 2 (simulated loop) — only if the Simulated column for this skill isn't already ✅.** Follow
the plugin playbook's Prompt 2 exactly, with these autonomous-mode additions:

- Every grading pass MUST use adversarial-realistic instructions (${evalSchemaPath}) — no exceptions, even
  under time pressure. A suspiciously perfect first-baseline score is not something to celebrate,
  it's something to double check the grading methodology on before trusting it.
- **Eval-design-candidate assertions** (same specific assertion fails 2 targeted-fix attempts):
  classify before doing anything else. If it's narration-dependent (asks the transcript to
  "explicitly note/cite X") or provably conflicts with the skill's own stated output terseness —
  fix the eval itself (remove/reframe), log why, stage it. Otherwise (genuinely ambiguous, you can't
  self-certify which reading is right): do NOT touch the eval, do NOT keep chasing it. Mark it
  \`NEEDS-HUMAN-REVIEW\` in loop-log.md and in this skill's STATUS.md Notes cell. This does not stop
  your work on this skill — move on.
- **Residual notes** (something you notice that no assertion covers): if it's in scope for the
  section/step you're already touching, fold it into your current fix. If it's out of scope
  (different skill, different subsystem, a bigger design question) — file a real GitHub issue in
  ${pluginRepoPath}'s repo IMMEDIATELY (\`gh issue create\`), never just mention it in prose. This
  applies in the simulated tier too, not only the live tier — a real example: a book-conceptualizer
  run found two stale skill-name references this way and they'd have been lost if not filed.
  **Issue title format is fixed, not your call:** \`${skillName}: <description>\` — no
  fix/feat/bug/refactor prefix, see ${evalSchemaPath} §7 for the full convention and why it exists
  (past runs drifted across four different title shapes in the same repo before this was written
  down).
- **Incremental progress logging** — after every full grade-fix-regrade cycle (one iteration of
  the improvement loop): immediately append a timestamped entry (real time via \`date\`, same as the
  batch digest) to \`${skillEvalsDir}/${pluginName}/${skillName}/loop-log.md\` documenting what you
  fixed and what the updated score is, and update \`loop-state.json\` to reflect current iteration
  state. Do NOT defer both writes to the end of this stage — a mid-run \`/skill-rollout:status\` check
  should be meaningful even while this skill is still being processed. Whenever any of this work gets
  committed inside ${skillEvalsDir} (evals.json's initial commit, or these loop-log/loop-state
  writes) — including the plugin playbook's own Prompt 1/Prompt 2 commit instructions:

${skillEvalsGitSafety(skillEvalsDir, pluginName)}

**Prompt 3 (live-MCP tier) — only if ALL of: the plugin has a real MCP server (per the playbook's
repo facts) AND this skill's SKILL.md actually calls domain MCP tools (grep it — don't assume from a
skill's name or a stale STATUS.md note; \`configure\` in storyforge was wrongly assumed MCP-free once
and it wasn't) AND the Live column isn't already ✅ or verified N/A AND the plugin playbook's own
Prompt 3 section is a real, ready-to-run prompt, not a blocked placeholder.**

**Read-only bypass, check this FIRST, before the hard gate below (issue #24):** grep every domain
MCP tool call this skill's own SKILL.md actually makes — not a plugin-wide sample, this specific
skill's own surface, real invocations only (a tool NAMED in cautionary prose, e.g. "unlike
\`update_note\`, this skill only reads", is not itself a call). Two independent conditions must both
hold, checked in this order:

1. **Classify by what each tool DOES, not by its name.** For every call found, confirm from the
   tool's actual documented behavior (its description, or the MCP server's own source if the
   description is ambiguous) that it cannot create/update/delete/move/append/write anything — never
   infer this from a prefix alone. A name that LOOKS read-ish is not evidence: e.g. a hypothetical
   \`search_and_replace_X\` starts with \`search_\` but mutates; \`resolve_and_apply_Y\` starts with
   \`resolve_\` but applies a change. The read-verb prefixes below are a closed list to sanity-check
   against, NOT a shortcut that replaces checking real behavior — a call matching one of these
   prefixes still needs its actual behavior confirmed, and a call matching NONE of them (even if it
   "sounds read-only" some other way) fails this bypass outright, no exceptions invented on the spot:
   \`get_\`, \`list_\`, \`search_\`, \`resolve_\`, \`read_\`. If you cannot confirm a call's real
   behavior with confidence, treat it as disqualifying — fall through to the hard gate, do not guess
   it's safe.
2. **Zero write-capable calls anywhere in this skill's surface**, per that same real-behavior check —
   \`create_\`, \`update_\`, \`delete_\`, \`write_\`, \`move_\`, \`append_\`, and any other verb (this
   list is illustrative, not closed) whose actual behavior mutates state. One write-capable call
   anywhere disqualifies the whole skill from this bypass — no partial credit; fall through to the
   hard gate below as normal.

**Even if both conditions above hold, this bypass addresses MUTATION risk only — it is not a
read-anything clearance.** If the real data these calls would READ is itself sensitive (personal,
legal, medical, or business/customer data — not just "this plugin's own docs" or public content),
that is still a stop-and-flag under the "would touch real non-sandbox data" condition later in this
prompt, exactly as if this were a write. Read-only clearance existing for storyforge/mm-skills-style
lookups (public wiki pages, the plugin's own project registry) does not generalize to a skill whose
read surface touches a real person's case file, medical record, or financial data — treat that case
as blocked regardless of mutation risk, add the \`needsHumanReview\` entry, and do not proceed.

If — and only if — both conditions above hold AND the data being read isn't independently sensitive:
this skill is 🟩 READ-ONLY-cleared regardless of the plugin-level sandbox gate below. Skip the hard
gate entirely and go straight to running Prompt 3 against the real system, per the "if the gate
above does NOT apply" paragraph further down. Record in loop-log.md which calls you found, their
confirmed real behavior (not just their names), and that zero were write-capable — so the
classification is auditable, not asserted.

**Hard gate, check this if the read-only bypass above did NOT apply:** if the plugin playbook states
that this plugin has not yet implemented and verified the \`create-testdata\`/\`reset-testdata\`/
\`delete-testdata\` convention (per \`reference/prompt-self-improving-skill-playbook.md\` Phase 1 step
3a's discovery+static+live checks — issue #35), do NOT attempt Prompt 3 yourself, do NOT invent a
sandbox strategy on the spot no matter how sensible it seems, and do NOT skip it silently either.
This gate is about whether that three-skill convention already exists and is verified-safe for the
plugin's shared storage — NOT about whether the plugin's subject matter sounds fictional or
low-stakes. storyforge's own shared \`~/.storyforge/authors/\` holds a real, non-sandbox author
(\`ethan-cole\`) right next to \`zz-sandbox-author\` — a "fictional domain" is not automatically safe,
and a corrupted real chapter is just as real a loss as a corrupted real legal case. storyforge only
qualifies because the underlying design (the \`zz-sandbox-\` naming convention, path-scoped resets,
the isolated-files-vs-shared-DB distinction — see its own \`sandbox.md\` files) is what the three-skill
convention's \`create-testdata\`/\`reset-testdata\`/\`delete-testdata\` skills are expected to encode and
enforce, not because of its subject matter. Add an entry to \`needsHumanReview\` naming this skill and
stating that its live tier is blocked pending the three-skill convention being implemented (or fixed)
for this plugin — point at the per-plugin GitHub issue if the playbook names one, this is a buildable
engineering task, never an undefined "conversation" — mark the Live column 🟥 BLOCKED (not ⬜ — leaving
it ⬜ is indistinguishable from "not attempted yet"; not N/A either — N/A means "verified not
applicable", this is "applicable but blocked", a third, distinct state), and move on. This is exactly
as hard a stop as the "would touch real non-sandbox data" condition later in this prompt — because
it's the same risk, just caught earlier, before any sandbox even exists to accidentally misuse.

**MCP Surface Register pre-check (issue #26/#27) — sandbox-exists path only, run this BEFORE any
live case that writes anything.** Read \`${skillEvalsDir}/${pluginName}/mcp-surface-register.md\`.
If it does not exist yet — either this plugin's onboarding predates this register (e.g. an
already-onboarded plugin like storyforge, self-healing on its first rollout after this feature
shipped) or something skipped the onboarding step that should have created it — create it now with
the two empty table skeletons rather than treating a missing file as a blocker; do not assume
"missing" means "first-ever live-tier run for this plugin", it doesn't for storyforge. Full
mechanics in \`${referenceDir || '(referenceDir not provided — see the warning already logged for this run)'}/self-improving-skills.md\`'s
"MCP Surface Register" section, do not re-derive them here. For each planned live case:
1. Look up every MCP tool it calls in the register's Tool Scope table. A tool with no entity-scoping
   slug parameter (writes/reads one single row shared plugin-wide, not per-author/book/chapter) is
   \`global-singleton\` — classify by real behavior, same rigor as the read-only bypass above, not by
   guessing from the name; add a new row if this tool isn't in the register yet.
2. **Rule 1, mandatory for every \`global-singleton\` write, no exceptions:** capture its current
   value via a real read/get call immediately before making the write — this alone prevents the
   documented chapter-writer failure mode (prior value never captured, restore impossible).
3. Decide restore strategy by what happens AFTER the call, not by why the call is being made: does
   this case's own assertions, a later step in this same skill, or another skill's live case
   (current or future — the register is plugin-wide, the singleton has no sandbox baseline) read
   this value afterward? If nothing does: \`no-restore-accepted-drift\` — do not attempt a restore,
   do not downgrade the rest of this case to simulated, just don't assert on this one call's effect;
   record it as an expected outcome, not a NEEDS-HUMAN-REVIEW flag (this is issue #26's actual
   fix). If something does: \`best-effort-snapshot-restore\` — restore the captured value afterward,
   document any lossy edge case actually hit (e.g. a transport limitation), and never claim a
   byte-identical restore you didn't verify.
4. Look up every fixture STATE this skill's live cases need (an enum value, a specific field) in the
   register's Fixture Inventory table. Missing and it's a known enum permutation of the domain (not
   inventing a new data shape) → create it once via the plugin's own real creation MCP tool,
   \`zz-sandbox-\`-prefixed, same discipline as any other sandbox entity; record the addition in the
   register immediately. Missing and not safely auto-creatable → block only THIS specific case with
   a named gap (\"case N needs fixture state X on entity Y, does not exist\") in \`needsHumanReview\`,
   keep running this skill's other cases normally — this is issue #27's actual fix, replacing the
   old pattern of leaving a vague NEEDS-HUMAN-REVIEW note that nothing ever resolves.
5. Write back anything newly learned into the register before finishing this skill's live tier —
   the whole point is that skill #2 never re-derives what skill #1 already found. Commit it under
   the same scoped-add/scoped-commit git-safety rule as every other \`${skillEvalsDir}\` file.

If neither block above stopped you — either this skill cleared the read-only bypass, or a
verified-safe sandbox strategy already exists for this plugin (storyforge being the only confirmed
case today, purely because that design work happened here first) — run Prompt 3 against the real
system, with the exact evidentiary rigor depending on which path got you here:
- **Read-only-cleared skill:** no sandbox needed — there is nothing to reset before or after, since
  a read cannot mutate shared state. Still require a real \`tool_use\` block as evidence for every
  claimed call (never take the executor's prose claim alone), and still run cases strictly in
  sequence.
- **Sandbox-exists path:** follow the plugin playbook's Prompt 3 exactly, including the MCP Surface
  Register pre-check just above for every case that writes anything: reuse the shared sandbox,
  never touch another skill's fixtures, scope every reset to the exact sub-path this skill's own
  cases touch, run live cases strictly in sequence (never parallel — they mutate shared state),
  require a real tool_use block as evidence for every claimed action, verify claimed side effects
  with an independent post-run check.

If this skill's SKILL.md genuinely has no MCP domain-tool calls at all (a different case from the
gate above — this is "no live tier needed", not "blocked"): do NOT leave the Live column ⬜. Grep it
yourself to confirm, then mark it 🟦 N/A in STATUS.md with a one-line note of what you checked (per
${evalSchemaPath}'s convention) — this is required, not optional, so a future batch selection doesn't wait
forever on a skill that will never have a live tier.

## Stage boundary — stop here, do NOT commit the ${pluginRepoPath} diff

This is Stage A of a 3-stage pipeline (eval+edit → independent review → commit+PR). An independent
reviewer sees your ${pluginRepoPath} diff next; you never commit, push, or open a PR for it
yourself. **This prohibition is about ${pluginRepoPath} specifically — it does NOT apply to
${skillEvalsDir}.** evals.json's initial commit (per the plugin playbook's Prompt 1) and any
loop-log.md/loop-state.json commits from the "Incremental progress logging" step above happen
INSIDE this stage, into the separate ${skillEvalsDir} repo, following the git-safety rule given
there — that is expected and correct, not a violation of this boundary.

1. If you made no file changes at all in ${pluginRepoPath} (skill turned out already fully done, or
   you stopped early per a stop-and-flag condition below): set \`hasChanges: false\` and do NOT run
   \`git add\`.
2. Otherwise: \`git add -A\` (stage everything, including new untracked eval/fixture files) but do
   **not** run \`git commit\`. The staged diff is exactly what Stage B will review — anything you
   leave unstaged is invisible to it.
3. Do NOT write the closing loop-log.md entry, STATUS.md's final state, or batch-digest.md yet —
   those happen in Stage C, after the diff has actually been reviewed and (if needed) fixed, so they
   reflect the true final state rather than a pre-review guess. The per-iteration loop-log entries
   from Prompt 2 above still happen as normal — only the CLOSING entry is deferred.

## Stop-and-flag conditions (the only things that should make you NOT just proceed)

Add an entry to \`needsHumanReview\` (do not guess, do not silently proceed) if you hit:
- Ambiguity about whether a live-tier case, handled wrong, would touch real (non-sandbox) data.
- Any destructive git operation outside the sanctioned pattern (force-push, history rewrite) —
  this stage should never need one; if something seems to require it, stop and flag instead.
- A finding that clearly belongs to a different, unrelated repo this rollout isn't authorized to
  touch (file the issue in the right repo if you can identify it; do not push there).

Everything else (including NEEDS-HUMAN-REVIEW eval-design flags) does not block you — keep going.

## Return value

Return the structured result: hasChanges, stoppedEarly/stopReason, evalScores (simulated/live),
needsHumanReview, issuesFiled (filed during Prompt 2/3 residual-note handling), worktreePath (per
the isolation section above — only set when non-preIsolated and you actually called EnterWorktree),
and a short prose summary of what you did.`
}

// Special-case Stage A for the three fixed-name testdata-convention skills (issue #35):
// create-testdata/reset-testdata/delete-testdata. As ORDINARY skills in their target plugin they get
// their own STATUS.md rows and would otherwise go through the normal Prompt 1/2/3 flow — but that
// creates an ordering problem: create-testdata's own live case would very likely find test data
// already left over from a prior rollout run of a DIFFERENT skill (or of one of its own two
// siblings, since all three eventually get rolled out in the same batch/plugin), and a naive test
// would either fail on an unexpected precondition or create duplicate fixtures. Fix: a fixed test
// sequence (check exists -> delete if exists -> create -> reset) that exercises all three code paths
// deterministically in one pass, regardless of which of the three is the CURRENT skill being rolled
// out, and leaves the sandbox clean for every other skill's rollout afterward.
function testdataSkillEvalAndEditPrompt(pluginName, pluginRepoPath, skillName, skillEvalsDir, preIsolated, evalSchemaPath, referenceDir) {
  return `You are Stage A (eval + edit) of a 3-stage unattended pipeline for ONE skill — but this run
is the SPECIAL CASE for \`${skillName}\`, one of the three fixed-name testdata-convention skills
(\`create-testdata\`/\`reset-testdata\`/\`delete-testdata\`, issue #35). Do NOT follow the normal
Prompt 1/2/3 flow described in the plugin playbook for this skill — these three skills ARE the
sandbox mechanism every other skill's live tier depends on, not an ordinary domain skill, and testing
them the normal way creates an ordering problem: this skill's own live case would very likely find
test data already left over from a PRIOR rollout run of a different skill (or of one of its two
siblings), and a naive test would either fail on an unexpected precondition or create duplicate
fixtures.

Plugin: ${pluginName} (repo: ${pluginRepoPath})
Skill: ${skillName}

(Note: the doc paths below may contain spaces — quote them in any shell command.)

Background on why this convention exists and what each of the three skills must guarantee (the
Hard Safety Rule, the \`zz-sandbox-\` prefix decision, idempotency requirement):
${referenceDir || '(referenceDir not provided — see the warning already logged for this run)'}/self-improving-skills.md's
"create-testdata / reset-testdata / delete-testdata Convention" section — read it if anything below
is ambiguous, do not re-derive the convention from first principles.

${isolationSection(pluginRepoPath, skillName, skillEvalsDir, preIsolated, 'create', null)}

## The fixed test sequence — run this instead of Prompt 1/2/3, regardless of which of the three
## skills is the one actually being rolled out right now

Run all three skills' real behavior, in this exact order, discovering each via ToolSearch/Skill
invocation if not already loaded — never simulate any of these calls, every step below needs a real
\`tool_use\`/Skill-invocation as evidence, same evidentiary rigor as any other live-tier case in this
rollout:

1. **Check whether test data already exists.** Use whichever read/lookup path this plugin's own
   sandbox convention provides (per ${skillEvalsDir}/${pluginName}/mcp-surface-register.md's Fixture
   Inventory table if populated, or the target plugin's own \`create-testdata\`/\`reset-testdata\`
   SKILL.md for how existence is checked) to determine if \`zz-sandbox-\`-prefixed test entities are
   already present from a prior rollout run. This does NOT decide whether step 2 runs — it only sets
   which of step 2's two valid outcomes you expect to see.
2. **Run \`delete-testdata\`, UNCONDITIONALLY, regardless of what step 1 found.** This is this skill's
   own live case whenever \`${skillName}\` is \`delete-testdata\` — it must actually execute every
   single pass, never be skipped because the sandbox happened to start empty. An earlier version of
   this sequence only ran \`delete-testdata\` "if test data already exists", which meant a
   freshly-cleaned sandbox could reach the end of this sequence having marked \`delete-testdata\`'s
   Live column ✅ without the tool ever having been called once — a false pass, exactly the failure
   class this whole convention exists to prevent. Two valid outcomes, matching what step 1 found:
   - **Step 1 found existing test data:** confirm via an independent post-call read that it is now
     actually gone.
   - **Step 1 found nothing (fresh/empty sandbox):** confirm the call recognizes "nothing to delete"
     and proceeds without erroring — **\`delete-testdata\` must be idempotent/no-op-safe on an empty
     sandbox**; if it errors instead, that is itself a real bug to fix in this skill (same as any
     other Prompt-2-style fix), not something to route around by skipping the call.
   This step also serves as setup for step 3 below (guaranteeing a known-clean starting point before
   \`create-testdata\` runs) whenever \`${skillName}\` is one of the OTHER two skills — one
   unconditional call covers both purposes, there is no separate "setup-only" invocation.
3. **Run \`create-testdata\`.** Confirm via an independent post-call read that the entities it claims
   to have created actually exist, \`zz-sandbox-\`-prefixed, via the plugin's own real creation tools
   (never hand-written files) — record the returned slugs/IDs.
4. **Run \`reset-testdata\`.** Mutate one of the just-created entities' fields first (a trivial,
   reversible change, so there is something real to reset), then call \`reset-testdata\` and confirm
   via an independent post-call read that the entity is back at its documented baseline state AND
   still exists (reset must never delete — that would make it indistinguishable from
   \`delete-testdata\`, defeating the whole point of having two separate skills).

This exercises all three code paths deterministically in a single pass and leaves the sandbox in a
clean, known-good state for every other skill's rollout to use afterward — regardless of which ONE of
the three skills \`${skillName}\` happens to be, running the full sequence is what actually tests it,
since each skill's correctness depends on the other two behaving correctly around it (you cannot
meaningfully test \`reset-testdata\` without a working \`create-testdata\` first, and you cannot safely
re-run \`create-testdata\` without a working \`delete-testdata\` to clear prior leftovers first).

## Grading this skill

Treat step 2 above (which always ran, per the fix to the ordering problem described there) as this
skill's own live case if \`${skillName}\` is \`delete-testdata\`; step 3 if \`${skillName}\` is
\`create-testdata\`; step 4 if \`${skillName}\` is \`reset-testdata\`. Grade that step's specific
behavior adversarially — same methodology as any other
live case (${evalSchemaPath}): did it actually call the plugin's real tools (not narrate), did the
claimed side effect actually happen per an independent read, did the \`zz-sandbox-\`-prefix refuse
guard get exercised correctly. If this skill's SKILL.md needs a fix as a result (e.g. the idempotency
requirement in step 2 was violated, or the prefix guard didn't fire before the underlying operation),
propose and make ONE change, same content-capture-before-edit / keep-if-improved-else-restore
discipline as Prompt 2 in the plugin playbook — capture the file's exact content via a plain Read
before the edit, re-run the relevant step of the sequence above to re-verify, keep or restore based on
whether the specific defect is now fixed (there is no numeric pass-rate score here the way evals.json
produces one — "keep" means the sequence step this skill owns now behaves correctly per the check
above, "discard" means it doesn't and the content-based restore applies).

Do NOT create an evals.json or run a simulated-tier grading loop for this skill — the fixed sequence
above IS this skill's test, both simulated-equivalent (does the logic make sense) and live (did the
real tool calls behave correctly) collapse into the one sequence for these three special-case skills.
Mark this skill's Simulated column ✅ with a one-line note "tested via the create/reset/delete fixed
sequence, no evals.json (issue #35 special case)" instead of a pass/total score, and its Live column
✅ the same way, once the sequence above has run clean for this skill's own step.

${skillEvalsGitSafety(skillEvalsDir, pluginName)}

## Stage boundary — stop here, do NOT commit the ${pluginRepoPath} diff

Same boundary as the normal pipeline: an independent reviewer sees your ${pluginRepoPath} diff next
(if this skill's own fix touched its SKILL.md); you never commit, push, or open a PR for it yourself.
If you made no SKILL.md changes (the sequence ran clean, nothing needed fixing): set \`hasChanges:
false\` and do NOT run \`git add\`. Otherwise: \`git add -A\`, do NOT \`git commit\`.

## Stop-and-flag conditions

Add an entry to \`needsHumanReview\` if:
- \`delete-testdata\` is NOT idempotent/no-op-safe on an empty sandbox and you could not fix it in one
  targeted change.
- Any step's \`zz-sandbox-\`-prefix refuse guard did not fire correctly when it should have — this is a
  genuine safety defect in the sandbox mechanism itself, not a normal eval-loop finding; flag it
  loudly and do NOT let this plugin's other skills' Live columns be treated as unblocked until it's
  fixed.
- Ambiguity about whether any step in the sequence touched real (non-\`zz-sandbox-\`) data.

## Return value

Return the structured result: hasChanges, stoppedEarly/stopReason, evalScores (simulatedScore/
liveScore as the fixed-sequence note described above, not a pass/total), needsHumanReview,
issuesFiled, worktreePath, and a short prose summary of the sequence run and this skill's own step's
outcome.`
}

function reviewPrompt(pluginName, pluginRepoPath, skillName, skillEvalsDir, preIsolated, worktreePath) {
  return `You are Stage B (independent review) of a 3-stage unattended pipeline for ONE skill. You did
NOT write these changes and have no prior context on why they were made — review them on their own
merits, the same way you would review a stranger's pull request. Nothing here should be taken on
trust from whatever produced the diff.

Plugin: ${pluginName} (repo: ${pluginRepoPath})
Skill: ${skillName}

${isolationSection(pluginRepoPath, skillName, skillEvalsDir, preIsolated, 'resume', worktreePath)}

## What to review

Inspect the staged diff — not bare \`git diff\`, which misses untracked new files (this rollout
routinely creates new fixture and eval files):
- \`git diff HEAD\` — staged + unstaged tracked changes.
- \`git status --porcelain\` — catches new untracked files. Read each one in full; you cannot review
  what you have not read.

Review every changed chunk adversarially for each of these categories:
- **Logic/correctness**: off-by-one mistakes, wrong variable, broken edge case, incorrect score
  arithmetic, an assertion that would trivially pass even with a wrong implementation.
- **SKILL.md structural compliance**: required frontmatter fields present and non-empty, no banned
  patterns (check the plugin's own CLAUDE.md ban-list if it has one), "Use when…" description is
  trigger-rich and specific, model ID is a valid current-release Claude model string.
- **Eval design quality**: assertions test actual behavior, not transcript phrases; grading is
  adversarial-realistic (never self-grading); no narration-dependent assertion that only checks
  whether the skill "explicitly noted X" in its own output.
- **Data hygiene**: no machine-specific paths, no sandbox-author names hardcoded where a generic
  placeholder belongs, no credentials or API tokens even in comments.
- **Cross-file consistency**: do changes in one file contradict any other changed file in this same
  diff? (E.g. a SKILL.md step referencing a tool the MCP server no longer exports.)
- **Security/credential/data-loss risk**: mark any such finding with \`isSecurityRisk: true\` — the
  next stage must NOT auto-fix these, only flag them to a human.

List every finding with severity (critical/high/medium/low), file, line (if applicable), and a
concrete, specific description — completeness matters, a finding you skip listing is a finding the
next stage cannot fix. If the diff is empty, trivial, or genuinely clean, return an empty
\`findings\` array — do not invent findings just to appear thorough.

**Do NOT edit any files. Do NOT run \`git add\`, \`git reset\`, or \`git commit\`.** You are read-only in
this stage; a subsequent stage applies fixes and commits.`
}

function commitPrompt(pluginName, pluginRepoPath, skillName, skillEvalsDir, preIsolated, worktreePath, editResult, reviewResult, reviewFailed, evalSchemaPath) {
  const findings = Array.isArray(reviewResult && reviewResult.findings) ? reviewResult.findings : []
  const nonSecurityFindings = findings.filter((f) => !f.isSecurityRisk)
  const securityFindings = findings.filter((f) => f.isSecurityRisk)

  // Stage C is a FRESH agent with no memory of Stage A — its own evalScores/issuesFiled/
  // needsHumanReview only exist in the editResult object here in JS. Without surfacing them
  // explicitly, Stage C cannot write correct scores into STATUS.md/batch-digest.md (it was never
  // told what they are), and the final Digest phase would silently under-report Stage A's flags.
  // The loop ALSO merges these programmatically after Stage C returns (belt-and-suspenders — do not
  // rely solely on the agent correctly echoing them back), but Stage C still needs the real values
  // here to do its bookkeeping writes correctly in the first place.
  const stageAResultsBlock = `Stage A's own results, for your bookkeeping writes below (loop-log/STATUS.md/batch-digest —
these are NOT automatically visible to you otherwise, since you are a fresh agent):

${JSON.stringify({
  evalScores: editResult.evalScores,
  issuesFiled: editResult.issuesFiled,
  needsHumanReview: editResult.needsHumanReview,
  stoppedEarly: editResult.stoppedEarly,
  stopReason: editResult.stopReason,
}, null, 2)}`

  // reviewFailed: Stage B's agent() call itself threw (harness/transient error), as opposed to
  // Stage B running successfully and finding nothing. In that case there is no independent review
  // to apply — committing on an unreviewed diff would be WORSE than the old issue #12 manual
  // self-review design, so this stage falls back to doing that same manual review itself rather
  // than silently skipping review altogether.
  const findingsIntro = reviewFailed
    ? `**Stage B (the independent reviewer) failed to run for this skill** (its agent() call errored —
see batch notes). There is no independent review to apply here. Do NOT commit on an unreviewed diff
— instead, perform the SAME review yourself first, adversarially, using the identical criteria Stage
B would have used:

\`git diff HEAD\` (staged + unstaged tracked changes) and \`git status --porcelain\` (new untracked
files — read each one in full; you cannot review what you have not read). Review every changed chunk
for: **Logic/correctness**, **SKILL.md structural compliance**, **Eval design quality**, **Data
hygiene**, **Cross-file consistency**, and any **security/credential/data-loss risk** (list these
separately — do NOT self-fix them, they go to \`needsHumanReview\` same as step 1 below). Build your
own findings list from this pass, then treat it exactly like Stage B's findings for steps 1-3 below.
Also add a \`needsHumanReview\` note stating "Stage B (independent review) failed for this skill —
commit proceeded on manual self-review only", so a human knows this skill's review was degraded from
the normal pipeline.`
    : `Stage B (an independent reviewer with no context on why these changes were made) reviewed this
skill's staged diff and returned:

${JSON.stringify({ findings: nonSecurityFindings, summary: reviewResult && reviewResult.summary }, null, 2)}
${securityFindings.length
  ? `

It also flagged ${securityFindings.length} finding(s) as security/credential/data-loss risk — these
are listed below and must NOT be touched by you; add them to \`needsHumanReview\` verbatim instead:

${JSON.stringify(securityFindings, null, 2)}`
  : ''}`

  // Three-way branch, NOT two — hasChanges/stoppedEarly are independent booleans, and Stage B's own
  // gate (see the rollout loop) is `hasChanges && !stoppedEarly`. A naive `hasChanges` gate here
  // would diverge from Stage B's gate and let a `hasChanges: true, stoppedEarly: true` result
  // (Stage A partially edited/staged something, THEN hit a stop-and-flag condition) commit a diff
  // that was never independently reviewed — silently defeating the entire point of this pipeline.
  // Committing that partial diff anyway (rather than leaving it, which would be wiped by the NEXT
  // skill's fresh branch reset in preIsolated mode — same shared worktree) is still the right call,
  // but it must be committed AS-IS, unreviewed, with a loud human-facing flag — never silently
  // treated as if Stage B had cleared it.
  const applySection = editResult.hasChanges && !editResult.stoppedEarly
    ? `## Apply the review's findings, then commit

${stageAResultsBlock}

${findingsIntro}

1. **Fix every non-security finding above, at ANY severity (critical/high/medium/low), before
   committing.** Do not ask, do not defer to a follow-up — this checkpoint is pre-approved, not
   skipped. If you disagree with a finding, still address it (fix, or at minimum add a one-line
   \`needsHumanReview\` note explaining why you judged it a false positive) rather than silently
   dropping it — a dropped finding is indistinguishable from a missed one to anyone reading the
   result later.
2. **Re-read every file your fixes touched** (not just the hunks — the whole file) to confirm each
   fix addresses the root cause and has not introduced a cross-file inconsistency. If this targeted
   re-read surfaces NEW findings introduced by your own fixes, fix those too (same rule as step 1).
   One fix-and-re-read pass is the limit — any fix applied in response to this pass ships without a
   further confirmation pass; add a one-line \`needsHumanReview\` note naming which finding(s) got a
   second-round fix that was never itself re-reviewed. This "note and move on" allowance applies
   ONLY to items surfaced by THIS re-review pass, never to anything Stage B already found — nothing
   from Stage B's review gets quietly downgraded to "chose not to chase".
3. \`git add -A\` again (your fixes may have touched files or added new ones), then \`git commit\`,
   push, and open the PR. Use the PR-creation mechanism the plugin playbook's repo facts specify
   (gh api workaround if a PreToolUse hook blocks \`gh pr create\`, otherwise \`gh pr create\` directly
   — never guess which applies, it's documented per plugin). **Commit message and PR title format is
   fixed, not your call:** \`type(${skillName}): subject\` — type is \`fix\` for the default
   eval-driven case, \`feat\`/\`refactor\`/\`docs\` only if genuinely dominant, never \`skills(...)\` and
   never a bare plugin-name prefix. The PR title must be IDENTICAL to the commit subject line — see
   ${evalSchemaPath} §7 for the full convention and why it exists (past runs drifted across five
   different PR-title shapes in the same repo before this was written down).

**Hard, non-negotiable limit: never self-approve or self-merge a PR.** Leave every PR open for human
review, regardless of how autonomous everything upstream was.`
    : (editResult.hasChanges
      ? `## Staged, but Stage A stopped early — commit AS-IS, unreviewed, and flag it loudly

${stageAResultsBlock}

Stage A staged real changes (\`hasChanges: true\`) but then hit a stop-and-flag condition
(\`stopReason: ${editResult.stopReason || '(none given)'}\`) — Stage B was DELIBERATELY SKIPPED for
this skill (its gate is \`hasChanges && !stoppedEarly\`, same as this one), so this diff has NEVER
been independently reviewed. Do NOT treat it as reviewed-and-clean.

Committing anyway (rather than leaving it staged-but-uncommitted) is still correct here: in
preIsolated mode this worktree is shared across every skill in the batch, and the NEXT skill's
branch reset (\`git checkout -f -B skill-eval-{next} origin/main && git clean -fd\`) would silently
wipe this skill's uncommitted work otherwise — leaving nothing for a human to even find.

1. Do NOT run the review-findings-apply steps above — there are no findings, because no review ran.
2. \`git add -A\` (in case anything changed since Stage A staged), then \`git commit\`, push, and open
   the PR exactly as in the normal flow — same fixed \`type(${skillName}): subject\` commit/PR-title
   format as above, see ${evalSchemaPath} §7.
3. **Mandatory:** add a \`needsHumanReview\` entry stating, verbatim in substance, "this PR was
   committed WITHOUT independent review — Stage A stopped early after staging changes, see
   stopReason above — review this diff with extra scrutiny before merging." This must be prominent,
   not buried among Stage A's other flags.

**Hard, non-negotiable limit: never self-approve or self-merge a PR.** Leave every PR open for human
review, regardless of how autonomous everything upstream was.`
      : `## Nothing was staged — no commit needed

${stageAResultsBlock}

Stage A reported \`hasChanges: false\`. There is nothing to review or commit for this skill in this
run. Do not run any git mutation. Skip straight to the bookkeeping section below, carrying forward
Stage A's stoppedEarly/stopReason/needsHumanReview as-is into your own return value.`)

  const exitSection = preIsolated
    ? '' // preIsolated: the operator owns worktree lifecycle across the whole batch — nothing to exit here.
    : (editResult.hasChanges && worktreePath
        ? `\n\n## Before returning: release the worktree

You resumed this worktree via EnterWorktree above. Now that this skill's pipeline is finished:
- If you made a commit above: \`ExitWorktree({action: "keep"})\` — the branch must survive on disk for
  human PR review, or for whoever picks up a failed PR-creation attempt next.
- If you made zero commits (stopped before committing): \`ExitWorktree({action: "remove"})\` —
  nothing worth keeping.`
        : '')

  return `You are Stage C (apply review + commit + bookkeeping) of a 3-stage unattended pipeline for ONE
skill, the final stage. No human will review anything until the PR you open here — act accordingly,
but never skip the "never self-approve" limit below no matter how routine this skill's changes look.

Plugin: ${pluginName} (repo: ${pluginRepoPath})
Skill: ${skillName}

${editResult.hasChanges ? isolationSection(pluginRepoPath, skillName, skillEvalsDir, preIsolated, 'resume', worktreePath) : '(No worktree/isolation steps needed — Stage A staged nothing, see below.)'}

${applySection}
${exitSection}

## Bookkeeping — do this regardless of whether anything was committed above

Append the closing entry to ${skillEvalsDir}/${pluginName}/${skillName}/loop-log.md (per-iteration
entries were already written by Stage A during Prompt 2 — this is the closing entry, and should
reflect the actually-reviewed, actually-committed final state, including the PR URL if one was
opened), write the final loop-state.json, and update this skill's row in
${skillEvalsDir}/${pluginName}/STATUS.md. Sync any SKILL.md change to every deploy location the
plugin playbook's repo facts list.

Commit and push this closing bookkeeping (and anything else this stage wrote inside
${skillEvalsDir}) following:

${skillEvalsGitSafety(skillEvalsDir, pluginName)}

**Also append your result to the running batch digest**, so a human checking on a long batch
mid-run doesn't have to wait for the whole batch to finish or dig through individual loop-logs:
append (do not overwrite, do not remove anything already there — same append-only convention as
loop-log.md) a new section to ${skillEvalsDir}/${pluginName}/batch-digest.md with this skill's name,
simulated/live scores, PR URLs, issues filed, and any needsHumanReview entries — a few lines, not a
full report. Create the file with a one-line header if it doesn't exist yet.

Return the structured result: scores (carry forward Stage A's evalScores), PR URLs (open, not
merged — empty array if nothing was staged), issues filed (Stage A's issuesFiled, plus any you filed
yourself), needsHumanReview (Stage A's entries + Stage B's security findings + any of your own),
stoppedEarly/stopReason (carry forward from Stage A if nothing was staged), and a short prose
summary of the whole skill's pipeline run — not just this stage.`
}

phase('Select')
// Defensive: despite passing args as a real JSON object in the Workflow tool call (per its own
// documented convention), it has been observed arriving here as a JSON-encoded STRING instead of
// an object — a caller-side/harness serialization quirk, not something this script can prevent by
// calling it "more correctly". Parse defensively rather than assuming either shape.
let parsedArgs = args
if (typeof args === 'string') {
  try {
    parsedArgs = JSON.parse(args)
  } catch (e) {
    return {
      batchSummary: `Aborted: args arrived as a string and failed to JSON.parse (${e && e.message ? e.message : String(e)}). Raw value: ${args}`,
      totalPRs: [], totalIssues: [], totalNeedsHumanReview: [],
    }
  }
}

const plugin = parsedArgs.plugin
const pluginRepoPath = parsedArgs.pluginRepoPath
const count = parsedArgs.count ?? 5 // safety-net default only — the run skill's contract is to always pass an explicit count (large sentinel if only max_duration was given)
// Machine-specific path, resolved by the run skill (skills/run/SKILL.md Step 1) via the MCP tool
// resolve_config (which reads ~/.skill-rollout/config.yaml). The neutral default below only covers a
// broken invocation where the caller omitted it — the real path lives in the user's config.yaml.
const skillEvalsDir = parsedArgs.skillEvalsDir || '~/projekte/skill-evals'
const batchNotes = [] // cross-cutting notes (path/slug problems, onboarding issues) fed into the final digest
// referenceDir: the plugin's own versioned generic docs (eval schema + onboarding meta-prompt),
// passed by the run skill from resolve_config (= ${pluginRoot}/reference). These docs are GENERIC to
// the rollout tool, so they live in-plugin, not per-machine. The run skill always passes this — an
// absent value means a broken/outdated invocation, not a normal case, so it's flagged rather than
// silently substituted with a guessed path.
const referenceDir = parsedArgs.referenceDir || null
if (!referenceDir) {
  batchNotes.push([
    'referenceDir was not passed by the caller — expected from a current run skill invocation.',
    'This degrades EVERY skill in this batch, not just onboarding: evalSchemaPath falls back to',
    'skillEvalsDir/schema.md, a path that no longer exists (the plugin\'s eval schema now ships',
    'only at referenceDir/eval-schema.md), so every skill\'s "source of truth" grading-methodology',
    'reference will point at a dead file. The onboarding-playbook fallback path is equally dead.',
    'Fix the run skill invocation to pass referenceDir rather than proceeding on this fallback.',
  ].join(' '))
}
const evalSchemaPath = referenceDir ? `${referenceDir}/eval-schema.md` : `${skillEvalsDir}/schema.md`
const onboardPlaybookPath = referenceDir
  ? `${referenceDir}/prompt-self-improving-skill-playbook.md`
  : `${skillEvalsDir}/prompt-self-improving-skill-playbook.md`
// preIsolated: the caller has already placed pluginRepoPath inside a DEDICATED, single-use git
// worktree (created outside this script), so per-skill agents must NOT call EnterWorktree — they
// work directly in the provided checkout instead. Use this on harnesses where subagent-side
// EnterWorktree is unavailable (the cwd override is refused from a workflow-subagent context). The
// operator owns the worktree's lifecycle. Defaults to false (agents self-isolate via EnterWorktree).
const preIsolated = parsedArgs.preIsolated === true

if (!isValidPluginSlug(plugin)) {
  return {
    batchSummary: `Aborted before doing anything: "${plugin}" is not a valid plugin slug (expected lowercase letters/digits/hyphens only). Fix the argument and retry.`,
    totalPRs: [], totalIssues: [], totalNeedsHumanReview: [],
  }
}

const selection = await agent(
  `Determine the batch selection for plugin "${plugin}" (repo: ${pluginRepoPath}).

First, actually verify (via Bash/ls, do not assume) that "${pluginRepoPath}" exists and is a
directory. Set pluginRepoPathExists accordingly — this must be a real check, not a guess.

Then check whether ${skillEvalsDir}/${plugin}/STATUS.md exists. If it does not exist, this
plugin has never been onboarded — set onboardingNeeded=true and return an empty skills array
(onboarding happens in the next phase, before any skill selection makes sense).

If it exists: read it. **Before selecting anything, cross-check STATUS.md's row list against the
actual current skill directory listing** — per ${evalSchemaPath} §6, a plugin/repo can gain a brand-new
skill directory mid-rollout (e.g. as a side effect of another skill's own live-tier fix, like
storyforge's \`delete-author\` appearing because \`create-author\`'s live tier found a missing MCP
tool and the fix added a whole new skill alongside it). Two possible directory layouts — detect
which one this repo actually uses, don't assume:
- **Plugin layout** (Claude Code plugin with a \`.claude-plugin/plugin.json\`): skills live nested at
  \`${pluginRepoPath}/skills/{skill-name}/SKILL.md\`. List that directory.
- **Flat-collection layout** (a private skill collection with no plugin.json — mm-skills itself is
  the reference case): skills live directly at \`${pluginRepoPath}/{skill-name}/SKILL.md\`, one level
  up from the plugin case. List \`${pluginRepoPath}\`'s own top-level directories and keep only the
  ones that directly contain a SKILL.md (this naturally excludes non-skill directories like \`docs/\`
  or scratch/workspace folders that don't have one).
Whichever layout applies (check for \`.claude-plugin/plugin.json\` first — its presence or absence is
the single deciding signal), use that listing for the cross-check. Any directory with
no matching STATUS.md row needs one added (⬜/⬜) NOW, before selection — otherwise it stays invisible
to every future batch forever, since selection only ever looks at existing rows. Place the new row
at its correct pipeline-order position (check the plugin's own CLAUDE.md/routing table for where the
new skill sits — it's very likely adjacent to whichever skill's fix produced it, not at the end),
with a one-line note on when/why it appeared, and correct STATUS.md's total-skill-count footer line
to match. Do this even if it means this batch's actual work now includes a newly-added skill you
weren't expecting.

A skill counts as fully done only if Simulated is ✅ AND Live is either ✅ or a verified 🟦 N/A (per
${evalSchemaPath}'s convention — never treat plain ⬜ as done). Return the first ${count} skills, in the
table's current row order (this is the plugin's own dependency/pipeline order, not alphabetical —
do not re-sort it), that are not yet fully done. A skill with Simulated ✅ but Live ⬜ counts as
not-done and should be included (to finish its live tier), not skipped in favor of a fresh skill.

Once you know the selected skills: append (create if missing, never overwrite existing content —
same convention as loop-log.md) a "## Batch started" header to
${skillEvalsDir}/${plugin}/batch-digest.md with the real current date/time (via \`date\`),
the requested count (${count}), and the list of skills selected for this batch. This is the file
each skill's own rollout will append its result to as it finishes — the header marks where this
batch's entries begin, so a human tailing the file mid-run can tell batches apart. **Do NOT commit
this write yourself** — leave it uncommitted in the working tree; the first selected skill's own
Stage C bookkeeping commit (scoped to \`${skillEvalsDir}/${plugin}/\`) picks it up naturally as part
of its normal commit, without this stage needing its own git-safety cycle.`,
  { schema: SELECTION_SCHEMA, phase: 'Select' }
)

if (!selection.pluginRepoPathExists) {
  return {
    batchSummary: `Aborted: "${pluginRepoPath}" could not be confirmed to exist as a directory for plugin "${plugin}". Not proceeding on an unverified path — check the argument and retry.`,
    totalPRs: [], totalIssues: [], totalNeedsHumanReview: [],
  }
}

let skillsToProcess = Array.isArray(selection.skills) ? selection.skills : []
if (!Array.isArray(selection.skills)) {
  batchNotes.push('Select phase returned a non-array `skills` field — treated as empty, investigate the Select agent output.')
}

if (selection.onboardingNeeded) {
  phase('Onboard')
  log(`No skill-evals setup found for ${plugin} — starting onboarding (one-time, can take several minutes)...`)
  const onboardResult = await agent(
    `Run the onboarding meta-prompt for plugin "${plugin}" at repo path ${pluginRepoPath}, exactly as
documented in ${onboardPlaybookPath}
({PLUGIN_REPO_PATH} = ${pluginRepoPath}, {skillEvalsDir} = ${skillEvalsDir}, {referenceDir} =
${referenceDir || '(not provided — see the warning already logged for this run)'}). That document's
own placeholders are ABSOLUTE paths on THIS machine, resolved above — they are NOT relative to
${pluginRepoPath} (the target repo you are onboarding, which is a different repo than skill-rollout
itself). Follow its Phase 1 (Investigate) / Phase 2 (Draft) / Phase 3
(Self-check) exactly, including the "never guess" rule and the PreToolUse-hook check for
\`gh pr create\`. This creates ${skillEvalsDir}/${plugin}/self-improving-skill-${plugin}.md,
${skillEvalsDir}/${plugin}/STATUS.md (mirroring storyforge/STATUS.md's format and the
N/A/NEEDS-HUMAN-REVIEW conventions in ${evalSchemaPath}), and — only if step 3a found a verified-safe
sandbox strategy — ${skillEvalsDir}/${plugin}/mcp-surface-register.md (empty table skeletons, per the
playbook's step 3b). Commit these new files following:

${skillEvalsGitSafety(skillEvalsDir, plugin)}

If anything cannot be confirmed with certainty,
list it in needsHumanReview instead of guessing — never guess. But set ok=false ONLY when the
unconfirmed item actually gates a safe rollout (e.g. you could not determine the repo layout, the
MCP-server facts, or the PR-creation mechanism / whether a PreToolUse hook blocks \`gh pr create\`).
Do NOT set ok=false for an unconfirmed fact that does not gate the rollout and already has a
documented fallback. In particular: branch-protection / merge-policy that the GitHub API won't return
(e.g. \`gh api .../branches/main/protection\` returning HTTP 403 on a private repo with a non-admin
token) is NOT a blocker — the git-workflow feature-branch+PR rule applies regardless — so record it
in needsHumanReview and keep ok=true. Reserve ok=false for things that would make building on this
playbook actually unsafe, since it aborts the entire batch before any skill runs.

${preIsolated
  ? `If this onboarding phase will create any commits/PRs directly in ${pluginRepoPath}: that path is
already a DEDICATED, single-use git worktree the operator created for this batch, so do NOT call
\`EnterWorktree\` (it is unavailable from this workflow-subagent context on this harness). Work
directly in ${pluginRepoPath}; branch off the remote main (\`git fetch origin && git checkout -B
onboard-${plugin} origin/main\`, or the real default branch), commit/push/PR from there, and do NOT
touch the operator's main checkout or any other worktree. There is no ExitWorktree to call.`
  : `If this onboarding phase will create any commits/PRs directly in ${pluginRepoPath} (as opposed to
only in ${skillEvalsDir}): \`cd "${pluginRepoPath}"\` and call \`EnterWorktree\` FIRST,
before any investigation/reads/edits in that repo (not just before the commit — same reasoning as
the per-skill rollout prompt: entering late means what you already read/edited never makes it into
the worktree). Do all such work inside the worktree, then \`ExitWorktree({action: "keep"})\` if any
commits were made, \`({action: "remove"})\` otherwise — same concurrency-isolation requirement as the
per-skill rollout prompt, same reason (real past collisions in this shared working directory, not
hypothetical).`}

If this onboarding phase does commit/PR directly in ${pluginRepoPath}: this is the one target-repo
PR path that is NOT skill-scoped (onboarding touches STATUS.md/the playbook file, not a single
skill's own files), so ${evalSchemaPath} §7's \`type(skill-name): subject\` shape doesn't apply
verbatim — use \`chore(rollout-onboarding): subject\` instead (same Conventional Commits type rules,
different scope) so it's still consistently distinguishable from a per-skill PR at a glance.`,
    { schema: ONBOARD_SCHEMA, phase: 'Onboard' }
  )
  batchNotes.push(`Onboarding: ${onboardResult.summary}`)
  if (Array.isArray(onboardResult.needsHumanReview)) batchNotes.push(...onboardResult.needsHumanReview)

  if (!onboardResult.ok) {
    return {
      batchSummary: `Onboarding for "${plugin}" did not complete cleanly — stopping before any skill work rather than building on an unverified playbook. Details: ${batchNotes.join(' | ')}`,
      totalPRs: [], totalIssues: [], totalNeedsHumanReview: onboardResult.needsHumanReview ?? [],
    }
  }

  log(`Onboarding for ${plugin} complete — selecting skills for this batch...`)
  const reselect = await agent(
    `Onboarding for "${plugin}" (repo: ${pluginRepoPath}) just completed. Read the newly-created
${skillEvalsDir}/${plugin}/STATUS.md and return the first ${count} skills in table order
(all should be ⬜/⬜ at this point, since this is a fresh onboarding). Also re-verify
pluginRepoPathExists the same way as before.`,
    { schema: SELECTION_SCHEMA, phase: 'Select' }
  )
  skillsToProcess = Array.isArray(reselect.skills) ? reselect.skills : []
}

// Dedupe by name in case the Select agent returned a skill twice (code review L5).
const seenNames = new Set()
skillsToProcess = skillsToProcess.filter((s) => {
  if (seenNames.has(s.name)) return false
  seenNames.add(s.name)
  return true
})

if (skillsToProcess.length === 0) {
  log(`Nothing to do for ${plugin} — every skill already fully done, or none matched.`)
  return {
    batchSummary: `No skills selected for ${plugin} — rollout may already be complete.${batchNotes.length ? ' Notes: ' + batchNotes.join(' | ') : ''}`,
    totalPRs: [], totalIssues: [], totalNeedsHumanReview: [],
  }
}

phase('Rollout')
if (preIsolated) log(`preIsolated mode: agents work directly in the dedicated worktree ${pluginRepoPath} (no EnterWorktree; branch per skill off origin/main).`)
const results = []
let consecutiveFailures = 0
const FAILURE_CIRCUIT_BREAKER = 3 // stop the batch if this many skills in a row error out or self-report stoppedEarly — almost certainly a systemic problem, not a per-skill fluke

for (const skill of skillsToProcess) {
  const positionLabel = `${results.length + 1}/${skillsToProcess.length}`
  const doneNote = skill.simulatedDone && !skill.liveDone ? ' (live tier only — simulated already done)' : ''
  log(`${skill.name} (${positionLabel}): evaluation running${doneNote}...`)

  // Stage A — eval + edit, stage changes but do not commit. The three testdata-convention skills
  // (issue #35) get the fixed-sequence special case instead of the normal Prompt 1/2/3 prompt.
  const isTestdataSkill = TESTDATA_SKILL_NAMES.has(skill.name)
  const stageAPrompt = isTestdataSkill
    ? testdataSkillEvalAndEditPrompt(plugin, pluginRepoPath, skill.name, skillEvalsDir, preIsolated, evalSchemaPath, referenceDir)
    : evalAndEditPrompt(plugin, pluginRepoPath, skill.name, skillEvalsDir, preIsolated, evalSchemaPath, referenceDir)
  let editResult
  try {
    editResult = await agent(stageAPrompt, {
      label: `eval:${skill.name}`,
      phase: 'Rollout',
      schema: EDIT_RESULT_SCHEMA,
    })
  } catch (err) {
    editResult = {
      skill: skill.name,
      hasChanges: false,
      stoppedEarly: true,
      stopReason: 'agent_error',
      summary: `Stage A (eval+edit) agent call threw and was caught: ${err && err.message ? err.message : String(err)}`,
      needsHumanReview: [`${skill.name}: Stage A agent call failed, see batch log — this skill's own state files may be partially updated, check before assuming it's untouched.`],
    }
  }

  // Stage B — independent review, only if there is something staged to review.
  // editResult.worktreePath is Stage A's own `git rev-parse --show-toplevel` output (non-preIsolated
  // mode only), interpolated into Stage B/C's EnterWorktree({path}) instruction below. Deliberately
  // not further validated here: it comes from a trusted agent's own git output, not raw user input,
  // and isolationSection's own EnterWorktree-failure fallback (added for code review finding M1)
  // already covers the case where it points at something EnterWorktree rejects.
  let reviewResult = { findings: [], summary: 'Skipped — Stage A reported no changes or stopped early, nothing to review.' }
  let reviewFailed = false
  if (editResult.hasChanges && !editResult.stoppedEarly) {
    log(`${skill.name} (${positionLabel}): independent review running...`)
    try {
      reviewResult = await agent(reviewPrompt(plugin, pluginRepoPath, skill.name, skillEvalsDir, preIsolated, editResult.worktreePath), {
        label: `review:${skill.name}`,
        agentType: 'git-pr-workflows:code-reviewer',
        phase: 'Rollout',
        schema: REVIEW_RESULT_SCHEMA,
      })
    } catch (err) {
      reviewFailed = true
      reviewResult = {
        findings: [],
        summary: `Stage B (review) agent call threw and was caught: ${err && err.message ? err.message : String(err)}. Stage C will fall back to its own manual review for this skill — flagged below.`,
      }
      batchNotes.push(`${skill.name}: Stage B (independent review) failed — Stage C fell back to a manual self-review before committing. See loop-log for detail.`)
    }
  }

  // Stage C — apply review findings (if any), commit + push + PR, bookkeeping. Always runs, even
  // on a Stage A early-exit, so the loop-log/STATUS.md/batch-digest bookkeeping is never skipped.
  let result
  log(`${skill.name} (${positionLabel}): ${editResult.hasChanges && !editResult.stoppedEarly ? 'committing + opening PR' : 'bookkeeping'}...`)
  try {
    result = await agent(
      commitPrompt(plugin, pluginRepoPath, skill.name, skillEvalsDir, preIsolated, editResult.worktreePath, editResult, reviewResult, reviewFailed, evalSchemaPath),
      { label: `commit:${skill.name}`, phase: 'Rollout', schema: SKILL_RESULT_SCHEMA }
    )
  } catch (err) {
    result = {
      skill: skill.name,
      summary: `Stage C (commit) agent call threw and was caught: ${err && err.message ? err.message : String(err)}`,
      stoppedEarly: true,
      stopReason: 'agent_error',
      needsHumanReview: [`${skill.name}: Stage C agent call failed after Stage A staged changes — check ${pluginRepoPath} for an uncommitted/unreviewed diff before starting the next skill.`],
    }
  }

  // Belt-and-suspenders merge (code review finding H2): commitPrompt's stageAResultsBlock already
  // gives Stage C the data to echo back itself, but do NOT rely solely on a fresh agent correctly
  // carrying every field forward — merge programmatically so Stage A's needsHumanReview/issuesFiled
  // survive into the final Digest even if Stage C's own echo is incomplete. Concat rather than
  // overwrite: both stages may have independently legitimate entries.
  result.needsHumanReview = [
    ...(Array.isArray(editResult.needsHumanReview) ? editResult.needsHumanReview : []),
    ...(Array.isArray(result.needsHumanReview) ? result.needsHumanReview : []),
  ]
  result.issuesFiled = [
    ...(Array.isArray(editResult.issuesFiled) ? editResult.issuesFiled : []),
    ...(Array.isArray(result.issuesFiled) ? result.issuesFiled : []),
  ]
  if (!result.simulatedScore && editResult.evalScores) result.simulatedScore = editResult.evalScores.simulatedScore
  if (!result.liveScore && editResult.evalScores) result.liveScore = editResult.evalScores.liveScore

  results.push(result)
  log(`${skill.name} (${positionLabel}): done — ${result.summary}`)

  if (result.stoppedEarly) {
    consecutiveFailures += 1
    if (consecutiveFailures >= FAILURE_CIRCUIT_BREAKER) {
      log(`${FAILURE_CIRCUIT_BREAKER} skills in a row stopped early — halting the rest of this batch rather than burning through it on what looks like a systemic problem.`)
      batchNotes.push(`Circuit breaker tripped after ${consecutiveFailures} consecutive stoppedEarly results — remaining skills in this batch were not attempted.`)
      break
    }
  } else {
    consecutiveFailures = 0
  }
}

phase('Digest')
const digest = await agent(
  `Synthesize ONE batch-wide digest from these per-skill results (this is the ONLY summary a human
will read after this batch — be concrete, not generic):

${JSON.stringify(results, null, 2)}

Batch-level notes (onboarding, path validation, circuit breaker, Stage B failures): ${JSON.stringify(batchNotes)}

Include: which skills were processed and their scores, every PR URL (all still open, awaiting
review — say so explicitly), every GitHub issue filed, every needsHumanReview entry across all
skills (these matter most — surface them prominently, don't bury them), and any skill that stopped
early or hit a genuine blocker. If the batch was cut short (circuit breaker or fewer skills selected
than requested), say so explicitly rather than implying the full batch size was processed.`,
  { schema: DIGEST_SCHEMA, phase: 'Digest' }
)

return digest
