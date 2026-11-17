# TicTacTest als Web-Konsole

Diese Dokumentation begleitet Auftrag 1 schrittweise. Die praktischen Versuche aus
Teil 1 sind durchgeführt. Teil 2 ist ebenfalls umgesetzt: Die Version wird aus dem
Release-Jar ausgelesen und ist per HTTP abrufbar. Teil 3 ergänzt das statische
Frontend mit konfigurierbaren Adressen und beiden Versionsanzeigen. Teil 4 ist
ebenfalls abgeschlossen: v1.1.0 wurde veröffentlicht und die frisch heruntergeladenen
Release-Assets wurden ohne Git-Checkout im Browser geprüft. Die Cloud-Infrastruktur
gehört erst zu Auftrag 2 und ist noch nicht eingerichtet.

## Teil 1 – Werkzeug und Funktionsweise

Wir verwenden **ttyd 1.7.7**. Es enthält bereits ein Browser-Terminal und kann direkt
das vorhandene Java-Spiel starten. Dadurch sind weder Änderungen am Spiel noch ein
eigenes Terminal-Frontend erforderlich. Das Werkzeug wird auch im Auftrag empfohlen.

```text
Browser-Terminal ←→ WebSocket ←→ ttyd ←→ Pseudo-Terminal ←→ java -jar …
```

- **WebSocket:** Die Verbindung überträgt Eingaben und Ausgaben in beide Richtungen,
  ohne dass nach jedem Zug eine neue Webseite geladen werden muss.
- **Pseudo-Terminal (PTY):** Es stellt dem Java-Prozess ein Terminal bereit, obwohl
  keine physische Tastatur und kein Bildschirm am Prozess hängen.
- **Eigener Prozess pro Verbindung:** Jede aktive Spielverbindung erhält einen
  eigenen Java-Prozess. Die Spiele haben getrennte Spielzustände.
- **Zwei Lebenszyklen:** Das Java-Spiel endet nach einer Partie oder einem nicht
  abgefangenen Fehler. Der Web-Konsolen-Server ttyd läuft unabhängig davon weiter.

## Verwendetes Release-Artefakt

