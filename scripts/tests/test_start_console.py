"""Verify that the console launcher extracts metadata and execs only the JAR."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "start-console.sh"


class StartConsoleTest(unittest.TestCase):
    def test_extracts_version_then_passes_java_and_jar_directly_to_ttyd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "release bundle"
            root.mkdir()
            jar = root / "misleading-9.9.9.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr(
                    "META-INF/MANIFEST.MF",
                    "Manifest-Version: 1.0\r\nImplementation-Version: 2.3.4\r\n\r\n",
                )
            before = hashlib.sha256(jar.read_bytes()).hexdigest()
            capture = root / "arguments.json"
            ttyd = root / "fake ttyd"
            ttyd.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "Path(os.environ['CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            ttyd.chmod(0o755)
            env = os.environ | {
                "TTYD_BIN": str(ttyd), "JAVA_BIN": sys.executable,
                "TTYD_PORT": "17681", "CAPTURE": str(capture),
            }
            result = subprocess.run(
                ["bash", str(SCRIPT), str(jar)],
                cwd=root, env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "version.txt").read_text(), "2.3.4\n")
            self.assertEqual(json.loads(capture.read_text()), [
                "-W", "-O", "-i", "127.0.0.1", "-p", "17681", "-m", "4",
                sys.executable, "-Xmx64m", "-jar", str(jar),
            ])
            self.assertEqual(hashlib.sha256(jar.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
