# Skill Improving

## evals.json bauen

Prompts + Assertions direkt aus den expliziten Regeln der SKILL.md ableiten (nicht raten)

- Immer den Pfad zur SKILL.md angeben

- Darauf achten, dass Memoryeintrag betreffend privaten und öffentlichen Repos eingehalten wird.

### Beispielprompt für evals.json

```tex
Read {PATHTO SKILL.md} and derive an evals.json file for it, following the simulated-mode schema in this plugin's reference/eval-schema.md (skill_name + evals[] with id/prompt/expected_output/expectations).

For each distinct behavior rule or edge case stated in the SKILL.md, write one eval case: a realistic multi-turn user scenario (not a single-line prompt) that would actually exercise that rule, plus true/false-checkable expectations grounded in the rule's exact wording. Let the number of cases follow from how many distinct rules/edge cases the SKILL.md has — don't target a fixed count.

evals.json always lives externally, at ~/projekte/skill-evals/<plugin-or-repo-name>/<skill-name>/evals.json — never inside the source repo itself, regardless of whether it's a private repo or a public Claude plugin repo (one with a .claude-plugin/plugin.json that declares a shipped "skills" path). This also keeps eval/test material from ever shipping to end users of a packaged plugin. (Earlier revisions of this playbook kept private-repo evals in-repo at <skill-dir>/evals/evals.json — that convention was retired; any pre-existing in-repo evals.json files have already been migrated externally as a one-time cleanup, don't recreate them.)
```

- Nach dem Erstellen: evals.json separat committen, BEVOR die Loop startet — sonst gibt's keinen sauberen Diff-Ausgangspunkt für Iteration 1.

## Loop laufen lassen

Die eigentliche Mechanik (Grading, Commit/Reset, Iterationszählung, Abbruchbedingungen) steckt komplett im Beispielprompt unten. Während die Loop läuft, zusätzlich beachten:

Alles, was beim Transkript-Lesen auffällt, aber von keiner Assertion erfasst wird, im Log als "residual note" festhalten — nicht ignorieren, aber auch nicht automatisch draufsatteln.

### Beispielprompt für Skill Self-Improvement

```tex
Use the skill-creator skill to run a self-improvement loop on my {Skill-Name/PATHTO Skill} skill. Use the test prompts and assertions in {PATHTO evals.json} to evaluate each iteration. For each cycle: run all test prompts through the skill, grade each assertion pass/fail, calculate the overall pass rate as a score. If any assertions fail, propose and make ONE change to the SKILL.md. Re-run all tests and recalculate. If the score improved, keep the change and git commit (scope the commit to only the skill's own files, not unrelated repo changes). If it dropped or stayed the same, git reset.

Not every failing assertion is a real skill bug — sometimes the assertion itself is too strict or ambiguous. So: track per-assertion failure history across iterations. If the same specific assertion fails 2 iterations in a row despite a targeted fix attempt each time, stop trying to fix it via SKILL.md changes — flag it in the log as a candidate eval-design issue instead (needs human review of the assertion, not more churn). If the overall score hasn't improved for 2 consecutive iterations, stop the loop entirely and report the final score plus which assertions are still failing, rather than continuing to iterate without my input.

Log each iteration: number, score, keep or discard, what you tried. Do NOT stop to ask me. I may be asleep. Keep looping until I interrupt you, you hit a perfect score, or one of the stall conditions above triggers.

Alongside the prose log, maintain a loop-state.json next to it, per the schema in this plugin's reference/eval-schema.md (iteration number, best score + pass/total, per-iteration history with keep/discard labels and commit hashes, stall streak, per-assertion fail streaks, stopped/stop_reason). Update it after every iteration, not just at the end — it's the quick-glance, machine-readable twin of the prose log, and lets a resumed/interrupted session pick up state without re-reading the whole thing.
```

## Nach Abschluss

Residual notes einzeln durchgehen, entscheiden pro Fund: neue Assertion + Nachiteration, oder bewusst liegen lassen.

## Allgemeiner Hinweis

Das Log ist kein Einmal-Artefakt — bei einer zukünftigen erneuten Loop auf demselben Skill wird in dieselbe Datei weitergeschreiben (neue Iterationen anhängen), nicht überschreiben, damit die Historie durchgängig bleibt.

