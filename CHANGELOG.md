# Changelog

Alle wichtigen Änderungen an TicTacTest werden in dieser Datei dokumentiert.
Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionsnummern nach
[Semantic Versioning](https://semver.org/lang/de/). Wann welche Stelle erhöht wird, steht in [RELEASE.md](RELEASE.md).

## [Unreleased]

## [1.0.0] - 2026-10-20

### Added
- Erste spielbare Version von TicTacTest: Ein Mensch (X) spielt in der Konsole gegen einen einfachen Computer-Spieler (O).
- Spielfeld mit nummerierten freien Feldern (0-8), Gewinnerkennung für alle acht Linien und Erkennung von Unentschieden.
- Ungültige Züge (besetztes Feld oder Feld ausserhalb von 0-8) beenden das Spiel mit einer Fehlermeldung.
- Ausführbares JAR, startbar mit `java -jar tictactest-1.0.0.jar` (benötigt Java 25).
- Für Entwickler: Unit-Tests (JUnit 5, AssertJ), Coverage-Prüfung mit mindestens 90 %, CI-Pipeline, Coverage-Gate für Pull Requests und DevContainer.
- Release-Prozess: Ein `v*`-Tag startet einen Workflow, der testet, baut und das JAR als GitHub Release veröffentlicht.

### Changed
- Das Build-Artefakt heisst jetzt `tictactest-<version>.jar` (vorher `tictactoe.jar` ohne Version und ohne Startklasse).
