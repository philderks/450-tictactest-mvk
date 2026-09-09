# Ist-Situation gegenüber den Anforderungen

Dieses Dokument hält den aktuellen Stand des Projekts (Stand: 2026-09-09) gegen die gestellten Bewertungskriterien fest. Es dient als Ausgangspunkt, um die verbleibenden Lücken gezielt zu schliessen.

Legende: ✅ erfüllt · ⚠️ teilweise erfüllt · ❌ fehlt · – nicht code-bezogen

## Übersicht

| # | Kriterium | Status |
|---|---|---|
| 1 | Unit Testing mit AssertJ (fluent, keine reinen `isTrue()`), Hilfsstrukturen | ⚠️ teilweise |
| 2 | ParameterizedTest wo möglich, Vermeidung von Coderepetition | ⚠️ teilweise |
| 3 | JaCoCo Coverage Reports + Verification (90% Branch Coverage enforced) | ❌ fehlt |
| 4 | StdIn/StdOut Testing mit JUnit Pioneer | ❌ fehlt |
| 5 | CI-Pipeline mit allen Reports als Build Artifacts bei jedem Commit, grüner Build | ⚠️ teilweise |
| 6 | Zusätzlicher, perfekt spielender Player | ❌ fehlt |
| 7 | Zusätzliches, selbst gewähltes Testframework mit Beispieltest, automatisiert | ❌ fehlt |
| 8 | Automatisiertes Mutation Testing mit PITest | ❌ fehlt |
| 9 | Keine SonarLint-Warnings, einheitlicher Codestyle, `var` bevorzugt, aktuellste Library-Versionen | ⚠️ nicht verifiziert |
| 10 | Pünktliche Abgabe als privates GitHub-Projekt | – |

## Details

### 1. AssertJ fluent Assertions + Hilfsstrukturen — ⚠️ teilweise

- Benannte Fixtures sind vorhanden: `ROW_WIN_CROSS`, `DIAGONAL_WIN_CROSS`, `FULL_BOARD_NO_WINNER` ([TicTacToeMainTest.java:17-33](../src/test/java/ch/bbw/m450/tictactoe/TicTacToeMainTest.java#L17-L33)).
- Die `isWin_*`-Tests bestehen jedoch fast ausschliesslich aus `assertThat(...).isTrue()` / `.isFalse()` ([Zeilen 37-49](../src/test/java/ch/bbw/m450/tictactoe/TicTacToeMainTest.java#L37-L49)) — genau die "langweiligen" Assertions, die das Kriterium ausschliesst. Aussagekräftigere/fluentere Assertions (z.B. mit Beschreibung via `.as(...)`, Vergleich auf Objektebene, Custom-Assertions) fehlen.

### 2. ParameterizedTest, Vermeidung von Coderepetition — ⚠️ teilweise

- `isWin_detectsAllWinningLines` ist sauber parametrisiert und deckt alle 8 Gewinnlinien ab ([Zeilen 52-77](../src/test/java/ch/bbw/m450/tictactoe/TicTacToeMainTest.java#L52-L77)).
- Allerdings decken `isWin_detectsRowWin` und `isWin_detectsDiagonalWin` dieselben Fälle (Reihe, Diagonale) nochmals einzeln ab → Redundanz statt Vermeidung von Coderepetition.

### 3. JaCoCo — ❌ fehlt

- Kein JaCoCo-Plugin, kein Coverage-Report, keine Verification-Regel in [build.gradle](../build.gradle).

### 4. StdIn/StdOut Testing mit JUnit Pioneer — ❌ fehlt

- `HumanPlayer` liest direkt von `System.in` ([HumanPlayer.java:17](../src/main/java/ch/bbw/m450/tictactoe/players/HumanPlayer.java#L17)) und ist komplett ungetestet.
- Keine JUnit-Pioneer-Dependency in [build.gradle](../build.gradle).

### 5. CI-Pipeline mit Reports als Build Artifacts — ⚠️ teilweise

- [ci.yml](../.github/workflows/ci.yml) führt bei Push/PR auf `main` `./gradlew test` und `./gradlew build` aus, Build ist grün.
- Es fehlt ein Upload-Schritt (`actions/upload-artifact`) für Test-/Coverage-/Mutation-Reports.

### 6. Perfekt spielender Player — ❌ fehlt

- Nur `GreedyPlayer` (belegt immer erstes freies Feld) und `HumanPlayer` vorhanden. Kein Minimax- oder anderweitig perfekt spielender Player.

### 7. Zusätzliches Testframework — ❌ fehlt

- Einziges Test-Framework ist JUnit 5 (+ AssertJ als Assertion-Library). Kein zweites Framework (z.B. Spock, TestNG, Cucumber) mit eigenem Beispieltest im Build eingebunden.

### 8. Mutation Testing mit PIT — ❌ fehlt

- Kein PIT-Plugin/Task in [build.gradle](../build.gradle).

### 9. Codequalität — ⚠️ nicht verifiziert

- `var` wird im gesamten Code konsequent verwendet (z.B. [TicTacToeMain.java](../src/main/java/ch/bbw/m450/tictactoe/TicTacToeMain.java), [TicTacToeMainTest.java](../src/test/java/ch/bbw/m450/tictactoe/TicTacToeMainTest.java)) ✅.
- Library-Versionen aktuell: `junit-bom 5.11.4`, `assertj-core 3.26.3` ([build.gradle:16-19](../build.gradle#L16-L19)) — ob dies die jeweils neuesten Releases sind, wurde nicht geprüft.
- SonarLint-Warnings wurden nicht automatisiert geprüft (kein Sonar-Plugin/CI-Step vorhanden).

### 10. Abgabe — –

- Kein Code-Aspekt, betrifft den Abgabeprozess.

## Priorisierte Lücken

Fehlende bzw. unvollständige Punkte, absteigend nach Aufwand/Impact:

1. JaCoCo einrichten (Report + 90%-Branch-Coverage-Gate)
2. PIT-Mutation-Testing einrichten
3. Perfekt spielenden Player implementieren und testen
4. StdIn/StdOut-Tests für `HumanPlayer` mit JUnit Pioneer
5. Zweites Testframework mit Beispieltest ergänzen
6. CI-Pipeline um Artifact-Uploads erweitern
7. Redundante `isWin_*`-Tests bereinigen, Assertions in Richtung fluent/aussagekräftig überarbeiten
8. Library-Versionen und SonarLint-Konformität verifizieren
