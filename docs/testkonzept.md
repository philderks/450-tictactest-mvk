# Testkonzept

Dieses Dokument beschreibt die Teststrategie für TicTacTest: Testziele, Stufen, Werkzeuge, Grenzen und Erfolgskriterien. Aktuelle Einzeltests und Messwerte sind in [tests.md](tests.md) und [ist-situation.md](ist-situation.md) dokumentiert.

## Ziel

Die Kernlogik des Spiels (Gewinnerkennung und Spielablauf) soll zuverlässig durch automatisierte Tests abgesichert sein, sodass Änderungen (z.B. neue Spieler-Strategien) mit Vertrauen vorgenommen werden können. Die CI-Pipeline ([.github/workflows/ci.yml](../.github/workflows/ci.yml)) führt die Tests bei Pushes auf Branches und bei Pull Requests nach `main` aus.

| Testziel | Nachweis / Erfolgskriterium |
|---|---|
| TZ-01 Gewinnlogik und Regeln | Alle acht Gewinnlinien, Negativfälle, Unentschieden und ungültige Spielerzüge in Unit-/Integrationstests. |
| TZ-02 Strategien | Greedy-Verhalten im Spiel, PerfectPlayer (gewinnt/blockiert/verliert nie), sowie legale Züge und unverändertes Brett mit jqwik. |
| TZ-03 Konsolenverhalten | Vollständiger X-Sieg, O-Sieg und Draw via `main()`, ungültige/böswillige Eingaben und EOF mit zeitbegrenzten E2E-Tests. |
| TZ-04 Automatisierte Qualitätskontrolle | Unit- und E2E-Tests grün, mindestens 90 % **Branch Coverage** im JaCoCo-Gate; PIT-Report vorhanden (derzeit kein PIT-Gate). |
| TZ-05 Nachvollziehbarkeit | JUnit-/E2E-, JaCoCo- und PIT-Reports im CI-Lauf; Soll/Ist der E2E-Fälle dokumentiert. |

## Werkzeuge

- **JUnit Jupiter 6.1.3** als Test-Framework, inkl. `@ParameterizedTest`/`@MethodSource`; **AssertJ 3.27.7** für Assertions.
- **JUnit Pioneer 2.3.0** für `@StdIo` und **jqwik 1.10.2** für Property-Tests.
- **JaCoCo 0.8.15** erzeugt HTML/XML/CSV und erzwingt bei `check` mindestens 90 % Branch Coverage der regulären `test`-Suite; **PIT 1.30.1** erstellt einen Mutationsbericht ohne Mindestwert.
- Ausführung mit dem Gradle-Wrapper und **Java 25**: `./gradlew test` für Unit-/Integrationstests (inkl. jqwik); `./gradlew e2eTest` für Konsolen-E2E-Tests; `./gradlew check` führt beide und das JaCoCo-Gate aus; `./gradlew pitest` läuft separat. Die E2E-Source-Set-Tests erhöhen nicht automatisch die JaCoCo-/PIT-Messwerte der regulären Suite.

## Aufbau / Teststufen

Die Teststufen sind Unit-Tests für Logik und Strategien, Integrationstests für `play(...)` und separate E2E-Tests über `main(...)`.

### 1. Unit-Tests für reine Logik

Betrifft `TicTacToeMain.isWin(...)`: eine reine, zustandslose Funktion ohne Seiteneffekte – ideal für isolierte Unit-Tests.

- Alle 8 Gewinnlinien (3 Reihen, 3 Spalten, 2 Diagonalen) werden parametrisiert abgedeckt (`isWin_detectsAllWinningLines`).
- Negativfälle: volles Brett ohne Gewinner (Unentschieden-Board), falsche Farbe gewinnt nicht.
- Fixtures (benannte, wiederverwendbare Testbretter) statt Boards inline in jeder Methode aufzubauen, für Lesbarkeit.

### 2. Unit-Tests für Spieler-Strategien

