# Manuelles TicTacTest-Deployment auf EC2

**Aktueller Stand (23. November 2026):** Auftrag 2 ist technisch abgenommen:
Release `1.2.0` läuft öffentlich auf der vollständig neu aufgebauten EC2 und
übersteht deren Neustart. Die aktuelle Adresse liefert
`tofu -chdir=infra output -raw frontend_url`; sie änderte sich beim destroy/apply.
HTTP ist ausdrücklich freigegeben, HTTPS noch nicht eingerichtet. Die frühen
Abschnitte sind historische Zwischenstände; die abschliessende Abnahme steht unten.

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

## Automatische Erststartdefinition aus IaC — 23. November 2026

`infra/bootstrap.tf` rendert `bootstrap/user-data.sh.tftpl` aus genau den vier
bestehenden Runtime-Dateien. Der Bash-Wrapper legt root-eigene Dateien unter
`/usr/local/share/tictactest-bootstrap` an und führt den versionsgebundenen
Installer aus. Weder Release-Nummer noch Jar-/Frontend-Download gehören in
`user_data`; der anschliessende manuelle Release-Deploy bleibt unabhängig.
Der tatsächlich mit OpenTofu gerenderte Inhalt umfasst **8.041 Bytes** und
passt in das 16-KiB-Limit; die Dateien bleiben beim Einbetten byte-identisch.

```bash
tofu -chdir=infra fmt -check
tofu -chdir=infra validate
python3 -B -m unittest discover -s infra/tests -v
printf 'jsonencode(local.bootstrap_user_data)\n' | \
  AWS_PROFILE=tictactest-lab tofu -chdir=infra console -no-color
umask 077
AWS_PROFILE=tictactest-lab tofu -chdir=infra plan -input=false -no-color \
  -out=.terraform/bootstrap.tfplan
tofu -chdir=infra show -json .terraform/bootstrap.tfplan \
  > infra/.terraform/bootstrap-plan.json
# Geprüft: nur aws_instance.server in-place, nur user_data ändert sich.
# public_ip/public_dns sind nach Stop/Start berechnete unbekannte Attribute;
# EIP, Zuordnung, SSH-Key, Security Group und Instance Profile bleiben gleich.
AWS_PROFILE=tictactest-lab tofu -chdir=infra apply -input=false -no-color \
  .terraform/bootstrap.tfplan
ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" \
  'sudo cloud-init status --wait --long; test ! -d /usr/local/share/tictactest-bootstrap && echo FIRST_BOOT_NOT_RERUN; cat /proc/sys/kernel/random/boot_id; systemctl is-enabled tictactest-console tictactest-web; readlink -f /opt/tictactest/current; sha256sum /opt/tictactest/current/*.jar'
curl -fsS "$(tofu -chdir=infra output -raw frontend_url)version.txt"
curl -fsS "$(tofu -chdir=infra output -raw backend_version_url)"
AWS_PROFILE=tictactest-lab tofu -chdir=infra plan -input=false -no-color -detailed-exitcode
```

**Beobachtung am vorhandenen Host:** Apply **0 hinzugefügt, 1 geändert,
0 gelöscht**. EC2 wurde gestoppt/gestartet, nicht ersetzt; Instance-ID und
Elastic IP bleiben gleich. Der neue Boot begann um **14:45 UTC**. Beide
Dienste starten mit unverändertem Jar-Hash und Release `1.1.0`; auch eine neue
öffentliche Browserpartie mit `4`, `2`, `6` endet mit CROSS als Gewinner.
Der Folgeplan liefert Exitcode **0**. 27 Infrastruktur-, 10 Support- und
3 Frontendtests bestehen.

**Wichtige Grenze:** `user_data_replace_on_change = false` verhindert die
Neuerstellung, aber nicht den Stop/Start bei einer User-Data-Änderung. cloud-init
führt das Erststartskript auf diesem bestehenden Host nicht erneut aus; der
Bootstrap-Stagingordner bleibt hier deshalb noch abwesend. Das AWS-Attribut
enthält dennoch nachweislich exakt den gerenderten Inhalt. Ein No-op-Plan
beweist also nicht, dass eine neue Erststartkonfiguration auf einen bestehenden
Host angewendet wurde. Der echte Erststartnachweis bleibt bis zum freigegebenen
Wiederaufbau-Test offen; kein `cloud-init clean` oder verstecktes Redeployment.

## Architekturentscheidungen und Schnittstellen

**Artefakte:** Die EC2 lädt die ausdrücklich gewählte Version direkt vom
öffentlichen GitHub-Release. Dadurch bleiben Jar und beide Archive prüfbar und
es braucht weder einen zusätzlichen Artefakt-Bucket noch einen GitHub-Token
auf EC2. Alle drei Prüfsummen werden vor dem Entpacken geprüft. Bei einem
privaten Repository müsste der Zugriff separat autorisiert werden, etwa durch
einen privaten Artefaktspeicher mit den tatsächlich verfügbaren Rollenrechten;
ein Token in `user_data` oder `config.js` ist keine Lösung.

**Versionswahl:** `release.env` und der `current`-Symlink liegen auf der
Instanzdisk. Ein normaler Stop/Start behält diese Auswahl. Ein zerstörter Host
verliert sie: Nach dem Wiederaufbau muss dieselbe Versionsnummer bewusst erneut
an den Deployer übergeben werden. Die Infrastruktur lädt weder «latest» noch
beim Booten irgendeinen Applikationsrelease.

**Öffentliche Frontend-Konfiguration:** Das Deployment schreibt `config.js`
*nach* dem Entpacken des Frontend-Archivs. Die Infrastruktur stellt über nginx
die gleichnamigen relativen Routen `/console/` und `/backend-version.txt`
bereit; eine umgebungsspezifische Hostadresse steht nicht im App-Code. Damit
bleibt die Konfiguration auch nach einem Frontend-Update richtig. Es braucht
keinen S3-Website-Bucket, weil derselbe nginx die statischen Dateien öffentlich
ausliefert. Öffentlich werden nur die erlaubten Frontend-Dateien ausgeliefert,
nicht Jar, Runtime, State, Credentials oder private Konfigurationsdateien.

**Outputs und Vertraulichkeit:** Spiel-/Console-/Versions-URL, öffentliche IP,
Instanz-ID, EIP-Allocation-ID und Profil-/Rollenname sind Schnittstellen für
Bedienung und spätere Pipeline, keine Zugangsdaten. Sie werden trotzdem nicht
unnötig als feste Umgebungswerte in den Quellcode geschrieben. Private Schlüssel,
AWS-Credentials und Session Tokens bleiben ausserhalb von Git; State, tfvars
und gespeicherte Pläne werden ebenfalls privat gehalten, nicht öffentlich
gehostet. Die SSH-Public-Key-Registrierung enthält keinen privaten Schlüssel.

