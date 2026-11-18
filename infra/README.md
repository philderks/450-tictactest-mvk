# IaC-Grundlage für TicTacTest

Hier entsteht die Infrastruktur im bestehenden TicTacTest-Repository. Das entspricht
Abschnitt 3 des Auftragsblatts «OpenTofu / Terraform – Erste Cloud-Infrastruktur»
(Version `261025-2975cf8f-DIRTY-c8d191ad`). Die zugehörigen Begriffe und Befehle
behandelt das gleich versionierte Handout für Lernende.

## Roter Faden

1. **Vorbereitung:** Werkzeuge installieren und Git vor lokalen Betriebsdaten schützen.
2. **Zugriff:** temporäre Learner-Lab-Zugangsdaten ausserhalb von Git einrichten;
   Konto, Region und vorhandene Ressourcen zuerst nur lesend prüfen.
3. **Konfiguration:** eine EC2-Instanz der Grössenordnung `micro`, ein eigenes
   SSH-Key-Paar und eine Security Group für SSH beschreiben; SSH auf die tatsächlich
   benötigten Quelladressen beschränken. Einen öffentlichen Endpunkt ausgeben.
4. **Plan und Test:** Konfiguration initialisieren und validieren, Plan gemeinsam
   prüfen, erst nach Freigabe anwenden und echten SSH-Zugriff testen.
5. **Abschluss:** State, Git-Regeln, Kostenkontrolle und den CI/CD-Ausblick erklären;
   Testressourcen nach abgesprochener Freigabe entfernen und das Ergebnis prüfen.

Erst danach folgt Webapp-Auftrag 2: Die Grundlage für den Betrieb und das manuelle
Deployment der veröffentlichten TicTacTest-Artefakte erweitern. Anwendung und
Infrastruktur bleiben getrennt; ein Release ist keine Infrastruktur-Neuerstellung.

## Aktueller, nachgewiesener Stand

- Der Nutzer hat das Learner Lab laut eigener Angabe gestartet.
- In der Hermes-Entwicklungsumgebung sind OpenTofu `1.13.9` und AWS CLI `2.41.0`
  installiert; beide Versionsbefehle wurden erfolgreich ausgeführt.
- Der OpenTofu-Download wurde gegen die veröffentlichten SHA-256-Prüfsummen und
  die offiziellen GitHub-Asset-Digests geprüft. Das AWS-CLI-Paket wurde vor der
  Installation mit dem Signaturschlüssel aus der offiziellen AWS-Dokumentation geprüft.
- `infra/.gitignore` schützt lokale Variablen, State, Providerdateien, Plan-Dateien
  und übliche Schlüsseldateien vor versehentlichem Hinzufügen.
- Das Profil `tictactest-lab` wurde vom Nutzer ausserhalb des Repositorys angelegt.
  Der AWS-Ordner hat Modus `0700`, die Zugangsdaten-Datei Modus `0600` und gehört
  dem ausführenden Benutzer. Die Zugangsdaten wurden nicht angezeigt.
- Die reine Identitätsabfrage `sts get-caller-identity` war mit diesem Profil und
  expliziter Region `us-east-1` erfolgreich; AWS meldet eine angenommene
  Learner-Lab-Rolle `voclabs`. Konto-ID und persönliche Sitzungskennung werden
  nicht ins Repository übernommen. Das bestätigt die Anmeldung, nicht sämtliche
  EC2-Berechtigungen oder die erlaubten Regionen.
- Die lesenden EC2-/Netzwerkabfragen in `us-east-1` waren erfolgreich; die
  Ergebnisse und Grenzen stehen im Abschnitt «Lesende Bestandsaufnahme».
- Die erste Konfigurationsbasis besteht aus `main.tf` (Provider und
  Versionsanforderungen) und `variables.tf` (Regionsvariable). `tofu init`,
  `tofu fmt -check` und `tofu validate` waren erfolgreich. Installiert wurde der
  signierte AWS-Provider `6.73.0`; `.terraform.lock.hcl` hält diese Auswahl fest.
- Ein lokaler Konsolentest schlug vor dem Anlegen der Variable mit «undeclared
  input variable» fehl und liefert danach den erwarteten Standard `us-east-1`.
- Datenquellen, Ressourcen und Outputs sind ergänzt. Der erste echte AWS-Plan
  enthielt nur drei Neuerstellungen: Instanz, SSH-Key-Pair und Security Group.
  Der Planchecker bestand mit 21 Prüfungen.
- Ein eigenes Ed25519-Key-Paar wurde lokal ausserhalb des Repositorys erzeugt;
  der private Schlüssel hat Modus `0600` und wird von OpenTofu nicht gelesen.