Betrifft Implementierungen von `TicTacToePlayer`: `GreedyPlayer` wird im vollständigen Spiel sowie beim vollen Brett geprüft; `PerfectPlayer` wird auf sofortigen Sieg, Block, nie verlorene Spiele, legales Feld und unverändertes Eingabebrett geprüft. Der jqwik-Property-Test erzeugt 100 Zugfolgen für erreichbare, noch nicht abgeschlossene Stellungen. Die umgekehrte Farbauswahl (`Stone.opponent()`) hat zwei eigene Tests.

### 3. Integrationstests für den Spielablauf

Betrifft `TicTacToeMain.play(...)`: orchestriert zwei Spieler über mehrere Runden und kombiniert Spielerlogik + Gewinnerkennung. Hier wird das Zusammenspiel getestet, nicht mehr die Einzelteile isoliert.

Abgedeckt:
- Deterministischer Spielverlauf zwischen zwei `GreedyPlayer`n endet mit erwartetem Sieger.
- Guard-Klausel: dieselbe Spielerinstanz für beide Seiten wirft `IllegalArgumentException`.

Abgedeckt sind auch ein Unentschieden (`play()` liefert `null`) und ein fehlerhafter Spielerzug (`IllegalStateException`).

### 4. End-to-End-Tests für den Konsoleneinstieg

[`TicTacToeE2ETest`](../src/e2eTest/java/ch/bbw/m450/tictactoe/TicTacToeE2ETest.java) ruft mit JUnit Pioneer `@StdIo` tatsächlich `main()` auf: Eingabe über `System.in`, Ausgabe bis zum Spielresultat über `StdOut`. Der Computer (`GreedyPlayer`) spielt immer das erste freie Feld. Jeder Test hat ein JUnit-Timeout von 5 Sekunden in einem separaten Thread; dadurch kann ein hängender Build abgebrochen werden. Die Suite läuft isoliert über `./gradlew e2eTest`, als Teil von `check` und explizit in [CI](../.github/workflows/ci.yml) mit eigenem JUnit-Report-Artefakt. Testumgebung: Java 25, Gradle-Wrapper und JUnit 6/Pioneer 2.3.0.

| Testziel / Eingabe des Menschen (X) | Erwartetes Verhalten | Tatsächlich nach dem Fix (`e2eTest`) |
|---|---|---|
| E2E-01 `0,3,6` | X gewinnt; Eingaben bis zum Resultat verarbeitet | Drei X-Aufforderungen, `winner is: CROSS` |
| E2E-02 `3,4,6` | O gewinnt | Drei X-Aufforderungen, `winner is: CIRCLE` |
| E2E-03 `1,3,4,6,8` | Volles Spiel endet unentschieden | Fünf X-Aufforderungen, `it's a draw!` |
| E2E-04 `abc,0,3,6` | Text wird zurückgewiesen; nach neuer Eingabe geht das Spiel weiter | `Invalid input`, anschliessend X-Sieg |
| E2E-05 `99,0,0,3,6` | Zahl ausserhalb des Brettes und belegtes Feld werden zurückgewiesen | Zwei Rückfragen, anschliessend X-Sieg |
| E2E-06 Steuerzeichen, `-1`, überlaufende Zahl, `0,3,6` | Böswillige/fehlerhafte Eingaben verursachen weder ungefangene Ausnahme noch Endlosschleife | Drei Zurückweisungen, anschliessend X-Sieg innerhalb von 5 s |
| E2E-07 `abc`, Leerzeile, Leerzeichen, dann EOF | Endliche Folge ungültiger Eingaben darf nach EOF nicht endlos weiterlaufen | Drei Zurückweisungen, `Input ended. Game stopped.` innerhalb von 5 s |
| E2E-08 EOF vor dem ersten Zug | Kein Hängen oder Stacktrace ohne Eingabe | `Input ended. Game stopped.` innerhalb von 5 s |

