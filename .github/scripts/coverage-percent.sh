#!/usr/bin/env bash
# Prints the overall JaCoCo instruction coverage in percent (one decimal).
# The last INSTRUCTION counter in the XML report is the total across all packages.
set -euo pipefail

xml="${1:-build/reports/jacoco/test}/jacocoTestReport.xml"

grep -oE '<counter type="INSTRUCTION" missed="[0-9]+" covered="[0-9]+"/>' "$xml" |
	tail -1 |
	sed -E 's/[^0-9]+/ /g' |
	awk '{ printf "%.1f\n", $2 * 100 / ($1 + $2) }'
