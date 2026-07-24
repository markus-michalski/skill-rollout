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

- Nach dem Erstellen: evals.json separat committen, BEVOR die Loop startet — sonst gibt's keinen sauberen Diff-Ausgangspunkt für Iteration 1. **Dabei die Git-Sicherheitsregel unten befolgen — Pflicht, nicht optional.**

## Git-Sicherheit für JEDEN Commit in skill-evals (Issue #20)

`~/projekte/skill-evals` ist EIN geteiltes Git-Repo über alle Rollout-Ziel-Plugins hinweg (mm-skills, storyforge, ...) — anders als der Ziel-Plugin-Repo selbst, der pro Batch über `preIsolated`/`EnterWorktree` isoliert ist, hat skill-evals **keine** Isolation. Zwei Rollout-Sessions gegen unterschiedliche Plugins teilen sich dasselbe Arbeitsverzeichnis, denselben Index, denselben HEAD.

Gilt für JEDEN Commit hier — evals.json, loop-log.md, loop-state.json, STATUS.md, batch-digest.md, self-improving-skill-{plugin}.md, mcp-surface-register.md, alles. Die beiden Schritte gehören zusammen, nicht einzeln befolgen:

1. **Scoped Add UND Scoped Commit — Scoped Add allein reicht nicht.** `git add ~/projekte/skill-evals/{plugin-name}/` (oder noch spezifischer) — NIEMALS `git add -A`, NIEMALS blankes `git add .` vom skill-evals-Root aus. Aber: ein scoped Add kontrolliert nur, was DU staged — eine parallel laufende Session kann bereits eigene Dateien im selben, geteilten Index stehen haben, und ein normales `git commit` snapshotted den GESAMTEN Index, nicht nur die eigenen Pfade. Deshalb auch beim Commit scopen: `git commit -- ~/projekte/skill-evals/{plugin-name}/ -m "..."` (die `--`-Pathspec-Form committet NUR passende Pfade, unabhängig davon, was sonst noch gestaged ist) — niemals ein blankes `git commit` hier.
2. **Bei `git add`/`git commit`-Fehler durch Index-Lock** (`Unable to create '.git/index.lock': File exists`): eine andere Session arbeitet gerade parallel an diesem geteilten Repo — kein echter Fehler. Ein paar Sekunden warten, erneut versuchen, bis zu 5x. Die Lock-Datei nie selbst anfassen.
3. **Bei `git push`-Rejection** (andere Session hat zwischenzeitlich gepusht): `git fetch origin` dann `git rebase origin/main` — kein blankes `git pull`, der eigene Change ist durch Schritt 1 bereits scoped committed. Zwei unterschiedliche Fehlerarten, unterschiedlich behandeln:
   - **Rebase verweigert wegen uncommitteter Änderungen im geteilten Arbeitsverzeichnis:** das ist der In-Flight-Write der ANDEREN Session, nicht deiner — nicht anfassen. Transient, löst sich meist von selbst, sobald die andere Session ihren eigenen Add+Commit-Zyklus abschließt. Ein paar Sekunden warten, Fetch+Rebase erneut versuchen, bis zu 5x. **Niemals** `git stash`, `git checkout -- .` oder `git reset --hard` zum "Aufräumen" — das würde die uncommittete Arbeit der anderen Session zerstören, genau das, was diese Regel verhindern soll.
   - **Rebase meldet einen echten Inhalts-Konflikt** (keine Verweigerung, echter Konflikt): sollte bei korrektem Scoped-Commit nicht passieren — falls doch: stoppen, nicht raten, `needsHumanReview`-Eintrag mit den betroffenen Dateien.
   Nach erfolgreichem Rebase: Push einmal erneut versuchen. **Niemals `git push --force`**, unter keiner der obigen Bedingungen.

## Loop laufen lassen

Die eigentliche Mechanik (Grading, Commit/Reset, Iterationszählung, Abbruchbedingungen) steckt komplett im Beispielprompt unten. Während die Loop läuft, zusätzlich beachten:

Alles, was beim Transkript-Lesen auffällt, aber von keiner Assertion erfasst wird, im Log als "residual note" festhalten — nicht ignorieren, aber auch nicht automatisch draufsatteln.

### Beispielprompt für Skill Self-Improvement

