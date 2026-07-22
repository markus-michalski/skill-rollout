# Konzept: Plugin-übergreifende Rollout-Automatisierung

Ausgangslage: der storyforge-Rollout (49 Skills) läuft manuell — pro Skill wird Prompt 1/2/3
aus `self-improving-skill-storyforge.md` von Hand angestoßen, Ergebnisse geprüft, PRs gemerged.
Funktioniert, skaliert aber nicht auf mehrere Plugins mit jeweils Dutzenden Skills, wenn dazwischen
immer ein manueller Anstoß nötig ist. Dieses Dokument entwirft einen wiederverwendbaren Runner, der
N Skills eines beliebigen Plugins nacheinander durchläuft — Onboarding, Prompt 1, Prompt 2, Live-Tier
falls zutreffend, PR-Erstellung — ohne dass zwischendurch jemand freigeben muss.

**Wichtig: das hier ist ein Konzept, keine Implementierung.** Nichts davon läuft, bis es gebaut und
freigegeben ist. Kapitel 1-8 beantworten deine 8 Punkte 1:1, danach Architekturentscheidung, Risiken,
übersehene Punkte.

---

## Bereits vorhandene Bausteine (nicht neu bauen)

- `~/projekte/skill-evals/schema.md` — Eval-Schema, jetzt inkl. adversarial-realistic-Grading-Pflicht
  und `loop-state.json`-Companion-Format.
- `~/SeaDrive/.../docs/self_improving_skill/self-improving-skills.md` — allgemeines Playbook (Prompt 1+2 generisch).
- `~/SeaDrive/.../docs/self_improving_skill/self-improving-skill-storyforge.md` — storyforge-konkretes
  Playbook (Prompt 1/2/3 mit echten Pfaden/Fakten).
- `~/SeaDrive/.../docs/self_improving_skill/prompt-self-improving-skill-playbook.md` — der
  generalisierte Onboarding-Meta-Prompt, der aus einem beliebigen `{PLUGIN_REPO_PATH}` ein
  `self-improving-skill-{plugin-name}.md` erzeugt (Investigate → Draft → Self-check, "never guess"-Regel).
  **Kleiner Fund dabei:** die Datei referenziert sich selbst und die storyforge-Datei ohne das
  `self_improving_skill/`-Unterverzeichnis (`docs/self-improving-skill-storyforge.md` statt
  `docs/self_improving_skill/self-improving-skill-storyforge.md`) — Pfad ist inzwischen falsch,
  seit die drei Dateien in den Unterordner verschoben wurden. Muss vor dem ersten Einsatz gefixt
  werden, sonst liest der Onboarding-Prompt beim ersten Lauf die falsche/keine Datei.

Der Onboarding-Meta-Prompt deckt Punkt 8 also schon zu 90% ab. Eine Ergänzung fehlt: er prüft
Branch-Protection-Regeln (Schritt 7), aber nicht, ob ein **PreToolUse-Hook `gh pr create` blockiert**
(wie bei storyforge — `git-workflow` ist dort Pflicht, `gh api` die Ausnahme für die PR-Erstellung).
Das ist repo-spezifisch und muss genauso "nie geraten, immer verifiziert" werden wie der Rest — Test:
einen `gh pr create --dry-run`-artigen Check gibt es nicht, also stattdessen `.claude/settings.json`/
`.claude/hooks/` auf PreToolUse-Hooks für `gh pr create` durchsuchen, und falls nichts gefunden wird,
das explizit als "kein Hook gefunden, gh pr create direkt erlaubt" im generierten Playbook festhalten
(nicht stillschweigend annehmen, dass jedes Repo wie storyforge funktioniert).

---

## 1. Welches Plugin + welche Skills

Parameter: **ein** Plugin-Repo-Pfad pro Lauf (kein Multi-Plugin-Lauf in v1 — siehe Risiken).
Skill-Auswahl kommt aus `~/projekte/skill-evals/{plugin}/STATUS.md`, gescannt top-down.

