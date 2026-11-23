# Manuelles TicTacTest-Deployment auf EC2

**Aktueller Stand (23. November 2026):** Frontend und Spiel sind nach expliziter
Freigabe öffentlich per HTTP über die Elastic IP erreichbar. Die Adresse steht
in `tofu -chdir=infra output -raw frontend_url`; HTTPS ist noch nicht eingerichtet.
Die frühere private Etappe bleibt unten als historischer Nachweis erhalten.

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

## Auftrag 2, Teil 1: feste Adresse ergänzt — 23. November 2026

Die bestehende EC2 hat jetzt eine durch OpenTofu verwaltete Elastic IP. Ergänzt
wurden nur `aws_eip.server` und `aws_eip_association.server`; weder die Instanz
noch die Firewall wurden ersetzt oder erweitert. Die ausführbaren Plan-/Apply-
Befehle und die Begründung stehen im [IaC-Nachweis](../infra/README.md#auftrag-2-teil-1-feste-adresse--23-november-2026).

Das Deployment erhält die feste Adresse über diese Schnittstelle, nicht über
eine im Skript hinterlegte IP:

```bash
tofu -chdir=infra output -raw public_ip
tofu -chdir=infra output -raw elastic_ip_allocation_id
```

Nach dem Apply wurde die Zuordnung über AWS zurückgelesen, der eigene SSH-Tunnel
auf die feste Adresse umgestellt und die bestehende private HTTPS-Route wieder
geprüft. Browserpartie mit `4`, `2`, `6`: CROSS gewinnt; beide Versionen bleiben
`1.1.0`. Der anschliessende OpenTofu-Plan meldet keine Änderungen.
Ein Session-Neustart **nach dieser EIP-Zuordnung** ist noch als gesondertes
Robustheitsexperiment offen. Der heutige erfolgreiche Autostart vor der
EIP-Ergänzung beweist nicht bereits diesen nächsten Test.

## Öffentlicher HTTP-Zugang — 23. November 2026

Dieser separat freigegebene Schritt macht denselben Release über die Elastic IP
spielbar, ohne Tailscale oder SSH-Tunnel im Browserpfad. Das Frontend bleibt auf
der EC2: kein zusätzlicher Bucket und kein neuer Applikationsrelease. Die drei
öffentlichen URLs kommen aus OpenTofu:

```bash
tofu -chdir=infra output -raw frontend_url
tofu -chdir=infra output -raw console_url
tofu -chdir=infra output -raw backend_version_url
```

### Laufzeit aktualisieren, bevor die Firewall geöffnet wird

`HOST` und `SSH_OPTIONS` wie oben setzen. Die folgenden Befehle dokumentieren
die tatsächlich angewendeten Schritte; der bisherige Dienstzustand wurde vor
jedem Ersetzen gesichert:

```bash
HOST="$(tofu -chdir=infra output -raw public_ip)"
ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" \
  'mkdir -p "$HOME/tictactest-admin/public-http-new"'
scp "${SSH_OPTIONS[@]}" infra/bootstrap/nginx.conf \
  infra/bootstrap/tictactest-web.service infra/scripts/deploy-release.py \
  "ec2-user@$HOST:tictactest-admin/public-http-new/"

ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" 'bash -s' <<'REMOTE'
set -eu
stage=/home/ec2-user/tictactest-admin/public-http-new
backup="/var/lib/tictactest-admin-backups/public-http-$(date -u +%Y%m%dT%H%M%SZ)"
sudo install -d -m 0700 "$backup"
sudo cp -p /etc/tictactest/nginx.conf "$backup/nginx.conf"
sudo cp -p /etc/systemd/system/tictactest-web.service "$backup/tictactest-web.service"
sudo cp -p /home/ec2-user/tictactest-admin/scripts/deploy-release.py "$backup/deploy-release.py"
sudo /usr/sbin/nginx -t -e stderr -c "$stage/nginx.conf"
sudo systemd-analyze verify "$stage/tictactest-web.service"
rollback() {
  sudo cp -p "$backup/nginx.conf" /etc/tictactest/nginx.conf
  sudo cp -p "$backup/tictactest-web.service" /etc/systemd/system/tictactest-web.service
  sudo cp -p "$backup/deploy-release.py" /home/ec2-user/tictactest-admin/scripts/deploy-release.py
  sudo systemctl daemon-reload
  sudo systemctl restart tictactest-web.service
}
trap 'rollback' ERR
sudo install -o root -g root -m 0644 "$stage/nginx.conf" /etc/tictactest/nginx.conf
sudo install -o root -g root -m 0644 "$stage/tictactest-web.service" /etc/systemd/system/tictactest-web.service
sudo install -o root -g root -m 0644 "$stage/deploy-release.py" /home/ec2-user/tictactest-admin/scripts/deploy-release.py
sudo systemctl daemon-reload
sudo systemctl restart tictactest-web.service
curl --retry 5 --retry-connrefused --retry-delay 1 --max-time 10 -fsS http://127.0.0.1/backend-version.txt
sudo python3 -B -c "import runpy; m=runpy.run_path('/home/ec2-user/tictactest-admin/scripts/deploy-release.py'); m['wait_healthy']('1.1.0')"
trap - ERR
REMOTE
```

nginx bindet Port 80 mit der einzigen zusätzlichen Capability
`CAP_NET_BIND_SERVICE`; UID bleibt `tictactest` und `NoNewPrivileges` aktiv.
Die Console-Unit und ihr laufender Prozess wurden dabei nicht neu gestartet.
Die beiden Loopback-Ports bleiben bestehen und der angepasste Healthcheck
verlangt exakt diese beiden privaten Listener plus öffentliches HTTP.

### Nur die HTTP-Freigabe anwenden und von aussen prüfen

```bash
umask 077
AWS_PROFILE=tictactest-lab tofu -chdir=infra plan -input=false \
  -out=.terraform/public-http.tfplan
tofu -chdir=infra show -json .terraform/public-http.tfplan \
  > infra/.terraform/public-http-plan.json
# Plan prüfen: nur aws_security_group.ssh in-place, nur TCP/80 ergänzen.
AWS_PROFILE=tictactest-lab tofu -chdir=infra apply -input=false \
  .terraform/public-http.tfplan
curl -fsS "$(tofu -chdir=infra output -raw frontend_url)version.txt"
curl -fsS "$(tofu -chdir=infra output -raw backend_version_url)"
AWS_PROFILE=tictactest-lab tofu -chdir=infra plan -input=false -detailed-exitcode
```

Ergebnis: **0 hinzugefügt, 1 geändert, 0 gelöscht**, danach No-op mit Exitcode 0.
Die AWS-API bestätigt nur TCP/80 für alle IPv4-Adressen und die unveränderte
SSH-Einzeladresse. Von ausserhalb der EC2 ist Port 80 erreichbar, 7681/8080 nicht.
Release-Jar, Runtime-Skripte, `.git` und `release.env` werden nicht ausgeliefert;
die geprüften entsprechenden URLs geben 404 zurück. Öffentlich ist nur der
Frontend-Inhalt einschliesslich seiner absichtlich öffentlichen `config.js`.

Eine echte Browserpartie über öffentliches HTTP/WebSocket wurde mit `4`, `2`,
`6` gewonnen; Frontend und Backend melden `1.1.0`. Der Desktop-Testbrowser
schrieb HTTP zunächst auf HTTPS um und blockierte clientseitig; der vollständige
Spielnachweis wurde deshalb in einem separaten Chromium-Testprofil ohne diese
Upgrade-Einstellung erbracht. Keine globalen Browser-Sicherheitseinstellungen
wurden geändert. Screenshot und Terminalmitschnitt liegen wie zuvor ausserhalb
von Git. Die private HTTPS-Vorschau funktioniert zusätzlich weiter.

**Bewusste Grenze:** öffentliches HTTP, noch kein TLS, keine Anmeldung. Hier
keine Zugangsdaten eingeben. `ttyd -O`, direkter Java-Aufruf und das Limit von
vier Spielverbindungen bleiben aktiv. Alle 21 lokalen Infrastruktur-/Runtime-
Tests bestanden; Java-Spiel und veröffentlichte Release-Artefakte sind unverändert.

## Vorhandenes Instance Profile zuordnen — 23. November 2026

`instance-profile.tf` liest `LabInstanceProfile` mit der vorhandenen `LabRole`.
Die Instanz referenziert den Profilnamen; eigene IAM-Ressourcen werden nicht
angelegt. Dieser Schritt verändert nicht die LabRole-Policies und wählt auch
keinen neuen Applikationsrelease aus.

```bash
# Vorhandenes Profil zuerst lesen, keine IAM-Rolle erstellen.
aws --profile tictactest-lab --region us-east-1 --no-cli-pager \
  iam get-instance-profile --instance-profile-name LabInstanceProfile \
  --query 'InstanceProfile.{Name:InstanceProfileName,Roles:Roles[].RoleName}'

tofu -chdir=infra fmt -check
tofu -chdir=infra validate
python3 -B -m unittest discover -s infra/tests -v
umask 077
AWS_PROFILE=tictactest-lab tofu -chdir=infra plan -input=false \
  -out=.terraform/instance-profile.tfplan
tofu -chdir=infra show -json .terraform/instance-profile.tfplan \
  > infra/.terraform/instance-profile-plan.json
# Geprüft: nur iam_instance_profile an aws_instance.server ändert sich.
AWS_PROFILE=tictactest-lab tofu -chdir=infra apply -input=false \
  .terraform/instance-profile.tfplan

INSTANCE_ID="$(tofu -chdir=infra output -raw instance_id)"
aws --profile tictactest-lab --region us-east-1 --no-cli-pager \
  ec2 describe-iam-instance-profile-associations \
  --filters "Name=instance-id,Values=$INSTANCE_ID" \
  --query 'IamInstanceProfileAssociations[].State'
tofu -chdir=infra output -raw instance_profile_name
tofu -chdir=infra output -raw instance_profile_role
```

Ergebnis: **0 hinzugefügt, 1 geändert, 0 gelöscht**, Zuordnung `associated`.
Der JSON-Plan wurde vor dem Apply auf dieselbe Instanz-ID, ausschliesslich das
Profilfeld und No-op aller anderen verwalteten Ressourcen geprüft. State-
Sicherungen und konkrete IDs bleiben ausserhalb von Git.

### Rollenidentität wirklich auf EC2 prüfen

Der folgende Test verwendet absichtlich weder AWS-Umgebungs-Credentials noch
lokale Credential-Dateien. Die auf EC2 bereits vorhandene AWS CLI muss die
kurzlebigen Rollen-Credentials selbst aus den Instanzmetadaten beziehen.
`HOST` und `SSH_OPTIONS` stammen aus dem SSH-Abschnitt oben:

```bash
HOST="$(tofu -chdir=infra output -raw public_ip)"
INSTANCE_ID="$(tofu -chdir=infra output -raw instance_id)"
ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" python3 - "$INSTANCE_ID" <<'PY'
import os, subprocess, json, sys, time
env = {k: v for k, v in os.environ.items() if not k.startswith('AWS_')}
env.update({
    'AWS_CONFIG_FILE': '/dev/null',
    'AWS_SHARED_CREDENTIALS_FILE': '/dev/null',
    'BOTO_CONFIG': '/dev/null',
    'AWS_EC2_METADATA_DISABLED': 'false',
    'AWS_METADATA_SERVICE_TIMEOUT': '2',
    'AWS_METADATA_SERVICE_NUM_ATTEMPTS': '2',
    'AWS_PAGER': '',
})
command = ['/usr/bin/aws', '--region', 'us-east-1', '--no-cli-pager',
           '--cli-connect-timeout', '5', '--cli-read-timeout', '10',
           'sts', 'get-caller-identity', '--output', 'json']
for attempt in range(12):
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=25)
    if result.returncode == 0:
        break
    time.sleep(2)
assert result.returncode == 0, 'STS-Test fehlgeschlagen; keine Credentials ausgeben'
identity = json.loads(result.stdout)
assert identity['Arn'].split(':assumed-role/', 1)[1] == 'LabRole/' + sys.argv[1]
print('PASS: LabRole mit Instanz-Session, ohne lokale Credential-Dateien')
PY

curl -fsS "$(tofu -chdir=infra output -raw backend_version_url)"
AWS_PROFILE=tictactest-lab tofu -chdir=infra plan -input=false -detailed-exitcode
```

Die Prüfung war erfolgreich. Boot-ID, beide Dienst-PIDs, Jar-Hash und feste IP
blieben gleich; beide Versionsanzeigen melden `1.1.0`. Die komplette öffentliche
Browserpartie nach der Profilzuordnung wurde mit CROSS gewonnen. Der letzte
Plan ist ein No-op mit Exitcode 0; 22 lokale Infrastruktur-/Runtime-Tests bestanden.

**Nicht daraus ableiten:** Der STS-Test bestätigt die Rolle, nicht beliebige
SSM-/S3-Berechtigungen. Access Keys oder Session Tokens wurden nicht auf den
Server kopiert, ausgegeben oder committed. Das vorhandene Lab-Profil bleibt
extern verwaltet. Seine Rechte ersetzen nicht die weitere Dienstabsicherung.

Für den vollständigen Auftrag 2 bleiben automatische Ersteinrichtung aus IaC,
ein zweiter Release sowie die vorgeschriebenen Session-/Wiederaufbau-Experimente
offen. Sie wurden in diesem begrenzten Profil-Schritt nicht vorweggenommen.