```tex
Use the skill-creator skill to run a self-improvement loop on my {Skill-Name/PATHTO Skill} skill. Use the test prompts and assertions in {PATHTO evals.json} to evaluate each iteration. For each cycle: run all test prompts through the skill, grade each assertion pass/fail, calculate the overall pass rate as a score. If any assertions fail, propose and make ONE change to the SKILL.md.

Before making that change, capture the file's exact current content (a plain Read, not a git operation) — this is what a later discard restores, so do this on EVERY iteration, not just ones you expect to fail.

Re-run all tests and recalculate. If the score improved: keep the change.
- Standalone run (this loop is NOT executing inside the skill-rollout batch pipeline's Stage A): git commit it now (scope the commit to only the skill's own files, not unrelated repo changes). Commit message and PR title format is fixed, not improvised per skill — `type(skill-name): subject`, per this plugin's `reference/eval-schema.md` §7 (`fix` for the default eval-driven case, never a bare plugin-name prefix or a `skills(...)` type).
- Pipeline run (this IS Stage A of the skill-rollout batch pipeline): do NOT commit — Stage A's own boundary rule forbids committing the plugin-repo diff here; leave the edit applied, uncommitted, in the working tree. The outer pipeline's Stage C commits once, after independent review, covering every kept iteration from this whole loop in one diff. Record `"commit": null` in loop-state.json for this iteration, with a one-line `"note"` explaining why (so a resumed/reviewing session doesn't mistake the absence of a hash for a discard) — this is the CORRECT, expected shape in pipeline mode, not an anomaly to fix.

If it dropped or stayed the same: discard. Restore the file to the content captured just before this iteration's edit (via Edit/Write) — this content-based restore is correct and safe in BOTH modes (standalone and pipeline), always use it rather than a git-based revert. It matters most in pipeline mode: nothing may have been committed yet there, and a git-based revert (`git checkout`/`git reset`) would jump back to the pre-loop baseline, silently wiping out any EARLIER kept iteration's edit too, not just this iteration's — content-based restore works correctly regardless of how many keeps came before, in either mode.

Not every failing assertion is a real skill bug — sometimes the assertion itself is too strict or ambiguous. So: track per-assertion failure history across iterations. If the same specific assertion fails 2 iterations in a row despite a targeted fix attempt each time, stop trying to fix it via SKILL.md changes — flag it in the log as a candidate eval-design issue instead (needs human review of the assertion, not more churn). If the overall score hasn't improved for 2 consecutive iterations, stop the loop entirely and report the final score plus which assertions are still failing, rather than continuing to iterate without my input.

Log each iteration: number, score, keep or discard, what you tried. Do NOT stop to ask me. I may be asleep. Keep looping until I interrupt you, you hit a perfect score, or one of the stall conditions above triggers.

Alongside the prose log, maintain a loop-state.json next to it, per the schema in this plugin's reference/eval-schema.md (iteration number, best score + pass/total, per-iteration history with keep/discard labels and commit hashes — `null` + a `note` on "keep" entries in pipeline mode, per above — stall streak, per-assertion fail streaks, stopped/stop_reason). Update it after every iteration, not just at the end — it's the quick-glance, machine-readable twin of the prose log, and lets a resumed/interrupted session pick up state without re-reading the whole thing.

Whenever loop-log.md or loop-state.json get committed inside skill-evals: use the scoped-add + scoped-commit + safe-push-retry rule from "Git-Sicherheit für JEDEN Commit in skill-evals" above — never a blind `git add -A`/`.` or a plain `git commit` from the skill-evals root, never a force-push.
```

## Nach Abschluss

Residual notes einzeln durchgehen, entscheiden pro Fund: neue Assertion + Nachiteration, oder bewusst liegen lassen.

## Allgemeiner Hinweis

Das Log ist kein Einmal-Artefakt — bei einer zukünftigen erneuten Loop auf demselben Skill wird in dieselbe Datei weitergeschreiben (neue Iterationen anhängen), nicht überschreiben, damit die Historie durchgängig bleibt.

## Skills mit MCP-Tool-Nutzung: zweites Test-Tier

Simulierte Evals (Fixture-Daten direkt im Prompt-Text eingebettet, kein echter Tool-Call) testen nur die Entscheidungslogik des Skills — sie können strukturell nicht erkennen: falscher Toolname/Parameter, Schema-Drift zwischen Skill-Annahme und echter MCP-Response, Fehlerpfade (Timeout, fehlender Datensatz), oder ob ein behaupteter Seiteneffekt (Datei schreiben, DB-Eintrag) wirklich passiert. Dafür braucht's ein zweites Tier mit echtem Tool-Zugriff gegen eine Sandbox.

