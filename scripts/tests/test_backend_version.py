"""Tests for extracting a backend version from a release JAR."""

import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "backend-version.py"


class BackendVersionTest(unittest.TestCase):
    def test_uses_manifest_version_not_filename_and_preserves_jar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jar = root / "misleading-9.9.9.jar"
            output = root / "version.txt"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr(
                    "META-INF/MANIFEST.MF",
                    "Manifest-Version: 1.0\r\n"
                    "Implementation-Version: 2.3.4\r\n\r\n",
                )
            before = hashlib.sha256(jar.read_bytes()).hexdigest()

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(jar), str(output)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_text(), "2.3.4\n")
            self.assertEqual(result.stdout, "2.3.4\n")
            self.assertEqual(hashlib.sha256(jar.read_bytes()).hexdigest(), before)


    def test_missing_version_fails_without_replacing_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jar = root / "no-version.jar"
            output = root / "version.txt"
            output.write_text("previous-version\n")
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr(
                    "META-INF/MANIFEST.MF", "Manifest-Version: 1.0\r\n\r\n"
                )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(jar), str(output)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Implementation-Version", result.stderr)
            self.assertEqual(output.read_text(), "previous-version\n")


    def test_output_cannot_overwrite_the_release_jar(self):
        with tempfile.TemporaryDirectory() as directory:
            jar = Path(directory) / "release.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr(
                    "META-INF/MANIFEST.MF",
                    "Manifest-Version: 1.0\r\nImplementation-Version: 2.3.4\r\n\r\n",
                )
            before = jar.read_bytes()

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(jar), str(jar)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(jar.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