- Ungültige Eingaben wurden tatsächlich abgewiesen: weltweiter SSH-Zugriff,
  ein grösserer Instanztyp und eine fehlende öffentliche Schlüsseldatei.
- Der Nutzer hat die Anzeige als «Used $0 of $50» präzisiert und das Anwenden
  freigegeben. Nach erneuter Plan-, Konto-, Regions- und SSH-Quellprüfung war
  `apply` erfolgreich: **3 hinzugefügt, 0 geändert, 0 gelöscht**.
- Die AWS-API bestätigt die laufende Instanz, das eigene Key-Pair, die
  eingeschränkte Security Group, die verschlüsselte Systemdisk, IMDSv2 und
  Standard-CPU-Credits. Instanz- und Systemstatus sind jeweils `ok`.
- Echter SSH-Login vom Hermes-Host als `ec2-user` war erfolgreich. Der
  SSH-Hostschlüssel wurde vorher mit dem Fingerprint aus der authentifizierten
  EC2-Konsolenausgabe verglichen. Das System meldet Amazon Linux
  `2023.12.20261117`.
- Ein anschliessender `plan -detailed-exitcode` endete mit Exitcode `0`:
  keine Infrastrukturänderungen. State, lokale Variablen und Plan-Dateien sind
  mit Modus `0600` geschützt und von Git ausgeschlossen.
- **Noch offen:** kontrolliertes Aufräumen nach separater Freigabe sowie die
  übrige Grundlagenreflexion. Die Instanz läuft derzeit; die Webapp ist dort
  noch nicht installiert. Der vollständige IaC-Lernauftrag ist noch nicht als
  abgeschlossen zu betrachten.

## Erste Konfigurationsbasis: Provider und Variable

Dieser erste Lernschritt gehörte zu Abschnitt 3 des IaC-Auftrags. Seine
Konfiguration beschrieb zunächst nur das Provider-Plugin und die Region.
Die später ergänzten Ressourcen stehen im folgenden Abschnitt.

- `main.tf`: `required_providers` wählt `hashicorp/aws` in Version `6.x`;
  `provider "aws"` erhält die Region über `var.aws_region`. Der Block
  `terraform` heisst auch bei OpenTofu so und enthält die Versionsanforderungen.
- `variables.tf`: deklariert `aws_region` als Zeichenkette mit dem Standard
  `us-east-1`. Die Variable ist die Eingabe; `var.aws_region` liest ihren Wert.
- `.terraform.lock.hcl`: von OpenTofu erzeugte, versionierbare Provider-Lockdatei,
  keine Zugangsdaten-Datei und kein Infrastruktur-State.

Aus dem Repository-Hauptverzeichnis wurden erfolgreich ausgeführt:

```bash
tofu -chdir=infra init -input=false
tofu -chdir=infra fmt -check
tofu -chdir=infra validate
printf 'var.aws_region\n' | tofu -chdir=infra console
```

`init` lädt das Plugin und bereitet in dieser Konfiguration den lokalen
Arbeitsbereich vor. `validate` prüft die Konfiguration; es ist kein Nachweis
für AWS-Schreibrechte, erreichbare Instanzen oder einen vollständigen Auftrag.
`console` wertete hier nur die lokale Regionsvariable aus. Keine dieser Prüfungen
erstellte eine EC2-Instanz. In diesem ersten Lernschritt wurde noch kein Plan
ausgeführt; der echte Ressourcenplan folgte erst nach der Konfiguration unten.

Für spätere AWS-Abfragen mit OpenTofu das Profil ohne Geheimnisse im Code wählen,
zum Beispiel mit `AWS_PROFILE=tictactest-lab` vor dem jeweiligen Befehl. Die
Zugangsdaten bleiben in der vom Nutzer gepflegten Datei ausserhalb von Git.

## Ressourcen und erster echter Plan

Dieser zweite Konfigurationsschritt gehört ebenfalls zu Abschnitt 3 des
IaC-Grundauftrags, noch nicht zum Deployment der Webapp.

| HCL-Block | Bedeutung |
| --- | --- |
| `data.aws_vpc.default` | Vorhandene Standard-VPC lesen, nicht erstellen oder übernehmen. |
| `data.aws_subnet.selected` | Vorhandenes Standard-Subnetz in der gewählten Zone lesen. |
| `data.aws_ami.server` | Die feste AMI-ID gegen ein Amazon-Abbild für `x86_64` prüfen. |
| `aws_key_pair.ssh` | Nur den öffentlichen Teil des eigenen Schlüssels bei AWS registrieren. |
| `aws_security_group.ssh` | Eingehend ausschliesslich TCP/22 von einer IPv4-Adresse mit `/32` erlauben. |
| `aws_instance.server` | Eine `t3.micro` mit diesen Netzwerk- und SSH-Einstellungen beschreiben. |
| `output.public_ip` / `output.instance_id` | Nach Erstellung Adresse und Instanz-ID ausgeben. |

