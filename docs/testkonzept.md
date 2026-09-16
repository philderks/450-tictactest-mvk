# Testkonzept

Dieses Dokument beschreibt die Teststrategie für das TicTacToe-Projekt: was getestet wird, was bewusst nicht getestet wird, mit welchen Werkzeugen und nach welchem Muster.

## Ziel

Die Kernlogik des Spiels (Gewinnerkennung und Spielablauf) soll zuverlässig durch automatisierte Tests abgesichert sein, sodass Änderungen (z.B. neue Spieler-Strategien) mit Vertrauen vorgenommen werden können. Die CI-Pipeline ([.github/workflows/ci.yml](../.github/workflows/ci.yml)) führt die Tests bei jedem Push/PR auf `main` aus.

## Werkzeuge

- **JUnit 5** (Jupiter) als Test-Framework, inkl. `@ParameterizedTest`/`@MethodSource` für datengetriebene Tests.
- **AssertJ** für lesbare, fluent Assertions (`assertThat`, `assertThatThrownBy`).
- Ausführung über Gradle: `./gradlew test`.

## Aufbau / Teststufen

Das Projekt ist klein genug für eine schlanke, zweistufige Pyramide statt einer vollen Unit/Integration/E2E-Trennung:

### 1. Unit-Tests für reine Logik

Betrifft `TicTacToeMain.isWin(...)`: eine reine, zustandslose Funktion ohne Seiteneffekte – ideal für isolierte Unit-Tests.

- Alle 8 Gewinnlinien (3 Reihen, 3 Spalten, 2 Diagonalen) werden parametrisiert abgedeckt (`isWin_detectsAllWinningLines`).
- Negativfälle: volles Brett ohne Gewinner (Unentschieden-Board), falsche Farbe gewinnt nicht.
- Fixtures (benannte, wiederverwendbare Testbretter) statt Boards inline in jeder Methode aufzubauen, für Lesbarkeit.

### 2. Unit-Tests für Spieler-Strategien

Betrifft Implementierungen von `TicTacToePlayer`, z.B. `GreedyPlayer`: deterministisches Verhalten wird direkt geprüft (spielt immer das erste freie Feld).

### 3. Integrationstests für den Spielablauf

Betrifft `TicTacToeMain.play(...)`: orchestriert zwei Spieler über mehrere Runden und kombiniert Spielerlogik + Gewinnerkennung. Hier wird das Zusammenspiel getestet, nicht mehr die Einzelteile isoliert.

Abgedeckt:
- Deterministischer Spielverlauf zwischen zwei `GreedyPlayer`n endet mit erwartetem Sieger.
- Guard-Klausel: dieselbe Spielerinstanz für beide Seiten wirft `IllegalArgumentException`.

**Lücken, die noch zu schliessen sind:**
- Unentschieden-Fall (`play()` gibt `null` zurück, wenn kein Spieler gewinnt).
- Fehlerfall, wenn ein Spieler ein ungültiges oder bereits belegtes Feld liefert (`IllegalStateException`).

## Bewusst nicht automatisiert getestet

`HumanPlayer` liest direkt von `System.in` (`Scanner`) und ist damit an Konsoleneingabe gekoppelt. Er wird aktuell nicht durch automatisierte Tests abgedeckt, da:
- ein Test entweder `System.in` mocken/umleiten müsste, oder
- die Klasse für Testbarkeit umgebaut werden müsste (z.B. Reader/Scanner injizierbar machen).

Solange `HumanPlayer` keine eigene Logik ausser reinem Input-Parsing enthält, wird dieser Trade-off als akzeptabel bewertet. Sollte die Klasse komplexer werden (z.B. Eingabevalidierung), ist eine Umstellung auf Dependency Injection sinnvoll, um sie testbar zu machen.

## Namenskonvention & Dokumentation

- Testmethoden folgen dem Schema `methodeUnterTest_erwartetesVerhalten` (z.B. `isWin_detectsRowWin`).
- Jeder Test wird nach dem **Given-When-Then**-Muster in [docs/tests.md](tests.md) dokumentiert:
  - **Given**: Ausgangszustand
  - **When**: ausgeführte Aktion
  - **Then**: erwartetes Ergebnis
- Neue Tests müssen dort ergänzt werden, damit die Dokumentation konsistent bleibt.

## Vorgehen bei neuen Features

1. Neue reine Logik (analog zu `isWin`) → Unit-Test mit Fixtures/parametrisierten Fällen.
2. Neue Spieler-Strategie → Unit-Test für deren `play(...)`-Verhalten isoliert.
3. Änderungen am Spielablauf (`play()`) → Integrationstest, der das Zusammenspiel mehrerer Spieler prüft.
4. Dokumentation in [docs/tests.md](tests.md) nach Given-When-Then nachführen.

## Audit-Feedback

**Gesamtbild:** Das Testkonzept ist für ein kleines Projekt gut gemacht. Die wichtigste Logik (wer gewinnt, wie ein Spiel abläuft) wird automatisch mit JUnit 5 und AssertJ getestet, und die Tests laufen bei jedem Pull Request von selbst. Es ist klar geschrieben, und der Autor sagt ehrlich, was noch fehlt. Schwach sind die Fehlerfälle, und es fehlt eine Angabe, wie viel vom Code getestet ist.

**Bewertung:** Solide und verständlich, aber nicht vollständig. Für eine 5.5 oder 6 müssten die bekannten Lücken geschlossen und die Testabdeckung gemessen werden.

**Verbesserungsvorschläge:**
- Den Widerspruch korrigieren: Im Text steht „zwei Stufen“, es werden aber drei beschrieben.
- Test für ein Unentschieden im ganzen Spiel ergänzen.
- Test für ungültige oder schon belegte Felder ergänzen.
- Die Testabdeckung messen (z.B. mit JaCoCo) und ein Ziel festlegen.
- Die Tests auch auf dem dev-Branch automatisch laufen lassen.
- Randfälle testen, z.B. ein leeres Brett oder ungültige Eingaben.
- Eine kurze Checkliste für den manuellen Test des HumanPlayer schreiben.

*Auditor: Nik*