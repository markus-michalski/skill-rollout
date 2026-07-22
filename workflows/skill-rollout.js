export const meta = {
  name: 'skill-rollout-runner',
  description: 'Sequentially run the self-improvement rollout (Prompt 1/2/3) over N skills of a target Claude plugin, one batch, no auto-chaining',
  phases: [
    { title: 'Select', detail: 'read STATUS.md, pick the next skills not yet fully done, in table order' },
    { title: 'Onboard', detail: 'only if this plugin has never been onboarded before' },
    { title: 'Rollout', detail: 'process each selected skill fully, one at a time, never in parallel' },
    { title: 'Digest', detail: 'synthesize one batch-wide summary' },
  ],
}

// Design doc: reference/plugin-rollout-automation-concept.md (migrated into this plugin).
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
// another skill in this batch). Fixed by instructing each git-touching agent prompt
// (skillRolloutPrompt below, and the Onboard prompt if it commits to pluginRepoPath) to call the
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

function skillRolloutPrompt(pluginName, pluginRepoPath, skillName, docsBase, skillEvalsDir, preIsolated, evalSchemaPath) {
  const isolationSection = preIsolated
    ? `## Concurrency isolation — already provided; do NOT call EnterWorktree

You are running against a DEDICATED, single-use git worktree checkout at ${pluginRepoPath}, created
by the operator specifically for this batch and used by no other session. Isolation is therefore
already guaranteed by the path you were given. Do NOT call \`EnterWorktree\` — it is unavailable from
this workflow-subagent context on this harness anyway, and calling it and then blocking on failure
is exactly the failure this mode exists to avoid.

Do this BEFORE reading, editing, or committing anything:
1. \`cd "${pluginRepoPath}"\` — this IS your isolated worktree; everywhere below, ${pluginRepoPath}
   means this checkout.
2. **Safety assertion — do this before ANY git mutation.** Confirm ${pluginRepoPath} really is a
   linked worktree and not a primary checkout: a launcher mistake could otherwise point this at the
   operator's main checkout, and the branch reset below would then hijack it. Run
   \`git rev-parse --git-dir\` and \`git rev-parse --git-common-dir\` — in a linked worktree they
   DIFFER (equivalently, \`.git\` here is a file, not a directory). If they are the SAME, this is a
   primary checkout, NOT an isolated worktree: do NOT run any state-mutating git command, add a
   \`needsHumanReview\` entry saying "preIsolated set but ${pluginRepoPath} is a primary checkout, not
   a worktree — git-workflow skipped to avoid hijacking it", and skip this skill's git-workflow
   (still report its evals/grading normally).
3. Start this skill from a PRISTINE base branched off the remote default branch, so sequential skills
   sharing this one worktree never inherit each other's edits or leftovers (a prior skill may have
   stopped mid-edit — the operator's main checkout holds the default branch, and git forbids checking
   out the same branch in two worktrees, so branch off the REMOTE ref, do NOT \`git checkout main\`):
   \`git fetch origin && git checkout -f -B skill-eval-${skillName} origin/main && git clean -fd\`
   (resolve the real default branch with \`git symbolic-ref --short refs/remotes/origin/HEAD\` if it
   is not \`main\`; \`git clean -fd\` is safe here — the eval state lives OUTSIDE this worktree). Then
   commit, push, and open the PR from this \`skill-eval-${skillName}\` branch — do NOT spawn a
   separate branch-creating git-workflow on top of it; run the git-workflow steps (review → test →
   commit → push → PR) directly on it.
4. Do ALL reads, edits, evals, and git-workflow steps directly in this worktree. There is NO
   ExitWorktree to call — the operator owns this worktree's lifecycle.
5. Never touch any other worktree or the operator's main checkout; stay entirely inside
   ${pluginRepoPath}.`
    : `## Concurrency isolation — mandatory, do this FIRST, before anything else in this prompt

This exact working directory has been the site of real concurrent-session collisions during past
unattended batches (documented in ${skillEvalsDir}/storyforge/bootstrap-book-from-series/sandbox.md
and two STATUS.md rows there): another process moved the shared HEAD out from under a running
session, and a separate incident overwrote another session's own \`.git-workflow/\` state file. This
is not a hypothetical risk — it has happened, more than once.

Do this BEFORE reading any file, running any eval, or editing anything — not just before the
git-workflow/commit step. Entering the worktree late (e.g. only right before committing) means
whatever you already read/edited in the shared checkout never makes it into the worktree, and the
commit ends up empty or wrong — isolation would silently fail to isolate anything.

1. \`cd "${pluginRepoPath}"\` first. \`EnterWorktree\` isolates whatever repo your current working
   directory is inside — it does NOT take a repo path argument, so you must actually be in
   ${pluginRepoPath} (not your launch directory) before calling it, or you'll silently isolate the
   wrong repo while every real git mutation still lands in the shared, unisolated checkout.
2. Call the \`EnterWorktree\` tool (no \`name\`/\`path\` needed — a fresh worktree is created and you're
   switched into it automatically).
3. From this point on, ${pluginRepoPath} in every instruction below means the worktree you just
   entered, not the original shared path — do ALL reads, edits, evals, and git-workflow steps
   (review → test → commit → branch/push → PR) inside it. Nothing else about the process changes.
4. When finished: keep the worktree (\`ExitWorktree\` with \`action: "keep"\`) if you made ANY commits,
   regardless of whether PR creation itself succeeded — the branch must survive on disk either way
   (for human PR review, or for whoever picks up a failed PR-creation attempt next). Only use
   \`action: "remove"\` if you made zero commits (skill turned out already fully done) — nothing to
   keep in that case.
5. If \`EnterWorktree\` fails or is unavailable for any reason, do NOT fall back to working directly
   in the shared checkout — add a \`needsHumanReview\` entry naming this a concurrency-isolation gap
   for this skill's run, and stop before any git mutation (still report the rest of this skill's
   tiers — evals, grading — normally; only the git-workflow portion is blocked by this).`
  return `You are autonomously running the self-improvement rollout for ONE skill, as part of an
unattended batch. No human will review anything until the whole batch finishes — act accordingly,
but DO NOT guess at anything you can verify or that materially affects safety/correctness.

Plugin: ${pluginName} (repo: ${pluginRepoPath})
Skill: ${skillName}

(Note: the doc paths below may contain spaces — quote them in any shell command.)

${isolationSection}

## Source of truth — read these first, in order, don't re-derive what they already document

1. ${docsBase}/self-improving-skill-${pluginName}.md
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

- Every grading pass MUST use adversarial-realistic instructions (schema.md) — no exceptions, even
  under time pressure. A suspiciously perfect first-baseline score is not something to celebrate,
  it's something to double check the grading methodology on before trusting it.
- **Eval-design-candidate assertions** (same specific assertion fails 2 targeted-fix attempts):
  classify before doing anything else. If it's narration-dependent (asks the transcript to
  "explicitly note/cite X") or provably conflicts with the skill's own stated output terseness —
  fix the eval itself (remove/reframe), log why, commit. Otherwise (genuinely ambiguous, you can't
  self-certify which reading is right): do NOT touch the eval, do NOT keep chasing it. Mark it
  \`NEEDS-HUMAN-REVIEW\` in loop-log.md and in this skill's STATUS.md Notes cell. This does not stop
  your work on this skill — move on.
- **Residual notes** (something you notice that no assertion covers): if it's in scope for the
  section/step you're already touching, fold it into your current fix. If it's out of scope
  (different skill, different subsystem, a bigger design question) — file a real GitHub issue in
  ${pluginRepoPath}'s repo IMMEDIATELY (\`gh issue create\`), never just mention it in prose. This
  applies in the simulated tier too, not only the live tier — a real example: a book-conceptualizer
  run found two stale skill-name references this way and they'd have been lost if not filed.

**Prompt 3 (live-MCP tier) — only if ALL of: the plugin has a real MCP server (per the playbook's
repo facts) AND this skill's SKILL.md actually calls domain MCP tools (grep it — don't assume from a
skill's name or a stale STATUS.md note; \`configure\` in storyforge was wrongly assumed MCP-free once
and it wasn't) AND the Live column isn't already ✅ or verified N/A AND the plugin playbook's own
Prompt 3 section is a real, ready-to-run prompt, not a blocked placeholder.**

**Hard gate, check this BEFORE anything else in this section:** if the plugin playbook states that
this plugin's live-tier sandbox strategy has not been designed yet, do NOT attempt Prompt 3
yourself, do NOT invent a sandbox strategy on the spot no matter how sensible it seems, and do NOT
skip it silently either. This gate is about whether a verified-safe isolation strategy already
exists for the plugin's shared storage — NOT about whether the plugin's subject matter sounds
fictional or low-stakes. storyforge's own shared \`~/.storyforge/authors/\` holds a real,
non-sandbox author (\`ethan-cole\`) right next to \`zz-sandbox-author\` — a "fictional domain" is not
automatically safe, and a corrupted real chapter is just as real a loss as a corrupted real legal
case. storyforge only qualifies because concrete design work already happened here (the
\`zz-sandbox-\` naming convention, path-scoped resets, the isolated-files-vs-shared-DB distinction —
see its own \`sandbox.md\` files), not because of its subject matter. Add an entry to
\`needsHumanReview\` naming this skill and stating that its live tier is blocked pending a human
sandbox-design conversation, leave the Live column as ⬜ (not N/A — N/A means "verified not
applicable", this is "applicable but blocked", a different state), and move on. This is exactly as
hard a stop as the "would touch real non-sandbox data" condition later in this prompt — because
it's the same risk, just caught earlier, before any sandbox even exists to accidentally misuse.

If the gate above does NOT apply (a verified-safe sandbox strategy already exists for this plugin —
storyforge being the only confirmed case today, purely because that design work happened here
first): follow the plugin playbook's Prompt 3 exactly, including: reuse
the shared sandbox, never touch another skill's fixtures, scope every reset to the exact sub-path
this skill's own cases touch, run live cases strictly in sequence (never parallel — they mutate
shared state), require a real tool_use block as evidence for every claimed action, verify claimed
side effects with an independent post-run check.

If this skill's SKILL.md genuinely has no MCP domain-tool calls at all (a different case from the
gate above — this is "no live tier needed", not "blocked"): do NOT leave the Live column ⬜. Grep it
yourself to confirm, then mark it 🟦 N/A in STATUS.md with a one-line note of what you checked (per
schema.md's convention) — this is required, not optional, so a future batch selection doesn't wait
forever on a skill that will never have a live tier.

## git-workflow — autonomous mode

Every git-workflow checkpoint (code-review + breaking-change, test, commit-message, branch/push, PR
creation) is pre-approved — do not stop to ask. Any code-review finding, at ANY severity
(critical/high/medium/low), gets fixed without asking, same as every checkpoint. Use the PR-creation
mechanism the plugin playbook's repo facts specify (gh api workaround if a PreToolUse hook blocks
\`gh pr create\`, otherwise gh pr create directly — never guess which applies, it's documented per
plugin).

**Hard, non-negotiable limit unaffected by any of the above: never self-approve or self-merge a PR.**
Leave every PR open for human review, regardless of how autonomous everything upstream of it was.

## Stop-and-flag conditions (the only things that should make you NOT just proceed)

Add an entry to \`needsHumanReview\` (do not guess, do not silently proceed) if you hit:
- Ambiguity about whether a live-tier case, handled wrong, would touch real (non-sandbox) data.
- A finding that looks like a security/credential/data-loss risk.
- Any destructive git operation outside the sanctioned pattern (force-push, history rewrite).
- A finding that clearly belongs to a different, unrelated repo this rollout isn't authorized to
  touch (file the issue in the right repo if you can identify it; do not push there).

Everything else (including NEEDS-HUMAN-REVIEW eval-design flags) does not block you — keep going.

## Before you finish

Update ${skillEvalsDir}/${pluginName}/${skillName}/loop-log.md, loop-state.json, and this
skill's row in ${skillEvalsDir}/${pluginName}/STATUS.md. Sync any SKILL.md change to every
deploy location the plugin playbook's repo facts list.

**Also append your result to the running batch digest**, so a human checking on a long batch
mid-run doesn't have to wait for the whole batch to finish or dig through individual loop-logs:
append (do not overwrite, do not remove anything already there — same append-only convention as
loop-log.md) a new section to ${skillEvalsDir}/${pluginName}/batch-digest.md with this
skill's name, simulated/live scores, PR URLs, issues filed, and any needsHumanReview entries — a
few lines, not a full report. Create the file with a one-line header if it doesn't exist yet.

Return the structured result: scores, PR URLs (open, not merged), issues filed, any
needsHumanReview entries, and a short prose summary.`
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
// Machine-specific paths, resolved by the run skill (skills/run/SKILL.md Step 1) via the MCP tool
// resolve_config (which reads ~/.skill-rollout/config.yaml). The neutral defaults below only cover a
// broken invocation where the caller omitted them — the real path lives in the user's config.yaml.
const docsBase = parsedArgs.docsBase || '~/Documents/self_improving_skill'
const skillEvalsDir = parsedArgs.skillEvalsDir || '~/projekte/skill-evals'
// referenceDir: the plugin's own versioned generic docs (eval schema + onboarding meta-prompt),
// passed by the run skill from resolve_config (= ${pluginRoot}/reference). These docs are GENERIC to
// the rollout tool, so they live in-plugin, not in the per-machine docsBase / per-plugin skillEvalsDir.
// When referenceDir is absent (older/broken invocation), the two derived paths gracefully fall back to
// their pre-migration locations so nothing breaks either way.
const referenceDir = parsedArgs.referenceDir || null
const evalSchemaPath = referenceDir ? `${referenceDir}/eval-schema.md` : `${skillEvalsDir}/schema.md`
const onboardPlaybookPath = referenceDir
  ? `${referenceDir}/prompt-self-improving-skill-playbook.md`
  : `${docsBase}/prompt-self-improving-skill-playbook.md`
// preIsolated: the caller has already placed pluginRepoPath inside a DEDICATED, single-use git
// worktree (created outside this script), so per-skill agents must NOT call EnterWorktree — they
// work directly in the provided checkout instead. Use this on harnesses where subagent-side
// EnterWorktree is unavailable (the cwd override is refused from a workflow-subagent context). The
// operator owns the worktree's lifecycle. Defaults to false (agents self-isolate via EnterWorktree).
const preIsolated = parsedArgs.preIsolated === true
const batchNotes = [] // cross-cutting notes (path/slug problems, onboarding issues) fed into the final digest

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
actual current skill directory listing** — per schema.md §6, a plugin/repo can gain a brand-new
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
schema.md's convention — never treat plain ⬜ as done). Return the first ${count} skills, in the
table's current row order (this is the plugin's own dependency/pipeline order, not alphabetical —
do not re-sort it), that are not yet fully done. A skill with Simulated ✅ but Live ⬜ counts as
not-done and should be included (to finish its live tier), not skipped in favor of a fresh skill.

