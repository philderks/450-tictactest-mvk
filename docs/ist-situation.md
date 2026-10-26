# Ist-Situation gegenüber den Anforderungen

**Stand:** 2026-10-26, Commit [`fbb7102`](https://github.com/philderks/450-tictactest-mvk/commit/fbb7102). Diese Bestandsaufnahme ersetzt die Momentaufnahme vom 09.09.2026. Sie trennt die im Repo belegten Ergebnisse von offenen oder extern zu prüfenden Anforderungen. Testfälle stehen in [tests.md](tests.md), Strategie und E2E-Erwartung/Ist in [testkonzept.md](testkonzept.md).

Legende: ✅ nachweisbar erfüllt · ⚠️ teilweise erfüllt/offen · ❓ nicht verifiziert · – organisatorisch

| # | Kriterium | Stand und Beleg |
|---|---|---|
| 1 | AssertJ, aussagekräftige Assertions und Hilfsstrukturen | ⚠️ AssertJ und benannte Fixtures vorhanden; mehrere `isTrue()`/`isFalse()`-Assertions bleiben (siehe [`TicTacToeMainTest`](../src/test/java/ch/bbw/m450/tictactoe/TicTacToeMainTest.java) und [`PerfectPlayerTest`](../src/test/java/ch/bbw/m450/tictactoe/players/PerfectPlayerTest.java)). Ein `toBoard(String)`-Helper fehlt. |
| 2 | Parametrisierte Tests, wenig Duplikation | ⚠️ Acht Gewinnlinien in einer `@MethodSource` sowie X/O über `@EnumSource` parametrisiert; einzelne Zeilen-/Diagonalen-Tests überschneiden sich mit der `@MethodSource`. |
| 3 | JaCoCo-Reports und durchgesetzte 90 % **Branch** Coverage | ✅ [`build.gradle`](../build.gradle) erzwingt `counter = 'BRANCH'`, `minimum = 0.90` über `check`; zuletzt **105/110 = 95,45 %**. HTML, XML und CSV werden erzeugt. |
| 4 | Standard-Ein-/Ausgabe mit JUnit Pioneer | ✅ [`HumanPlayerTest`](../src/test/java/ch/bbw/m450/tictactoe/players/HumanPlayerTest.java) prüft Eingabe/Aufforderungen; acht [`TicTacToeE2ETest`](../src/e2eTest/java/ch/bbw/m450/tictactoe/TicTacToeE2ETest.java)-Fälle spielen ganze Partien über `main()` inkl. Fehler- und EOF-Fällen mit Timeout. |
| 5 | CI und Test-/Coverage-/Mutationsberichte | ✅ [CI](../.github/workflows/ci.yml) testet Pushes auf Branches und PRs nach `main`; JUnit (Unit + E2E), JaCoCo und PIT werden hochgeladen. [Letzter geprüfter Lauf](https://github.com/philderks/450-tictactest-mvk/actions/runs/40367789784) erfolgreich. **Aber:** Der GitHub-Ruleset verlangt diese Checks nicht als Merge-Bedingung (siehe unten). |
| 6 | Perfekt spielender Player | ✅ [`PerfectPlayer`](../src/main/java/ch/bbw/m450/tictactoe/players/PerfectPlayer.java) mit Minimax; Tests prüfen unmittelbare Siege/Blocks, vollständige Gegnerzug-Suche und Unentschieden zweier perfekter Spieler. |
| 7 | Zusätzliches Testframework mit automatisiertem Beispiel | ✅ jqwik-Property-Test in [`PerfectPlayerPropertyTest`](../src/test/java/ch/bbw/m450/tictactoe/players/PerfectPlayerPropertyTest.java) mit `tries = 100`; als ein JUnit-Testergebnis gezählt. |
| 8 | Automatisches Mutation Testing | ✅ [PIT](../build.gradle) läuft in CI und erzeugt XML/HTML; zuletzt **71/87 Mutationen getötet (82 %)**. ⚠️ Kein `mutationThreshold`; E2E-Tests im getrennten Source-Set fliessen nicht standardmässig in PIT ein. |
| 9 | SonarLint-Warnungen, einheitlicher Stil und aktuelle Abhängigkeiten | ❓ Kein SonarLint-/Sonar-Analyseergebnis vorhanden; grüne Tests belegen **nicht** null Warnungen. Stile und aktuelle Versionen sind nicht vollständig verifiziert. |
| 10 | Pünktliche Abgabe / private GitHub-Abgabe | – Abgabefrist nicht aus dem Code verifizierbar. Das Repo ist **öffentlich**; die private-repo-Vorgabe des Handouts ist formal nicht erfüllt. Der Eigentümer akzeptiert Öffentlichkeit, sofern keine sensiblen Inhalte gepusht werden. |

## Aktuelle Testzahlen und Geltungsbereich

Beim geprüften lokalen Java-25-Lauf: **27** reguläre JUnit/jqwik-Testaufrufe in sechs Klassen und **8** separate E2E-Testaufrufe, alle grün. JaCoCo misst 105 abgedeckte und 5 fehlende Branches (**95,45 %**) nur für `test`; PIT meldet 71 KILLED, 13 SURVIVED und 3 NO_COVERAGE aus 87 Mutationen (**82 %** gerundet). Diese Werte sind ein Messstand, keine unveränderlichen Ziele; nach Codeänderungen neu ermitteln. Das Coverage-Diagramm auf Pages visualisiert **Instruction** Coverage, obwohl die eingezeichnete 90-%-Linie als Quality Gate bezeichnet ist; das Build-Gate prüft dagegen **Branch** Coverage.

`./gradlew test` führt die regulären Tests aus; `./gradlew e2eTest` die vollständigen Konsolenfälle; `./gradlew check` führt beide und die Coverage-Prüfung aus; `./gradlew pitest` läuft separat. Die Tests verwenden JDK **25**, den Gradle-Wrapper, JUnit Jupiter 6.1.3, AssertJ 3.27.7, Pioneer 2.3.0, jqwik 1.10.2 und PIT 1.30.1 (Versionen nach [`build.gradle`](../build.gradle), **nicht** als «aktuellste» behauptet).

## Offene Risiken und nächste Verbesserungen

1. **Schutz von `main`:** Der aktive Ruleset fordert PRs, hat aber keine verpflichtenden CI-Checks, null erforderliche Reviews und einen Bypass für eine Repository-Rolle. Ein direkter Push auf `main` wurde tatsächlich akzeptiert. Erforderliche Checks und Bypass/Review-Regeln erst nach Entscheidung über den Solo-Workflow ändern; grüne CI allein schützt `main` nicht.
2. **Testqualität:** Aussagekräftigere AssertJ-Vergleiche statt bloss `isTrue()`/`isFalse()`, ein lesbarer Board-Helper, weniger duplizierte Gewinnfall-Tests und zusätzliche Ausgabefälle sind mögliche Verbesserungen. Einen 90-%-PIT-Gate nicht ohne neue Tests setzen: der gemessene Wert ist 82 %.
3. **Messung/Kommunikation:** Das Coverage-Diagramm (Instruction) und das Branch-Gate unterscheiden sich; Beschriftung/Gate-Linie angleichen. SonarLint und die jeweils neuesten Dependency-Versionen separat prüfen.
4. **Release-Konsistenz:** [`build.gradle`](../build.gradle) steht weiterhin auf `1.0.1`, obwohl der aktuelle `main` neue Funktionalität und Eingabefixes enthält. Das lokal gebaute JAR ist nicht identisch mit dem früher veröffentlichten v1.0.1-Artefakt; vor dem nächsten Release Version, Changelog und Artefakt prüfen. Die Änderungen stehen unter `[Unreleased]` im [Changelog](../CHANGELOG.md).

Die alte Prioritätenliste vom 09.09. (JaCoCo/PIT/PerfectPlayer/Pioneer fehlten) ist damit überholt; sie ist nicht länger eine aktuelle Aufgabenliste.
