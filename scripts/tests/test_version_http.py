"""HTTP integration tests for the read-only backend version endpoint."""

import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request


SCRIPT = Path(__file__).resolve().parents[1] / "serve-backend-version.py"
ORIGIN = "http://localhost:8000"


class VersionHTTPTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "The HTTP version server must exist")
        spec = importlib.util.spec_from_file_location("version_http", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.version = Path(self.directory.name) / "version.txt"
        self.version.write_text("2.3.4\n", encoding="utf-8")
        self.server = module.create_server(self.version, "127.0.0.1", 0, [ORIGIN])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_version_has_no_cache_and_cors_only_for_allowed_origin(self):
        for origin in [ORIGIN, "https://untrusted.example.test", None]:
            with self.subTest(origin=origin):
                headers = {"Origin": origin} if origin else {}
                request = urllib.request.Request(self.url + "/version.txt", headers=headers)
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), b"2.3.4\n")
                    self.assertEqual(response.headers.get_content_type(), "text/plain")
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertEqual(response.headers["Vary"], "Origin")
                    expected = ORIGIN if origin == ORIGIN else None
                    self.assertEqual(response.headers["Access-Control-Allow-Origin"], expected)

    def test_missing_file_returns_service_unavailable(self):
        self.version.unlink()
        request = urllib.request.Request(self.url + "/version.txt", headers={"Origin": ORIGIN})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(caught.exception.code, 503)
        caught.exception.close()

    def test_unrelated_paths_do_not_expose_files_or_a_directory_listing(self):
        for path in ["/", "/release.jar", "/../version.txt", "/version.txt/extra"]:
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(self.url + path, timeout=5)
                self.assertEqual(caught.exception.code, 404)
                caught.exception.close()


if __name__ == "__main__":
    unittest.main()
