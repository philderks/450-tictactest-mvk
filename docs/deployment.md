# Manuelles TicTacTest-Deployment auf EC2

## Einordnung und bewusste Grenze

Dies ist die erste manuelle EC2-Deployment-Etappe aus Webapp-Auftrag 2, nicht
bereits der vollständige Auftrag. Die bestehende Instanz aus `infra/` wird
weiterverwendet. Ein Release-Deploy baut weder das Jar noch die Instanz neu.

Für diese Etappe bleibt der Zugang bewusst **privat**:

```text
Browser im Tailnet
  -> Tailscale Serve auf dem Hermes-Host
  -> lokaler SSH-Tunnel
  -> EC2: nginx auf 127.0.0.1:8080
       |-> statisches Release-Frontend
       |-> /backend-version.txt aus dem verwendeten Jar
       `-> /console/ -> ttyd auf 127.0.0.1:7681 -> java -jar
```

Die AWS-Security-Group bleibt unverändert: SSH nur vom freigegebenen
Administrationshost. Es werden weder Port 80 noch 443 oder 7681 öffentlich
geöffnet. Die öffentliche Erreichbarkeit und feste IP aus dem vollständigen
Auftrag 2 sind damit ausdrücklich **noch nicht erfüllt**.

## Voraussetzungen

- Aktive Learner-Lab-Session und gültiges lokales Profil `tictactest-lab`.
- Bestehende Instanz, lokaler OpenTofu-State und bereits sicher geprüfter
  SSH-Hostschlüssel; siehe [IaC-Nachweis](../infra/README.md).
- Der eigene private SSH-Schlüssel liegt auf dem Hermes-Host ausserhalb von Git.
- Öffentlicher GitHub-Release `v1.1.0` mit Jar, Frontend- und Runtime-ZIP und den
  drei zugehörigen SHA-256-Dateien.

Keine temporären AWS-Zugangsdaten werden auf die Instanz kopiert. Der öffentliche
Release kann ohne GitHub-Token heruntergeladen werden. Bei einem privaten
Repository müsste der Artefaktzugang separat und sicher gelöst werden.

## Infrastrukturvorbereitung und Deployment sind getrennt

- `infra/bootstrap/install-runtime.sh`: auf der Instanz die feste
  Laufzeitumgebung, Dienstbenutzer, nginx-Konfiguration und systemd-Units
  einrichten. Das Skript wählt keine Applikationsversion.
- `infra/scripts/deploy-release.sh VERSION`: veröffentlichte Artefakte beziehen,
  prüfen und die ausgewählte Version aktivieren. Kein Git-Checkout und kein
  Java-Build auf EC2, kein `tofu apply` pro Release.
- `infra/access/tictactest-ec2-tunnel@.service`: privater Zugang über den
  Administrationshost; keine zusätzliche AWS-Firewallregel.

Die Installationsdateien werden hier zunächst manuell per SSH ausgeführt.
Eine Einbindung der Einrichtung in `user_data` sowie weitere AWS-Ressourcen
sind spätere, getrennte Schritte. Diese Etappe behauptet noch keine vollständige
Wiederherstellung allein durch `tofu destroy` und `tofu apply`.

## Versionsgebundene Laufzeit

Für die bestehende Amazon-Linux-2023-Instanz wurden die folgenden Pakete
verifiziert und installiert:

- `java-25-amazon-corretto-headless`, Epoch/Version
  `1:25.0.5.1.2-1.amzn2023.1.x86_64`.
- `nginx`, Epoch/Version `1:1.30.6-1.amzn2023.0.1.x86_64`.

`ttyd` wird auf `1.7.7` festgelegt. Die offizielle Datei `ttyd.x86_64` wird
vor der Installation gegen den veröffentlichten SHA-256-Wert
`8a217c968aba172e0dbf3f34447218dc015bc4d5e59bf51db2f2cd12b7be4f55` geprüft.

Nicht unbemerkt «latest» verwenden. Wenn eine Paketversion künftig nicht mehr
verfügbar ist, die Version bewusst neu prüfen und dokumentieren statt die
Versionsbindung stillschweigend zu entfernen.

## Manuelle Befehle vom Hermes-Host

Aus dem Repository-Hauptverzeichnis, auf dem bereits eingerichteten
Administrationshost:

```bash
HOST="$(tofu -chdir=infra output -raw public_ip)"
SSH_OPTIONS=(
  -i "$HOME/.ssh/tictactest_lab_ed25519"
  -o IdentitiesOnly=yes
  -o BatchMode=yes
  -o StrictHostKeyChecking=yes
  -o UserKnownHostsFile="$HOME/.local/share/tictactest-iac/known_hosts"
)

ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" 'mkdir -p "$HOME/tictactest-admin"'
scp "${SSH_OPTIONS[@]}" -r infra/bootstrap infra/scripts \
  "ec2-user@$HOST:tictactest-admin/"

ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" \
  'sudo bash /home/ec2-user/tictactest-admin/bootstrap/install-runtime.sh'
ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" \
  'sudo bash /home/ec2-user/tictactest-admin/scripts/deploy-release.sh 1.1.0'
