# Changelog

Alle wichtigen Änderungen an TicTacTest werden in dieser Datei dokumentiert.
Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionsnummern nach
[Semantic Versioning](https://semver.org/lang/de/). Wann welche Stelle erhöht wird, steht in [RELEASE.md](RELEASE.md).

## [Unreleased]

## [1.4.0] - 2026-11-24

### Changed
- Die Akzentfarbe des Frontends ist neu Grün statt Blau. Das Backend bleibt unverändert.

## [1.3.0] - 2026-11-24

### Added
- Automatisches Deployment veröffentlichter Releases: Nur geänderte Komponenten werden ausgeliefert, jede veröffentlichte Version lässt sich gezielt erneut deployen.

### Changed
- Bei einem Unentschieden zeigt die Konsole wie bei einem Sieg das vollständige Schlussbrett.
- Die Spielregeln im Frontend erwähnen das Unentschieden.
- Für Entwickler: Der Smoke-Test im Release-Workflow hängt nicht mehr vom eingestellten Gegner ab.

## [1.2.0] - 2026-11-23

### Added
- Reproduzierbare EC2-Laufzeit mit versionsgebundenem Erststart-Bootstrap, unprivilegierten systemd-Diensten und geprüftem manuellem Release-Deployment.
- Öffentliches Frontend über eine feste Elastic IP sowie Zuordnung des vorhandenen Learner-Lab-Instance-Profils ohne eigene IAM-Rollen.

### Changed
- Ein gemeinsamer blauer Akzent für Titel, Links und Feldnummern macht Release B im Frontend sichtbar; Spielregeln und Java-Spiellogik bleiben unverändert.

## [1.1.0] - 2026-11-17

### Added
- Statisches Browser-Frontend mit eingebetteter Web-Konsole, Spielregeln und unabhängigen Versionsanzeigen; Server-Adressen werden über `config.js` konfiguriert.
- Automatische Backend-Versionsdatei aus dem Release-Jar und ein lokaler HTTP-Endpunkt mit gezielter CORS-Freigabe.
- Versioniertes Frontend-Archiv und Runtime-Werkzeuge mit Startskript, Anleitung und SHA-256-Prüfsummen als zusätzliche Release-Assets.
- Separate End-to-End-Tests für vollständige Konsolenspiele, fehlerhafte Eingaben und Eingabeende mit Timeout-Absicherung; Gradle-Task und CI-Report.

### Fixed
- Ungültige oder belegte Felder und nichtnumerische Eingaben lassen sich erneut eingeben statt das Spiel abstürzen zu lassen.
- Bei Eingabeende stoppt das Konsolenspiel mit einer verständlichen Meldung statt einem Stacktrace.

### Changed
- Das Pages-Diagramm verwendet eine neue Branch-Coverage-Historie für die 90-%-Gate-Linie; die bisherige Instruction-Historie bleibt getrennt erhalten.
- JaCoCo wurde auf 0.8.16 aktualisiert.

## [1.0.1] - 2026-10-20

### Fixed
- Das Spiel stürzt nicht mehr ab, wenn mehrere Züge auf einmal eingegeben werden (z. B. per Pipe: `printf '4\n8\n2\n6\n' | java -jar tictactest-1.0.1.jar`). Vorher ging nach dem ersten Zug die restliche Eingabe verloren.

### Changed
- Für Entwickler: Der Smoke-Test im Release-Workflow spielt jetzt ein ganzes Spiel mit dem gebauten JAR durch, statt nur den Start zu prüfen.

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