**SSH gegenüber SSM:** Manuell ist der vorhandene, streng hostgeprüfte
SSH-/SCP-Zugang unmittelbar nachvollziehbar. Dafür müssen privater Schlüssel,
`known_hosts` und die erlaubte Quelladresse verfügbar sein. Gehostete
GitHub-Runner haben nicht automatisch dieselbe feste SSH-Quelladresse wie der
Administrationshost; deshalb wird Port 22 nicht für das gesamte Internet
geöffnet. SSM wäre für die Pipeline ohne eingehenden SSH-Zugang möglich,
benötigt aber einen erreichbaren Agenten und nachgewiesene Send-/Leserechte
für ihre AWS-Identität. Das als online gelesene SSM allein ist kein Nachweis
für diese Rechte. Im Learner Lab müssen ausserdem Ablauf und Erneuerung der
temporären Credentials berücksichtigt werden. Die konkrete Automatisierung
gehört zu Auftrag 3, nicht zu diesem manuellen Deployment.

## Dienstabsturz wirklich prüfen — 23. November 2026

Zusätzlich zur Konfiguration wurde der laufende Console-Hauptprozess gezielt
mit SIGKILL beendet. systemd startete ihn ohne manuellen `start` erneut;
Boot und nginx-Prozess blieben unverändert, derselbe Release `1.1.0` bestand
den vollständigen Routen-/Listener-Healthcheck. Der Test ist eine bewusste
Unterbrechung laufender Spielverbindungen, keine Datenmigration:

```bash
ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" \
  'sudo systemctl kill --kill-who=main --signal=SIGKILL tictactest-console.service'
sleep 4
ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" \
  'systemctl is-active tictactest-console.service tictactest-web.service'
ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" \
  'sudo python3 -B -c "import runpy; runpy.run_path(\"/home/ec2-user/tictactest-admin/scripts/deploy-release.py\")[\"wait_healthy\"](\"1.1.0\")"'
```

## Robustheit: tatsächlicher Lab-Sessionwechsel — 23. November 2026

Nach der EIP-/HTTP-Einrichtung wurde die Learner-Lab-Session bereits beendet
und vom Nutzer neu gestartet. Dieser tatsächliche Wechsel ist nun auch
technisch nachvollzogen, bevor eine weitere Infrastrukturänderung erfolgt:

- EC2 meldet den erneuten Start am **23. November 2026 um 13:11:11 UTC**;
  das Gast-Journal beginnt den neuen Boot um **13:11:15 UTC**. Es enthält auch
  den vorherigen Boot, dessen letzte Einträge von **11:51 UTC** stammen.
- Dieselbe Instanz und dieselbe Elastic IP sind weiterhin zugeordnet. An der
  Spieladresse, den Firewallregeln und dem App-Deployment wurde für die
  Wiederherstellung nichts repariert.
- Beide systemd-Dienste laufen automatisch. `/opt/tictactest/current` zeigt
  weiterhin auf `releases/1.1.0`, beide öffentlichen Versionen sind `1.1.0`.
  Der Jar-Hash ist unverändert `5d7ce03c167f39484506eda7d6325f5e280200231ba8fa4a2246567fc0bd1c0f`.
- Der vom Nutzer gesicherte öffentliche Spiel-Screenshot von **14:13 UTC**
  zeigt beide Versionen und eine abgeschlossene Partie. Die zusätzlichen
  rein lesenden Prüfungen um **14:32–14:37 UTC** bestätigen den Zustand.

Die Kontrolle wiederholt keinen künstlichen Sessionwechsel und misst keine
Ausfallzeit; sie dokumentiert den wirklich erfolgten Wechsel. Die Belege
liegen privat unter `~/.local/share/tictactest-iac/evidence/`.

```bash
HOST="$(tofu -chdir=infra output -raw public_ip)"
INSTANCE_ID="$(tofu -chdir=infra output -raw instance_id)"
aws --profile tictactest-lab --region us-east-1 --no-cli-pager \
  ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].{Id:InstanceId,LaunchTime:LaunchTime,Ip:PublicIpAddress,State:State.Name}' \
  --output json
ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" \
  'date -u; uptime -s; sudo journalctl --list-boots --no-pager; readlink -f /opt/tictactest/current; sha256sum /opt/tictactest/current/*.jar; systemctl is-active tictactest-console tictactest-web'
curl -fsS "$(tofu -chdir=infra output -raw frontend_url)version.txt"
curl -fsS "$(tofu -chdir=infra output -raw backend_version_url)"
```

## Release B ohne Infrastrukturänderung — 23. November 2026

Release A war `v1.1.0`. Release B ist **`v1.2.0`**, mit einem sichtbaren blauen
Akzent für Titel, Links und Feldnummern. Die Spiellogik ist unverändert.
Feature-PR **#18** wurde nach Tests in `dev`, die ausdrücklich freigegebene
Promotion **#19** nach grüner CI und Coverage Gate in `main` gemergt.
Der neue annotierte Tag zeigt auf `ce8586372128ba7040748598eb5c3c227c292536`;
alle bisherigen Tags bleiben unverändert. Der Release-Lauf **45200072905**
veröffentlichte Release **455577145** mit genau sechs Assets: Jar, Frontend-
und Runtime-ZIP sowie jeweils eine Prüfsummendatei.

| Veröffentlichtes Artefakt | SHA-256 |
|---|---|
| `tictactest-1.2.0.jar` | `b4f35b35a65b01db4181ea22e1d1185785d7fdd6488ba9c7380a1ed673e74cdf` |
| `tictactest-frontend-1.2.0.zip` | `7528a9ff88e6921a398b9b1f2da2ca817b41425a5a26fb2d3b8c9949e1f93406` |
| `tictactest-runtime-1.2.0.zip` | `b1f64f80c881387dd7c7f5ad3e4ba535d894efa41f001d4ca71c7aa2f1f80adc` |

Die Veröffentlichung erfolgte wie in [RELEASE.md](../RELEASE.md) über einen
neuen Tag, nicht durch Verschieben eines alten Tags. Anschliessend wurde nur
dieser manuelle Deploymentbefehl auf der bestehenden Instanz ausgeführt:

```bash
HOST="$(tofu -chdir=infra output -raw public_ip)"
ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" \
  'sudo bash /home/ec2-user/tictactest-admin/scripts/deploy-release.sh 1.2.0'
curl -fsS "$(tofu -chdir=infra output -raw frontend_url)version.txt"
curl -fsS "$(tofu -chdir=infra output -raw backend_version_url)"
AWS_PROFILE=tictactest-lab tofu -chdir=infra plan -input=false -no-color -detailed-exitcode
```

**Ergebnis um 15:01 UTC:** beide Versionen `1.2.0`, echte öffentliche Partie
mit CROSS gewonnen, blaue Darstellung im Screenshot überprüft. Instance-ID,
EIP, AWS-Startzeit und Gast-Boot-ID bleiben gleich. Der installierte Jar-Hash
entspricht dem veröffentlichten Asset-Digest. Der Folgeplan ist **Exitcode 0**.
Für diesen Release-Deploy gab es **kein `tofu apply`**, keinen Hostersatz und
keinen Build auf EC2. Der vorherige lokale Build war nur ein getesteter
Release-Kandidat, nicht das deployte Artefakt.

