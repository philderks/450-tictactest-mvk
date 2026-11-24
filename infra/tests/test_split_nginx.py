"""Split frontend proxy contracts; no running nginx or cloud is modified."""
from pathlib import Path
import unittest


CONFIG = Path(__file__).resolve().parents[1] / "bootstrap/nginx.conf"


class SplitProxyTests(unittest.TestCase):
    def test_frontend_root_is_independent_from_backend_selection(self):
        text = CONFIG.read_text()
        self.assertIn("root /opt/tictactest/frontend-current/frontend;", text)
        self.assertNotIn("root /opt/tictactest/current/frontend;", text)

    def test_public_configuration_is_owned_by_infrastructure(self):
        text = CONFIG.read_text()
        self.assertIn("location = /config.js {", text)
        block = text.split("location = /config.js {", 1)[1].split("\n        }", 1)[0]
        self.assertIn("default_type application/javascript;", block)
        self.assertIn('add_header Cache-Control "no-store" always;', block)
        self.assertIn('add_header X-TicTacTest-Layout "split-v1" always;', block)
        self.assertIn('return 200 "window.TICTACTEST_CONFIG = {', block)
        self.assertIn("consoleUrl: '/console/'", block)
        self.assertIn("backendVersionUrl: '/backend-version.txt'", block)
        self.assertNotIn("alias ", block)
        self.assertNotIn("try_files", block)


if __name__ == "__main__":
    unittest.main()
