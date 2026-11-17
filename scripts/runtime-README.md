# TicTacTest aus Release-Assets starten

Benötigt: Java 25, Python 3, Bash, `ttyd` (getestet mit 1.7.7) und `unzip`.
Diese Werkzeuge sind Laufzeitvoraussetzungen, keine Dateien aus einem Git-Checkout.
Ein Java-Build, Node.js oder ein Klonen des Repositorys ist zum Spielen nicht nötig.
Die lokalen Python-Webserver sind für den Versuch gedacht, nicht für öffentlichen
Produktionsbetrieb.

## Herunterladen und prüfen

Lade aus demselben GitHub-Release das Jar, das Frontend-Archiv, das Runtime-Archiv
und jeweils deren `.sha256`-Datei in einen leeren Ordner herunter.
Die Version dieses Pakets ist:

```bash
VERSION="@VERSION@"
sha256sum -c "tictactest-$VERSION.jar.sha256"
sha256sum -c "tictactest-frontend-$VERSION.zip.sha256"
sha256sum -c "tictactest-runtime-$VERSION.zip.sha256"
unzip "tictactest-frontend-$VERSION.zip" -d frontend
unzip "tictactest-runtime-$VERSION.zip" -d runtime
```

## Drei lokale Prozesse

Die folgenden Befehle jeweils vom entpackten Release-Ordner aus in getrennten
Terminals starten; `VERSION` in jedem Terminal auf die oben genannte Version setzen.
Die Standard-Ports sind 7681 (Terminal), 7682 (Versionsdatei) und 8000 (Frontend).

Terminal 1:

```bash
VERSION="@VERSION@"
bash runtime/start-console.sh "tictactest-$VERSION.jar"
```

Das Startskript liest die Backend-Version aus genau diesem Jar in `version.txt` aus
und startet dann `ttyd` mit direktem `java -jar`-Aufruf, nicht mit einer Shell.
Es bindet nur an Loopback, prüft den WebSocket-Origin und erlaubt höchstens vier
Spielverbindungen. `-Xmx64m` begrenzt nur den Java-Heap, nicht den gesamten RAM.

Falls Java oder ttyd nicht im Suchpfad liegen, die Pfade explizit setzen:

```bash
JAVA_BIN=/pfad/zu/java TTYD_BIN=/pfad/zu/ttyd \
  bash runtime/start-console.sh "tictactest-$VERSION.jar"
```

Terminal 2:

```bash
python3 -B runtime/serve-backend-version.py version.txt \
  --allow-origin http://localhost:8000 \
  --allow-origin http://127.0.0.1:8000
```

Terminal 3:

```bash
python3 -m http.server 8000 --bind 127.0.0.1 --directory frontend
```

Im Browser `http://localhost:8000/` öffnen. Das Terminal muss Eingaben annehmen,
beide Versionsanzeigen müssen zur Auswahl der Assets passen. Feldnummer 0–8 und
Enter geben einen Zug ein; Enter verbindet nach Spielende neu.

Zum Beenden in den drei Terminals jeweils Strg+C drücken.

## Andere Umgebung konfigurieren

`frontend/config.js` enthält nur öffentliche Adressen, niemals Secrets. Für eine
andere Umgebung genau diese Datei in der entpackten Kopie ersetzen. Den passenden
Frontend-Origin zusätzlich beim Versionsserver mit `--allow-origin` freigeben.
Bei HTTPS müssen auch die konfigurierten Backend-Adressen HTTPS verwenden.

`TTYD_PORT` und `VERSION_FILE` können beim Konsolenstart abweichende Werte setzen.
Der Versionsserver nimmt `--port` und den Pfad zu dieser Datei entgegen. Die Adressen
in `config.js` und die CORS-Allowlist müssen dazu passen. Das sind Umgebungswerte,
keine Gründe für eine Änderung an `app.js` oder am Jar.

Die Versionsdatei ist kein Gesundheitscheck: Nach einem Jar-Wechsel muss sie durch
Start des ausgewählten Jars neu erzeugt werden. Ein vorhandener Wert allein beweist
nicht, dass ein Java-Prozess läuft.

## Warum diese Dateien im Release liegen

Frontend und Startwerkzeuge gehören zur Anwendung: Sie müssen zusammen mit ihrem
Release nachvollziehbar herunterladbar und bei einem Rollback wiederverwendbar sein.
Die Archive enthalten keine Testdateien, privaten Vorschauadressen oder Zugangsdaten.
Java, ttyd und Python werden als Voraussetzungen installiert. EC2, Firewall,
Systemd-Units und ein vorgeschalteter Produktions-Webserver gehören zur späteren
Infrastruktur und sind hier bewusst nicht eingerichtet.