## Einrichtung ändern: neue Dienstvariable — 23. November 2026

Nach dem abgeschlossenen Release-B-Nachweis wurde in der Console-Unit
`Environment=TICTACTEST_ENV=lab` ergänzt. Das ist eine bewusst beobachtbare
Infrastruktureinstellung, keine Applikationsversion und kein Secret.
Die vorher fehlende Einstellung wurde zuerst durch einen roten Test erkannt;
nach der Ergänzung bestehen **28 Infrastrukturtests**.

```bash
AWS_PROFILE=tictactest-lab tofu -chdir=infra plan -input=false -no-color \
  -out=.terraform/environment.tfplan
tofu -chdir=infra show -json .terraform/environment.tfplan \
  > infra/.terraform/environment-plan.json
# Prüfen: nur user_data der bisherigen EC2; EIP/SG/Key/Profile bleiben gleich.
AWS_PROFILE=tictactest-lab tofu -chdir=infra apply -input=false -no-color \
  .terraform/environment.tfplan
ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" \
  'sudo cloud-init status --wait --long; systemctl show tictactest-console.service -p Environment --value; readlink -f /opt/tictactest/current; cat /proc/sys/kernel/random/boot_id'
AWS_PROFILE=tictactest-lab tofu -chdir=infra plan -input=false -no-color -detailed-exitcode
```

**Beobachtung um 15:05 UTC:** wiederum **0 hinzugefügt, 1 geändert, 0 gelöscht**.
Dieselbe EC2 und EIP, neuer Gast-Boot, unveränderte Version `1.2.0` mit identischem
Jar. Die vorhandene Unit enthält die neue Variable **noch nicht**, obwohl die
aktualisierte User Data gespeichert und der Folgeplan leer ist. cloud-init ist
keine dauerhafte Konfigurationsverwaltung: Erststartskripte laufen standardmässig
nur einmal. Für eine Änderung am bestehenden Host wäre ein ausdrücklich
ausgeführtes Konfigurations-Update nötig; hier wird stattdessen im nächsten
Pflichttest frisch aufgebaut. Mit `user_data_replace_on_change = true` würde
der Provider die Instanz ersetzen statt nur stoppen/starten. Auch dann müsste
das Deployment die gewünschte App-Version wieder auswählen.

## Vollständig löschen und wieder aufbauen — 23. November 2026

Dieser destruktive Test wurde **gesondert freigegeben**. Vorher wurden privater
State, Versionswahl `1.2.0`, Asset-Digests, aktuelle Outputs und ein geprüftes
Fallback-Archiv der App-/Dienstkonfiguration ausserhalb von Git gesichert.
Der private SSH-Schlüssel blieb unverändert auf dem Administrationshost.
Das Archiv war ein Sicherheitsnetz und wurde **nicht** zur App-Wiederherstellung
verwendet: Dafür wurden erneut die veröffentlichten Release-Assets geladen.

Der konkrete Löschplan wurde vor Ausführung auf genau fünf eigene Ressourcen
geprüft: EC2 samt löschbarer Systemdisk, EIP, EIP-Zuordnung, SSH-Public-Key-
Registrierung und Security Group. IAM-Profil/Rolle, Standard-VPC und Subnetz
sind nur Datenquellen und werden nicht gelöscht. Der private SSH-Tunnel wurde
vorher gestoppt, damit er nicht zu einer freigegebenen alten IP weiterverbindet.

```bash
umask 077
# Äquivalent zu tofu destroy, aber mit vorher geprüftem gespeicherten Plan.
AWS_PROFILE=tictactest-lab tofu -chdir=infra plan -destroy -input=false -no-color \
  -out=.terraform/robustness-destroy.tfplan
tofu -chdir=infra show -json .terraform/robustness-destroy.tfplan \
  > infra/.terraform/robustness-destroy-plan.json
# Erst nach eigener Prüfung und ausdrücklicher Freigabe ausführen:
sudo systemctl stop tictactest-ec2-tunnel@phil.service
AWS_PROFILE=tictactest-lab tofu -chdir=infra apply -input=false -no-color \
  .terraform/robustness-destroy.tfplan
```

**Löschnachweis:** **5 gelöscht**, verwalteter State leer; AWS bestätigt alte
EC2 `terminated` und alte EIP/SG/Key-Registrierung nicht mehr vorhanden.
Dasselbe `LabInstanceProfile` mit `LabRole` bleibt bestehen. Anschliessend:

```bash
AWS_PROFILE=tictactest-lab tofu -chdir=infra plan -input=false -no-color \
  -out=.terraform/robustness-rebuild.tfplan
tofu -chdir=infra show -json .terraform/robustness-rebuild.tfplan \
  > infra/.terraform/robustness-rebuild-plan.json
# Prüfen: genau fünf Creates, dieselbe AMI/micro-Klasse, VPC/Subnetz/Profile,
# gleicher Public Key; verschlüsselte 8 GiB, IMDSv2, Standard-CPU-Credits,
# ausschliesslich HTTP und SSH vom aktuellen Administrator-/32.
AWS_PROFILE=tictactest-lab tofu -chdir=infra apply -input=false -no-color \
  .terraform/robustness-rebuild.tfplan
HOST="$(tofu -chdir=infra output -raw public_ip)"
INSTANCE_ID="$(tofu -chdir=infra output -raw instance_id)"
aws --profile tictactest-lab --region us-east-1 --no-cli-pager \
  ec2 get-console-output --instance-id "$INSTANCE_ID" --latest --output json
# Neuen Ed25519-Hostschlüssel gegen diesen authentifizierten Console-Fingerprint
# prüfen und erst dann known_hosts aktualisieren; siehe infra/README.md.
ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" \
  'sudo cloud-init status --wait --long; systemctl is-enabled tictactest-console tictactest-web; systemctl show tictactest-console.service -p Environment --value'
```

**Echter Erststart:** **5 erstellt**. cloud-init war um **15:11 UTC** fertig.
Ohne manuelles Runtime-Setup waren Corretto/nginx in den festgelegten
RPM-Versionen und ttyd mit der festgelegten Prüfsumme installiert; Benutzer
`tictactest` war ein Nicht-Login-Konto. Beide App-Dienste waren aktiviert und
`TICTACTEST_ENV=lab` jetzt automatisch installiert. Alle vier eingebetteten
Dateien stimmen byte-identisch mit den Quellen überein; der aktuelle Render
umfasst **8.081 Bytes**. Vor dem Deployment gab es ausdrücklich **weder
`release.env` noch `current`**, und beide App-Dienste waren inaktiv: Runtime
vorhanden bedeutet nicht, dass eine App-Version gewählt ist.

Nur die zwei versionskontrollierten **Betriebswerkzeuge**, kein App-Checkout,
wurden kopiert. Danach lief wieder exakt derselbe Release:

```bash
ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" \
  'mkdir -p /home/ec2-user/tictactest-admin/scripts'
scp "${SSH_OPTIONS[@]}" infra/scripts/deploy-release.sh infra/scripts/deploy-release.py \
  "ec2-user@$HOST:tictactest-admin/scripts/"
ssh "${SSH_OPTIONS[@]}" "ec2-user@$HOST" \
  'sudo bash /home/ec2-user/tictactest-admin/scripts/deploy-release.sh 1.2.0'
curl -fsS "$(tofu -chdir=infra output -raw frontend_url)version.txt"
curl -fsS "$(tofu -chdir=infra output -raw backend_version_url)"
```

| Wert | Nach destroy/apply tatsächlich beobachtet |
|---|---|
| Instance-ID, Rootvolume, SG-ID, Key-Pair-ID | Neu; Key-Name und Fingerprint bleiben gleich |
| EIP-Allocation/-Association und öffentliche Spiel-URL | Neu; die alte Adresse wurde freigegeben |
| Private IP und Gast-Boot-ID | Neu |
| AMI, Instanzklasse, Standard-VPC/Subnetz, Lab-Profil/Rolle | Gleich |
| App-Version und Jar-Hash nach manuellem Restore | Wieder exakt `1.2.0` / veröffentlichter Digest |
| Inhalt der früheren Instanzdisk | Nicht vorhanden; Release-Auswahl musste erneut gesetzt werden |

Eine EIP bleibt bei Stop/Start fest, nicht nach absichtlichem Löschen ihrer
Allocation. Deshalb Adressen immer aus Outputs beziehen. Der neue Host-Key
wurde über AWS verifiziert, nicht blind akzeptiert. Der private Tunnel wurde
auf genau die neue Adresse umgestellt und öffentliches sowie privates HTTP
erneut geprüft; sonstige Tailscale-Routen blieben unangetastet. **Nie die alte
State-Sicherung über den erfolgreichen neuen State kopieren:** Sie beschreibt
gelöschte AWS-IDs und ist nur ein datierter Nachweis/Sicherungsstand.

## Abschliessende Abnahme Auftrag 2

Der frisch aufgebaute Host wurde nach dem Restore zusätzlich per EC2-API
neugestartet. Um **15:16 UTC** liefen beide Dienste automatisch mit derselben
Version `1.2.0`, neuem Gast-Boot und unverändertem Jar-Hash wieder an:

```bash
aws --profile tictactest-lab --region us-east-1 --no-cli-pager \
  ec2 reboot-instances --instance-ids "$INSTANCE_ID"
# Auf den neuen Gast-Boot und aktive Dienste warten, nicht nur API-Rückgabe prüfen.
curl -fsS "$(tofu -chdir=infra output -raw frontend_url)version.txt"
curl -fsS "$(tofu -chdir=infra output -raw backend_version_url)"
AWS_PROFILE=tictactest-lab tofu -chdir=infra plan -input=false -no-color -detailed-exitcode
```

- [x] Feste öffentliche Adresse über tatsächlichen Lab-Sessionwechsel geprüft.
- [x] Automatischer frischer Bootstrap mit festen Paket-/ttyd-Versionen und Prüfsumme.
- [x] Nicht-root-Dienste, automatischer Wiederanlauf nach SIGKILL und Boot.
- [x] Profilidentität auf **neuer** EC2 erneut durch echten STS-Aufruf ohne lokale Credentials belegt.
- [x] Öffentlich nur TCP/80; TCP/22 nur Administrator-/32. 7681/8080 von aussen gesperrt.
- [x] Console ohne Capability, nginx nur `CAP_NET_BIND_SERVICE`, beide `NoNewPrivileges`.
- [x] Frontend öffentlich, Konfiguration nach Entpacken erzeugt, keine feste App-Hostadresse.
- [x] Alle benötigten URLs, Instanz-/EIP-/Profilinformationen als Outputs.
- [x] Release A und B manuell aus veröffentlichten Assets deployt; B ohne Apply/Hostersatz.
- [x] Session-, Konfigurations- und tatsächlicher destroy/apply-Test dokumentiert.
- [x] Finale echte Browserpartie mit CROSS gewonnen, beide Versionen `1.2.0`.
- [x] Finaler OpenTofu-Plan **Exitcode 0**, keine Änderungen; privater Zugang funktioniert ebenfalls.

Ausgehender Verkehr bleibt für Paketquellen, GitHub und AWS/SSM freigegeben;
dies ist keine Egress-/Hostnamen-Allowlist. Die bewusst vereinbarten Grenzen
bleiben: HTTP ohne TLS/Login, maximal vier Console-Verbindungen, begrenzter
Java-Heap statt behaupteter harter Gesamt-RAM-Grenze; kein Last-/Sicherheitsaudit.
Das optionale S3-Spielprotokoll wurde nicht umgesetzt. Der aktuelle Lab-Budgetwert
wurde nicht angegeben und wird hier nicht erfunden. Für Auftrag 3 laufen wieder
eine micro-Instanz und ihre EIP; der Budgetverbrauch geht weiter. Screenshots,
API-/Terminalnachweise und private Sicherungen liegen ausserhalb von Git unter
`~/.local/share/tictactest-iac/evidence/`. Auftrag 3 ist damit vorbereitet, aber
seine automatisierte Deployment-Pipeline ist noch nicht implementiert.

## Auftrag 3: Deployment-Konzept — freigegeben, 24. November 2026

**Status:** Der Nutzer hat das Konzept freigegeben. Der erste Umsetzungsschritt
hat SSM-Befehlsausführung und Ergebnisabfrage mit einem echten reinen Lesebefehl
nachgewiesen; siehe Abschnitt 11. Dies ist noch keine Deployment-Pipeline.
Release `1.2.0` läuft unverändert. GitHub-Environment/Secrets und Workflows wurden
noch nicht eingerichtet; kein Deployment, Dienstneustart oder Apply ausgeführt.

### 1. Entscheidung: GitHub Actions steuert die EC2 über SSM

GitHub-gehostete Runner verwenden AWS Systems Manager Run Command statt SSH.
Damit braucht die Pipeline keinen privaten SSH-Schlüssel und keine Öffnung von
Port 22 für wechselnde Runner-Adressen. Die vorhandene SSH-Regel bleibt für
manuelle Administration beschränkt. Ein harmloser SSM-Befehl samt Ergebnisabfrage
mit der tatsächlichen Lab-Identität ist inzwischen erfolgreich geprüft. Diese
Prüfung wird bei der späteren Runner-Einrichtung wiederholt; bei fehlenden
Rechten wird nicht einfach die Firewall aufgeweicht.[8]

Zwei Identitäten bleiben getrennt: Der Runner nutzt die temporären
Learner-Lab-Zugangsdaten; SSM-Agent und EC2 nutzen das vorhandene
`LabInstanceProfile`/`LabRole`. Runner-Credentials werden nicht auf die EC2
kopiert. Die Instanz lädt die ausdrücklich gewählten **öffentlichen**
GitHub-Release-Assets ohne zusätzliches GitHub-Secret. Für ein privates Repo
müsste der Artefaktzugriff separat entworfen werden.

### 2. Secrets, Variables und Ablauf der Lab-Zugangsdaten