```

Der private Schlüssel bleibt auf dem Administrationshost. Die Release-Auswahl
steht ausserhalb der systemd-Unit; Booten soll die bereits gewählte Version
starten, nicht automatisch einen neueren GitHub-Release herunterladen.

## Dienste und Versionsabfrage

Die beiden Dienste laufen als nicht privilegierter Benutzer `tictactest`:

- `tictactest-console.service`: erzeugt die Backend-Versionsdatei aus dem
  tatsächlichen Jar-Manifest und startet ttyd mit direktem `java -jar`-Aufruf,
  Origin-Prüfung und höchstens vier gleichzeitigen Spielverbindungen.
- `tictactest-web.service`: nginx nur auf Loopback; liefert das statische
  Frontend und leitet den Terminal-WebSocket weiter. Der allgemeine
  `nginx.service` wird dafür nicht gestartet.

Die öffentliche `config.js` in der entpackten Deploymentkopie verwendet
relative URLs `/console/` und `/backend-version.txt`. Backend und Frontend
haben damit denselben Origin; die unabhängig paketierte Frontend-Version
bleibt unter `/version.txt` erhalten. In `config.js` stehen keine Secrets.

## Privater Zugang

Der SSH-Tunnel wird auf dem Hermes-Host als systemd-Instanz für dessen
Benutzer betrieben. Seine nicht eingecheckte Datei unter
`/etc/tictactest-tunnel/BENUTZER.env` enthält nur `EC2_HOST`, `SSH_KEY` und
`KNOWN_HOSTS` als Adresse bzw. Dateipfade, keine privaten Schlüsselinhalte.
Er bindet ausschliesslich `127.0.0.1:18080` und leitet nach EC2-Loopback weiter.

Nach erfolgreicher lokaler Prüfung kann dieser Port mit einer eigenen
Tailscale-Serve-Route verfügbar gemacht werden. Kein Funnel, keine globale
Freigabe und kein Zurücksetzen bestehender Serve-Routen. Die genaue private
Adresse gehört nicht in den öffentlichen Quellcode.

## Abnahme dieser Etappe — 18. November 2026

- [x] Alle drei Release-Artefakte vor dem Entpacken gegen ihre SHA-256-Dateien geprüft.
- [x] Beide Dienste aktiv, als Benutzer `tictactest` und beim Booten aktiviert.
- [x] Tatsächliche Listener mit `ss` geprüft: nur `127.0.0.1:7681` und
  `127.0.0.1:8080`, keine Wildcard-Bindung der Anwendung.
- [x] Frontend und Backend melden jeweils `1.1.0`, auch über privaten HTTPS-Zugang.
- [x] Echte Browserpartie über EC2 gespielt: Züge `4`, `2`, `6`, Ausgabe
  `...and the winner is: CROSS`. Den Test-Tab danach geschlossen.
- [x] Dienste neu gestartet, Listener und alle vier HTTP-Routen erneut geprüft;
  Browserpartie lief auf den neu gestarteten Diensten.
- [x] Erneuter `tofu plan -detailed-exitcode`: Exitcode `0`, keine Änderungen.

Der installierte Jar-Hash wurde zusätzlich mit dem GitHub-Asset-Digest verglichen:
`5d7ce03c167f39484506eda7d6325f5e280200231ba8fa4a2246567fc0bd1c0f`.
Die offiziellen ZIP-Digests für denselben Release lauten:

- Frontend: `298fad9bc8aa35e5167210ef935ee1250598a7ef6be997b64b4cb3bca5575d49`.
- Runtime: `7748aff810580eb9087276ff03ec65d2151f13fde99b8e8489c625fea5947c5e`.

Screenshot und Terminalmitschnitt liegen ausserhalb von Git unter
`~/.local/share/tictactest-iac/evidence/`. Die bestehende Dashboard-Route und
beide früheren Vorschauen blieben unverändert; Funnel ist nicht aktiviert.

Die lokalen Tests umfassen 18 Runtime-/Deploymenttests, 10 bestehende
Support-Tool-Tests und 3 Frontendtests. CI führt die neuen Infrastrukturtests
im vorhandenen `web-checks`-Job mit aus; dieser Job installiert weder AWS-
Ressourcen noch Pakete auf EC2 und deployt nichts.

### Beobachtete Integrationsfallen

- Ein erster Startversuch wurde wegen nginx-Logging abgebrochen. Unter systemd
  ist stdout ein Journal-Socket; nginx kann `/dev/stdout` nicht wie eine Datei
  neu öffnen. Access-Logs liegen deshalb im beschreibbaren RuntimeDirectory
  `/run/tictactest-web/access.log` und gehen beim Dienstneustart verloren;
  Fehler gehen über `stderr` ins Journal. Die fehlgeschlagene Releasekopie
  wurde unverändert zur Diagnose aufbewahrt, bevor frisch deployt wurde.
- `libwebsockets` benötigt `AF_NETLINK` für `getifaddrs`. Ohne diese Freigabe
  konnte die an sich explizite Loopback-Option dennoch an `0.0.0.0` binden.
  Die Console-Unit erlaubt deshalb zusätzlich diese Adressfamilie. Der
  Deployment-Healthcheck prüft nun die tatsächlichen Socketadressen und weist
  Wildcard- oder fehlende Listener zurück. Die AWS-Firewall wurde nicht geöffnet.

Für den vollständigen Auftrag 2 bleiben zusätzlich feste IP, Instance Profile,
öffentliche Frontend-Auslieferung und entsprechende Outputs, ein zweiter
Release sowie die vorgeschriebenen Session-/Wiederaufbau-Experimente offen.
Keine dieser offenen Anforderungen wird durch einen einzelnen erfolgreichen
EC2-Deploy als erledigt markiert.
