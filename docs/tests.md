# Testdokumentation

Stand: 2026-10-26 (`main` nach `fbb7102`). Die folgenden Fälle beschreiben die tatsächlich vorhandenen Tests unter [`src/test/java`](../src/test/java). **Given** bezeichnet den Ausgangszustand, **When** die Aktion und **Then** die geprüfte Erwartung. Parametrisierte Aufrufe zählen im JUnit-Report einzeln: `./gradlew test` führt **27 Tests** in sechs Klassen aus. Die acht separaten Konsolen-E2E-Tests stehen mit erwarteten und beobachteten Ergebnissen im [Testkonzept](testkonzept.md#4-end-to-end-tests-für-den-konsoleneinstieg) und laufen mit `./gradlew e2eTest`.

| Klasse / Testfälle | Given | When | Then |
|---|---|---|---|
| [`TicTacToeMainTest`](../src/test/java/ch/bbw/m450/tictactoe/TicTacToeMainTest.java): `isWin_detectsRowWin` | Benanntes Brett `ROW_WIN_CROSS` mit X in der obersten Reihe | Gewinnerprüfung für X und O | X gewinnt, O nicht. |
| `isWin_detectsDiagonalWin` | `DIAGONAL_WIN_CROSS` mit X auf 2–4–6 | Gewinnerprüfung für X | X gewinnt. |
| `isWin_returnsFalseForNonWinningBoard` | Vollständiges `FULL_BOARD_NO_WINNER` | Gewinnerprüfung für beide Farben | Keine Farbe gewinnt. |
| `isWin_detectsAllWinningLines` (8 Aufrufe) | Je eine belegte Gewinnlinie aus `winningLines()`; Reihen, Spalten und Diagonalen | Gewinnerprüfung für die jeweilige Farbe | Alle acht Linien werden als Gewinn erkannt. |
| `play_throwsIllegalArgumentException_whenSamePlayerInstanceUsedForBothSides` | Dieselbe `GreedyPlayer`-Instanz für beide Seiten | `play(player, player)` | `IllegalArgumentException`. |
| `play_withTwoGreedyPlayers_producesDeterministicCrossWin` | Zwei getrennte `GreedyPlayer`-Instanzen | Vollständiges `play(...)` | X gewinnt über 2–4–6. |
| `play_throwsIllegalStateException_whenPlayerReturnsOutOfRangePosition` | Ein testinterner `QueuePlayer` liefert `-1` | `play(...)` | `IllegalStateException`. |
| `play_returnsNull_onDraw` | Zwei `QueuePlayer` mit Zugfolgen für ein volles Brett ohne Gewinner | `play(...)` | Ergebnis `null` (Unentschieden). |
| [`TicTacToePlayerTest`](../src/test/java/ch/bbw/m450/tictactoe/TicTacToePlayerTest.java): `opponent_ofCrossIsCircle`, `opponent_ofCircleIsCross` | Je eine Farbe | `opponent()` | Die jeweils andere Farbe. |
| [`GreedyPlayerTest`](../src/test/java/ch/bbw/m450/tictactoe/players/GreedyPlayerTest.java): `play_throwsIllegalStateException_whenBoardIsFull` | Voll besetztes Brett | `GreedyPlayer.play(...)` | `IllegalStateException`. Der Zug auf dem ersten freien Feld wird hier **nicht** separat geprüft. |
| [`HumanPlayerTest`](../src/test/java/ch/bbw/m450/tictactoe/players/HumanPlayerTest.java): `play_readsConsecutiveMoves_whenAllInputIsAvailableAtOnce` | Eingabestrom mit `4` und `8` | Zwei Aufrufe derselben Spielerinstanz | Züge 4, dann 8. |
| `play_readsStdIn_andPrintsPromptForEachMove` | JUnit Pioneer `@StdIo` liefert `4` und `8` | Menschlicher Spieler liest `System.in` | Züge 4 und 8; je eine korrekte X-/O-Eingabeaufforderung in `StdOut`. |
| [`PerfectPlayerTest`](../src/test/java/ch/bbw/m450/tictactoe/players/PerfectPlayerTest.java): `playsImmediateWin`, `blocksImmediateLoss` | Brett mit unmittelbarer Gewinn- bzw. Verlustmöglichkeit | `PerfectPlayer.play(...)` | Feld 2 wird gewählt. |
| `neverLosesAgainstAnyLegalOpponentMoves` (2 Aufrufe, X/O) | Leeres Brett; rekursiv alle legalen gegnerischen Züge | Perfekter Spieler entscheidet in jeder erreichbaren Stellung | Legaler Zug, Brett unverändert, Gegner gewinnt nie. |
| `twoPerfectPlayersDraw`, `cannotPlayOnFullBoard` | Zwei perfekte Spieler bzw. volles Brett | `play(...)` bzw. `PerfectPlayer.play(...)` | Unentschieden (`null`) bzw. `IllegalStateException`. |
| [`PerfectPlayerPropertyTest`](../src/test/java/ch/bbw/m450/tictactoe/players/PerfectPlayerPropertyTest.java): `choosesLegalMoveWithoutChangingBoard` | jqwik erzeugt Zugfolgen für erreichbare, nicht abgeschlossene Bretter | Perfekter Spieler wählt einen Zug | Zug im Brettbereich auf freiem Feld; Eingabebrett unverändert. Eine entdeckte Property mit `tries = 100`, **nicht** 100 separate JUnit-Tests. |

## Ausführung und Nachweise

- `./gradlew test` → JUnit HTML/XML unter `build/reports/tests/test` bzw. `build/test-results/test`.
- `./gradlew e2eTest` → acht über `main()` gespielte Konsolentests unter `build/reports/tests/e2eTest` und `build/test-results/e2eTest`.
- `./gradlew check` → beide Teststufen und die JaCoCo-Prüfung für **mindestens 90 % Branch Coverage** der regulären Tests; E2E ist ein separater Source-Set und fliesst nicht automatisch in diesen JaCoCo-/PIT-Wert ein.
- `./gradlew pitest` → Mutationstest-Bericht unter `build/reports/pitest`; derzeit **kein** Mutation-Score-Gate.
- Der [CI-Workflow](../.github/workflows/ci.yml) lädt JUnit-, E2E-, JaCoCo- und PIT-Berichte als Artefakte hoch. Der Lauf für `fbb7102` war [erfolgreich](https://github.com/philderks/450-tictactest-mvk/actions/runs/40367789784).

Die älteren Bilder [`test_success.png`](media/test_success.png) und [`test_failure.png`](media/test_failure.png) stammen aus einem früheren Teststand (einschliesslich des inzwischen gelöschten `DummyTest`) und belegen **nicht** die aktuellen Testzahlen. Massgeblich sind der aktuelle Testcode, die JUnit-Berichte und der verlinkte CI-Lauf.
