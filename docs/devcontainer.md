# DevContainer: Versionierung, Freigabe, Deployment

- **Image:** `ghcr.io/philderks/tictactest-devcontainer` (GHCR, privat)
- **Definition:** [.devcontainer/Dockerfile](../.devcontainer/Dockerfile) – Alpine, Temurin JDK 25, Gradle 9.7.0, Benutzer `vscode` mit UID:GID 1000:1000

## Versionierung: Git-Commit-Hash

Der Image-Tag ist der Commit-Hash, aus dem das Image gebaut wurde, gekürzt auf 12 Zeichen:

```
ghcr.io/philderks/tictactest-devcontainer:sha-a1b2c3d4e5f6
```

Kein manuelles Hochzählen, keine Auslegungsfragen: zu jedem Image gehört genau
ein Commit und umgekehrt. Der volle Hash steht zusätzlich im Label
`org.opencontainers.image.revision`. Rollback heisst: alten `sha-…`-Wert in
`devcontainer.json` eintragen, fertig.

| Tag | entsteht bei | verwendet von |
| --- | --- | --- |
| `sha-<hash>` | Push auf `main` | `devcontainer.json` (lokal) und alle CI-Workflows – nach Merge des Auto-PR |
| `latest` | Push auf `main` | nur Bootstrap und manuelles `docker pull` |

## Freigabe

Der Workflow [devcontainer.yml](../.github/workflows/devcontainer.yml) baut das
Image bei jeder Änderung am `Dockerfile` – **gepusht wird aber nur von `main`**
(`push: ${{ github.ref == 'refs/heads/main' }}`). In einem PR wird das Image nur
gebaut und per Smoke-Test geprüft. Ein nicht freigegebenes Image existiert in der
Registry also gar nicht erst; es kann schon technisch niemand verwenden.

Zweite Stufe: Nach dem Push auf `main` öffnet der Workflow automatisch einen
Pull Request, der den neuen Hash in `devcontainer.json` **und in allen
CI-Workflows** (`.github/workflows/*.yml`) einträgt. Auf diesem PR läuft die CI
bereits mit dem neuen Image. Ist sie grün und wird der PR gemergt, ist das Image
freigegeben; erst dann ziehen CI und lokale Umgebung nach.

```
PR  ──► Image wird gebaut + getestet, NICHT gepusht
     │
     ▼ merge nach main                    (1. Freigabe)
   sha-<hash> + latest in der GHCR
     │
     ▼ Auto-PR "chore(devcontainer): …"
     ▼ merge                              (2. Freigabe)
   devcontainer.json + CI-Workflows pinnen sha-<hash>
```

## Wie CI und lokal die neueste Version bekommen

- **CI:** `container: image: …/tictactest-devcontainer:sha-<hash>` in
  [ci.yml](../.github/workflows/ci.yml) und
  [coverage-gate.yml](../.github/workflows/coverage-gate.yml). Der Tag wird vom
  Auto-PR gesetzt, die CI nutzt nach jedem Merge also automatisch den neuesten
  freigegebenen Stand. Bewusst nicht `latest`: das wird schon beim Push auf
  `main` verschoben, also vor der zweiten Freigabe. `actions/setup-java`
  entfällt, JDK und Gradle kommen aus dem Image.
- **Lokal:** `devcontainer.json` pinnt den Hash. Nach `git pull` sieht VS Code
  die geänderte Datei und bietet den Rebuild an; das Image wird dabei automatisch
  gezogen, weil der Tag lokal noch nicht existiert.

Zwei Details in den CI-Jobs: `credentials` ist nötig, weil das Package privat
ist, und `options: --user root`, weil der Runner das Workspace-Verzeichnis mit
seiner eigenen UID anlegt.

## Einmalige Einrichtung

1. **Package mit dem Repo verknüpfen**, sonst darf `GITHUB_TOKEN` weder pushen
   noch ziehen: Packages → `tictactest-devcontainer` → *Package settings* →
   *Manage Actions access* → `450-tictactest-mvk` mit Rolle **Write**.
2. **Lokal einmal anmelden** (Token-Scope `read:packages`):
   ```bash
   echo "$GITHUB_TOKEN" | docker login ghcr.io -u <github-user> --password-stdin
   ```
3. **PAT als Secret `DEVCONTAINER_PR_TOKEN` hinterlegen** (Pflicht). Der Auto-PR
   ändert Dateien unter `.github/workflows/`, und das darf `GITHUB_TOKEN` nicht.
   Ausserdem lösen PRs, die mit `GITHUB_TOKEN` erstellt werden, keine CI aus.
   Fine-grained PAT, nur dieses Repo, mit *Contents*, *Pull requests* und
   *Workflows* jeweils **Read and write**. Hinterlegen unter Settings → Secrets
   and variables → Actions.
4. Settings → Actions → General → *Allow GitHub Actions to create and approve
   pull requests* aktivieren.

## Bootstrap

Solange kein `sha-…`-Tag existiert, steht in `devcontainer.json` und in den
CI-Workflows `:latest`. Einmal den Workflow *DevContainer* im Actions-Tab auf
`main` manuell starten (`workflow_dispatch`) und den Auto-PR mergen. Danach
läuft alles von selbst.

Von Hand entspricht das (Auftrag 2, Schritt 1 und 2):

```bash
docker build -t ghcr.io/philderks/tictactest-devcontainer:latest .devcontainer
echo "$GITHUB_TOKEN" | docker login ghcr.io -u philderks --password-stdin
docker push ghcr.io/philderks/tictactest-devcontainer:latest
```
