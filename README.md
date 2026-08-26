# TicTacToe

Ein kleines TicTacToe-Spiel in Java mit einem menschlichen Spieler (`HumanPlayer`) und einem einfachen Computer-Spieler (`GreedyPlayer`), der stets das erste freie Feld belegt.

## Voraussetzungen

- JDK 25 (wird über den Gradle-Toolchain-Mechanismus bei Bedarf automatisch bezogen)

## Dev Container einrichten

Das Projekt enthält eine Dev-Container-Konfiguration ([.devcontainer/devcontainer.json](.devcontainer/devcontainer.json)) mit vorinstalliertem JDK 25 (Zulu) sowie den VS-Code-Erweiterungen für Java und Gradle.

1. [VS Code](https://code.visualstudio.com/) und die Erweiterung [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) installieren (Docker muss lokal laufen).
2. Repository in VS Code öffnen.
3. Über die Befehlspalette **Dev Containers: Reopen in Container** ausführen (oder den Hinweis-Dialog unten rechts bestätigen).
4. VS Code baut das Container-Image und richtet die Umgebung automatisch ein (`postCreateCommand` macht `gradlew` ausführbar und prüft die Gradle-Version).

Alternativ mit der [GitHub CLI](https://cli.github.com/) bzw. [GitHub Codespaces](https://github.com/features/codespaces) direkt im Browser starten: **Code → Create codespace on main**.

## Build

```bash
./gradlew build
```

## Tests

```bash
./gradlew test
```

Die Tests sind nach dem Given-When-Then-Muster in [docs/tests.md](docs/tests.md) dokumentiert.

## CI

Bei jedem Push/Pull-Request auf `main` führt die GitHub-Actions-Pipeline ([.github/workflows/ci.yml](.github/workflows/ci.yml)) automatisch Tests und Build aus.
