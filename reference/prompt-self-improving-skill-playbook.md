# Onboarding Meta-Prompt

You are onboarding a Claude plugin repo into the skill self-improvement rollout process (see
{referenceDir}/eval-schema.md and the general playbook {referenceDir}/self-improving-skills.md,
both shipped inside the skill-rollout plugin, for the underlying method). Target plugin repo:
{PLUGIN_REPO_PATH}.

`{skillEvalsDir}` and `{referenceDir}` below mean the same machine-resolved, absolute paths the
`run` skill already substituted when invoking this onboarding step (via `tool_resolve_config` — see
`skills/run/SKILL.md`) — not literal folder names to create verbatim, and NOT relative to your
current working directory. Your working directory for this onboarding task is {PLUGIN_REPO_PATH}
(the TARGET plugin you're onboarding), which is a different repo than skill-rollout itself — do not
resolve `reference/...` relative to it; always use the absolute `{referenceDir}` path given here.

## Hard rule: never guess

For every fact you need below — MCP server name, tool prefix, deploy paths, branch protection
rules, test command, whether skill-evals setup already exists — you must confirm it directly
(read the actual file, run the actual check, call the actual tool). If something cannot be
confirmed with certainty (e.g. an MCP server clearly exists but its tool prefix can't be verified
because the server isn't currently connected), STOP and ask me rather than writing your best guess
into the generated file. A wrong assumption baked into a permanent playbook is worse than a pause
to ask.

## Phase 1 — Investigate (do this for real — verify everything about this specific repo fresh,

don't infer from any other plugin you may have worked on before)

0. **Repo-type detection — do this FIRST, it determines every path convention below.** Check
   whether {PLUGIN_REPO_PATH}/.claude-plugin/plugin.json exists.
   - **Exists → "Claude Code plugin" repo type.** Skills live nested at
     {PLUGIN_REPO_PATH}/skills/{{skill-name}}/SKILL.md. Continue to step 1.
   - **Does not exist → check for the other known shape:** does {PLUGIN_REPO_PATH} have top-level
     directories that each directly contain a SKILL.md (e.g. {PLUGIN_REPO_PATH}/{{skill-name}}/SKILL.md,
     no `skills/` subfolder)? If so, this is a **"flat skill-collection" repo type** — a private
     collection of independent skill definitions, not a packaged Claude Code plugin (mm-skills is
     the reference case: 16 top-level dirs each with their own SKILL.md, no plugin.json, no MCP
     server, installed by copying/symlinking individual skill dirs into `~/.claude/skills/` per the
     repo's own CLAUDE.md — read that file for the actual install method, don't assume it matches
     mm-skills' exact wording for a different flat-collection repo). Skills live at
     {PLUGIN_REPO_PATH}/{{skill-name}}/SKILL.md directly.
   - **Neither shape found:** stop and ask — don't guess a third layout into existence.
   - Record which type was found; every {PLUGIN_REPO_PATH}/skills/... reference in the rest of this
     document means {PLUGIN_REPO_PATH}/... directly (no `skills/` segment) for a flat-collection repo.
1. **Plugin-type repos only:** read {PLUGIN_REPO_PATH}/.claude-plugin/plugin.json — get the plugin
   name, version, and whether "mcpServers" is declared. **Flat-collection repos:** skip this step —
   there is no plugin.json, hence no MCP server declaration possible; go straight to step 3's
   "no MCP server" conclusion for the whole repo (a flat skill collection has no shared MCP server
   the way a plugin might — each skill in it is independent).
2. If plugin.json declares "mcpServers": read the referenced .mcp.json to get the actual MCP server
   name. Verify the real tool-name prefix via ToolSearch or an actually connected tool call — never
   infer it by pattern-matching a naming convention you've seen on a different plugin.
3. If plugin.json does NOT declare "mcpServers", no .mcp.json exists, or this is a flat-collection
   repo (no plugin.json at all): this plugin/repo has no MCP server. Note this explicitly — Prompt 3
   (live-MCP tier) does not apply and must be omitted from the generated file, for every skill in it.
3a. **Only if an MCP server DOES exist (step 2): check whether this plugin implements the
   `create-testdata`/`reset-testdata`/`delete-testdata` skill convention — this, not a "human
   sandbox-design conversation" and not whether the plugin's subject matter is "fictional," is what
   determines whether Prompt 3 can be auto-generated.**

   Earlier drafts of this rule gated Prompt 3 behind an undefined "human sandbox-design conversation"
   step. That gate was never actually honored in practice: confirmed for storyforge, the one plugin
   that went through this before — a grep across every `loop-log.md` in its skill-evals history and
   the generated playbook itself turns up zero documented human-Claude design discussion. What
   actually happened is that autonomous rollout sessions unilaterally designed the `zz-sandbox-`
   naming convention, the git-tag-baseline reset mechanic, and the MCP-tool-scoped reset for shared
   storage, then recorded it as settled practice without ever having the conversation the gate
   required. A vague, unenforceable gate gives an autonomous session under time/token pressure every
   incentive to just design it itself and move on — exactly what happened.

   Replaced with a concrete, checkable artifact (skill-rollout issue #35): every plugin that wants
   live-tier testing implements three fixed-name skills — `create-testdata`, `reset-testdata`,
   `delete-testdata` — per {referenceDir}/self-improving-skills.md's "create-testdata /
   reset-testdata / delete-testdata convention" section, which onboarding discovers and verifies
   instead of improvising sandbox design itself. Fixed names across every plugin, never
   per-plugin-invented ones.

   Check, in order — do not skip either half, existence alone is not enough:

   1. **Discovery.** Do all three of {PLUGIN_REPO_PATH}/skills/create-testdata/SKILL.md,
      .../reset-testdata/SKILL.md, .../delete-testdata/SKILL.md exist? All three, not a subset — a
      plugin with only `create-testdata` has not earned the safe classification. Missing any one →
      outcome is "not yet designed" (below), skip straight there.
   2. **Static check.** Read each of the three SKILL.md files' actual instruction text (not their
      prose claims about themselves). Confirm each documents an explicit, unconditional FIRST step
      that refuses and stops when the target slug does not carry the plugin's disposable-test-data
      prefix (`zz-sandbox-`) — a concrete, numbered instruction the skill actually follows, not an
      aspirational mention of safety somewhere in the file. Missing this in any of the three → "not
      yet designed", same as a missing skill.
   3. **Live verification — corrected methodology, do not use the original flawed version of this
      check.** Call `delete-testdata` (the highest-blast-radius of the three) once, with a synthetic
      test slug that satisfies BOTH: (a) does NOT carry the `zz-sandbox-` prefix, so a working guard
      refuses it outright, and (b) is constructed so it cannot coincide with any real entity even if
      the guard were completely broken (a random/timestamp suffix appended — not just "any old
      non-matching string"). Two outcomes are both zero-risk and acceptable:
      - The call refuses immediately, before any lookup, citing the prefix mismatch — guard
        confirmed working.
      - The call proceeds past a missing/broken guard but then fails with "not found" — the guard
        didn't fire, but nothing was destroyed, because the synthetic slug never existed as a real
        entity in the first place.
      Any OTHER outcome (an actual deletion succeeds, or an error suggests real data was touched)
      means the guard is not verified-safe — do NOT proceed to Prompt 3; treat this the same as "not
      yet designed" and add a `needsHumanReview` entry naming the concrete failure.

      **Why this exact construction, not the original proposal:** an earlier version of this check
      called `delete-testdata` with only "a deliberately non-matching slug," with no
      provably-nonexistent requirement — if the guard was broken AND that slug happened to resolve to
      something real, the verification attempt itself would have been the data loss, the test and the
      damage the same event. The synthetic-slug construction above closes that gap: both possible
      outcomes of a broken guard stay harmless, only a genuinely working guard or a genuinely inert
      delete-of-nothing can result. Combine this live check with the static check above — neither
      replaces the other; a skill can document a guard it doesn't actually enforce, or enforce one it
      never wrote down for a future maintainer.

   Two outcomes:
   - **All three checks pass (discovery + static + live)** — proceed to generate Prompt 3.
   - **Any check fails** — Prompt 3 is blocked, exactly as before, but now with a concrete, buildable
     unblock path instead of an undefined "have a conversation" step: implement (or fix) the three
     skills for this plugin per {referenceDir}/self-improving-skills.md's convention section — file a
     per-plugin GitHub issue for this if one does not already exist, do not attempt to design or fix
     the sandbox strategy yourself as part of this onboarding.
   **Default to "not yet designed" — do not guess a plugin into the safe bucket because its domain
   sounds fictional or low-stakes**, and do not accept the three skills' mere existence (discovery
   alone) as sufficient without both the static and the live check also passing.
3b. **Only if 3a's outcome was "all three checks pass" (discovery + static + live):** check whether
   {skillEvalsDir}/{plugin-name}/mcp-surface-register.md already exists. This is a separate,
   continuously-maintained file — not part of this generated playbook — that every skill's later
   Stage A rollout reads before running Prompt 3 and writes new findings into, so skill #2 never
   re-derives what skill #1 already learned about this plugin's MCP surface (per-entity vs.
   global-singleton tools, which sandbox fixture states already exist). If it doesn't exist yet,
   Phase 2 below must create it with an empty table skeleton — do not defer this to the first
   skill rollout, since the whole point is that it exists before any skill needs it.
3c. **Only if 3a's outcome was "all three checks pass":** provision the sandbox for real now, don't
   leave it empty for whichever skill happens to be selected first to improvise (skill-rollout
   issue #37). Step 3a's live verification only ever tests the refuse path — a synthetic,
   provably-nonexistent slug against `delete-testdata` — it never actually creates anything. This
   step is the real provisioning run:
   1. Call `create-testdata` for real (no synthetic slug involved this time — a genuine,
      unconditional invocation), exactly as this plugin's own `create-testdata/SKILL.md` documents.
      If it reports the sandbox already exists (e.g. re-onboarding after a partial prior attempt),
      that is a valid outcome too — do not treat "already provisioned" as a failure.
   2. Confirm via an independent read (a real get/list tool call, never trusting `create-testdata`'s
      own return value as the only evidence) that the fixtures it claims to have created actually
      exist.
   3. Record what was created — the exact fixed identifiers `create-testdata`'s own SKILL.md
      documents (per this plugin's implementation) — in the `mcp-surface-register.md` file from step
      3b's Fixture Inventory table, so every future skill's live tier finds the sandbox pre-seeded
      and consistent instead of rediscovering or re-provisioning it.
   If `create-testdata` itself fails for a reason unrelated to "already exists" (a real tool error,
   an unexpected response shape): do not proceed to Prompt 3 as if the sandbox were ready — add a
   `needsHumanReview` entry naming the concrete failure, same treatment as a failed step 3a check.
4. **Plugin-type repos:** confirm "skills" in plugin.json ships a directory verbatim to installers
   (true for essentially all Claude plugins). **Flat-collection repos:** confirm each skill directory
   is installed by copy or symlink per the repo's own CLAUDE.md/README (mm-skills documents this in
   its own CLAUDE.md "Installation" section) — read it, don't assume.
5. Check whether this repo is public or private: CLA.md, LICENSE.md, a public GitHub remote
   (`git remote -v`). This matters for branch-protection/CLA relevance (step 7) — it does **not**
   affect where evals.json lives. **evals.json always lives externally**, at
   ~/projekte/skill-evals/{plugin-name}/{skill-name}/evals.json, regardless of whether this repo is
   public or private, plugin-type or flat-collection-type. (Earlier revisions of this playbook kept
   private-repo evals inside the repo itself — that branch was removed; if you find existing
   in-repo evals.json files from before this change, they've already been migrated externally as a
   one-time cleanup, don't recreate the in-repo copy.)
6. Check whether {skillEvalsDir}/{plugin-name}/ already exists. The question is only whether THIS
   plugin's own subfolder exists yet — {skillEvalsDir} itself is expected to already exist as a
   shared resource across every plugin/repo in this rollout, do NOT recreate it. If the plugin's own
   subfolder doesn't exist, this is the first skill from this plugin being onboarded — flag this so
   Phase 2 also creates a {skillEvalsDir}/{plugin-name}/STATUS.md tracker (see Phase 2).
7. If public with a GitHub remote: check branch protection on the default branch
   (`gh api repos/{owner}/{repo}/branches/{default}/protection`) — required reviews, required
   status checks, allowed merge methods (merge commit / squash / rebase).
7a. Check whether a PreToolUse hook blocks `gh pr create`. Verified directly (not assumed) across
   two different repos in the same session: this is actually a **global, user-level hook**
   (`~/.claude/settings.json` → `hooks.PreToolUse` with `matcher: "Bash"` →
   `bash $HOME/.claude/hooks/enforce-git-workflow-skill.sh`), not a per-repo setting — it fires for
   every Bash call containing the literal text "gh pr create" (naive string match, not AST-aware —
   it can even false-positive on a `grep` command that merely searches for that string, not just an
   actual invocation), in every repo, always. Earlier drafts of this playbook wrongly described it as
   repo-specific ("storyforge has one, not universal") — that was never verified and turned out to
   be wrong. Still worth checking per-repo for a *narrower, repo-local* hook/config that could apply
   in ADDITION to the global one, but don't frame the global block itself as something that needs
   per-repo detection — it is already known and applies everywhere. The sanctioned workaround is the
   `gh api repos/{owner}/{repo}/pulls -f title=... -f body=... -f base=... -f head=...` call, used as
   the final step inside the `git-pr-workflows:git-workflow` skill (never before it, never as a
   standalone bypass). **The commit message, PR title, and issue title format themselves are fixed
   plugin-wide** (see {referenceDir}/eval-schema.md §7) — never invent or adapt a per-repo title
   convention here, regardless of what style this specific target repo's own history happens to use.
8. Check for CI (.github/workflows/) and a real test suite (tests/ directory) — find the actual
   invocation command from README/CONTRIBUTING/pyproject.toml/package.json.
9. If an MCP server exists: check whether Claude Code loads it from a deployed copy distinct from
   the source repo (~/.claude/plugins/marketplaces/{plugin-name} and
   ~/.claude/plugins/cache/{plugin-name}/{plugin-name}/<version>) — confirm whether code/skill
   changes need syncing there before they take effect, and whether an MCP-server code change needs
   a full Claude Code restart to reload (vs. a plain SKILL.md change, which doesn't).

Do not write anything yet. Report what you found before drafting, so I can catch any wrong
assumption before it goes into a permanent playbook document.

## Phase 2 — Draft {skillEvalsDir}/{plugin-name}/self-improving-skill-{plugin-name}.md

Use {referenceDir}/self-improving-skills.md (shipped inside the skill-rollout plugin — an ABSOLUTE
path, resolve it exactly as given, do NOT interpret `reference/` as relative to {PLUGIN_REPO_PATH})
as the structural template —
its "Beispielprompt für evals.json" and "Beispielprompt für Skill Self-Improvement" sections are the
generic Prompt 1/2 shape to adapt below, in the same section headings, formatting, level of detail,
and German-explanatory/English-prompt-block style. Every fact you write into the new file must come
from Phase 1's findings about {PLUGIN_REPO_PATH} specifically — never invent a fact that isn't in
Phase 1's findings, and never carry over a repo-specific detail (an MCP server name, a path, a
branch-protection fact) from any OTHER plugin's already-onboarded playbook you may have seen —
each playbook's facts are specific to its own repo.

- Opening paragraph + "Repo-Fakten" bullet list: plugin repo path, MCP server name + tool prefix
  (if any), deploy-location sync requirements (if any), branch protection / CI / merge-policy facts.
- **First-time setup note (only if Phase 1 step 6 found no existing subfolder):** state explicitly
  that {skillEvalsDir}/{plugin-name}/ doesn't exist yet, and that Prompt 1 (below) must
  create it on its first run. Also create {skillEvalsDir}/{plugin-name}/STATUS.md now: one row per
  skill, in folder order, with Simulated/Live checkbox columns and a Notes column, header text
  adapted to this plugin's name — see the status-legend table in {referenceDir}/eval-schema.md for the
  exact symbols (⬜/✅/🟦 N/A/🟨 NEEDS-HUMAN-REVIEW) and their meaning. Use whichever layout step 0
  found — nested {PLUGIN_REPO_PATH}/skills/{{skill-name}}/SKILL.md for a plugin-type repo, or flat
  {PLUGIN_REPO_PATH}/{{skill-name}}/SKILL.md for a flat-collection repo — either way, the row list
  comes from that repo's real current directory contents, not assumed. For a flat-collection repo,
  every skill's Live column starts as 🟦 N/A (no MCP server exists for the whole repo, per step 3) —
  set that immediately rather than leaving it ⬜ for a live tier that will never apply.
- **MCP Surface Register (only if step 3b found it missing):** create
  {skillEvalsDir}/{plugin-name}/mcp-surface-register.md now, with the two table skeletons (MCP Tool
  Scope; Fixture Inventory) per {referenceDir}/self-improving-skills.md's "MCP Surface Register"
  section. The MCP Tool Scope table starts genuinely empty — do not pre-populate rows from a guess,
  leave it for the first skill rollout to fill in from real findings. The Fixture Inventory table is
  different: if step 3c ran a real `create-testdata` provisioning pass, record what it actually
  created there now (the fixed identifiers, per this plugin's own `create-testdata/SKILL.md`) —
  this table should NOT start empty when 3c succeeded, since the whole point of 3c is that the next
  skill's rollout finds the sandbox already documented, not empty.
- **Prompt 1** (evals.json bauen, simulierter Tier): same shape as {referenceDir}/self-improving-skills.md's
  example, referencing the skill-rollout plugin's reference/eval-schema.md (this is the correct target
  location to write into the NEW playbook's text — never the {skillEvalsDir}/schema.md path, which
  does not exist), saving to
  {skillEvalsDir}/{plugin-name}/{skill-name}/evals.json (always this external location, per Phase 1
  step 5).
- **Prompt 2** (Loop laufen lassen, simulierter Tier): same shape as the example, adapted
  paths/repo name, including the sync-to-deploy-locations step ONLY if Phase 1 found real deploy
  locations distinct from the source repo.

  **Hard requirement on Prompts 1 AND 2 — do not lose this to paraphrasing (issue #20):** both
  prompts commit into `{skillEvalsDir}` (evals.json in Prompt 1; loop-log.md/loop-state.json in
  Prompt 2). `{skillEvalsDir}` is a single repo SHARED across every plugin this rollout has ever
  onboarded — a concurrently-running session for a DIFFERENT plugin may be committing to its own
  subtree of this exact same repo, in this exact same shared working tree/index/HEAD, at the exact
  same time, and it has no worktree isolation the way the target plugin's own repo does. "Same
  shape as the example" is not enough for this specific part — copy the FULL "Git-Sicherheit für
  JEDEN Commit in skill-evals" section from `{referenceDir}/self-improving-skills.md` verbatim in
  substance into the generated prompt text, not just its headline. In short (the source section has
  the full reasoning, do not compress it away): (1) scope BOTH the `git add` AND the `git commit`
  itself to `{skillEvalsDir}/{plugin-name}/` — a scoped add alone does not stop a plain `git commit`
  from also picking up another session's files already staged in the same shared index; (2) retry
  on index-lock errors (a concurrent session mid-operation, not a real error); (3) on a rejected
  push, `git fetch` + `git rebase` — distinguish a transient refusal (another session's in-flight
  uncommitted work sitting in the shared tree — wait and retry, NEVER stash/checkout/reset to "clean
  up", that destroys the other session's work) from a genuine content conflict (stop, flag,
  `needsHumanReview`); (4) never `git push --force`, under any of the above conditions.

  **Second hard requirement on Prompt 2 specifically — do not lose this to paraphrasing (issue
  #22):** the generated Prompt 2 text runs as Stage A of the skill-rollout batch pipeline, whose
  own boundary rule forbids committing the target plugin repo's diff at all — staging happens once,
  at the very end of Stage A, and Stage C commits once after independent review. "Same shape as the
  example" is not enough for the per-iteration keep/discard mechanics either — copy the standalone-
  vs-pipeline-mode keep split and the content-capture-restore discard mechanics from
  `{referenceDir}/self-improving-skills.md`'s "Beispielprompt für Skill Self-Improvement" verbatim in
  substance, not just paraphrased. In short (again, the source has the full reasoning — two
  independent production runs already hit this exact gap and each had to improvise its own
  workaround before it was fixed here, do not let a fresh onboarding regenerate the same gap):
  (1) capture the file's exact content via a plain Read immediately before EVERY iteration's edit,
  starting with iteration 1; (2) on "keep", do NOT git-commit into the target plugin repo — leave
  the edit applied uncommitted, record `"commit": null` plus an explanatory `"note"` in
  loop-state.json (this is the correct, expected shape, not an anomaly); (3) on "discard", restore
  the file to the content captured in step 1 via Edit/Write — NEVER `git checkout`/`git reset` for
  this, since Stage A never commits per iteration, so HEAD stays at the pre-loop baseline and a
  git-based revert after any earlier kept iteration would silently destroy that kept edit too, not
  just the current one.
- **Prompt 3** (Live-MCP-Tier): three possible outcomes, per step 3/3a's findings — do not blur
  them together:
  1. No MCP server at all → short explicit note instead of a prompt ("Dieses Plugin hat keinen
     MCP-Server — Live-Tier entfällt, nur Prompt 1+2 gelten.").
  2. MCP server exists AND step 3a's discovery + static + live checks ALL passed for the
     `create-testdata`/`reset-testdata`/`delete-testdata` convention → generate Prompt 3 in full,
     same shape as the template.

     **Hard constraint on Prompt 3's execution step — do not write "spawn a subagent" (issue #15):**
     Prompt 3 will be executed by an agent running inside the skill-rollout Workflow's own
     `agent()` call (see `workflows/skill-rollout.js`'s per-skill rollout prompt) — a context where
     the Task/Agent tool is unavailable, so that agent cannot itself spawn a further subagent. This
     is the same harness constraint already documented throughout `workflows/skill-rollout.js` for
     `EnterWorktree` (e.g. its "unavailable from this workflow-subagent context on this harness"
     comments) — Prompt 3's live-tier step hits the identical wall for agent-spawning instead of
     cwd-override. It was confirmed the hard way: storyforge's first-generated Prompt 3 said "spawn
     a subagent with real MCP tool access," and every real rollout run silently substituted direct
     execution instead (evidenced in per-skill `loop-log.md` NEEDS-HUMAN-REVIEW entries, e.g.
     `world-builder/loop-log.md` and `character-creator-memoir/loop-log.md`), because the tool
     genuinely was not there.

     Do NOT write a "spawn a subagent" instruction into a newly generated Prompt 3 — it is a
     reasonable-sounding isolation design (clean tool-call-log isolation, no context bleed from the
     eval-grading agent's own state) but cannot be implemented via nested agent-spawning from this
     execution context, no matter how natural it feels while drafting. Instead, the live-case
     execution step must say: the current agent calls the real MCP tools itself directly
     (discovering them via ToolSearch if not pre-loaded), outputs a TOOL CALL LOG (tool name + exact
     parameters + result) as evidence, and for any claimed side effect, performs an independent
     Read/tool call afterward proving it actually happened — same evidentiary rigor as the subagent
     design intended, just executed directly instead of delegated.

     **Reference the MCP Surface Register (step 3b):** Prompt 3's text must instruct the executing
     agent to read {skillEvalsDir}/{plugin-name}/mcp-surface-register.md before running any live
     case, and to write back anything it newly learns (a tool's per-entity/global-singleton scope, a
     fixture state it created) — see {referenceDir}/self-improving-skills.md's "MCP Surface Register"
     section for the exact mechanics and the mandatory capture-before-write rule for any singleton
     tool call. Do not inline that mechanics text again here; point at the source section so the two
     copies cannot drift apart.
  3. MCP server exists AND step 3a's checks did NOT all pass (the default until a plugin actually
     implements and verifies the `create-testdata`/`reset-testdata`/`delete-testdata` convention —
     regardless of whether its subject matter sounds fictional or real-world) → do **NOT** generate a
     ready-to-run Prompt 3. Write a blocked placeholder instead: state plainly which check failed
     (missing skill(s) / missing static refuse-step / live-verification outcome that wasn't one of
     the two zero-risk cases), name the specific risk (e.g. "a single shared database holds every
     real case/contact/author profile alongside whatever test entity gets created — a mis-scoped
     reset could delete real data"), and point at the concrete, buildable unblock path — implement or
     fix the three-skill convention for this plugin per {referenceDir}/self-improving-skills.md, file
     a per-plugin GitHub issue if one doesn't already exist — BEFORE Prompt 3 is ever written for this
     plugin. No "have a conversation" step; this is a buildable engineering task, not an undefined
     social one. This blocked state is mandatory, not a suggestion the runner can skip past — Prompt 2
     (simulated tier) still runs fully, only Prompt 3 is gated.

     **This plugin-level block is not necessarily final per-skill (issue #24):** at rollout time,
     `workflows/skill-rollout.js`'s Stage A checks each individual skill's OWN domain-tool surface
     for a verified-read-only bypass BEFORE falling back to this plugin-level block — a skill whose
     MCP calls are all read-verbs (`get_`/`list_`/`search_`/`resolve_`/`read_`) with zero write-verb
     calls anywhere gets classified 🟩 READ-ONLY and runs Prompt 3 directly against the real system,
     regardless of this placeholder. Nothing to add here in the generated playbook for that — the
     bypass check lives entirely in the workflow script and applies uniformly to every plugin.
- Closing "Nach Abschluss" section, same as the template, pointing at this plugin's own STATUS.md.

## Phase 3 — Self-check before finishing

Before presenting the result, re-read the generated file against Phase 1's actual findings: does
every stated fact trace back to something you actually verified for {PLUGIN_REPO_PATH} in Phase 1 —
none of it copied from {referenceDir}/self-improving-skills.md's own example content? Does Prompt 3's
presence/absence/blocked-state correctly match step 3/3a's findings (no MCP server → omitted; MCP
server + all three of discovery/static/live checks passed → full prompt; MCP server + any of those
three checks failed or uncertain → blocked placeholder naming which check failed, never a
ready-to-run prompt)? Did you guess anywhere instead of confirming or asking — including guessing a
plugin into the safe bucket on domain vibes ("sounds fictional", "sounds low-stakes") rather than the
three concrete checks? For the live-verification check specifically: did you confirm the test slug
was actually constructed to be provably-nonexistent (not just non-matching), and did you record which
of the two zero-risk outcomes actually occurred? If any of this was guessed rather than confirmed,
stop and ask now rather than presenting it.

Write the output in German (explanatory text) with English prompt blocks, matching
{referenceDir}/self-improving-skills.md's style.