### create-testdata / reset-testdata / delete-testdata Convention (Issue #35)

Primärer Weg, um ein Plugin für den Live-Tier freizuschalten — ersetzt das frühere, nie tatsächlich eingehaltene "menschliches Sandbox-Design-Gespräch"-Gate (bei storyforge, dem einzigen bisher onboardeten Plugin, fand dieses Gespräch nachweislich nie statt — Grep über alle `loop-log.md` findet keine dokumentierte Design-Diskussion; die `zz-sandbox-`-Konvention wurde von autonomen Rollout-Sessions eigenständig entworfen und einfach als settled practice übernommen). Siehe `reference/prompt-self-improving-skill-playbook.md` Phase 1 Schritt 3a für die volle Discovery-/Verifikations-Mechanik — hier nur die Konvention selbst, nicht erneut duplizieren.

Jedes Plugin, das Live-Tier-Tests will, implementiert drei fest benannte Skills — feste Namen über alle Plugins hinweg, nie pro Plugin erfunden, gewählt weil sie ohne Nachschlage-Tabelle selbsterklärend sind:

- **`create-testdata`** — legt frische, wegwerfbare Test-Entities über die echten Anlage-Tools des Plugins an (spiegelt die "über die echten Skills, nicht handgetippt"-Konvention weiter unten — formalisiert sie jetzt zu einem eigenständigen, first-class Skill statt Ad-hoc-Improvisation während des Onboardings). Gibt die Slugs/IDs der angelegten Entities zurück.
- **`reset-testdata`** — setzt dieselben Test-Entities auf einen bekannten Baseline-Zustand zurück (macht Mutationen aus Live-Tier-Läufen rückgängig), OHNE sie zu löschen — sie bleiben als wiederverwendbare Fixtures über viele Rollout-Läufe hinweg erhalten, genau wie `zz-sandbox-author`/`zz-sandbox-book` es für storyforge bereits in der Praxis tun.
- **`delete-testdata`** — vollständiges Teardown/Entfernen, für einen wirklich sauberen Neustart oder die Dekommissionierung der Sandbox. Muss idempotent/no-op-safe sein — der allererste Aufruf (noch nichts angelegt) darf nicht fehlschlagen, sondern muss "nichts zu löschen" erkennen und normal weiterlaufen.

**Hard Safety Rule — keine Konvention, ein struktureller Gate:** alle drei Skills MÜSSEN als nicht überspringbarer erster Schritt jede Entity ablehnen, deren Slug nicht dem Präfix-Muster für Test-Daten entspricht — kein dokumentierter Best-Practice-Hinweis, ein echter Refuse-and-Stop-Check bei JEDEM Aufruf.

**Präfix-Entscheidung getroffen (2026-07-24):** `zz-sandbox-` bleibt der feste Präfix — storyforges bereits etablierte Konvention wird NICHT auf `zzzz-` umgestellt. Kein Migrationsaufwand für storyforge; life-hub, project-hub und vidcraft implementieren die drei Skills direkt mit `zz-sandbox-` als hartem Präfix-Gate, ohne Zwischenschritt.

**Onboarding vertraut dem Skill-Namen nie, sondern live-verifiziert die Ablehnung** — zwei Prüfungen, keine ersetzt die andere (voller Wortlaut in der Playbook-Datei, hier nur die Kurzfassung):
1. **Statischer Check:** die tatsächliche Instruktions-Text der drei SKILL.md-Dateien lesen und bestätigen, dass jede einen konkreten, unbedingten ersten Schritt zur Präfix-Ablehnung dokumentiert — nicht nur eine Sicherheits-Prosa-Erwähnung irgendwo im Text.
2. **Live-Verifikation, korrigierte Methodik:** `delete-testdata` (das Tool mit dem größten Blast-Radius der drei) einmal mit einem synthetischen Test-Slug aufrufen, der (a) NICHT das `zz-sandbox-`-Präfix trägt UND (b) so konstruiert ist (Zufalls-/Zeitstempel-Suffix), dass er selbst bei komplett kaputtem Guard mit keiner echten Entity kollidieren kann. Der ursprüngliche Vorschlag ("ruf delete-testdata einmal mit einem nicht-passenden Slug auf") hatte einen echten Fehler: wenn der Guard kaputt ist UND der Test-Slug zufällig auf etwas Echtes verweist, IST der Verifikationsversuch selbst der Datenverlust — Test und Schaden sind dasselbe Ereignis. Die korrigierte Konstruktion schließt diese Lücke: beide möglichen Ausgänge eines kaputten Guards bleiben harmlos — entweder lehnt ein funktionierender Guard sofort vor jedem Lookup ab (erwarteter Pass), oder ein kaputter Guard lässt den darunterliegenden Delete-Call durchlaufen, der dann mit "nicht gefunden" fehlschlägt (nichts zu zerstören, da das Ziel von Anfang an synthetisch war) — ein klar unterscheidbarer, aber risikofreier zweiter Fehlermodus.

