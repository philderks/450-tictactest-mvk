#!/usr/bin/env bash
# Prints the overall JaCoCo coverage in percent (one decimal).
# Usage: coverage-percent.sh [report-dir] [INSTRUCTION|BRANCH]
# Defaults to INSTRUCTION for the existing PR comparison; the published chart uses BRANCH.
# The last matching counter in the XML report is the total across all packages.
set -euo pipefail

xml="${1:-build/reports/jacoco/test}/jacocoTestReport.xml"
counter="${2:-INSTRUCTION}"
case "$counter" in
	INSTRUCTION|BRANCH) ;;
	*) printf 'Unsupported JaCoCo counter: %s\n' "$counter" >&2; exit 2 ;;
esac

grep -oE "<counter type=\"$counter\" missed=\"[0-9]+\" covered=\"[0-9]+\"/>" "$xml" |
	tail -1 |
	sed -E 's/[^0-9]+/ /g' |
	awk '{ printf "%.1f\n", $2 * 100 / ($1 + $2) }'