Vorgesehen ist ein GitHub Environment **`learner-lab`**, zugänglich nur für den
vertrauenswürdigen Deployjob von `main`. PR-Tests und Release-Build benötigen
keine AWS-Secrets. Secrets werden verschlüsselt gespeichert und dem Job nur
über ausdrücklich verwendete Inputs/Umgebungsvariablen bereitgestellt.[4]

| Name | Ablage | Herkunft/Zweck |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | Environment Secret | Aktueller temporärer Lab-Credential-Satz |
| `AWS_SECRET_ACCESS_KEY` | Environment Secret | Derselbe Satz; niemals Repo-/Log-Inhalt |
| `AWS_SESSION_TOKEN` | Environment Secret | Derselbe Satz, bei temporären Credentials erforderlich |
| `AWS_REGION` | Environment Variable | Tatsächlich verwendete Lab-Region |
| `AWS_ACCOUNT_ID` | Environment Variable | Erwartetes Zielkonto als Verwechslungsschutz, kein Zugangsschlüssel |
| `TICTACTEST_INSTANCE_ID` | Environment Variable | Aus `tofu output -raw instance_id` |
| `TICTACTEST_FRONTEND_URL` | Environment Variable | Aus `tofu output -raw frontend_url` |
| `GITHUB_TOKEN` | Automatisch von GitHub | Nur nötige Repo-Leserechte im Deployworkflow; kein manuell angelegter PAT |

Variables werden als nicht vertrauliche Konfiguration behandelt. Keine Tokens,
Passwörter oder privaten Schlüssel hineinlegen. Die tatsächlichen Werte stehen
nicht in diesem Dokument. Die Lab-Credentials stammen aus der Lab-Oberfläche,
nicht aus dem Instance Profile. Ihre konkrete Gültigkeit richtet sich nach der
aktuellen Sitzung/AWS-Ablaufzeit; es wird keine feste Laufzeit erfunden.

**Erneuerung und Fehlerfälle:**

1. Nach einer neuen Lab-Session aktualisiert der Betreiber alle drei Secrets als
   zusammengehörigen Satz in GitHub, bevor ein Release-/Deploylauf gestartet wird.
   Kein Copy/Paste in Chat, Git, Workflow-YAML oder öffentliche Terminalausgabe.
2. Der Deployjob prüft zuerst STS-Identität, erwartetes Konto/Region und den
   Zielhost/SSM-Status. Abgelaufene, fehlende oder gemischte Credentials lassen
   den Job **vor** dem Senden einer Deploymentanweisung fehlschlagen. Die laufende
   App bleibt in diesem Fall unberührt; der Release bleibt veröffentlicht.
3. Nach Erneuerung wird der vorhandene Release gezielt per manuellem Deploylauf
   nachgeholt. Kein neuer Tag, kein Verschieben alter Tags, kein erneuter Build.
4. Laufen Credentials **nach** Annahme eines SSM-Befehls ab, kann der Befehl auf
   EC2 weiterlaufen. Der Job darf daraus weder Erfolg noch unveränderten Zustand
   ableiten: `CommandId` sichern, nach Erneuerung genau diesen Auftrag und die
   tatsächlich laufenden Versionen prüfen, erst danach erneut deployen.
5. Keine interaktiven Geheimniswerte in Logs: kein `set -x`, `env`/`printenv`,
   kein Echo der Credentials und keine Credential-JSON-Dateien als Artefakte.
   Automatische Maskierung ist keine Garantie für abgeleitete/transformierte
   Werte; zusätzliche vertrauliche Ausgaben werden vorab maskiert. Nach jedem
   Lauf Logs kontrollieren, besonders bei Fehlern.[3][5]

**Wer darf zugreifen?** Nur freigegebene Deployjobs erhalten Environment-Secrets.
Gespeicherte Secret-Werte sollen nicht ausgelesen werden; Personen mit Einfluss
auf ausführbare Workflows können sie aber indirekt missbrauchen. Deshalb nur
vertrauenswürdiger `main`-Code, Review von Workflowänderungen, minimale
Job-Permissions und keine Secret-Freigabe an PR-/Fork-Code. Fork-PRs erhalten
standardmässig keine solchen Secrets; diese Schutzgrenze wird nicht durch
`pull_request_target` oder unkontrolliertes `workflow_run` umgangen.[3][5]

**Bei einem Leak:** Deployments stoppen, betroffene GitHub-Secrets entfernen/
ersetzen, Log-/Artefakt-Lecks beseitigen, AWS-Aktivitäten prüfen und den
Lab-Betreiber einbeziehen. Mit Lab-Rechten können je nach Berechtigungen Daten
und Ressourcen gefährdet sowie Budget verbraucht werden. Lab-Ende ist kein
hier behaupteter garantierter Sofortwiderruf bereits ausgegebener Tokens;
verfügbare Widerrufsmassnahmen und Restgültigkeit müssen geklärt werden.

**Unternehmen statt Learner Lab:** GitHub OIDC gegen eine eng begrenzte
AWS-Deployrolle, kurzlebige STS-Sessions statt gespeicherter AWS-Schlüssel.
Trust Policy auf tatsächliche Repo-/Environment-Identität (`sub`) und passende
Audience beschränken; `id-token: write` nur für den Deployjob. Aktuelle
Subject-Formate können unveränderliche Repo-/Owner-IDs enthalten: keine alte
Beispiel-Trust-Policy blind übernehmen. Mit Environment muss auch dessen Name
zur Subject-/Schutzregel passen. Im Lab werden dafür keine eigenen
IAM-Rollen/Policies/Provider angelegt.[6]

### 3. Trigger: erst veröffentlichen, dann deployen

`release.yml` bleibt für Tagprüfung, Tests, Build und Veröffentlichung zuständig.
Ein neues `deploy.yml` reagiert auf den erfolgreichen Abschluss von **`Release`**
über `workflow_run`, zusätzlich auf `workflow_dispatch` mit einem veröffentlichten
Tag als Eingabe. Kein Deploy bei normalem Push auf `main` und kein PR-Deploy.

Der Grund für diese Verkettung: Ein vom bestehenden Workflow mit `GITHUB_TOKEN`
erstellter Release startet nicht einfach einen zweiten `release: published`-
Workflow. Dafür wird kein unnötiger langlebiger PAT eingeführt.[1]
`workflow_run` benötigt den Deployworkflow auf dem Default-Branch; das wird
vor den echten Release-Experimenten bewusst per PR bereitgestellt.[2]

Der automatische Eingang wird eng geprüft: Quellworkflow erfolgreich, eigenes
Repo, zulässiger Taglauf, strikt validiertes `vMAJOR.MINOR.PATCH`, Tag-Commit
passt zum Quelllauf und liegt auf freigegebenem `main`, dazu ein tatsächlich
veröffentlichter Nicht-Draft-Release mit den erwarteten Assets. Ein erfolgreicher
oder übersprungener Branchlauf ohne passenden Release genügt nicht.