Once you know the selected skills: append (create if missing, never overwrite existing content —
same convention as loop-log.md) a "## Batch started" header to
${skillEvalsDir}/${plugin}/batch-digest.md with the real current date/time (via \`date\`),
the requested count (${count}), and the list of skills selected for this batch. This is the file
each skill's own rollout will append its result to as it finishes — the header marks where this
batch's entries begin, so a human tailing the file mid-run can tell batches apart.`,
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
  log(`No skill-evals setup found for ${plugin} — running onboarding first.`)
  const onboardResult = await agent(
    `Run the onboarding meta-prompt for plugin "${plugin}" at repo path ${pluginRepoPath}, exactly as
documented in ${onboardPlaybookPath}
({PLUGIN_REPO_PATH} = ${pluginRepoPath}). Follow its Phase 1 (Investigate) / Phase 2 (Draft) / Phase 3
(Self-check) exactly, including the "never guess" rule and the PreToolUse-hook check for
\`gh pr create\`. This creates ${docsBase}/self-improving-skill-${plugin}.md
and ${skillEvalsDir}/${plugin}/STATUS.md (mirroring storyforge/STATUS.md's format and the
N/A/NEEDS-HUMAN-REVIEW conventions in schema.md). If anything cannot be confirmed with certainty,
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
only in ${docsBase} or ${skillEvalsDir}): \`cd "${pluginRepoPath}"\` and call \`EnterWorktree\` FIRST,
before any investigation/reads/edits in that repo (not just before the commit — same reasoning as
the per-skill rollout prompt: entering late means what you already read/edited never makes it into
the worktree). Do all such work inside the worktree, then \`ExitWorktree({action: "keep"})\` if any
commits were made, \`({action: "remove"})\` otherwise — same concurrency-isolation requirement as the
per-skill rollout prompt, same reason (real past collisions in this shared working directory, not
hypothetical).`}`,
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
  log(`Starting ${skill.name} (${positionLabel})${doneNote}...`)

  let result
  try {
    result = await agent(skillRolloutPrompt(plugin, pluginRepoPath, skill.name, docsBase, skillEvalsDir, preIsolated, evalSchemaPath), {
      label: `rollout:${skill.name}`,
      phase: 'Rollout',
      schema: SKILL_RESULT_SCHEMA,
    })
  } catch (err) {
    result = {
      skill: skill.name,
      summary: `Agent call threw and was caught: ${err && err.message ? err.message : String(err)}`,
      stoppedEarly: true,
      stopReason: 'agent_error',
      needsHumanReview: [`${skill.name}: agent call failed, see batch log — this skill's own state files may be partially updated, check before assuming it's untouched.`],
    }
  }
  results.push(result)
  log(`${skill.name}: ${result.summary}`)

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

Batch-level notes (onboarding, path validation, circuit breaker): ${JSON.stringify(batchNotes)}

Include: which skills were processed and their scores, every PR URL (all still open, awaiting
review — say so explicitly), every GitHub issue filed, every needsHumanReview entry across all
skills (these matter most — surface them prominently, don't bury them), and any skill that stopped
early or hit a genuine blocker. If the batch was cut short (circuit breaker or fewer skills selected
than requested), say so explicitly rather than implying the full batch size was processed.`,
  { schema: DIGEST_SCHEMA, phase: 'Digest' }
)

return digest
