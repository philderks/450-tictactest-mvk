# TicTacToe

Ein kleines TicTacToe-Spiel in Java mit einem menschlichen Spieler (`HumanPlayer`) und einem einfachen Computer-Spieler (`GreedyPlayer`), der stets das erste freie Feld belegt.

## Voraussetzungen

- JDK 25 (wird über den Gradle-Toolchain-Mechanismus bei Bedarf automatisch bezogen)

## Dev Container einrichten

Die Entwicklungsumgebung ist ein fertig gebautes Image aus der GitHub Container Registry
(`ghcr.io/philderks/tictactest-devcontainer`): Alpine mit JDK 25, Gradle und einem Benutzer
mit UID:GID 1000:1000. Dieselbe Version wird auch von der CI/CD-Pipeline verwendet.

1. [VS Code](https://code.visualstudio.com/) und die Erweiterung [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) installieren (Docker muss lokal laufen).
2. Einmalig an der Registry anmelden (das Package ist privat, Token-Scope `read:packages`):

   ```bash
   echo "$GITHUB_TOKEN" | docker login ghcr.io -u <github-user> --password-stdin
   ```

3. Repository in VS Code öffnen und über die Befehlspalette **Dev Containers: Reopen in Container** ausführen.
4. Das freigegebene Image wird automatisch gezogen, VS Code ist danach startklar.

Nach einem `git pull` mit aktualisierter DevContainer-Version bietet VS Code den Rebuild
automatisch an. Versionierung, Freigabeprozess und Continuous Deployment des Containers
sind in [docs/devcontainer.md](docs/devcontainer.md) beschrieben.

Alternativ mit [GitHub Codespaces](https://github.com/features/codespaces) direkt im Browser starten: **Code → Create codespace on main**.

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

Bei jedem Push/Pull-Request auf `main` führt die GitHub-Actions-Pipeline ([.github/workflows/ci.yml](.github/workflows/ci.yml)) automatisch Tests, Coverage-Prüfung und Build aus – im selben DevContainer-Image wie lokal. Ein Pull Request wird zusätzlich vom [Coverage Gate](.github/workflows/coverage-gate.yml) gegen `main` geprüft.

Der DevContainer selbst wird über den Git-Commit-Hash versioniert, mit dem Merge nach `main` freigegeben und per automatischem Pull Request ausgerollt – siehe [docs/devcontainer.md](docs/devcontainer.md).
