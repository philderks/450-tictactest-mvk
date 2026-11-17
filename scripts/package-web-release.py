#!/usr/bin/env python3
"""Package versioned web release assets without changing the source checkout."""

import argparse
import hashlib
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", args.version):
        parser.error("version must be MAJOR.MINOR.PATCH without a v prefix")
    args.output.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "frontend": {
            name: (ROOT / "frontend" / name).read_bytes()
            for name in ["index.html", "style.css", "app.js", "config.js"]
        },
        "runtime": {
            name: (ROOT / "scripts" / name).read_bytes()
            for name in ["backend-version.py", "serve-backend-version.py", "start-console.sh"]
        },
    }
    artifacts["frontend"]["version.txt"] = (args.version + "\n").encode("utf-8")
    artifacts["runtime"]["README.md"] = (
        (ROOT / "scripts/runtime-README.md").read_text(encoding="utf-8")
        .replace("@VERSION@", args.version).encode("utf-8")
    )
    for component, files in artifacts.items():
        archive = args.output / f"tictactest-{component}-{args.version}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, content in files.items():
                bundle.writestr(name, content)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
        print(archive)


if __name__ == "__main__":
    main()