## Skills mit MCP-Tool-Nutzung: zweites Test-Tier

Simulierte Evals (Fixture-Daten direkt im Prompt-Text eingebettet, kein echter Tool-Call) testen nur die Entscheidungslogik des Skills — sie können strukturell nicht erkennen: falscher Toolname/Parameter, Schema-Drift zwischen Skill-Annahme und echter MCP-Response, Fehlerpfade (Timeout, fehlender Datensatz), oder ob ein behaupteter Seiteneffekt (Datei schreiben, DB-Eintrag) wirklich passiert. Dafür braucht's ein zweites Tier mit echtem Tool-Zugriff gegen eine Sandbox.

### Sandbox anlegen — über die echten Skills, nicht handgetippt

Schließt das Schema-Drift-Risiko von vornherein: Autor/Projekt über die produktiven Anlage-Skills erzeugen (z.B. `create-author` + `new-book`), nicht die Zieldateien von Hand schreiben. Slug klar als Test markieren (Präfix wie `zz-sandbox-`), damit nie eine Verwechslung mit echten Daten passieren kann. Inhalt/Stimme ist irrelevant, wenn die Live-Tests binäre Fragen prüfen (wurde Tool X aufgerufen, hat Feld Y den erwarteten Wert) — schnelle synthetische Antworten im Anlage-Interview reichen.

### evals.json — Schema-Erweiterung für Live-Cases

Volles Schema (Feldreferenz, Beispiel, Live-Case-Anzahl-Faustregel) liegt zentral in diesem Plugin unter `reference/eval-schema.md` — nicht mehr hier duplizieren, sonst laufen die beiden Kopien irgendwann auseinander.

### Snapshot/Reset — nur sicher, wenn die Datenquelle isoliert ist

Vor dem Einrichten prüfen, ob die Sandbox-Daten in isolierten Dateien/DBs pro Autor/Buch liegen (git-Restore sicher) oder in einer **geteilten** Datei/DB über mehrere echte Autoren/Bücher hinweg (git-Restore NICHT sicher — würde auch echte Änderungen zurückrollen). Isolierte Artefakte: Git-Tag als Baseline, Reset via `git checkout <tag> -- <pfad>` + `git clean -fd -- <pfad>`, strikt pfad-gescoped. Geteilte Artefakte (z.B. eine gemeinsame Discoveries-DB über alle Autoren): niemals git-restoren — stattdessen über die MCP-Tools selbst zurücksetzen, die ohnehin nach `author_slug`/exakter ID scopen (z.B. Baseline-Liste bekannter Einträge vergleichen, Differenz per delete/write-Tool ausgleichen).

Konkretes Beispiel: `/home/markus-michalski/projekte/skill-evals/storyforge/author-check/sandbox.md`

### Live-Tier läuft NICHT in der schnellen Iterationsschleife mit

Kosten + echte Seiteneffekte. Stattdessen: einmal am Ende (bevor der SKILL.md-Change als fertig gilt), und erneut wenn sich MCP-Tool-Signaturen ändern. Scores von simuliertem und Live-Tier getrennt ausweisen, nie zusammenrechnen — ein 100%-Simulated-Score sagt nichts über den Live-Score aus.

### Nebenbefund: Live-Tests finden echte Produktionsbugs, nicht nur Skill-Formulierungsprobleme

Beim Aufbau der storyforge/author-check-Sandbox kam so ein Fund zutage: `author-check` erwartete vier Profil-Felder, die im echten MCP-Server nirgends geschrieben werden konnten (Allowlist fehlte UND die Cache-Projektion beim Lesen ließ sie fallen — zwei getrennte Lecks). Das ist kein Skill-Bug, sondern ein Bug im Produktionscode des Plugins selbst — geht als eigener PR ins Plugin-Repo (git-workflow-Skill, volle Review-Pipeline inkl. echter Test-Suite falls vorhanden), nicht als Teil der Skill-Improvement-Loop. Beim Live-Testen also immer offen bleiben: nicht jeder Fund gehört ins SKILL.md, manche gehören in den MCP-Server-Code.