**Reihenfolge-Korrektur gegenüber storyforge:** dort war "Ordner-Reihenfolge" (alphabetisch) fast
zufällig brauchbar, weil die Skill-Namen ungefähr mit der Pipeline-Reihenfolge übereinstimmen. Das
ist Zufall, kein Prinzip — bei einem anderen Plugin kann alphabetische Ordnung z. B. einen
Nachfolge-Skill vor seiner Abhängigkeit testen. Der Onboarding-Schritt sollte deshalb, falls das
Ziel-Repo eine dokumentierte Workflow-Pipeline hat (wie storyforges CLAUDE.md-Abschnitt "Workflow
Pipeline"), **diese Reihenfolge für STATUS.md übernehmen** statt blind alphabetisch zu sortieren.
Existiert keine dokumentierte Pipeline, bleibt alphabetisch als Fallback.

## 2. Batch-Größe

Parameter `count` (Zahl) oder `max_duration`: realistisch ≤5 tagsüber, ≤10 nachts — `"all"` bleibt
technisch als Option bestehen, wird aber laut Rückmeldung praktisch nie genutzt. Auswahl = die ersten
`count` Zeilen in `STATUS.md`, die noch nicht **vollständig** fertig sind (siehe Punkt 8 unten für die
genaue "fertig"-Definition — das ist komplizierter als nur "beide Häkchen gesetzt").

## 3. Umgang mit Log-Kommentaren / Eval-Design-Fragen (dein offener Punkt)

Braucht eine feste, deterministische Regel, weil niemand mehr nachfragt. Vorschlag — angewendet direkt
nach jedem Prompt-2-Lauf, bevor es zu Live-Tier/PR geht:

**a) Assertion als "eval-design candidate" geflaggt** (2 gescheiterte gezielte Fixversuche):
- Prüfen: ist es dasselbe Muster wie die schon bekannten Fälle (narrations-abhängig — "reasoning
  explicitly notes/cites X" — oder beweisbar im Widerspruch zur eigenen Terseness-Vorgabe der Skill)?
  → **automatisch korrigieren** (entfernen/umformulieren), Begründung ins Log, committen. Genau das
  Muster aus `backfill-style-principles`.
- Sonst (echt unklar, nicht selbst auflösbar): **nicht anfassen.** Assertion bleibt rot, wird explizit
  als `NEEDS-HUMAN-REVIEW` im Log UND in STATUS.md markiert (neuer State, siehe Punkt 8). Blockiert
  NICHT den weiteren Lauf — nächster Skill startet trotzdem.

**b) "Residual note"** (im Log erwähnt, aber von keiner Assertion erfasst — wie die zwei
Stale-References bei book-conceptualizer):
- Im Scope des gerade bearbeiteten Skills/Schritts → in den laufenden Fix mit reinnehmen.
- Außerhalb des Scope → sofort GitHub-Issue (siehe Punkt 4/5 unten, gilt hier genauso, nicht nur
  bei Prompt 3 wie bisher dokumentiert — book-conceptualizer hat gezeigt, dass das auch im
  simulierten Tier passiert).

**c) Am Ende jedes Skills:** eine kurze Zusammenfassung in einen **einzigen** Batch-weiten Digest
schreiben (nicht 10 verstreute Loop-Logs, die du einzeln aufmachen musst) — Score, PR-Link, Issues,
offene `NEEDS-HUMAN-REVIEW`-Punkte. Das ist die einzige Datei, die du nach einem Batch wirklich lesen
musst.

## 4. git-workflow Code-Review-Findings — alle Schweregrade autofixen

`git-workflow`s Code-Reviewer klassifiziert nach `critical/high/medium/low` (geprüft in der echten
Skill-Datei, keine andere Skala vorhanden — falls mit "C - L" etwas anderes gemeint war, bitte
korrigieren). Regel: **jeder gefundene Finding, unabhängig vom Schweregrad, wird ohne Rückfrage
gefixt**, exakt wie es heute Nacht bei backfill-style-principles/book-conceptualizer schon
organisch passiert ist (doppelter Report-Header, Ordering-Bug, etc.).