**Gefundene Fehler und test-first-Behebung:** Zunächst wurde der Fall E2E-04 geschrieben und **vor der Auslagerung in den eigenen Source-Set** gezielt über `./gradlew test --tests '*TicTacToeE2ETest.invalidTextIsRejectedAndPlayerCanFinishGame'` ausgeführt: **rot** mit `NumberFormatException` in `HumanPlayer.play`. Erst danach wurde das Einlesen so geändert, dass Text zurückgewiesen und nochmals gefragt wird: derselbe Test **grün**. Analog war E2E-05 vor seiner Behebung rot (`IllegalStateException` bei `99`); ein EOF-Reproduktionstest war vor EOF-Behandlung rot (`NoSuchElementException`). Die aktuelle Suite läuft über `./gradlew e2eTest`. Die Spiellogik prüft weiterhin ungültige Züge anderer Spieler und kann dort `IllegalStateException` werfen. Ein unbegrenzt langer *laufender* Eingabestrom ist kein automatischer Abbruchgrund; die Timeout-Tests sichern den Testlauf ab, nicht einen generellen Schutz gegen alle denkbaren DoS-Angriffe.

**Erfolgskriterium:** Alle acht E2E-Tests und `./gradlew check` sind grün; kein Test überschreitet das Timeout. Die E2E-Tests werden separat von den Unit-Tests gezählt. Ein veröffentlichtes Release-JAR ist durch diese Tests nicht nachträglich geändert; beim nächsten Release laufen sie durch `build` mit. Der [CI-Lauf für `fbb7102`](https://github.com/philderks/450-tictactest-mvk/actions/runs/40367789784) hat beide Teststufen, JaCoCo, PIT, Build und Artefakt-Uploads erfolgreich ausgeführt. Lokal wurden 27 reguläre Tests, 8 E2E-Tests, 105/110 abgedeckte Branches (95,45 %) und 71/87 getötete Mutationen (82 %) gemessen. Messwerte sind Momentaufnahmen und nach Änderungen erneut zu prüfen.

## Grenzen und Risiken

- Der JaCoCo-Gate prüft Branches **nur** der regulären Tests; die eigene E2E-Suite wird separat ausgeführt. PIT hat kein Mindestziel; der aktuelle Wert liegt unter 90 %. Ausgabepfade und Grenzfälle können trotz grüner Tests überlebende Mutanten enthalten.
- Die Tests simulieren Konsoleneingaben und decken endliche fehlerhafte Folgen und EOF ab, aber keinen unbegrenzt weiterlaufenden Eingabestrom, extrem lange Eingabezeilen, Betriebssystem-/Terminalverhalten oder jede mögliche DoS-Variante. Timeout schützt die Testausführung, nicht alle realen Anwendungen.
- SonarLint und die Aktualität aller Abhängigkeiten sind nicht als erfüllt nachgewiesen. Der GitHub-Ruleset erzwingt derzeit keine erfolgreichen CI-Checks vor dem Merge und erlaubt einen Rollen-Bypass; die Testpipeline ist deshalb kein garantierter Schutz für `main`. Näheres in [ist-situation.md](ist-situation.md).

## Namenskonvention & Dokumentation

- Testmethoden folgen dem Schema `methodeUnterTest_erwartetesVerhalten` (z.B. `isWin_detectsRowWin`).
- Unit-/Integrationstests werden nach dem **Given-When-Then**-Muster in [docs/tests.md](tests.md) dokumentiert; die E2E-Fälle mit Erwartung und tatsächlichem Verhalten stehen in der Tabelle oben:
  - **Given**: Ausgangszustand
  - **When**: ausgeführte Aktion
  - **Then**: erwartetes Ergebnis

## Vorgehen bei neuen Features

1. Neue reine Logik (analog zu `isWin`) → Unit-Test mit Fixtures/parametrisierten Fällen.
2. Neue Spieler-Strategie → Unit-Test für deren `play(...)`-Verhalten isoliert.
3. Änderungen am Spielablauf (`play()`) → Integrationstest, der das Zusammenspiel mehrerer Spieler prüft.
4. Neue oder geänderte Konsolenabläufe → E2E-Test über `main()` ergänzen, erwartetes und tatsächliches Verhalten in der Tabelle nachführen.
