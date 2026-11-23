#!/usr/bin/env bash
# Keep the Python helper beside this entrypoint; no checkout/build on EC2.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec /usr/bin/python3 -B "$here/deploy-release.py" "$@"