Getestet wurde das unveränderte Asset `tictactest-1.0.1.jar` aus
[Release v1.0.1](https://github.com/philderks/450-tictactest-mvk/releases/tag/v1.0.1).
Es wurde **nicht lokal gebaut**. Die SHA-256-Prüfsumme wurde gegen das ebenfalls im
Release veröffentlichte Asset geprüft:

```text
594abef02aef0704069a7a5922a095a2556f63764d14abb4fe248025576c5f03
```

Der Versuch verwendet Amazon Corretto **25.0.5.0.10**. Java 25 und ttyd wurden
separat bereitgestellt, ohne das systemweit installierte Java auszutauschen.
Das ttyd-Binary für Linux x86_64 stammt aus dem
[offiziellen Release 1.7.7](https://github.com/tsl0922/ttyd/releases/tag/1.7.7);
seine Prüfsumme wurde mit der dortigen Datei `SHA256SUMS` verglichen.

Quellcode und Artefakt sind nicht dasselbe: Der Quellcode lässt sich bearbeiten,
das Release-Jar ist das bereits gebaute, veröffentlichte Ergebnis. Für diesen
Auftrag wird genau dieses Ergebnis betrieben und nicht auf dem Zielsystem neu gebaut.

## Lokal starten

Voraussetzungen: Linux x86_64 für das genannte ttyd-Binary, Java 25, GitHub CLI für
den folgenden Download und ein freier Port 7681. Ein gleichwertiger Download über
die GitHub-Release-Seite ist möglich.

### Release herunterladen und prüfen

In einem eigenen Arbeitsordner ausführen, nicht im Ordner eines lokalen Gradle-Builds:

```bash
gh release download v1.0.1 \
  --repo philderks/450-tictactest-mvk \
  --pattern 'tictactest-1.0.1.jar' \
  --pattern 'tictactest-1.0.1.jar.sha256'
sha256sum --check tictactest-1.0.1.jar.sha256
```

### Web-Konsole starten

Im Versuch liegen das geprüfte Binary `ttyd.x86_64`, das Release-Jar und die separat
entpackte Java-Laufzeit `java25/` im selben Arbeitsordner. Dort lautet der Startbefehl:

```bash
./ttyd.x86_64 -W -O -i 127.0.0.1 -p 7681 -m 4 \
  ./java25/bin/java -Xmx64m -jar ./tictactest-1.0.1.jar
```

Wenn Java 25 bereits passend eingerichtet ist, kann statt `./java25/bin/java`
auch `java` verwendet werden. Danach im Browser desselben Rechners
`http://127.0.0.1:7681/` öffnen. Ins Terminal klicken und eine Feldnummer von
`0` bis `8`, gefolgt von Enter, eingeben.

| Option | Bedeutung im Versuch |
|---|---|
| `-W` | Eingaben erlauben; ttyd ist sonst standardmässig nur lesbar. |
| `-O` | WebSocket-Verbindungen auf passenden Origin prüfen. |
| `-i 127.0.0.1` | Nur auf der Loopback-Adresse des ausführenden Rechners lauschen. |
| `-p 7681` | Port der Web-Konsole explizit festlegen. |
| `-m 4` | Höchstens vier gleichzeitige Verbindungen zulassen. Die Ablehnung einer fünften Verbindung wurde nicht getestet. |
| `-Xmx64m` | Den maximalen Java-Heap begrenzen, nicht den gesamten RAM-Verbrauch der JVM. |

`localhost` bezeichnet immer den Rechner, auf dem der jeweilige Browser läuft.
Bei einem Versuch auf einem anderen Rechner ist ein zusätzlicher Zugangsweg nötig.
Für den gemeinsamen Test wurde ein privater Tailscale-Serve-HTTPS-Zugang verwendet;
dies ist nur ein Hilfsmittel für den Versuch, nicht das spätere EC2-Deployment.

## Sicherheit

Die Web-Konsole startet **direkt Java mit dem festgelegten Jar**, niemals eine
Shell wie `bash`, `sh` oder `login`. Sonst könnten Besucher Befehle mit den Rechten
des ausführenden Kontos ausführen, Dateien lesen oder verändern und auf erreichbare
Dienste zugreifen. Das wäre ein Fernzugriff auf das System statt nur auf das Spiel.

Der Versuch läuft als normaler Benutzer, nicht als root. URL-gesteuerte
Kommandoargumente (`ttyd -a`) sind nicht aktiviert. Loopback-Bindung und der private
Tailscale-Zugang vermeiden eine öffentliche Freigabe des Experiments. Diese
Massnahmen sind keine vollständige Sandbox: Ein Fehler im gestarteten Programm
kann weiterhin Auswirkungen im Rahmen seiner Benutzerrechte haben.

## Beobachtete Ergebnisse

Die folgenden Ergebnisse stammen aus manuellen Tests im Browser mit Release v1.0.1.

| Versuch | Beobachtung |
|---|---|
| Vollständige Partie gegen GreedyPlayer, Züge `4`, `2`, `6` | CROSS gewinnt. Danach erscheint `Press ↵ to Reconnect`. |
| Enter nach Spielende | Neue Verbindung und neues Spiel mit leerem Spielfeld. Die vorherige Partie wird nicht fortgesetzt. |
| Leere Eingabe, nur Enter | `NumberFormatException: For input string: ""`; die Partie endet. |
| Eingabe `10` | `IllegalStateException: cannot play to position 10`; die Partie endet. |
| Eingabe `sfg` | `NumberFormatException: For input string: "sfg"`; die Partie endet. |
| Enter nach diesen Eingabefehlern | Laut manuellem Benutzertest beginnt eine neue Partie. |
| Zwei gleichzeitig geöffnete Spiel-Tabs | Beide Spiele lassen sich unabhängig spielen. Während beide aktiv waren, liefen genau zwei Java-Spielprozesse. |

Leere Eingaben und Buchstaben scheitern beim Umwandeln der Eingabe in eine Zahl.
`10` lässt sich zwar als Zahl lesen, bezeichnet aber kein erlaubtes Feld. In beiden
Fehlerklassen endet das Spiel; die Web-Konsole bleibt für eine erneute Verbindung
verfügbar. Für diesen Auftrag wird das Verhalten dokumentiert, nicht durch eine
Änderung des Release-Jars repariert.

### Speicherbedarf mehrerer Spiele

Bei einer Momentaufnahme während des Zweitab-Tests ergaben sich folgende Werte aus
`/proc/<PID>/status` (`VmRSS`):

| Aktiver Java-Spielprozess | RAM-Verbrauch (RSS) |
|---|---:|
| Spielprozess 1 | 41,32 MiB |
| Spielprozess 2 | 41,65 MiB |

RSS beschreibt die im RAM befindlichen Speicherseiten eines Prozesses und enthält
auch geteilte Seiten. Eine Summe der RSS-Werte kann geteilten Speicher daher mehrfach
zählen. Die Werte sind eine Momentaufnahme dieses Versuchs, keine garantierten
Maximalwerte und kein Lasttest auf einer 1-GB-EC2-Instanz.

Für eine kleine Instanz ist die eigene JVM pro Besucher entscheidend: Weitere
Spielverbindungen benötigen zusätzliche Ressourcen. Betriebssystem, Web-Konsole
und später gegebenenfalls ein vorgeschalteter Webserver benötigen ebenfalls RAM.
Daher lässt sich die sichere Spielerzahl nicht einfach aus 1 GB geteilt durch den
beobachteten Speicher eines Spiels bestimmen. Verbindungsgrenze, Heap-Begrenzung
und Messungen auf der tatsächlichen Zielinstanz sind getrennt zu betrachten.

## Teil 2 – Versionsabfrage per HTTP

Das heruntergeladene Jar enthält in `META-INF/MANIFEST.MF` bereits:

```text
Implementation-Version: 1.0.1
```

Diese Versionsnummer wurde direkt aus dem Release-Artefakt gelesen, nicht aus dem
aktuellen Quellcode und nicht aus einer manuell gepflegten Versionsdatei. Der
[Release-Prozess](../RELEASE.md#versionsnummer) erklärt, wie sie beim Build ins
Manifest gelangt.

Das Skript [`scripts/backend-version.py`](../scripts/backend-version.py) liest die
Version aus dem Hauptabschnitt dieses Manifests und schreibt sie mit einem
Zeilenumbruch in die angegebene Ausgabedatei. Python 3 genügt; zusätzliche Pakete
oder ein erneuter Java-Build sind nicht nötig.

Vom Repository aus aufrufen (beide Beispielpfade durch die eigenen Pfade ersetzen;
der Ausgabeordner muss bereits existieren):

```bash
python3 scripts/backend-version.py \
  /pfad/zum/tictactest-1.0.1.jar \
  /pfad/zur/version.txt
```

Beim Versuch mit unserem echten Release-Jar enthält die erzeugte Datei:

```text
1.0.1
```

Es gibt keine fest eingetragene Versionsnummer im Skript. Bei jedem Bereitstellen
muss es mit dem dafür ausgewählten Jar ausgeführt werden; ein Jar-Wechsel allein
aktualisiert die Datei noch nicht. Die spätere Deployment-Automatisierung muss
diesen Schritt mit dem Versionswechsel verbinden.

Fehlt `Implementation-Version` oder ist sie leer, endet das Skript mit einem
Fehler und lässt eine bisherige Versionsdatei unverändert. Auch das versehentliche
Überschreiben des Release-Jars durch den Ausgabepfad wird abgewiesen.

Die drei automatisierten Tests prüfen die Manifest-Version trotz abweichendem
Dateinamen, fehlende Versionsmetadaten und den Schutz vor Überschreiben des Jars:

```bash
python3 -B -m unittest discover -s scripts/tests -v
```

Alle drei Tests bestanden. Zusätzlich wurde das Skript mit dem echten Release-Jar
v1.0.1 ausgeführt, die erzeugte Datei gelesen und die unveränderte SHA-256-Prüfsumme
des Jars kontrolliert.

### Warum ein zusätzlicher HTTP-Endpunkt?

ttyd überträgt die interaktive Terminal-Ein-/Ausgabe. Das Frontend und später die
Deployment-Pipeline sollen die Versionsnummer aber mit einer einfachen
HTTP-GET-Anfrage lesen können, ohne eine Spielverbindung zu öffnen.

```text
Release-Jar → Manifest auslesen → version.txt → Webserver → HTTP-GET

Browser → /             → ttyd → Java-Spiel
Browser → /version.txt  → automatisch erzeugte Versionsdatei
```

Der Webserver übernimmt die Auslieferung. Das Spiel selbst braucht dafür weder
einen HTTP-Server noch Änderungen an seinem Code.

### Lokal ohne Tailscale ausprobieren

Die folgenden Befehle im Repository ausführen. `RUNTIME_DIR` bezeichnet den eigenen
Arbeitsordner mit dem zuvor heruntergeladenen Release-Jar; den Beispielpfad anpassen:

```bash
RUNTIME_DIR="$HOME/tictactest-local"
mkdir -p "$RUNTIME_DIR/public"
python3 scripts/backend-version.py \
  "$RUNTIME_DIR/tictactest-1.0.1.jar" \
  "$RUNTIME_DIR/public/version.txt"
python3 -m http.server 7682 --bind 127.0.0.1 \
  --directory "$RUNTIME_DIR/public"
```

In einem zweiten Terminal abfragen:

```bash
curl --fail --silent --show-error http://127.0.0.1:7682/version.txt
```

Die Antwort ist `1.0.1`, ohne Terminal-Escape-Codes oder Spielausgabe. In diesem
separaten Web-Verzeichnis liegt nur die erzeugte Versionsdatei, nicht das Jar,
Quellcode oder Zugangsdaten. Den einfachen Python-Server verwenden wir ausschliesslich
für den lokalen Versuch, nicht als Empfehlung für den öffentlichen Cloud-Betrieb.

### Privater gemeinsamer Versuch mit Tailscale Serve

In Teil 2 lieferte Tailscale Serve bereits das Terminal über HTTPS aus. Wir haben
auf demselben HTTPS-Port 8443 einen zusätzlichen Handler für genau
die vorhandene Datei `version.txt` ergänzt. Die Terminal-Route `/` bleibt bestehen;
es wird kein ganzes Arbeitsverzeichnis freigegeben.

Für den anschliessenden Versuch mit getrennten Frontend-/Backend-Origins ersetzt
Teil 3 diesen Datei-Handler durch einen Proxy zum CORS-fähigen Versionsendpunkt.

Für einen bereits bestehenden privaten Konsolen-Zugang, mit dem absoluten Pfad zur
erzeugten Datei (Beispielpfad ersetzen):

```bash
VERSION_FILE="/absoluter/pfad/zur/version.txt"
sudo tailscale serve --bg --https=8443 --set-path=/version.txt "$VERSION_FILE"
tailscale serve status
```

Die ausgegebene HTTPS-Adresse mit dem Pfad `/version.txt` lässt sich im Browser
oder mit `curl --fail` öffnen. Tailscale muss auf dem zugreifenden Rechner verbunden
sein. Tailscale Funnel wurde nicht aktiviert: Der Zugang bleibt auf das Tailnet
beschränkt. Diese Freigabe ist nur die Zugangshilfe für unseren lokalen Versuch,
keine Voraussetzung für die spätere AWS-Lösung. Dort kann beispielsweise nginx
die Versionsdatei neben der vorgeschalteten Web-Konsole ausliefern.

### Nachweise für Teil 2

- Vor der Einrichtung lieferte die private Versionsadresse HTTP 404, danach HTTP 200.
- Die HTTP-Antwort hatte `Content-Type: text/plain; charset=utf-8` und den Inhalt
  `1.0.1` mit abschliessendem Zeilenumbruch.
- Die Antwort wurde automatisch mit `Implementation-Version` im echten Release-Jar
  verglichen; beide stimmten überein.
- Die Versionsnummer wurde zusätzlich im Browser geöffnet und gelesen.
- Das Spiel war weiterhin erreichbar; ein Zug wurde über denselben HTTPS-Zugang
  eingegeben und im Spielfeld dargestellt.
- Die direkten URL-Pfade zum Jar und zum Python-Skript lieferten weiterhin HTTP 404.
- Die bestehende Hermes-Weboberfläche auf HTTPS-Port 443 blieb unverändert.
- Die lokale Python-HTTP-Server-Variante wurde ebenfalls mit der aus dem echten Jar
  erzeugten Versionsdatei getestet und lieferte HTTP 200 mit demselben Inhalt.
- Die SHA-256-Prüfsumme des Release-Jars blieb unverändert.

**Wichtig für spätere Deployments:** Der Endpunkt zeigt die aus dem ausgewählten
Artefakt erzeugten Versionsmetadaten. Er prüft nicht, ob gerade ein Java-Spielprozess
läuft oder gesund ist. Jede neue Bereitstellung muss die Versionsdatei passend zum
tatsächlich ausgewählten Jar erneuern; eine alte Datei darf nicht versehentlich als
Nachweis für eine neue Version dienen. Bei der späteren automatisierten Prüfung
soll die HTTP-Abfrage ohne Cache erfolgen.

## Teil 3 – Statisches Frontend

[`frontend/`](../frontend/) enthält nur HTML, CSS und JavaScript, ohne Framework,
Paketinstallation oder Build-Schritt:

- `index.html` und `style.css`: Titel, Spielregeln, Feldnummern und eingebettetes Terminal.
- `config.js`: öffentliche, umgebungsspezifische Server-Adressen; niemals Secrets.
- `app.js`: liest die Konfiguration, setzt das iframe-Ziel und lädt beide Versionen.
- `version.txt`: Frontend-Version. Aktuell steht darin bewusst `dev`: Ein eigenes
  Frontend-Release entsteht erst in Teil 4. Dies ist nicht die Backend-Version.

### Konfiguration statt fest eingebauter Server-Adresse

Die im Repository enthaltene `config.js` zeigt auf lokale Dienste:

```javascript
window.TICTACTEST_CONFIG = {
  consoleUrl: 'http://localhost:7681/',
  backendVersionUrl: 'http://localhost:7682/version.txt',
};
```

Die HTML-Datei lädt zuerst `config.js`, dann `app.js`. Für eine andere Umgebung
wird nur die Konfigurationsdatei in der bereitgestellten Kopie ersetzt, nicht der
Anwendungscode. Die Konfiguration des privaten gemeinsamen Versuchs liegt ausserhalb
des Repositories. Bei einer HTTPS-Seite müssen auch die Backend-Adressen HTTPS
verwenden, sonst kann der Browser Mixed Content blockieren.

### Getrennte lokale Dienste starten

Das Terminal aus Teil 1 läuft weiterhin auf Port 7681. Die Versionsdatei aus Teil 2
muss vorher aus dem ausgewählten Release-Jar erzeugt worden sein. Statt des einfachen
Dateiservers verwenden wir jetzt den kleinen, nur lesenden Versionsserver mit einer
expliziten Liste erlaubter Frontend-Origins (Beispielpfad ersetzen):

```bash
python3 -B scripts/serve-backend-version.py /pfad/zur/version.txt \
  --allow-origin http://localhost:8000 \
  --allow-origin http://127.0.0.1:8000
```

Er bindet standardmässig nur an `127.0.0.1:7682` und liefert ausschliesslich
`/version.txt`. Andere Pfade erhalten HTTP 404; eine fehlende Versionsdatei führt
zu HTTP 503. Antworten mit Versionsdaten haben `Cache-Control: no-store`.

In einem weiteren Terminal das Frontend separat starten:

```bash
python3 -m http.server 8000 --bind 127.0.0.1 --directory frontend
```

Danach `http://localhost:8000/` im Browser öffnen. Damit laufen drei kleine Prozesse:
ttyd für das Spiel, der Versionsserver und der statische Frontend-Server. Die beiden
Backend-Endpunkte sind separat konfigurierbar; ein vorgeschalteter Webserver kann
sie wie im privaten Versuch unter einer gemeinsamen Backend-Adresse zusammenführen.

### Beobachtung: iframe funktioniert, Versionsabfrage zunächst nicht

Im ersten Browser-Versuch wurde das Terminal eingebettet, aber die JavaScript-Abfrage
der Backend-Version scheiterte: Das Frontend zeigte `nicht erreichbar`, während die
eigene Frontend-Version `dev` geladen wurde. Der Backend-Datei-Handler lieferte keinen
`Access-Control-Allow-Origin`-Header. Nach der gezielten Freigabe wurde `1.0.1`
auch im Frontend angezeigt.

Eine Origin besteht aus **Schema, Host und Port**. Auch zwei Adressen auf demselben
Host sind bei unterschiedlichen Ports verschiedene Origins. Das Einbetten eines
iframes erlaubt dem übergeordneten JavaScript nicht automatisch, fremde HTTP-Antworten
zu lesen. Deshalb ist die CORS-Freigabe für den Versions-GET erforderlich.

`--allow-origin` lässt sich mehrfach angeben. Nur bei einem exakt passenden
`Origin`-Request-Header sendet der Versionsserver `Access-Control-Allow-Origin`
mit dieser Adresse; `Vary: Origin` kennzeichnet die originabhängige Antwort.
Es gibt keine pauschale Stern-Freigabe und keine Cookies/Zugangsdaten für den GET.
CORS ist eine Browser-Leseregel, keine Authentifizierung: Der private Zugang wird
weiterhin durch das Tailnet begrenzt, nicht durch CORS.

Im privaten Versuch verwendet das Frontend HTTPS-Port 8444, das Backend 8443.
Für dessen Versionsroute wird der bisherige Datei-Handler durch einen Proxy zum
lokalen Versionsserver ersetzt. In dessen Allowlist steht die genaue HTTPS-Origin
des Frontends (Hostnamen im Beispiel ersetzen):

```bash
sudo tailscale serve --bg --https=8443 --set-path=/version.txt \
  http://127.0.0.1:7682/version.txt
sudo tailscale serve --bg --https=8444 http://127.0.0.1:8000
```

Die zusätzliche Origin wird beim Start des Versionsservers mit
`--allow-origin https://DEIN-TAILSCALE-HOST:8444` angegeben. Die Terminal-Route auf
8443 und die bestehende Hermes-Oberfläche auf 443 bleiben unverändert; kein Funnel.

### Prüfung

- Über das eingebettete Terminal eine ganze Partie mit den Zügen `4`, `2`, `6`
  gespielt: `the winner is: CROSS` und anschliessender Reconnect-Hinweis.
- Nach der CORS-Freigabe beide Versionsanzeigen geprüft: Backend `1.0.1`, Frontend `dev`.
- Desktop- und schmale Mobilansicht geprüft, ohne horizontales Seiten-Overflow.
- Versionsabfragen umgehen den Cache und haben ein Zeitlimit von fünf Sekunden.
  Ein Abfragefehler wird sichtbar angezeigt, statt einen erfolgreichen Backend-Check
  vorzutäuschen. Ein Versionsfehler verhindert nicht das Öffnen des Terminals.
- Automatisierte Tests prüfen konfigurierte URLs, unabhängige Versionsanzeigen,
  Fehlerfälle und den HTTP-Endpunkt inklusive CORS-Allowlist und gesperrter Pfade:

```bash
python3 -B -m unittest discover -s scripts/tests -v
node --test scripts/tests/frontend.test.cjs
```

Node.js ist nur für diese JavaScript-Tests erforderlich, nicht für das Frontend
selbst. Die lokalen Python-Webserver sind Versuchswerkzeuge, keine Empfehlung für
den öffentlichen Produktionsbetrieb. Die Release-Erweiterung folgt in Teil 4;
AWS ist noch nicht eingerichtet.

## Teil 4 – Release um Web-Assets erweitern

Die Erweiterung ist als Version **1.1.0** veröffentlicht. Der bestehende Release-Workflow
behält Tag-Trigger, Versionsprüfung, Main-Ancestry-Check, Java-Tests, Build und
Jar-Smoke-Test bei. Neu prüft er auch Frontend und Runtime-Werkzeuge und lädt neben
dem Jar zwei ZIP-Dateien hoch, alle drei Artefakte mit eigener SHA-256-Prüfsumme.
Ein normaler Branch-Push erstellt weiterhin keinen Release und deployt keine App.

[`scripts/package-web-release.py`](../scripts/package-web-release.py) erhält die
bereits vom Workflow geprüfte Version. Es paketiert nur die benötigten Dateien,
setzt im Frontend-Archiv `version.txt` auf diese Version und lässt
`frontend/version.txt` im Checkout unverändert bei `dev`. Ungültige Versionswerte
werden vor Dateierzeugung abgewiesen.

Das Frontend-Archiv enthält die statischen Dateien und eine lokale öffentliche
Konfigurationsvorlage. Das zusätzliche Runtime-Archiv enthält das Startskript und
die beiden Python-Werkzeuge sowie eine Anleitung. Alle eigenen Dateien zum Starten
sind damit in den Assets enthalten; Java 25, ttyd, Bash und Python sind installierte
Voraussetzungen. EC2, Firewall, Systemd und ein Produktions-Webserver gehören zur
Infrastruktur, nicht in dieses Anwendungspaket.

Auch ein kleines Frontend braucht einen eingefrorenen Stand: Ein versioniertes
Archiv macht Auslieferung und Rollback unabhängig vom aktuellen Branch. Ein Nutzer
kann die Assets direkt herunterladen und starten, ohne Repository, Build oder Node.
Umgebungsadressen werden erst in der entpackten `config.js` gesetzt.

Vollständiger Ablauf, Asset-Liste und Downloadbefehle stehen in
[RELEASE.md](../RELEASE.md#release-testen). Die Vorlage der mitgelieferten Anleitung
liegt in [`scripts/runtime-README.md`](../scripts/runtime-README.md).

### Bereits durchgeführter Vorabtest – noch kein veröffentlichter Release

1. `clean check pitest jar` mit Java 25 erfolgreich ausgeführt: 28 reguläre Tests
   und 8 E2E-Tests ohne Fehler; Branch-Gate bestanden. PIT erkannte 71 von 87 Mutationen.
2. Frontend- und Runtime-Archiv für 1.1.0 erzeugt und zusammen mit dem gebauten Jar
   sowie den Prüfsummen in einen separaten Ordner ausserhalb des Checkouts kopiert.
   Die sechs Kandidaten-Dateien und alle drei Prüfsummen wurden geprüft.
3. Beide Archive dort entpackt. Nur die öffentliche `config.js` der entpackten Kopie
   auf freie Testports angepasst; kein Anwendungscode aus dem Checkout verwendet.
4. Das enthaltene `start-console.sh` startete das Kandidaten-Jar direkt in ttyd und
   erzeugte die Backend-Versionsdatei aus dessen Manifest. Auch Versionsserver und
   Frontend wurden ausschliesslich aus den entpackten Assets gestartet.
5. Im Browser wurden Backend **1.1.0** und Frontend **1.1.0** angezeigt. Im iframe
   wurde mit `4`, `2`, `6` gewonnen; die tatsächlich empfangene Terminal-Ausgabe
   enthielt `...and the winner is: CROSS`.
6. Die zusätzlichen Testserver wurden anschliessend beendet; der bisherige private
   Zugang aus Teil 3 blieb bestehen. Das Jar blieb beim Starten unverändert.

Zusätzlich bestanden 10 Python-Tests und 3 JavaScript-Tests; `actionlint` prüfte
die geänderten Workflows ohne Befund. Die CI enthält einen eigenen `web-checks`-Job,
damit die neuen Prüfungen auch bei Branch-Pushes laufen.

### Abschlussnachweis mit veröffentlichten Assets

Am **17. November 2026** wurde nach ausdrücklicher Freigabe zuerst
[PR #11 nach dev](https://github.com/philderks/450-tictactest-mvk/pull/11) und danach
[PR #12 nach main](https://github.com/philderks/450-tictactest-mvk/pull/12) gemergt.
CI und Coverage Gate waren grün; der Main-Ancestry-Check blieb unverändert aktiv.

- Annotierter Tag: `v1.1.0`, Commit `1ea23ba075fce9cc9ea09061ee0e272b2f63a45b`.
- [Veröffentlichter Release](https://github.com/philderks/450-tictactest-mvk/releases/tag/v1.1.0),
  kein Draft und kein Prerelease; Release-ID `448542770`.
- [Release-Lauf 44075124349](https://github.com/philderks/450-tictactest-mvk/actions/runs/44075124349)
  erfolgreich; auch die CI auf dem Main-Merge war erfolgreich.
- Alle **sechs** veröffentlichten Assets in einen neuen, leeren Ordner ausserhalb
  des Checkouts heruntergeladen. Die drei mitgelieferten Prüfsummen und zusätzlich
  die sechs Asset-Digests aus der GitHub-API stimmten mit den Downloads überein.
- Nur die heruntergeladenen ZIPs entpackt und deren eigene Runtime-Werkzeuge
  gestartet. Keine Anwendungsdatei aus dem Checkout und kein erneuter Build waren
  für das Starten nötig. Lediglich die öffentliche `config.js` wurde angepasst.
- Im echten Browser zeigten Backend und Frontend **1.1.0**. Die Partie im iframe
  wurde mit `4`, `2`, `6` gewonnen; die empfangene Terminal-Ausgabe enthielt
  `...and the winner is: CROSS`.
- Das veröffentlichte Jar wurde nach dem Spielen erneut gegen seine unveränderte
  Prüfsumme geprüft. Seine SHA-256 lautet:

```text
5d7ce03c167f39484506eda7d6325f5e280200231ba8fa4a2246567fc0bd1c0f
```

Der bestehende private Vorschauzugang wurde danach auf genau diese heruntergeladenen
Release-Assets umgestellt und erneut im Browser geprüft: beide Versionen 1.1.0,
Terminal-Eingabe funktioniert. Die Hermes-Oberfläche blieb unverändert, kein Funnel
wurde aktiviert. Das ist weiterhin ein lokaler/tailnet-interner Versuch, kein
AWS-Deployment und noch keine Deployment-Automatisierung aus Auftrag 3.

**Auftrag 1 ist damit vollständig verifiziert. Als Nächstes folgt Auftrag 2:**
die bestehende OpenTofu-/EC2-Konfiguration prüfen, erweitern und von Hand deployen.
