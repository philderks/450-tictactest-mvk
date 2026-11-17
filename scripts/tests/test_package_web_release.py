"""Tests for packaging static frontend and runtime release assets."""

import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/package-web-release.py"


class PackageWebReleaseTest(unittest.TestCase):
    def test_frontend_archive_has_release_version_without_changing_checkout(self):
        source_version = (ROOT / "frontend/version.txt").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "2.3.4", str(output)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            archive = output / "tictactest-frontend-2.3.4.zip"
            with zipfile.ZipFile(archive) as frontend:
                self.assertEqual(set(frontend.namelist()), {
                    "index.html", "style.css", "app.js", "config.js", "version.txt",
                })
                self.assertEqual(frontend.read("version.txt"), b"2.3.4\n")
                self.assertEqual(frontend.read("config.js"), (ROOT / "frontend/config.js").read_bytes())
            checksum = output / (archive.name + ".sha256")
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(checksum.read_text(), f"{expected}  {archive.name}\n")
        self.assertEqual((ROOT / "frontend/version.txt").read_bytes(), source_version)


    def test_runtime_archive_contains_support_tools_and_versioned_instructions(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "2.3.4", str(output)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            archive = output / "tictactest-runtime-2.3.4.zip"
            self.assertTrue(archive.is_file(), "Runtime tools must be released with the frontend")
            with zipfile.ZipFile(archive) as runtime:
                self.assertEqual(set(runtime.namelist()), {
                    "backend-version.py", "serve-backend-version.py", "start-console.sh", "README.md",
                })
                for name in ["backend-version.py", "serve-backend-version.py", "start-console.sh"]:
                    self.assertEqual(runtime.read(name), (ROOT / "scripts" / name).read_bytes())
                instructions = runtime.read("README.md").decode()
                self.assertIn('VERSION="2.3.4"', instructions)
                self.assertNotIn("@VERSION@", instructions)
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(archive.with_suffix(".zip.sha256").read_text(), f"{expected}  {archive.name}\n")

    def test_invalid_versions_fail_before_creating_output(self):
        for version in ["v2.3.4", "../2.3.4", "2.03.4", "2.3.4\n", "2.3.4;echo unsafe"]:
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "assets"
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), version, str(output)],
                    capture_output=True, text=True, check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