Deploywerkzeuge kommen vom vertrauenswürdigen, festgehaltenen Workflow-/Main-
Commit, **nicht** aus beliebigem PR-Code oder dem alten Rollback-Tag. Der
Zieltag ist Dateninput, kein ausführbarer Shelltext. Manuelle Läufe werden nur
vom freigegebenen `main` gestartet. Das ist wegen der höheren Privilegien von
`workflow_run` eine Sicherheitsgrenze, keine reine Bequemlichkeitsfrage.[2][3]

### 4. Änderungen zwischen veröffentlichten Releases erkennen

Der automatische Plan vergleicht den Zieltag mit dem vorherigen veröffentlichten
stabilen Release-Tag, nicht mit `HEAD~1` und nicht blind mit `releases/latest`.
Für unsere fortlaufenden Main-Releases wird der höchste kleinere SemVer-Release
gewählt und seine Abstammung zum Ziel geprüft. Unklare/divergente Reihenfolgen
führen zu einer Fehlermeldung statt zu einem geratenen Basistag. Release-Listen
werden vollständig paginiert gelesen; reine Git-Tags ohne Release zählen nicht.
Beim allerersten Release ohne Vorgänger werden beide Komponenten gewählt.

`fetch-depth: 0` liefert die Historie. Ein expliziter Git-Diff berücksichtigt
Löschungen und beide Seiten von Umbenennungen; Pfade werden nicht als Shellcode
verarbeitet. Event-`paths`-Filter ersetzen diesen Release-zu-Release-Vergleich
nicht. Unbekannte relevante Pfade lassen den Planer zur bewussten Einordnung
fehlschlagen statt versehentlich «keine Änderung» zu liefern.

| Pfad/Änderung | Automatische Auswahl |
|---|---|
| `src/main/**` | Backend |
| `frontend/**` | Frontend |
| `scripts/start-console.sh`, `backend-version.py`, `serve-backend-version.py`, `runtime-README.md` jeweils unter `scripts/` | Backend samt Runtime-Werkzeugen |
| Funktionale Build-/Dependency-/Toolchainänderung in `build.gradle`, Gradle-Wrapper oder Build-Konfiguration | Backend |
| `scripts/package-web-release.py`, `.github/workflows/release.yml` | Beide: können beide ausgelieferten Pakete beeinflussen |
| `src/test/**`, `src/e2eTest/**`, `scripts/tests/**`, `infra/tests/**`, reine CI-Tests | Kein App-Deploy; Tests müssen trotzdem bestehen |
| `README.md`, `CHANGELOG.md`, `docs/**`, reine Repo-Metadaten | Kein App-Deploy |
| `infra/**` ausser Tests, dazu `scripts/plan-release-deploy.py` und `.github/workflows/deploy.yml` | Betrieb separat prüfen; kein heimliches `tofu apply` und kein automatischer App-Neubau |

**Entscheidende Ausnahme:** Eine ausschliessliche Änderung der einen geprüften
`version = '…'`-Zuweisung in `build.gradle` ist Release-Metadaten und zählt nicht
als Backendänderung. Nur wenn der übrige Build-Dateiinhalt unverändert ist,
gilt diese Ausnahme. Plugin-/Dependency-Versionen werden nicht pauschal
herausgefiltert. Sonst würde jeder Frontend-Release wegen seines Versionsbumps
auch das Backend neustarten. Ebenso entscheiden nicht die geänderten generierten
Jar-/ZIP-Hashes allein: Manifest und Versionsdatei werden bei jedem Release neu
beschriftet, auch wenn nur eine Komponente automatisch auszuliefern ist.

### 5. Zwei Auswahlzeiger statt gekoppeltem Deployment

Der heutige Deployer schaltet beide Teile gemeinsam um, prüft beide auf dieselbe
Version und verweigert vorhandene Versionsordner. Das genügt **noch nicht** für
getrennte Releases oder wiederholbare Rollbacks. Vorgesehen ist:

```text
/opt/tictactest/current          -> deployments/backend/<Backend-Version>/
/opt/tictactest/frontend-current -> deployments/frontend/<Frontend-Version>/
Backend-Paket: Jar + dazugehöriges runtime/ aus genau diesem Release
Frontend-Paket: frontend/ aus genau diesem Release
```

Der bestehende `current`-Name bleibt für Backend/Console kompatibel. nginx
liefert zukünftig aus `frontend-current/frontend`. Verifizierte Komponenten
liegen getrennt und unveränderlich unter `deployments/`; alte `releases/`
werden nicht gelöscht, um eine Immutable-Prüfung zu umgehen. Eine bereits
vorbereitete Version darf nach Integritätsprüfung wieder ausgewählt werden.
Bei abweichenden Inhalten wird nicht still überschrieben.

Die öffentliche `config.js` wird als exakte nginx-Route aus der
Infrastrukturkonfiguration bedient, mit den relativen Console-/Versionsrouten.
Die Datei im Frontend-Archiv überschreibt diese Route nicht. Damit ist die
Konfiguration unabhängig vom ausgetauschten Frontend-Verzeichnis. Vor dem
Pipelinebetrieb werden Zeiger und nginx-Konfiguration kontrolliert auf den
bestehenden `1.2.0`-Stand umgestellt. Das ist ein separat geprüfter lokaler
Betriebsschritt, kein Apply aus GitHub Actions. Die einmalige cloud-init-
Semantik aus Auftrag 2 bleibt dabei zu berücksichtigen.

| Auswahl | Änderung an der Umgebung | Prüfung |
|---|---|---|
| Nur Frontend | Frontend-Zeiger tauschen; keine Console-/Backend-Neustarts | Neue Frontend-Version/Inhalt, alte Backend-Version und derselbe Console-PID |
| Nur Backend | Jar + passende Runtime wählen, `release.env`/Backend-Zeiger umstellen, nur Console neustarten | Neue echte Manifest-Version, unveränderte Frontend-Auswahl und deren Dateiinhalte |
| Beide | Beide Auswahlzustände koordiniert ändern | Beide Zielversionen und funktionierende Console/Seite |
| Weder noch | Kein SSM-Deployauftrag, kein Secret-Zugriff nötig | Expliziter No-op mit Begründung im Lauf |

Es gibt keine App-Builds auf EC2 oder im Deployjob. Gewählte veröffentlichte
Assets werden heruntergeladen, vor Nutzung geprüft und sicher entpackt. Der
Deployer behält SHA-Prüfung, ZIP-Allowlist, Manifestprüfung, Nicht-root-Dienste
und die tatsächliche Listenerkontrolle aus Auftrag 2 bei. Download/Prüfung
fehlschlagen zu lassen darf noch keinen laufenden Zeiger verändern.

### 6. Erfolg, Serialisierung und Fehlerbehandlung

Eine gemeinsame Concurrency-Gruppe `tictactest-learner-lab` schützt automatische
und manuelle Deployments. Vorgesehen sind `cancel-in-progress: false` und die
aktuell dokumentierte Warteschlange `queue: max`, plus der lokale Dateilock auf
EC2. Ohne Queue-Einstellung kann ein neuer wartender Lauf einen älteren
wartenden Lauf verdrängen. Auch mit Queue wird Reihenfolge nicht aus der
Release-Publikationszeit abgeleitet; diese Annahme wird nicht als Garantie
verkauft.[7]