**Harte Grenze, die davon NICHT betroffen ist:** der finale Merge. PRs werden erstellt, Checks
laufen, aber **niemals selbst gemerged** — das bleibt bei dir, unabhängig davon, wie autonom der
Rest läuft. Das ist keine Einschränkung der Automatisierung, sondern eine bewusste, unveränderte
Grenze (Branch Protection + deine eigene Regel "PR-Freigabe nach manuellem Test").

## 5. git-workflow-Schritte auto-approved

Alle Checkpoints (Code-Review+Breaking-Change, Test, Commit-Message, Branch/Push, PR-Erstellung)
laufen ohne Rückfrage durch — exakt das Muster, das schon in `backfill-promises`' `state.json` als
`"checkpoint-1-autoapproved"` mit der Begründung "Autonomous overnight run... explicit user
pre-authorization" dokumentiert ist. Das wird jetzt zur Standard-Konfiguration dieses Runners,
nicht mehr Ad-hoc-Begründung pro Nacht. `gh pr create` bleibt für Repos mit Hook blockiert →
`gh api`-Workaround als sanktionierter letzter Schritt (wie bisher).

## 6. Sequenziell, nicht parallel

Zwei unterschiedliche Ebenen, die man nicht verwechseln sollte:

- **Skill-zu-Skill:** strikt sequenziell, ein Skill komplett fertig (inkl. PR erstellt) bevor der
  nächste startet. Technisch wichtig: das ist **nicht** derselbe Mechanismus wie beim `pipeline()`-
  Primitive des Workflow-Tools — `pipeline()` ist absichtlich für **Überlappung** gebaut (Skill B
  startet Stage 1, während Skill A noch in Stage 3 ist), also genau das Gegenteil von dem, was hier
  gebraucht wird. Für die Skill-Ebene muss eine simple sequenzielle Schleife her (ein `for`-Loop mit
  `await` pro Skill), keine `pipeline()`.
- **Live-Tier-Cases innerhalb eines Skills:** ebenfalls strikt sequenziell — das steht schon so in
  Prompt 3 ("never in parallel — they mutate shared sandbox state") und bleibt so.
- **Grading-Batches innerhalb der simulierten Loop:** dürfen weiterhin parallel laufen (wie die
  ganze Nacht über praktiziert, "4 Batches parallel") — das ist reines Lesen/Bewerten simulierter
  Transkripte ohne echten Seiteneffekt, also unproblematisch. Nicht aus falscher Vorsicht auch das
  noch sequenziell machen.

## 7. Volle Autonomie für N Skills — mit einem schmalen Sicherheitsventil

Grundsätzlich: kein Zutun nötig für die Dauer **eines** Batches (realistisch ≤5 tagsüber, ≤10
nachts) — danach stoppt der Runner sauber und wartet auf den nächsten manuellen Anstoß, siehe die
Klarstellung unter "Zwei Betriebsarten": kein automatisches Weiterlaufen in einen Folge-Batch.

Zusätzlich, innerhalb eines Batches: Ausnahmen, bei denen trotzdem gestoppt
werden sollte (schon in Prompt 3 für Live-Cases vorgesehen, hier auf den ganzen Runner ausgeweitet):

- Ambiguität, ob ein Live-Case bei falscher Behandlung echte (Nicht-Sandbox-)Daten anfassen würde.
- Ein Finding, das wie ein Sicherheits-/Credential-/Datenverlust-Risiko aussieht.
- Jede destruktive Git-Operation außerhalb des sanktionierten Musters (force-push, History-Rewrite).
- Ein Fund, der offensichtlich zu einem **anderen** Repo/Plugin gehört, das der Runner gar nicht
  bearbeitet (dann Issue im richtigen Repo, aber nicht versuchen, dort auch noch zu pushen).

