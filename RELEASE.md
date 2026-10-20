# Release-Prozess

Diese Anleitung beschreibt, wie aus einem bestimmten Stand des Repositorys eine veröffentlichte Version von
TicTacTest entsteht. Sie ist so geschrieben, dass jede Person mit Schreibrechten auf das Repository einen
Release ohne Rückfragen durchführen kann.

## Überblick

```text
Entwicklung auf dev
  ↓
Pull Request dev → main (CI + Coverage Gate grün) → Merge
  ↓
CHANGELOG.md und Version in build.gradle sind darin bereits aktualisiert
  ↓
Annotierten Git-Tag vX.Y.Z auf main setzen und pushen
  ↓
GitHub Actions (release.yml): Bedingungen prüfen → Tests → Build → JAR → Smoke-Test
  ↓
GitHub Release mit JAR + SHA-256-Prüfsumme
  ↓
JAR vom Release herunterladen und testen
```

## Wann wird ein Release erstellt?

Ein Release wird **bewusst** erstellt, wenn auf `main` ein Stand vorliegt, der an Benutzer ausgeliefert werden
soll: eine neue Funktion ist fertig, ein Fehler ist behoben, oder mehrere kleine Änderungen sollen zusammen
veröffentlicht werden. Es gibt keinen festen Rhythmus.

## Wer bzw. was startet einen Release?

Eine Person mit Schreibrechten startet den Release, indem sie einen Git-Tag `vX.Y.Z` auf `main` setzt und pusht.
Der Push des Tags startet automatisch den Workflow [.github/workflows/release.yml](.github/workflows/release.yml).

Falls ein Release-Lauf wiederholt werden muss (z. B. nach einem Ausfall von GitHub), kann der Workflow auch
manuell gestartet werden: **Actions → Release → Run workflow** und unter *Use workflow from* den **Tag** auswählen.
Auf einem Branch gestartet, tut der Workflow nichts.

## Warum löst nicht jeder Push auf `main` einen Release aus?

`main` ändert sich bei jedem gemergten Pull Request. Nicht jede dieser Änderungen ist für Benutzer relevant oder
schon zusammen mit anderen Änderungen auslieferbar. Ein Release ist ein Versprechen an die Benutzer
(Versionsnummer, Changelog, herunterladbares JAR) und soll deshalb eine bewusste Entscheidung sein.

Technisch ist das so umgesetzt:

- `release.yml` reagiert nur auf Tags `v*`, nicht auf Branch-Pushes.
- `ci.yml` reagiert nur auf Branch-Pushes und Pull Requests. Sie testet und baut, veröffentlicht aber keinen Release.

## Versionsnummer

