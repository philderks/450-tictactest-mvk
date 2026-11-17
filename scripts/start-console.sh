#!/usr/bin/env bash
# Generate release-derived metadata, then give ttyd a direct Java command.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'Usage: bash %s RELEASE.jar\n' "$0" >&2
  exit 2
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
JAR=$1
JAVA_BIN=${JAVA_BIN:-java}
TTYD_BIN=${TTYD_BIN:-ttyd}
command -v "$JAVA_BIN" >/dev/null
command -v "$TTYD_BIN" >/dev/null

python3 "$SCRIPT_DIR/backend-version.py" "$JAR" "${VERSION_FILE:-$(dirname -- "$JAR")/version.txt}"
exec "$TTYD_BIN" -W -O -i 127.0.0.1 -p "${TTYD_PORT:-7681}" -m 4 \
  "$JAVA_BIN" -Xmx64m -jar "$JAR"