**Strukturelle Erweiterung (2026-07-20, ausgelöst durch die life-hub-Frage — betrifft genauso
project-hub und vermutlich vidcraft, korrigiert nachdem sich die erste Fassung als falsch
aufgehängt herausstellte):** Das oben ist eine Laufzeit-Heuristik ("wenn dir während des Laufs
etwas verdächtig vorkommt, stoppe"). Reicht für Plugins mit MCP-Server allein nicht.

Erste Fassung dieser Regel unterschied "erfunden/wegwerfbar (storyforge)" vs. "echte Daten
(life-hub)" — das war falsch: storyforges eigene geteilte Ablage (`~/.storyforge/authors/`) enthält
einen echten, nicht-sandbox Autor (`ethan-cole`) direkt neben `zz-sandbox-author`, und die
book-projects-Historie zeigt echte, im Zeitverlauf entfernte Buchprojekte. storyforge ist nicht
sicher, *weil* Bücher erfunden sind — ein zerstörtes reales Kapitel, an dem der User tatsächlich
schreibt, ist genauso ein echter Verlust wie ein zerstörter echter Rechtsfall. storyforge ist
sicher, *weil* schon konkrete Engineering-Arbeit gemacht wurde: die `zz-sandbox-`-Namenskonvention
als eindeutiges Unterscheidungsmerkmal, pfad-gescopte Resets statt ganzer Verzeichnisse, die
Trennung isolierte-Dateien-vs-geteilte-DB mit je eigener Reset-Mechanik — dokumentiert in den
`sandbox.md`-Dateien dieses Rollouts.

Die richtige Frage ist also nicht "ist die Domäne fiktiv", sondern: **existiert für dieses Plugin
schon eine verifizierte, getestete Isolations-Strategie für seine geteilte Ablage?** Das ist jetzt
so im Onboarding-Meta-Prompt verankert (`prompt-self-improving-skill-playbook.md`, Schritt 3a):
Default ist "keine Strategie vorhanden, Prompt 3 gesperrt" für JEDES Plugin, unabhängig davon, wie
harmlos seine Domäne klingt — storyforge ist nur deshalb frei, weil die Design-Arbeit hier bereits
gemacht und verifiziert wurde, nicht wegen seines Sujets. Ein Plugin gilt nur dann als entsperrt,
wenn das Onboarding eine konkrete, dokumentierte Isolations-Strategie vorfindet, nie durch bloße
Einschätzung des Themas. Diese Sperre gilt zusätzlich zu, nicht statt der Laufzeit-Heuristik oben.

Das sind die einzigen Stopp-Bedingungen — alles andere (Punkt 3's `NEEDS-HUMAN-REVIEW`-Fälle
eingeschlossen) blockiert den Lauf nicht, sondern wird nur markiert.

## 8. self_improving_skill-Ordner ist Pflichtgrundlage

Für ein neues Plugin läuft der Runner immer erst durch den Onboarding-Meta-Prompt (siehe oben),
bevor überhaupt ein Skill drankommt. Für storyforge (schon onboarded) wird dieser Schritt übersprungen.

**Präzisierung der "fertig"-Definition für STATUS.md** (fehlt bisher, wird aber für die
Batch-Auswahl in Punkt 2 gebraucht): drei mögliche Zustände pro Spalte, nicht zwei —

| Symbol | Bedeutung |
|---|---|
| ⬜ | noch nicht versucht |
| ✅ | durchgelaufen (Score + evtl. PR-Link in der Notes-Spalte) |
| 🟦 N/A | bewusst übersprungen (z. B. Live-Tier bei einem Skill ohne MCP-Aufrufe — `configure`/`help`/`setup` waren im storyforge-Tracker schon als "likely no MCP surface" vorgemerkt, aber nie formal auf N/A gesetzt) |

Ohne den dritten Zustand bleibt so ein Skill für immer ⬜ in der Live-Spalte und der Runner hält ihn
fälschlich für "noch zu tun" — Punkt 2's Batch-Auswahl müsste sonst ewig auf Skills warten, die nie
fertig werden können. Zusätzlich: `NEEDS-HUMAN-REVIEW`-Marker aus Punkt 3 als viertes Symbol (🟨) in
der Notes-Spalte, nicht als eigene Spalte — verhindert, dass sowas im Digest untergeht.

---

## Architekturentscheidung: Workflow-Tool statt (nur) Agent-Ketten

Heute Nacht direkt beobachtet: der Cluster-B/C-Agent hat mehrfach "fertig" gemeldet, obwohl er nur
auf eigene Hintergrund-Subagenten wartete, die ihn nicht zuverlässig aufgeweckt haben — musste
manuell per SendMessage wieder angestoßen werden. Für einen Runner, der über Stunden ohne Aufsicht
laufen soll, ist das ein Zuverlässigkeitsrisiko, kein Detail.

**Empfehlung:** als gespeichertes Workflow-Skript bauen, nicht als lose Kette von `Agent`-Aufrufen.
**Git-Pflicht (bestätigt):** Source of truth liegt in `mm-skills/skill-rollout/workflow.js` (git,
neben der Plugin-Skill-Fassade), `~/.claude/workflows/skill-rollout.js` ist nur die deployte Kopie —
gleiches Source-vs-Deploy-Muster wie bei storyforges drei Skill-Kopien, inkl. derselben Pflicht, nach
jeder Änderung zu syncen (der `~/.claude/workflows/`-Ordner existiert noch nicht, muss angelegt werden).
Begründung:
- Workflows blockieren korrekt auf `await agent(...)` — genau die Klasse von Bug, die heute Nacht
  auftrat, entfällt strukturell.
- `resumeFromRunId` erlaubt einen Wiedereinstieg nach Unterbrechung, ohne von vorn anzufangen.
- Eingebautes Budget-Tracking (`budget.total`/`budget.remaining()`), falls du Tokenkosten pro Batch
  begrenzen willst (siehe Risiken).
- Für die Skill-Ebene wird trotzdem **kein** `pipeline()`/`parallel()` verwendet (siehe Punkt 6) —
  der Nutzen des Tools kommt hier aus Zuverlässigkeit/Resumability, nicht aus Parallelität.

Das Aufrufen eines gespeicherten Workflows per Namen ("führe skill-rollout für storyforge aus, 5
Skills") ist selbst die Opt-in-Handlung, die das Workflow-Tool laut seinen eigenen Regeln braucht —
kein separates Freischalten nötig, du triggerst es ja jedes Mal explizit.

**Realistische Größenordnung (Korrektur nach Rückmeldung):** kein 49-Skills-Marathon, sondern kleine
Batches — tagsüber ≤5 (Markus ist ja greifbar), nachts ≤10. Nach JEDEM Batch werden die entstandenen
Issues/PRs von Hand abgearbeitet und gemerged, **bevor** der nächste Batch startet. Das ändert einiges
gegenüber der ursprünglichen Annahme:

1. **Fixed-window-Lauf** (Hauptbetriebsart, unverändert): `count` Skills fertig ODER `max_duration`
   erreicht, je nachdem was zuerst eintritt — realistisch `count: 5` tagsüber, `count: 10` bzw.
   `max_duration: ~8-10h` nachts. Läuft als **ein** durchgehender Workflow-Aufruf, damit die
   Skill-zu-Skill-Sequenzialität (Punkt 6) über die ganze Dauer hinweg garantiert bleibt.
2. **Kein automatisches Batch-Chaining.** Der Runner stoppt nach dem Batch sauber mit Digest — er
   startet NICHT von selbst den nächsten Batch. Das ist gewollt: der eigentliche Workflow ist
   Batch → Digest → Markus arbeitet Issues/PRs ab und merged → erst dann nächster Batch, manuell
   angestoßen. Damit erledigt sich auch Risiko 5 (PR-Rückstau) von selbst — nie mehr als ein
   Batch's PRs gleichzeitig offen, by design.
3. **Cron: nice-to-have, nicht Teil des Kernkonzepts.** Bestätigt niedrige Priorität — bleibt als
   Option dokumentiert (falls doch mal ein Batch über Nacht durchlaufen UND direkt in den nächsten
   übergehen soll, ohne dass am nächsten Morgen erst gemerged wird), aber wird nicht als Teil der
   ersten Implementierung gebaut.

**Plugin-Skill-Fassade** (`/skill-rollout:run {plugin} {count-or-duration}`) — bestätigt gewünscht,
gehört unter `mm-skills` (privates Skill-Repo, kein öffentliches Plugin). Bleibt dünn: ruft intern
nur den Workflow auf, trägt selbst keine Logik.

---

## Risiken

1. **Kosten/Token-Verbrauch.** Der book-conceptualizer-Re-Grade allein hat heute Nacht 339k Tokens
   für **einen** Skill gebraucht (adversarial-realistic Grading + 6 Iterationen + Code-Review). Auf
   Dutzende Skills über mehrere Plugins hochgerechnet, unbeaufsichtigt, ist das ein echter
   Kostenfaktor ohne Frühwarnung. Empfehlung: Budget-Cap pro Batch (Workflow-Tool bringt das
   Primitiv mit), plus Kosten-Summe im Batch-Digest.
2. **Kein Cross-Skill-Circuit-Breaker.** Die 2-Iterationen-Stall-Regel schützt pro Skill, aber nicht
   den Batch als Ganzes — wenn z. B. der Grader selbst systematisch kaputt ist (Modellfehler,
   falsches Sandbox-Setup), könnte der Runner durch alle N Skills laufen und überall dieselbe
   sinnlose Fehlerklasse produzieren, bevor es jemand merkt. Empfehlung: wenn 3 Skills in Folge
   praktisch keine Verbesserung zeigen oder auf echte Fehler (nicht nur Score-Stall) laufen, ganzen
   Batch anhalten statt durchzuziehen.
3. **Eval-Verwässerung ohne Aufsicht.** Punkt 3's Auto-Fix-Regel für "eval-design candidate"
   Assertions ist notwendig für volle Autonomie, aber jede automatische Eval-Lockerung ist per
   Definition ein Punkt, an dem Testabdeckung leiser werden kann. Über Dutzende Skills hinweg könnte
   sich ein Muster ergeben, das niemand bemerkt, weil jede einzelne Änderung für sich plausibel
   aussieht. Empfehlung: harte Obergrenze, wie viele Eval-Änderungen ein Batch ohne Review machen
   darf, plus alle Eval-Änderungen prominent im Digest, nicht nur im jeweiligen Loop-Log.
4. **Sandbox-Reset-Fehler ohne menschliche Kontrolle.** Die pfad-gescopten Reset-Regeln (nie ganze
   Verzeichnisse restoren) waren bisher jedes Mal von einem Menschen (oder zumindest einer
   aufmerksamen Session) nachgelesen, bevor sie ausgeführt wurden. Ein Runner, der Live-Tests für
   viele Skills am Stück durchzieht, hat mehr Gelegenheiten für einen Scoping-Fehler, der eine andere
   Skill-Fixture stillschweigend zerstört — und niemand schaut zeitnah drauf. Empfehlung: vor/nach
   jedem Live-Tier-Lauf ein Manifest der Sandbox-Dateien snapshotten und diffen; Batch anhalten, wenn
   sich außerhalb des erwarteten Scopes etwas geändert hat.
5. **PR-Rückstau — durch dein eigenes Betriebsmodell bereits entschärft.** Ursprünglich als offenes
   Risiko eingeschätzt, ist aber durch die Klarstellung oben gelöst: kein automatisches
   Batch-Chaining heißt, es sind nie mehr als ein Batch's PRs gleichzeitig offen (max. ~5-10 bei
   deiner realistischen Batch-Größe), weil der nächste Batch erst startet, nachdem du den vorherigen
   abgearbeitet hast. `gh pr list` als fester Bestandteil deiner Morgen-/Feierabendroutine reicht.
6. **Andere Plugins haben andere Repo-Regeln.** storyforges Hook (blockiert `gh pr create`), CLA und
   Branch Protection sind storyforge-spezifisch, nicht universell. Der Onboarding-Meta-Prompt prüft
   das zwar grundsätzlich pro Ziel-Repo (nie raten), aber die "nie raten"-Regel muss explizit auch
   auf den PreToolUse-Hook ausgeweitet werden (siehe oben) — sonst wird beim ersten fremden Plugin
   ohne Hook trotzdem der `gh api`-Workaround verwendet, wo `gh pr create` direkt erlaubt gewesen
   wäre, oder umgekehrt schlimmer: bei einem Repo MIT Hook wird versucht, ihn zu umgehen.

## Übersehene Punkte / Verbesserungsvorschläge

- **"Fertig"-Zustand für Live-Tier fehlt** (oben unter Punkt 8 gelöst) — ohne den dritten Zustand
  (N/A) bleibt die Batch-Auswahl in Punkt 2 kaputt für MCP-freie Skills.
- **Mehrfach-Plugin-Betrieb ist kein Teil von v1.** Du hast "alle meine Plugins" als Motivation
  genannt, aber ein Lauf pro Plugin macht die erste Version deutlich einfacher und sicherer zu
  bauen. Cross-Plugin-Scheduling (nacheinander mehrere Plugins per Cron durchlaufen) ist eine
  natürliche v2-Erweiterung, sobald v1 an storyforge und einem zweiten Plugin (claude-ai-music-skills
  bietet sich an, da schon erwähnt) sich bewährt hat.
- **Skills mit echtem menschlichem Urteilsvermögen** (z. B. `memoir-ethics-checker`,
  Consent-Gates) sollten nicht pauschal ausgeschlossen werden — ihre *Entscheidungslogik* (fragt sie
  korrekt nach, flaggt sie korrekt?) ist genauso testbar wie bei jedem anderen Skill. Aber der
  Digest sollte diese Kategorie separat kennzeichnen, damit du beim Review bewusst genauer hinschaust
  als bei z. B. einem reinen Formatierungs-Skill.
- **Ein einziger Digest statt N Loop-Logs** (schon unter Punkt 3c erwähnt, hier nochmal als
  eigenständige Verbesserung): das war explizit dein eigener Wunsch bei `loop-state.json` ("Kurzüberblick
  ohne den riesigen Text lesen zu müssen") — sollte konsequent auf Batch-Ebene weitergedacht werden,
  nicht nur pro Skill.
- **Kein Mechanismus, der einen kaputten `evals.json`-Bau (Prompt 1) selbst erkennt.** Falls Prompt 1
  für einen neuen Skill fehlerhafte oder zu wenige Cases erzeugt, merkt das aktuell nur ein Mensch
  beim Draufschauen (wie bei backfill-style-principles, wo du selbst zwei Judgment-Calls geprüft
  hast). Für volle Autonomie fehlt eine Art Sanity-Check direkt nach Prompt 1 (z. B.: Anzahl Cases
  plausibel zur Anzahl der Regeln im SKILL.md? Jede `Do NOT`-Regel hat mindestens einen Case?)
  bevor in die Loop gegangen wird.

## Nächste Schritte (falls du das umsetzen willst)

1. Pfad-Fix im Onboarding-Meta-Prompt (`self_improving_skill/`-Unterordner ergänzen).
2. Onboarding-Meta-Prompt um PreToolUse-Hook-Check erweitern.
3. STATUS.md-Format auf den dritten Zustand (N/A) + `NEEDS-HUMAN-REVIEW`-Marker erweitern
   (rückwirkend für storyforge optional, verbindlich für jedes neu onboardete Plugin).
4. **storyforge STATUS.md-Reihenfolge auf Pipeline-Order umstellen** (bisher alphabetisch, siehe
   Punkt 1) — erledigt direkt im Anschluss an dieses Konzept, siehe unten.
5. `mm-skills/skill-rollout/` anlegen: `workflow.js` (Source of truth, git) + Plugin-Skill-Fassade
   `/skill-rollout:run {plugin} {count-or-duration}`; `~/.claude/workflows/skill-rollout.js` als
   deployte Kopie. Sequenzielle Skill-Schleife, kein `pipeline()` auf Skill-Ebene, Stop-Bedingung
   `count` ODER `max_duration` (je nachdem was zuerst eintritt).
6. Erster Testlauf mit `count: 1-2` / kurzem `max_duration` gegen storyforge (schon onboarded, kein
   Onboarding-Pfad nötig) — bewusst klein, um die Runner-Mechanik selbst zu verifizieren, bevor ein
   großer Batch, ein langes Zeitfenster, oder ein zweites Plugin drankommt.