Die Instanz referenziert Security Group und Key-Pair. Dadurch erkennt OpenTofu
die Abhängigkeiten selbst; die Reihenfolge der Blöcke im Text ist nicht die
Ausführungsreihenfolge.

### Lokale Werte und SSH

`terraform.tfvars.example` enthält bereinigte Beispielwerte. `terraform.tfvars`
enthält die tatsächlichen lokalen Werte, hat Modus `0600` und wird von Git
ignoriert. Die Dokumentationsadresse im Beispiel muss durch die echte öffentliche
Adresse des SSH-Clients ersetzt werden. Aktuell ist nur der Hermes-Host als
SSH-Quelle vorgesehen; der persönliche Rechner ist nicht zusätzlich freigegeben.

Das eigene Schlüsselpaar liegt auf dem Hermes-Host unter
`~/.ssh/tictactest_lab_ed25519` und der zugehörigen `.pub`-Datei. Es wurde ohne
Passphrase für den automatisierten Test erzeugt; Dateirechte schützen den
privaten Schlüssel. Nur die `.pub`-Datei wird von der Konfiguration gelesen.
Keine `tls_private_key`-Ressource verwenden, die den privaten Schlüssel in den
OpenTofu-State schreiben würde. Das vorhandene Lab-Key-Pair `vockey` bleibt
unverändert.

### Erster geprüfter Erstellungsplan

Im Repository-Hauptverzeichnis:

```bash
tofu -chdir=infra fmt -check
tofu -chdir=infra validate
AWS_PROFILE=tictactest-lab tofu -chdir=infra plan -input=false -out=.terraform/iac.tfplan
tofu -chdir=infra show -json .terraform/iac.tfplan > infra/.terraform/iac-plan.json
python3 infra/tests/check_plan.py infra/.terraform/iac-plan.json
```

Tatsächlich beobachtet: **3 erstellen, 0 ändern, 0 löschen**. Der Checker wurde
zuerst gegen den noch leeren Basisplan ausgeführt und scheiterte erwartungsgemäss
an den fehlenden Ressourcen. Nach Ergänzung bestand der echte Plan 21 Prüfungen.
Ein eigener Prüfskriptfehler wurde anhand des realen JSON-Formats korrigiert:
bereits gelesene Datenquellen stehen hier im `prior_state`, neue verwaltete
Ressourcen im `planned_values`.

Die Instanz hat eine verschlüsselte 8-GiB-`gp3`-Systemdisk, die mit der Instanz
gelöscht werden soll, und verlangt IMDSv2. CPU-Credits stehen auf `standard`,
nicht `unlimited`. Ausgehende Verbindungen sind erlaubt; die einzige eingehende
Regel ist SSH von der vorgesehenen Einzeladresse. Es gibt weder HTTP-Freigabe
noch installierte TicTacTest-Dienste. Eine öffentliche IP wird bei Erstellung
zugewiesen, ist hier aber noch nicht mit einer Elastic IP dauerhaft festgelegt.

Ein erfolgreicher Plan beweist noch keinen erfolgreichen Start oder SSH-Zugriff.
Vor `apply` sind Lab-Budget und Nutzerfreigabe erforderlich. Bei abgelaufenen
Zugangsdaten, geänderten Eingaben, geändertem SSH-Quellnetz oder einem späteren
Zeitpunkt den Plan erneut prüfen, statt einen alten Plan blind anzuwenden.

### Nachgewiesene Erstellung und SSH-Verbindung

Nach der Budgetklärung und Freigabe wurde der frisch geprüfte gespeicherte Plan
mit `AWS_PROFILE=tictactest-lab` angewendet. AWS-API-Abfragen lasen anschliessend
die konkret erstellte Instanz, Security Group, das Key-Pair und die Systemdisk
zurück. Beobachtet wurden:

- Instanz: `running`, `t3.micro`, das vorgesehene Amazon-Linux-Abbild und das
  eigene Key-Pair; Instanz- und Systemstatus jeweils `ok`.
- Firewall: eingehend nur TCP/22 von der vorgesehenen IPv4-Einzeladresse;
  kein HTTP und keine zusätzliche IPv6-, Gruppen- oder Prefix-List-Freigabe.