**Die Live-Verifikation allein befüllt die Sandbox nicht (Issue #37).** Schritt 2 oben testet nur den Ablehnungspfad gegen einen synthetischen, nie existierenden Slug — legt nichts Echtes an. Direkt danach, wenn beide Prüfungen bestanden haben, ruft das Onboarding `create-testdata` deshalb noch einmal echt auf (kein synthetischer Slug, ein tatsächlicher Anlage-Lauf), bestätigt per unabhängigem Read, und trägt das Ergebnis sofort in `mcp-surface-register.md`s Fixture-Inventory-Tabelle ein — siehe Playbook-Datei Schritt 3c. So findet jeder künftige Skill-Rollout die Sandbox von Anfang an vorbefüllt vor, statt dass der zufällig zuerst ausgewählte Skill sie improvisieren muss.

**create-testdata/reset-testdata/delete-testdata sind selbst Rollout-Ziele.** Als gewöhnliche Skills im Ziel-Plugin bekommen sie eigene STATUS.md-Zeilen und durchlaufen die normale Rollout-Pipeline — mit einem Ordnungsproblem: `create-testdata`s eigener Live-Test findet häufig bereits vorhandene Test-Daten vor (aus früheren Rollout-Läufen anderer Skills), und ein naiver Test würde entweder an einer unerwarteten Vorbedingung scheitern oder doppelte Fixtures anlegen. `workflows/skill-rollout.js` behandelt genau diese drei Skillnamen deshalb als Sonderfall mit einer festen Testsequenz statt dem normalen Prompt 1/2/3-Flow (prüfen ob Testdaten schon existieren → falls ja `delete-testdata` zuerst → dann `create-testdata` → dann `reset-testdata`) — siehe die entsprechende Sektion dort, hier nicht erneut duplizieren.

**Zwei gestaffelte Optionen, nicht eine erzwungene Wahl (Design-Refinement 2026-07-24):**
- **Option A (jetzt lieferbar, keine Server-Änderungen nötig):** präfixbasiert (`zz-sandbox-`) + die oben korrigierte synthetische Live-Verifikation + statischer Code-Check. Das ist die Baseline, die jedes Plugin-Issue (life-hub#13, project-hub#82, storyforge#431, vidcraft#76) zuerst implementieren sollte.
- **Option B (stärker, größerer Scope, Machbarkeit pro Plugin ungeprüft):** ein dediziertes Test-DB/Content-Root — `create-testdata` provisioniert eine komplett separate Test-Datenbank (Migrationen laufen lassen, dann Fixtures befüllen) statt in geteilten Storage unter einer Namenskonvention zu schreiben; `delete-testdata` wird trivial (nur die Test-DB/-Datei löschen), strukturell unfähig echte Daten zu berühren (keine Präfix-Check-Logik, die einen Bug haben könnte — die Isolation ist architektonisch, nicht policy-basiert). Nicht als einziger Weg übernommen, weil die Machbarkeit ungeprüft ist und vermutlich pro Plugin variiert: braucht MCP-Server-Support für eine alternative DB/einen alternativen Pfad zur Laufzeit (nicht garantiert vorhanden), storyforge ist ein Hybrid (Kapitel/Charaktere sind echte Dateien unter `book-projects`, nicht nur DB-Zeilen — "zweite Datenbank" allein deckt das nicht ab), braucht ein Migrationssystem, das einen beliebigen Pfad/eine beliebige Connection ansteuern kann. Wer eines der vier Plugin-Issues übernimmt, prüft zuerst dessen echte Storage-Architektur und entscheidet dann, ob Option B dort realistisch erreichbar ist, bevor auf Option A zurückgefallen wird.

### Sandbox anlegen — über die echten Skills, nicht handgetippt

**Diese Sektion und "Snapshot/Reset" weiter unten sind Implementierungs-Leitlinien FÜR den Bau von `create-testdata`/`reset-testdata`/`delete-testdata` — nicht etwas, das das Onboarding selbst entwirft.** Wer eines der vier Plugin-Issues (life-hub#13, project-hub#82, storyforge#431, vidcraft#76) umsetzt, folgt diesen Mustern beim Implementieren der drei Skills.

Schließt das Schema-Drift-Risiko von vornherein: Autor/Projekt über die produktiven Anlage-Skills erzeugen (z.B. `create-author` + `new-book`), nicht die Zieldateien von Hand schreiben. Slug klar als Test markieren (Präfix wie `zz-sandbox-`), damit nie eine Verwechslung mit echten Daten passieren kann. Inhalt/Stimme ist irrelevant, wenn die Live-Tests binäre Fragen prüfen (wurde Tool X aufgerufen, hat Feld Y den erwarteten Wert) — schnelle synthetische Antworten im Anlage-Interview reichen.

### evals.json — Schema-Erweiterung für Live-Cases

Volles Schema (Feldreferenz, Beispiel, Live-Case-Anzahl-Faustregel) liegt zentral in diesem Plugin unter `reference/eval-schema.md` — nicht mehr hier duplizieren, sonst laufen die beiden Kopien irgendwann auseinander.

### Snapshot/Reset — nur sicher, wenn die Datenquelle isoliert ist

**Auch diese Sektion ist Implementierungs-Leitlinie für `reset-testdata`/`delete-testdata` (siehe oben), nicht etwas, das das Onboarding selbst entwirft.**

Vor dem Einrichten prüfen, ob die Sandbox-Daten in isolierten Dateien/DBs pro Autor/Buch liegen (git-Restore sicher) oder in einer **geteilten** Datei/DB über mehrere echte Autoren/Bücher hinweg (git-Restore NICHT sicher — würde auch echte Änderungen zurückrollen). Isolierte Artefakte: Git-Tag als Baseline, Reset via `git checkout <tag> -- <pfad>` + `git clean -fd -- <pfad>`, strikt pfad-gescoped. Geteilte Artefakte (z.B. eine gemeinsame Discoveries-DB über alle Autoren): niemals git-restoren — stattdessen über die MCP-Tools selbst zurücksetzen, die ohnehin nach `author_slug`/exakter ID scopen (z.B. Baseline-Liste bekannter Einträge vergleichen, Differenz per delete/write-Tool ausgleichen).

Konkretes Beispiel: `/home/markus-michalski/projekte/skill-evals/storyforge/author-check/sandbox.md`

### MCP Surface Register — plugin-weites Gedächtnis statt Ad-hoc-Wiederentdeckung (Issue #26/#27)

Ohne dieses Register entdeckt jeder Skill-Rollout dieselben zwei Lückenklassen neu und schreibt eine
eigene Ad-hoc-Notiz in sein eigenes `sandbox.md` — bestätigt duplizierter Fall: `chapter-writer`s
`sandbox.md` leitete fast wortgleich her, was `start-session`s `sandbox.md` bereits dokumentiert
hatte. Stattdessen: eine Datei pro Plugin,
`{skillEvalsDir}/{plugin-name}/mcp-surface-register.md`, angelegt beim Onboarding (leer, siehe
`prompt-self-improving-skill-playbook.md` Phase 1 Schritt 3b + Phase 2) — für ein Plugin, das
bereits VOR dieser Erweiterung onboarded wurde (z.B. storyforge), existenzbasiert nachgeholt beim
nächsten Skill-Rollout (nicht am "ist das der allererste Live-Lauf?" festgemacht, das wäre für
storyforge falsch), von JEDEM Skill-Rollout vor
Prompt 3 gelesen und mit neuen Funden ergänzt. Zwei Tabellen:

**MCP Tool Scope** — Tool | Scope (`per-entity` / `global-singleton` / `shared-mutable-per-entity`) | Restore Strategy | Notes
**Fixture Inventory** — Entity (z.B. `zz-sandbox-book-memoir`) | Feld/Enum | Vorhandene Werte | Fehlende Werte

**Fixture-Completeness-Pre-Check:** Bevor ein Skill live-getestet wird, gegen die Fixture-Inventory-
Tabelle prüfen, ob die für seine Live-Cases benötigten Zustände (z.B. ein Enum-Wert wie
`consent_status: refused`) tatsächlich vorhanden sind. Fehlt einer und ist er eine bekannte
Enum-Permutation der Domäne (keine neu erfundene Datenart) → einmalig über das echte
Anlage-Tool des Plugins erzeugen, exakt nach derselben "über die echten Skills, nicht handgetippt"-
Regel oben, `zz-sandbox-`-Präfix, Ergebnis sofort in die Tabelle eintragen. Ist die fehlende
Fixture nicht sicher automatisch erzeugbar (z.B. würde reale Personendaten fingieren müssen, wo die
Zuordnung nicht eindeutig ist): genau diesen einen Case mit einer NAMENTLICH benannten Lücke
blocken — nicht vage NEEDS-HUMAN-REVIEW, sondern "Case X braucht Fixture-Zustand Y, existiert
nicht" — restliche Cases laufen normal weiter.

**Entscheidungsregel für globale Singleton-Tools** (Tools ohne Entity-Slug-Parameter, z.B.
storyforges `get_session()`/`update_session()` — eine einzelne Zeile, nicht pro Autor/Buch
gescoped, die `zz-sandbox-`-Konvention greift hier strukturell nicht): nicht danach klassifizieren,
*warum* ein Case den Call macht (narrativ, nicht prüfbar), sondern danach, was NACH dem Call
passiert — liest irgendetwas den Singleton-Wert danach: die eigenen Assertions dieses Cases, ein
späterer Schritt desselben Skills, ODER ein anderer Skill in einem künftigen Live-Lauf (das
Register ist plugin-weit, der Singleton hat keine Sandbox-Baseline)?
- **Nein** → `no-restore-accepted-drift`. Kein Restore-Versuch, kein Downgrade des restlichen Cases
  auf simuliert — nur dieser eine Call bleibt unbewertet. Konkretes Beispiel: `chapter-writer`s
  Step 7.5 (`update_session()` als reiner "zuletzt bearbeitet"-Zeiger-Update, nicht das eigentliche
  Testobjekt des Cases).
- **Ja** → Snapshot+Restore ist Pflicht. Ist der Call selbst das eigentliche Testobjekt (wie bei
  `start-session`, dessen ganzer Zweck das Testen von Session-Updates ist), gilt
  `best-effort-snapshot-restore` mit dokumentierten verlustbehafteten Rändern — Live-Abdeckung des
  eigentlichen Testobjekts zu verlieren wäre schlimmer als ein unvollständiger Restore. Konkretes
  Beispiel: `start-session`s Empty-String-Transport-Bug (Restore mit `" "` statt echtem `""`),
  dokumentiert in `start-session/sandbox.md` — dieser Workaround gehört als Restore-Strategie-Eintrag
  ins Register, nicht nur isoliert in `start-session`s eigenem `sandbox.md`.

**Regel 1 (zwingend, unabhängig von obiger Einstufung):** Jeder Live-Case, der einen im Register als
`global-singleton` erfassten Tool-Write macht, MUSS den Vorwert unmittelbar vor dem Call per
Read/Get sichern — schließt allein schon den Fehlermodus "Vorwert nie gesichert, Restore
unmöglich" (genau das, was `chapter-writer`s Case mit `update_session()` traf). Das Sichern kostet
fast nichts; ob der Snapshot danach für einen Restore genutzt wird, ist der einzige echte
Verzweigungspunkt (siehe Entscheidungsregel oben).

**Cross-Skill-Pollution:** Ein "incidental" Write in Skill A kann Skill B's eigenen
Core-Purpose-Live-Case später kaputtmachen, weil ein globaler Singleton keine Sandbox-Baseline zum
Zurücksetzen hat. Jeder Case, der auf einem Singleton-Wert assertiert, muss daher gegen seinen
EIGENEN, unmittelbar vorher gesicherten Snapshot/Delta prüfen — nie gegen einen angenommenen
absoluten Ausgangswert.

**Dritte Scope-Kategorie: `shared-mutable-per-entity`** (Issue #33 — verallgemeinert aus einem
konkreten storyforge-Fund). Anders als `global-singleton` (kein Entity-Slug überhaupt) und
klassischem `per-entity` (isoliert genug für Git-Restore, ein Skill "besitzt" seine eigene Sandbox-
Instanz) gibt es einen dritten Fall: ein Tool schreibt in eine per-Entity-Zeile (z.B.
`character_slug`), aber **zwei verschiedene Skills' Live-Tiers verwenden denselben Slug**, weil einer
den Sandbox-Charakter/-Entity des anderen bewusst wiederverwendet statt einen eigenen anzulegen —
konkret: storyforges `update_character_snapshot()`, wo `chapter-writer` und `chapter-reviewer` beide
denselben Sandbox-POV-Charakter (`freya`) benutzen, und ein späterer Call die Feld-Werte des
früheren Calls vollständig überschreibt (kein Array-Append). Symptom: ein Skill re-verifiziert seinen
eigenen, in `sandbox.md` dokumentierten "current state" und findet andere Werte vor, weil ein
GANZ ANDERER Skill zwischenzeitlich denselben Slug beschrieben hat — kein Bug, aber `sandbox.md`s
Doku ist dann nur ein Snapshot-zum-Schreibzeitpunkt, keine verlässliche Ground Truth.

Behandlung, analog zu `no-restore-accepted-drift`, aber mit einer zusätzlichen Dokumentationspflicht:
kein Restore-Versuch (dieselbe Begründung wie beim globalen Singleton — es gibt keine Baseline, zu
der EIN Skill zurücksetzen dürfte, ohne dem anderen Skill seine eigene Fixture kaputtzumachen), UND
jede `sandbox.md`, die exakte Werte für einen `shared-mutable-per-entity`-Slug als "current state"
dokumentiert, MUSS einen expliziten Disclaimer tragen ("diese Werte können durch einen anderen
Skill überschrieben worden sein — vor Gebrauch live neu lesen, nie ungeprüft übernehmen"). Für neue
Skills ist ein dedizierter Entity-Slug pro Skill (z.B. `freya-chapter-writer` statt geteiltem
`freya`) die sauberere Alternative und vermeidet das Problem strukturell — wird aber nicht
rückwirkend für bereits abgeschlossene Skills erzwungen, wenn der Disclaimer-Weg billiger ist und
ausreicht.

Klassifizierung (per-entity/global-singleton/shared-mutable-per-entity, welche Restore-Strategie greift) bleibt Agenten-Urteil
pro Fund — gleiches Muster wie die Read-Only-Klassifikation in `workflows/skill-rollout.js` (echtes
Tool-Verhalten prüfen, nicht Namens-Präfix, Ergebnis auditierbar im Log) —, das Ergebnis wird ins
Register geschrieben, damit der nächste Skill-Rollout es nachschlagen statt neu herleiten kann.

### Live-Tier läuft NICHT in der schnellen Iterationsschleife mit

Kosten + echte Seiteneffekte. Stattdessen: einmal am Ende (bevor der SKILL.md-Change als fertig gilt), und erneut wenn sich MCP-Tool-Signaturen ändern. Scores von simuliertem und Live-Tier getrennt ausweisen, nie zusammenrechnen — ein 100%-Simulated-Score sagt nichts über den Live-Score aus.

### Nebenbefund: Live-Tests finden echte Produktionsbugs, nicht nur Skill-Formulierungsprobleme

Beim Aufbau der storyforge/author-check-Sandbox kam so ein Fund zutage: `author-check` erwartete vier Profil-Felder, die im echten MCP-Server nirgends geschrieben werden konnten (Allowlist fehlte UND die Cache-Projektion beim Lesen ließ sie fallen — zwei getrennte Lecks). Das ist kein Skill-Bug, sondern ein Bug im Produktionscode des Plugins selbst — geht als eigener PR ins Plugin-Repo (git-workflow-Skill, volle Review-Pipeline inkl. echter Test-Suite falls vorhanden), nicht als Teil der Skill-Improvement-Loop. Beim Live-Testen also immer offen bleiben: nicht jeder Fund gehört ins SKILL.md, manche gehören in den MCP-Server-Code.

Auch dieser separate PR folgt der festen Titel-Konvention aus `reference/eval-schema.md` §7 — hier greift aber die dort dokumentierte Ausnahme für nicht-skill-scoped Arbeit (server-seitiger Fix, nicht ein einzelner Skill): `fix(mcp): subject` statt `fix(skill-name): subject`, damit ein MCP-Server-Fix auf den ersten Blick von einem Skill-PR unterscheidbar bleibt.
