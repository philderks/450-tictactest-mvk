"""Checks the JaCoCo percentage helper against a small XML report."""

import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("coverage-percent.sh")


class CoveragePercentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.report = Path(self.tmp.name) / "jacocoTestReport.xml"
        self.report.write_text(
            '<report name="test">'
            '<counter type="INSTRUCTION" missed="1" covered="9"/>'
            '<counter type="BRANCH" missed="2" covered="8"/>'
            '</report>',
            encoding="utf-8",
        )

    def run_metric(self, *args):
        return subprocess.run(
            ["bash", str(SCRIPT), self.tmp.name, *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_default_retains_instruction_coverage_for_pr_comparison(self):
        result = self.run_metric()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "90.0")

    def test_branch_counter_matches_enforced_gate(self):
        result = self.run_metric("BRANCH")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "80.0")

    def test_unsupported_counter_fails(self):
        result = self.run_metric("LINE")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