- Systemdisk: 8 GiB, `gp3`, verschlüsselt, an die richtige Instanz angehängt;
  `DeleteOnTermination` ist aktiv.
- Instanzmetadaten verlangen Tokens; CPU-Credits stehen auf `standard`.
- Die Netzverbindung per SSH funktioniert tatsächlich als `ec2-user`;
  `uname -sr` meldet `Linux 6.18.62-127.179.amzn2023.x86_64`.

Vor dem ersten Login wurde der Ed25519-Hostschlüssel aus `ssh-keyscan` nicht
blind akzeptiert, sondern sein SHA-256-Fingerprint mit der über die AWS-API
gelesenen EC2-Bootausgabe verglichen. Der übereinstimmende Schlüssel liegt in
`~/.local/share/tictactest-iac/known_hosts`, ausserhalb von Git. Der Login lief
mit `StrictHostKeyChecking=yes`, `IdentitiesOnly=yes` und `BatchMode=yes`.

Ein erneuter Login ist **auf dem Hermes-Host** aus dem Repository möglich:

```bash
host="$(tofu -chdir=infra output -raw public_ip)"
ssh -i "$HOME/.ssh/tictactest_lab_ed25519" \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="$HOME/.local/share/tictactest-iac/known_hosts" \
  "ec2-user@$host"
```

Dieser Schlüssel und die erlaubte Quell-IP sind nicht automatisch auf dem
persönlichen Rechner vorhanden. Bei geänderter öffentlicher Server-IP muss die
Hostschlüsselzuordnung erneut sicher geprüft werden.

Zur Wiederholbarkeitsprüfung wurde danach ausgeführt:

```bash
AWS_PROFILE=tictactest-lab tofu -chdir=infra plan -input=false -detailed-exitcode
```

Ergebnis: Exitcode `0`, keine Änderungen. Den Checker für den ersten
Erstellungsplan nicht auf einen späteren No-op-, Änderungs- oder Löschplan
anwenden: Er erwartet absichtlich genau die drei erstmaligen Neuerstellungen.

### Was der State jetzt bedeutet

`terraform.tfstate` verknüpft die HCL-Adressen wie `aws_instance.server` mit den
echten AWS-Objekten. Dadurch kann OpenTofu beim nächsten Plan dieselben Objekte
wiedererkennen, statt erneut einen Server anzulegen. Der State ist keine
Anmeldedatei und nicht die Provider-Lockdatei; er enthält aber interne
Laufzeitinformationen und muss geschützt, gesichert und aus Git herausgehalten
werden. Vorhandenen State nicht als vermeintlichen Build-Abfall löschen. Eine
byteidentische Sicherung des aktuellen State wurde mit Modus `0600` unter
`~/.local/share/tictactest-iac/terraform.tfstate` ausserhalb des Repositorys
angelegt; sie ist eine Momentaufnahme, kein automatisch aktuelles Backup.

Die Instanz ist noch nicht aufgeräumt. Für Kostenkontrolle klein dimensionieren,
das Lab-Budget beobachten und Testressourcen nach Freigabe vollständig entfernen.
Eine reine SSH-Abmeldung beendet den Server nicht. Ein Aufräumplan und die
Prüfung nach dessen Anwendung sind ein eigener, noch offener Lernschritt.

## Historische lesende Bestandsaufnahme vor der Konfiguration

Mit dem Profil `tictactest-lab` wurden die AWS-APIs tatsächlich abgefragt:

| Prüfung | Beobachtung | Bedeutung für die nächste Etappe |
| --- | --- | --- |
| VPC | Eine verfügbare Standard-VPC ist vorhanden. | Das bestehende Netz verwenden, nicht neu erstellen. |
| Subnetze und Routing | Verfügbare Subnetze mit automatischer öffentlicher IPv4-Zuweisung; die Haupt-Routentabelle hat eine aktive Standardroute zum angeschlossenen Internet Gateway. | Die Netzwerkgrundlage für einen öffentlichen SSH-Endpunkt ist vorhanden; eine konkrete Verbindung ist noch nicht getestet. |
| Instanztypen | `t2.micro` und `t3.micro` werden in der Region angeboten; `t3.micro` auch in `us-east-1a`. | `t3.micro` ist der vorgesehene kleine Instanztyp. Das Angebot ist keine Zusage für freie Kapazität oder die Berechtigung zum Starten. |
| Betriebssystem-Abbild | Der öffentliche AWS-SSM-Parameter für Amazon Linux 2023 liefert `ami-00f43ee0e98d52529`; EC2 bestätigt ein verfügbares Amazon-Abbild mit `x86_64`, EBS-Root und HVM. | Eine echte passende AMI wurde gefunden, nicht die Platzhalter-AMI aus dem Handout übernommen. |
| Vorhandene Instanzen | Die Abfrage nach `pending`, `running`, `stopping` und `stopped` liefert keine Instanzen. | In dieser Region wurde in diesen Zuständen keine bestehende Instanz gefunden; das ist keine Aussage über andere Regionen oder andere AWS-Dienste. |
| SSH-Key-Paare | Das Lab-Key-Paar `vockey` ist vorhanden. | Für den Auftrag trotzdem ein eigenes Paar vorsehen; der private Schlüssel bleibt ausserhalb des Repositorys. |

