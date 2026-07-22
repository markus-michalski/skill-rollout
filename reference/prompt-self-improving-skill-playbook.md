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
3a. **Only if an MCP server DOES exist (step 2): determine whether a verified-safe sandbox
   isolation strategy already exists for this plugin's shared storage — this, not whether the
   plugin's subject matter is "fictional," is what determines whether Prompt 3 can be auto-generated.**

   Earlier drafts of this rule framed the question as "is the domain disposable-fictional (like
   storyforge) or real-world (personal/legal/business data)?" — that framing is
   WRONG and was corrected after checking: storyforge's own shared storage (`~/.storyforge/authors/`)
   contains a real, actively-used author profile (`ethan-cole`, not sandbox-prefixed) sitting
   alongside `zz-sandbox-author`, and its book-projects content root has git history of real book
   projects being created and removed over time. storyforge is NOT safe because books are
   fictional — a corrupted real chapter the user is actually writing is just as much a real loss
   as a corrupted real legal case. It's safe because of concrete, already-done engineering: a
   positive naming convention (`zz-sandbox-` prefix) that unambiguously marks test entities apart
   from anything real, path-scoped resets that never touch a whole shared directory, an explicit
   isolated-files-vs-shared-DB distinction with different reset mechanics for each, and
   `sandbox-baseline` git tags as a restore reference point — all documented and iterated on across
   this rollout's own `sandbox.md` files.

   So the actual check is: **does this specific plugin already have that same kind of concretely
   documented, tested isolation design** (a real `sandbox.md`-equivalent naming/scoping/reset
   strategy that has been verified not to collide with real coexisting data)? Two outcomes:
   - **Yes, already designed and documented** — proceed to generate Prompt 3. (storyforge is the
     only confirmed case today, purely because that design work happened here first — not because
     of anything inherent to fiction as a subject.)
   - **No such design exists yet** (the default for every plugin not yet through this process,
     regardless of whether its subject matter sounds fictional or real-world) — Prompt 3 is
     blocked pending a human conversation to actually design it, per Phase 2 below.
   **Default to "not yet designed" — do not guess a plugin into the safe bucket because its domain
   sounds fictional or low-stakes.** A plugin with no prior sandbox work has not earned the "safe"
   classification yet, no matter what it manages.
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
   standalone bypass).
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
- **Prompt 1** (evals.json bauen, simulierter Tier): same shape as {referenceDir}/self-improving-skills.md's
  example, referencing the skill-rollout plugin's reference/eval-schema.md (this is the correct target
  location to write into the NEW playbook's text — never the {skillEvalsDir}/schema.md path, which
  does not exist), saving to
  {skillEvalsDir}/{plugin-name}/{skill-name}/evals.json (always this external location, per Phase 1
  step 5).
- **Prompt 2** (Loop laufen lassen, simulierter Tier): same shape as the example, adapted
  paths/repo name, including the sync-to-deploy-locations step ONLY if Phase 1 found real deploy
  locations distinct from the source repo.
- **Prompt 3** (Live-MCP-Tier): three possible outcomes, per step 3/3a's findings — do not blur
  them together:
  1. No MCP server at all → short explicit note instead of a prompt ("Dieses Plugin hat keinen
     MCP-Server — Live-Tier entfällt, nur Prompt 1+2 gelten.").
  2. MCP server exists AND the domain is confirmed disposable/fictional (storyforge's own
     precedent) → generate Prompt 3 in full, same shape as the template.

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
  3. MCP server exists AND the domain is real-world data (the default unless positively ruled
     out) → do **NOT** generate a ready-to-run Prompt 3. Write a blocked placeholder instead:
     state plainly that this plugin's live-tier sandbox strategy has not been designed yet because
     its MCP tools touch real (not disposable) data, name the specific risk (e.g. "a single shared
     database holds every real case/contact/author profile alongside whatever test entity gets
     created — a mis-scoped reset could delete real data"), and require an explicit conversation
     with the user about sandbox design (what becomes the disposable test entity, how it's marked
     unambiguously, what the reset procedure is and what it must never touch) BEFORE Prompt 3 is
     ever written for this plugin. This blocked state is mandatory, not a suggestion the runner can
     skip past — Prompt 2 (simulated tier) still runs fully, only Prompt 3 is gated.
- Closing "Nach Abschluss" section, same as the template, pointing at this plugin's own STATUS.md.

## Phase 3 — Self-check before finishing

Before presenting the result, re-read the generated file against Phase 1's actual findings: does
every stated fact trace back to something you actually verified for {PLUGIN_REPO_PATH} in Phase 1 —
none of it copied from {referenceDir}/self-improving-skills.md's own example content? Does Prompt 3's
presence/absence/blocked-state correctly match step 3/3a's findings (no MCP server → omitted; MCP
server + confirmed fictional domain → full prompt; MCP server + real-world data or genuine
uncertainty → blocked placeholder, never a ready-to-run prompt)? Did you guess anywhere instead of
confirming or asking — including guessing a plugin into the "fictional" bucket without a positive,
specific reason? If yes, stop and ask now rather than presenting it.

Write the output in German (explanatory text) with English prompt blocks, matching
{referenceDir}/self-improving-skills.md's style.
