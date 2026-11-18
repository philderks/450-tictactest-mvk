#!/usr/bin/env bash
# Run with sudo on Amazon Linux 2023 x86_64. Does not start the application.
set -euo pipefail
umask 022
[[ $EUID -eq 0 ]] || { echo 'Run this installer as root.' >&2; exit 1; }
[[ $(uname -m) == x86_64 ]] || { echo 'Only x86_64 is supported.' >&2; exit 1; }
source /etc/os-release
[[ $ID == amzn && $VERSION_ID == 2023 ]] || { echo 'Amazon Linux 2023 required.' >&2; exit 1; }
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# Verify all local inputs before making host changes.
for file in nginx.conf tictactest-console.service tictactest-web.service; do
    [[ -f "$here/$file" ]] || { echo "Missing $here/$file" >&2; exit 1; }
done
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
curl --fail --location --retry 3 --connect-timeout 15 --max-time 180 --proto '=https' --tlsv1.2 \
    --output "$stage/ttyd" https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64
printf '%s  %s\n' 8a217c968aba172e0dbf3f34447218dc015bc4d5e59bf51db2f2cd12b7be4f55 "$stage/ttyd" | sha256sum --check --strict -
# Never permit the distribution nginx service to open port 80 during package installation.
systemctl mask nginx.service
dnf install -y \
    java-25-amazon-corretto-headless-1:25.0.5.1.2-1.amzn2023.1.x86_64 \
    nginx-1:1.30.6-1.amzn2023.0.1.x86_64
systemctl disable --now nginx.service
if ! id tictactest >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /var/lib/tictactest --no-create-home --shell /sbin/nologin tictactest
fi
# Do not silently repurpose an existing login account.
[[ $(id -u tictactest) -ne 0 && $(getent passwd tictactest | cut -d: -f7) == /sbin/nologin ]] || {
    echo 'tictactest must be an unprivileged nonlogin account.' >&2; exit 1;
}
install -o root -g root -m 0755 "$stage/ttyd" /usr/local/bin/ttyd
install -d -o root -g root -m 0755 /opt/tictactest /opt/tictactest/releases /etc/tictactest
install -o root -g root -m 0644 "$here/nginx.conf" /etc/tictactest/nginx.conf
for unit in tictactest-console.service tictactest-web.service; do
    install -o root -g root -m 0644 "$here/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable tictactest-console.service tictactest-web.service
echo 'Runtime installed; deploy a release separately to start the loopback-only services.'
