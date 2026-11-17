#!/usr/bin/env python3
"""Write a release JAR's Implementation-Version to a text file."""

import argparse
from pathlib import Path
import zipfile


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("jar", type=Path, help="Release JAR to inspect without changing it")
parser.add_argument("output", type=Path, help="Destination version.txt file")
args = parser.parse_args()

if args.output.resolve() == args.jar.resolve() or (
    args.output.exists() and args.output.samefile(args.jar)
):
    parser.exit(1, "Fehler: Die Ausgabedatei darf nicht das Release-Jar sein.\n")

with zipfile.ZipFile(args.jar) as archive:
    manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8")
main_section = manifest.replace("\r\n", "\n").split("\n\n", 1)[0]
version = next(
    (line.partition(":")[2].strip() for line in main_section.splitlines()
     if line.startswith("Implementation-Version:")),
    "",
)
if not version:
    parser.exit(1, "Fehler: Implementation-Version fehlt oder ist leer.\n")
args.output.write_text(version + "\n", encoding="utf-8")
print(version)