Versionen folgen [Semantic Versioning](https://semver.org/lang/de/): `MAJOR.MINOR.PATCH`, z. B. `1.0.0`.
Der zugehörige Git-Tag hat zusätzlich ein `v` davor, z. B. `v1.0.0`.

| Stelle erhöhen | Wann | Beispiel für TicTacTest |
|---|---|---|
| **MAJOR** (`2.0.0`) | Änderung, die bestehende Benutzer oder Entwickler zu Anpassungen zwingt | anderes Eingabeformat für Züge, neue Mindest-Java-Version, geändertes `TicTacToePlayer`-Interface |
| **MINOR** (`1.1.0`) | neue Funktion, alles Bestehende funktioniert weiter wie bisher | neuer Computer-Gegner, Spiel gegen zweiten Menschen, Anzeige der Versionsnummer |
| **PATCH** (`1.0.1`) | nur Fehlerbehebung, kein neues Verhalten | Absturz bei falscher Eingabe behoben, Tippfehler in einer Ausgabe korrigiert |

Beim Erhöhen einer Stelle werden die rechts davon auf `0` gesetzt (`1.2.3` → `1.3.0` → `2.0.0`).
Enthält ein Release Änderungen mehrerer Arten, entscheidet die höchste.

**Wo steht die Version?** An genau einer Stelle: `version = 'X.Y.Z'` in [build.gradle](build.gradle).
Gradle übernimmt sie in den Dateinamen (`tictactest-X.Y.Z.jar`) und ins JAR-Manifest (`Implementation-Version`).
Der Release-Workflow bricht ab, wenn der Tag nicht genau `v` + diese Version ist. So können Tag und JAR nie
auseinanderlaufen.

## Voraussetzungen vor einem Release

| Bedingung | Wie sie sichergestellt wird |
|---|---|
| Die Anwendung ist auf dem gewünschten Stand. | Alle geplanten Pull Requests sind gemergt. Der Stand wurde lokal gespielt (`./gradlew build` und `java -jar build/libs/tictactest-X.Y.Z.jar`). |
| Alle Änderungen sind auf `main`. | `main` ist geschützt und nimmt Änderungen nur über Pull Requests an. Zusätzlich bricht der Workflow ab, wenn der getaggte Commit nicht auf `main` liegt. |
| Das Projekt lässt sich bauen. | CI ist auf dem Pull Request grün. Der Workflow baut noch einmal. |
| Alle automatisierten Tests sind erfolgreich. | CI und Coverage Gate sind grün. Der Workflow führt `./gradlew test` und `./gradlew build` aus (inkl. Coverage-Prüfung mit min. 90 %). |
| Das Changelog ist aktualisiert. | `CHANGELOG.md` hat einen Abschnitt `## [X.Y.Z] - JJJJ-MM-TT`. Der Workflow bricht ab, wenn er fehlt. |
| Die Versionsnummer ist festgelegt. | `version` in `build.gradle` ist erhöht und passt zum Tag. Der Workflow prüft das. |

## Anleitung: einen Release erstellen

Beispiel für Version `1.1.0`, die vorherige Version ist `1.0.0`.

**1. Release vorbereiten (auf `dev`)**

1. Version nach den Regeln oben festlegen.
2. In [build.gradle](build.gradle) `version = '1.1.0'` setzen.
3. In [CHANGELOG.md](CHANGELOG.md) die Einträge unter `## [Unreleased]` in einen neuen Abschnitt
   `## [1.1.0] - <heutiges Datum>` verschieben. `## [Unreleased]` bleibt leer stehen.
4. Lokal prüfen:

   ```bash
   ./gradlew clean build
   java -jar build/libs/tictactest-1.1.0.jar
   ```

5. Committen und pushen:

   ```bash
   git commit -am "chore(release): 1.1.0"
   git push origin dev
   ```

**2. Nach `main` bringen**

Pull Request `dev` → `main` erstellen. Warten, bis CI und Coverage Gate grün sind, dann mergen.

**3. Tag setzen und pushen**

```bash
git switch main
git pull
git log -1 --oneline            # das ist der Commit, der released wird
git tag -a v1.1.0 -m "Release v1.1.0"
git push origin v1.1.0
```

**4. Workflow beobachten**

Unter **Actions → Release** läuft jetzt der Workflow. Wenn er grün ist, erscheint der Release unter
**Releases**.

**5. Release testen** (siehe unten)

## Was der Release-Workflow macht

[.github/workflows/release.yml](.github/workflows/release.yml) läuft auf einem frischen Ubuntu-Runner:

1. **Repository auschecken** – genau den Commit, auf den der Tag zeigt.
2. **Java installieren** – Temurin JDK 25.
3. **Bedingungen prüfen** – Tag = `v` + Version aus `build.gradle`, Commit liegt auf `main`, Changelog-Abschnitt existiert.
4. **Tests ausführen** – `./gradlew test`.
5. **Bauen und JAR erzeugen** – `./gradlew build` (inkl. Coverage-Prüfung) erzeugt `build/libs/tictactest-X.Y.Z.jar`.
6. **Smoke-Test** – spielt mit dem JAR ein ganzes Spiel (Züge per Pipe) und prüft, dass es mit einem Gewinner endet.
7. **Prüfsumme** – erzeugt `tictactest-X.Y.Z.jar.sha256`.
8. **GitHub Release erstellen** – Titel `TicTacTest vX.Y.Z`. Der Text enthält Tag, Commit-ID, den Changelog-Abschnitt der Version und den Startbefehl. JAR und Prüfsumme werden angehängt.

## Welcher Commit gehört zu einem Release?

Genau der Commit, auf den der Tag zeigt. Der Workflow baut aus diesem Commit, und die Commit-ID steht im
Release-Text. Nachprüfen:

```bash
git rev-parse v1.0.0^{commit}   # Commit-ID des Tags
git show v1.0.0                 # Tag-Nachricht und Commit
```

Auf GitHub zeigt die Release-Seite neben dem Tag ebenfalls den Commit an.

## Wie wird das JAR gebaut?

Mit Gradle: `./gradlew build` erzeugt `build/libs/tictactest-X.Y.Z.jar`. Im Manifest steht
`Main-Class: ch.bbw.m450.tictactoe.TicTacToeMain`, daher startet `java -jar` das Spiel direkt. Das Spiel hat
keine Laufzeit-Abhängigkeiten, deshalb ist kein "Fat-JAR" nötig.

## Wo kann das JAR heruntergeladen werden?

Auf der Release-Seite des Repositorys:
<https://github.com/philderks/450-tictactest-mvk/releases>
(die neueste Version: <https://github.com/philderks/450-tictactest-mvk/releases/latest>).
Unter *Assets* liegen `tictactest-X.Y.Z.jar` und die Prüfsumme.

## Was enthält das Changelog?

[CHANGELOG.md](CHANGELOG.md) beschreibt pro Version, was sich für Benutzer und Entwickler geändert hat. Es ist
keine Liste von Git-Commits. Jeder Abschnitt hat:

- Versionsnummer und Release-Datum: `## [1.1.0] - 2026-10-20`
- `### Added` – neue Funktionen
- `### Changed` – Änderungen an bestehenden Funktionen
- `### Fixed` – behobene Fehler, wenn möglich mit Issue-Nummer, z. B. `(#12)`

Leere Kategorien werden weggelassen. Neue Einträge kommen laufend unter `## [Unreleased]` und werden beim Release
in den Versionsabschnitt verschoben.

## Was passiert, wenn beim Release ein Test fehlschlägt?

Der Workflow bricht beim fehlgeschlagenen Schritt ab. Es wird **kein** Release erstellt und kein JAR
veröffentlicht. Der Tag existiert dann bereits auf GitHub, hat aber keinen Release. Vorgehen:

1. Fehler auf `dev` beheben und über einen Pull Request nach `main` bringen.
2. Weil noch nichts veröffentlicht wurde, darf der Tag gelöscht und auf den korrigierten Commit neu gesetzt werden:

   ```bash
   git tag -d v1.1.0
   git push origin :refs/tags/v1.1.0
   git switch main && git pull
   git tag -a v1.1.0 -m "Release v1.1.0"
   git push origin v1.1.0
   ```

**Ein Tag, zu dem bereits ein Release veröffentlicht wurde, wird nie verschoben oder gelöscht.** Ein Fehler in
einer veröffentlichten Version wird mit einer neuen PATCH-Version behoben. Sonst gäbe es zwei verschiedene JARs
mit derselben Versionsnummer.

## Release testen

Ein Release gilt erst als erfolgreich, wenn das veröffentlichte Artefakt selbst funktioniert:

```bash
mkdir /tmp/release-test && cd /tmp/release-test
curl -LO https://github.com/philderks/450-tictactest-mvk/releases/download/v1.0.0/tictactest-1.0.0.jar
curl -LO https://github.com/philderks/450-tictactest-mvk/releases/download/v1.0.0/tictactest-1.0.0.jar.sha256
sha256sum -c tictactest-1.0.0.jar.sha256
java -jar tictactest-1.0.0.jar
```

Das Spiel muss starten und sich bis zum Ende spielen lassen, ohne dass etwas aus dem Quellcode gebaut wird.
Alternativ das JAR über die Release-Seite im Browser herunterladen.

## Wie entsteht aus einem Stand des Repositorys eine veröffentlichte Version?

- **Nachvollziehbar:** Der Tag `vX.Y.Z` zeigt unveränderlich auf einen Commit. Der Release nennt diesen Commit,
  und das Changelog beschreibt in verständlichen Worten, was sich geändert hat.
- **Reproduzierbar:** Das JAR wird nicht auf einem Entwickler-Rechner gebaut, sondern von GitHub Actions auf einem
  frischen Runner aus genau diesem Commit, mit festgelegter Java-Version und Gradle-Wrapper. Die Versionsnummer
  kommt aus `build.gradle` im Commit selbst, die SHA-256-Prüfsumme belegt, welches JAR veröffentlicht wurde.
- **Kontrolliert:** Nur ein bewusst gesetzter Tag startet einen Release. Vorher müssen die Änderungen per Pull
  Request auf den geschützten Branch `main`. Der Workflow veröffentlicht nur, wenn Version, Changelog, Tests,
  Coverage und Build stimmen.