Verwendete lesende Aktionen: `ec2 describe-vpcs`, `describe-subnets`,
`describe-route-tables`, `describe-internet-gateways`, `describe-instance-types`,
`describe-instance-type-offerings`, `describe-instances`, `describe-key-pairs`,
`describe-images` sowie `ssm get-parameter` für den öffentlichen AMI-Parameter.
Interne Netzwerk-IDs und persönliche Kontodaten werden hier nicht festgehalten.

Auf Grundlage dieser Bestandsaufnahme wurde die Konfiguration oben erstellt.
Bestehende Netzressourcen werden lediglich referenziert. Die anfänglich noch
offene Bereitstellung und Erreichbarkeit wurde anschliessend wie oben beschrieben
erfolgreich geprüft. Das Lab-Budget weiterhin in der Learner-Lab-Oberfläche
beobachten; der ursprüngliche Budgetstand ist keine aktuelle Kostenmessung.

Die Werkzeuge sind auf dem Hermes-Host installiert, nicht automatisch auf dem
persönlichen Rechner. In dessen Entwicklungsumgebung wäre eine eigene Installation
nötig. Die Versionsnummern oben dokumentieren den geprüften Stand, nicht dauerhaft
«die neueste Version».

```bash
# In der eingerichteten Entwicklungsumgebung:
tofu version
aws --version
```

## Warum zwei Werkzeuge?

- **AWS CLI:** einzelne AWS-API-Abfragen ausführen, zum Beispiel später das
  verwendete Konto prüfen. Hiermit wird zuerst der Zugriff überprüft.
- **OpenTofu:** den gewünschten Infrastrukturzustand in `.tf`-Dateien beschreiben
  und geplante Änderungen vor dem Anwenden anzeigen lassen.

Der Nutzer hat `us-east-1` als Lab-Region angegeben und die temporären Zugangsdaten
selbst hinterlegt. Der erfolgreiche erste Test lautet:

```bash
aws --profile tictactest-lab --region us-east-1 --no-cli-pager sts get-caller-identity
```

Dieser Befehl fragt nur die verwendete AWS-Identität ab und erstellt keine
Infrastruktur. Der erfolgreiche Test gilt für die zum Testzeitpunkt gültige
Lab-Sitzung; abgelaufene Zugangsdaten müssen erneuert werden. Keine Schlüssel,
Token, Credential-Screenshots oder State-Dateien in den Chat senden.

## Was gehört in Git?

| In Git | Nicht in Git |
| --- | --- |
| `.tf`-Konfiguration ohne Geheimnisse | AWS Access Keys, Secret Keys und Session Tokens |
| Dieses README und `.gitignore` | Private SSH-Schlüssel und lokale Zugangsdaten |
| Bereinigte `*.tfvars.example` | Lokale `*.tfvars` und `*.tfvars.json` |
| Die von `init` erzeugte `.terraform.lock.hcl` | `.terraform/`, State, State-Backups und gespeicherte Pläne |

Die Lockdatei hält Provider-Auswahl und Prüfsummen fest. Sie ist **nicht der State**.
Ignorieren ist kein sicherer Geheimnisspeicher: Zugangsdaten und private Schlüssel
werden grundsätzlich ausserhalb des Repositorys aufbewahrt. `.gitignore` schützt
auch keine bereits getrackten Dateien und kann mit `git add -f` umgangen werden.

## Quellen für die Werkzeugvorbereitung

- Offizielle OpenTofu-Releases: <https://github.com/opentofu/opentofu/releases>
- Offizielle AWS-CLI-Installation und Signaturprüfung:
  <https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html>

Das Handout enthält Lernbeispiele. Seine Beispiel-AMI und Beispielregion werden
nicht ungeprüft für das echte Learner Lab übernommen. Das S3-Minimalbeispiel
ersetzt nicht die ausdrücklich verlangte EC2-Instanz mit SSH-Zugriff.