Vor selektiven Updates wird deshalb auch geprüft, ob der tatsächliche
Komponentenzustand zur Quellbasis passt. Unterschiedliche Frontend-/Backend-
Versionsnummern sind dabei erlaubt. Ein ausgelassener Vorgänger oder falscher
Zielhost darf nicht als erfolgreicher selektiver Deploy durchgehen. Bei einer
Lücke: klar fehlschlagen und einen ausdrücklich gewählten vollständigen
manuellen Deploy nutzen, statt ungeändert deklarierte Komponenten heimlich
mitzudeployen. Kein automatisches Downgrade durch verspätete alte Läufe.

SSM-Annahme ist noch kein Befehlserfolg: auf genau `CommandId` und Instanz
pollen, terminalen Status und Exitcode prüfen. Anfangs noch nicht sichtbare
Invocation darf wegen der API-Eventual-Consistency begrenzt wiederholt werden;
Denied, Timeout und echte Befehlsfehler werden nicht weggeschluckt.[8][9]
Danach Versionen über HTTP prüfen. Beim Backendwechsel reicht eine passende
`backend-version.txt` **nicht** als JVM-Startnachweis: Die Datei kann schon vor
einem fehlgeschlagenen Spielstart erzeugt worden sein. Eine kurze echte Console-
WebSocket-Sitzung muss den laufenden Java-Spielprompt bestätigen; der Testclient
wird anschliessend auch im Fehlerfall geschlossen. Ein Jar mit korrekter
Prüfsumme/Versionsmetadaten, das sich nicht starten lässt, muss hier scheitern.
Beim Frontend-only-Deploy wird dafür nicht die laufende Backend-Sitzung ersetzt.
Geplant ist eine echte Health-Deadline von 60 Sekunden mit begrenzten Requests;
die reale Fehler-/Recoverydauer wird später gemessen, nicht aus einer Anzahl
verschachtelter Retries geraten. Die verbindlichen Host-/JVM-Prüfungen laufen
innerhalb der Remote-Transaktion unter dem Dateilock, bevor der Deployer Erfolg
meldet; die öffentliche Pipeline-Prüfung ist zusätzlich. Sonst könnte ein erst
nach SSM-Erfolg entdeckter Startfehler den automatischen Rollback umgehen.
Der Startprobe-Client muss zur vorhandenen Python-3.9-Laufzeit passen; seine
konkrete Umsetzung wird vor dem ersten echten Deploy getestet.

Vor Aktivierung werden beide Zeiger und die Backend-Environmentauswahl
festgehalten. Bei Fehler nach Aktivierung wird der **vollständige bisherige
Komponentenzustand** zurückgestellt und erneut geprüft. Ein fehlgeschlagener
Deploy bleibt auch bei erfolgreicher Wiederherstellung rot. Scheitert diese
zusätzlich, muss das ausdrücklich sichtbar werden. Beim Frontend-only-Fall
darf auch der Fehlerpfad nicht das Backend neustarten. Der Dateilock schützt
weiter, falls der Runner/SSM-Poller ausfällt, während der Remoteprozess läuft.

Backend-Neustarts trennen laufende Spiele; Frontend-only darf das nicht tun.
Eine spätere Verbesserung wäre Drain/Maintenance oder Blue-Green mit
Routing, das bestehende Sitzungen erhält. Das wird nur beschrieben, nicht als
zusätzliche Infrastruktur in diesem Auftrag gebaut.

### 7. Manuelles Deployment und Wiederaufbau

`workflow_dispatch` nimmt einen strikt validierten, bereits veröffentlichten
Tag wie `v1.2.0` an und deployt **immer beide** Komponenten dieser Version.
Versionspräfix erst nach Validierung zerlegen; keine unbekannten Tags,
Shellfragmente, still korrigierten Eingaben oder Neupublikationen akzeptieren.
Die laufende Version kommt nach Boot weiterhin aus der persistenten Auswahl
und dem tatsächlichen Jar, nicht aus «latest».

Nach einem erneut ausdrücklich freigegebenen destroy/apply laufen lokale
Infrastrukturbefehle auf dem bereits genutzten Administrationshost. Der neue
Host benötigt den freigegebenen Betriebs-Deployer; dieser wird separat
bereitgestellt, nicht aus einer unkontrollierten alten App-Version als root
übernommen. Neue Instanz-ID und Spiel-URL werden aus Outputs in den GitHub
Variables aktualisiert, SSM wird geprüft, Credentials bei Bedarf erneuert.
Danach stellt ein manueller Deploy den gewünschten veröffentlichten Stand
wieder her. Die Pipeline selbst führt dabei kein OpenTofu aus.

### 8. Vorgesehene Abnahme, noch nicht durchgeführt

| Versuch | Erwarteter Nachweis |
|---|---|
| Frontend-only-Release | Frontend neue Version; Backend alte Version, derselbe Console-PID; Partie läuft weiter |
| Backend-only-Release | Neue Backend-Version; Frontend-Auswahl/Inhalte unverändert |
| Release mit beiden Änderungen | Beide Zielversionen, echte Browserpartie |
| Nur Doku/Metadaten im Release | Expliziter No-op ohne Remoteaktivierung |
| Normaler Push auf `main`, kein Tag | Kein automatisches App-Deployment |
| Abgelaufene Credentials | Kontrollierter roter Lauf vor Mutation; nach Erneuerung denselben Release nachdeployen |
| Rollback `v1.3.0` → `v1.2.0` | Beide Teile gezielt `1.2.0`, alte Artefakte unverändert |
| Defekter Stand | Healthcheck rot, vorherige Version automatisch wiederhergestellt, tatsächliche Dauer und Lauf dokumentiert |
| Zwei überlappende Anforderungen | Keine parallele Aktivierung; kein unbemerkter Verlust einer Komponentenänderung |
| Wiederaufbau | Neue Zielwerte in Variables, gezielter manueller Restore, danach No-op-Plan |

Die konkreten neuen Releases, ein absichtlich defekter Testrelease und ein
weiterer Löschtest werden **vorher getrennt freigegeben**. Ein bereits im
Release-Build abgefangener Fehler ist kein Ersatz für einen getesteten
Deployment-Healthfehler. Bestehende Release-Tests werden dafür nicht heimlich
ausgeschaltet. Zu jedem echten Versuch gehören Workflow-Link, Versionen,
relevante PID-/Datei-/Instanzbelege und kontrollierte Logs. Noch keines dieser
Auftrag-3-Experimente wird durch dieses Konzept als bestanden markiert.

### 9. Umgebungen und Promotion — nur Skizze

```text
Backendänderung -> Feature/PR -> Tests -> main -> Tag -> Release-Artefakte
  -> Release-zu-Release-Plan: Backend -> SSM -> Console-Neustart -> Versions-/Spieltest
Frontendänderung -> Feature/PR -> Tests -> main -> Tag -> Release-Artefakte
  -> Release-zu-Release-Plan: Frontend -> Zeigerwechsel -> Inhalts-/Konfigtest
```

