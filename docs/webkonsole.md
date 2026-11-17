# TicTacTest als Web-Konsole

Diese Dokumentation begleitet Auftrag 1 schrittweise. Die praktischen Versuche aus
Teil 1 sind durchgeführt. In Teil 2 wird die Versionsdatei automatisch aus dem Jar
erzeugt; eine HTTP-Versionsabfrage ist noch nicht eingerichtet. Frontend und
Release-Erweiterung folgen später.

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

## Teil 2 – Versionsabfrage: Versionsdatei erzeugen

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

**Noch offen in Teil 2:** Die Datei per HTTP ausliefern und die Antwort überprüfen.
Das Jar bleibt unverändert. Die Versionsdatei allein ist noch kein Nachweis, dass
das Spiel tatsächlich gesund läuft.