Build, geprüfte Komponentenwahl, Auslieferung und Healthchecks werden
automatisiert; lokale Infrastrukturänderungen, neue Lab-Secrets und bewusst
gewählte Releases/Rollbacks bleiben Betreiberhandlungen. Für spätere Umgebungen
`dev → staging → prod` bräuchte die IaC ein Umgebungsparameter-/Modulkonzept,
eindeutige Ressourcennamen, getrennte States und pro Umgebung passende
Netz-/Zielwerte und Rollen. Blueprint/Paketversionen bleiben gemeinsam;
Adressen, Berechtigungen, Kapazität und Konfiguration dürfen unterschiedlich sein.
Hier werden **keine drei Umgebungen** aufgebaut.

Dasselbe geprüfte Artefakt wird weitergereicht, nicht pro Umgebung neu gebaut.
Dev könnte nach Veröffentlichung automatisch, staging nach Integrations-/
Smoke-Tests und prod erst nach Freigabe/Required Reviewers im GitHub Environment
deployen. Die tatsächliche Konfiguration dieser Schutzregeln wird bei Umsetzung
geprüft.[6] Für unterschiedlich weit zurückliegende Umgebungen genügt der Diff
zwischen den zwei zuletzt publizierten Tags nicht: Jede Umgebung braucht ihren
eigenen belegten Komponentenstand und einen Plan zum gewählten Zielstand.

### 10. Nächste Umsetzungsscheiben nach Konzeptfreigabe

1. SSM-Sende-/Ergebnisrechte sind harmlos nachgewiesen; als nächste Etappe das
   Environment und den sicheren Erneuerungsweg gemeinsam einrichten. Keine
   Secret-Werte im Chat und keine Behauptung, GitHub-Secrets seien schon vorhanden.
2. Getrennte, wiederverwendbare Komponentenaktivierung und Rollback im bestehenden
   `infra/scripts/deploy-release.py` testgetrieben umsetzen; nginx-Umstellung
   separat prüfen. Erst dann auf die aktuelle Umgebung übernehmen.
3. Release-Planer als neues `scripts/plan-release-deploy.py` mit Tests unter
   `scripts/tests/` ergänzen: Metadaten-Ausnahme, Pfadklassen, Vorversion,
   erster Release, Löschungen/Umbenennungen und ungültige Eingaben.
4. Erst anschliessend `.github/workflows/deploy.yml` mit den freigegebenen
   Secrets/Variables, Triggerguards, Sperre, SSM-Polling und Nachweisen ergänzen.
5. Prüfen, nach `dev` integrieren und die für echte automatische Läufe nötige
   Main-Promotion/Releases jeweils abstimmen; danach die Abnahmematrix ausführen.

**Freigabestand:** SSM mit temporären Environment-Secrets, getrennte
Komponentenaktivierung und Verkettung über den erfolgreichen Release-Workflow
sind als Konzept freigegeben. Der Dokumentationscheckpoint darf nach Prüfung
über `docs/auftrag-3-konzept` nach `dev` integriert werden. Das ersetzt weder
die noch ausstehende Einrichtung der GitHub-Secrets noch spätere Main-/Release-
oder Löschfreigaben. Die übrigen Umsetzungsscheiben bleiben offen.

### 11. Erster echter SSM-Zugriffstest — 24. November 2026

Um **10:27 UTC** wurde mit dem bestehenden geschützten Profil `tictactest-lab`
eine kontrollierte `AWS-RunShellScript`-Anweisung an genau die im aktuellen
IaC-State geführte Instanz gesendet. Zuvor wurden STS-Konto, laufende EC2,
zugeordnete EIP, Instance Profile, SSM `Online` und beide öffentlichen Versionen
rein lesend geprüft. Es wurde kein SSH-Zugang als SSM-Ersatz verwendet.

Der übermittelte Bash-/Python-Block las ausschliesslich UID, Dienstzustände,
Boot-ID/PIDs, aktuelle Release-Auswahl, Jar-Hash und die zwei lokalen
Versionsendpunkte. Er führte weder `start`/`restart` noch Installationen,
Konfigurationsänderungen oder Deployments aus. Zwei Snapshots innerhalb des
Blocks bestätigen denselben Boot und dieselben Dienstprozesse während der Probe.

**Ergebnis:** `SendCommand` akzeptiert; anschliessend wurde
`GetCommandInvocation` für **dieselbe CommandId und Instanz** bis zum terminalen
Ergebnis gelesen: **`Success`, ResponseCode `0`**. Der Block lief als **UID 0**.
Console und nginx waren aktiv; Frontend und Backend meldeten `1.2.0`, und der
Jar-Hash entsprach weiterhin dem veröffentlichten Digest aus Auftrag 2.
Öffentliche Versionen sowie EC2-ID/IP/Startzeit/Profile blieben vor/nach der
Probe gleich; auch der lokale State blieb byte-identisch.

Die vollständigen Parameter, CommandId, AWS-Invocation und Verifikation sind
privat unter `~/.local/share/tictactest-iac/evidence/auftrag3-ssm-…/` gesichert,
nicht als Credentials oder als öffentliche Account-/Zielkennung im Repository.
Die API-Abfolge ist: Ziel aus State/Outputs bestimmen → `ssm send-command`
mit `AWS-RunShellScript` und explizitem Zeitlimit → CommandId sichern →
`ssm get-command-invocation` auf genau dieses Paar abfragen → Status/Exitcode
und Inhalte prüfen. Anfangs noch nicht sichtbare Invocations sind begrenzt
wiederholbar, echte Zugriffs-/Credentialfehler dagegen nicht.[8][9]

**Was damit bewiesen ist:** Die aktuelle Lab-Identität darf auf diesem Ziel
einen Befehl ausführen und dessen Ergebnis lesen. Der zukünftige GitHub-Runner
ist noch nicht eingerichtet und wurde damit nicht getestet. Weil SSM hier
Root-Befehle ausführen kann, sind die geplanten Workflow-/Environment- und
Secret-Schutzgrenzen notwendig. Abgelaufene oder neue Lab-Credentials müssen
später erneut geprüft werden. Als Nächstes folgt die ausdrücklich getrennte
Einrichtung des Environments und des sicheren Credential-Erneuerungswegs.

## Sources

[1] https://docs.github.com/actions/using-workflows/triggering-a-workflow — GITHUB_TOKEN triggers
[2] https://docs.github.com/actions/using-workflows/events-that-trigger-workflows — workflow_run
[3] https://docs.github.com/en/actions/reference/security/secure-use — Workflow security
[4] https://docs.github.com/en/actions/concepts/security/secrets — Secrets storage
[5] https://docs.github.com/actions/automating-your-workflow-with-github-actions/creating-and-using-encrypted-secrets — Secrets forks and use
[6] https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws — AWS OIDC
[7] https://docs.github.com/en/actions/using-jobs/using-concurrency — Concurrency
[8] https://docs.aws.amazon.com/systems-manager/latest/userguide/walkthrough-cli.html — AWS Run Command
[9] https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_GetCommandInvocation.html — SSM eventual consistency
