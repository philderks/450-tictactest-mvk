"""Offline contract for the explicitly approved public HTTP frontend."""
from pathlib import Path
import re
import unittest


INFRA = Path(__file__).resolve().parents[1]


class PublicHTTPConfigTests(unittest.TestCase):
    def test_only_frontend_is_public_and_port_binding_stays_unprivileged(self):
        proxy = (INFRA / "bootstrap/nginx.conf").read_text()
        self.assertIn("listen 0.0.0.0:80;", proxy)
        self.assertIn("listen 127.0.0.1:8080;", proxy)
        self.assertIn("proxy_pass http://127.0.0.1:7681;", proxy)
        unit = (INFRA / "bootstrap/tictactest-web.service").read_text()
        for setting in ("User=tictactest", "NoNewPrivileges=true",
                        "CapabilityBoundingSet=CAP_NET_BIND_SERVICE",
                        "AmbientCapabilities=CAP_NET_BIND_SERVICE"):
            self.assertIn(setting, unit)
        console = (INFRA / "bootstrap/tictactest-console.service").read_text()
        self.assertIn("-i 127.0.0.1 -p 7681", console)
        self.assertIn("CapabilityBoundingSet=\n", console)
        self.assertNotIn("AmbientCapabilities=", console)
        main = (INFRA / "main.tf").read_text()
        rules = re.findall(r"ingress\s*\{([^}]+)\}", main)
        self.assertEqual(len(rules), 2)
        http = [r for r in rules if re.search(r"from_port\s*=\s*80\b", r)]
        self.assertEqual(len(http), 1)
        self.assertRegex(http[0], r"to_port\s*=\s*80\b")
        self.assertIn('["0.0.0.0/0"]', http[0])
        ssh = [r for r in rules if re.search(r"from_port\s*=\s*22\b", r)]
        self.assertEqual(len(ssh), 1)
        self.assertIn("[var.ssh_allowed_cidr]", ssh[0])
        outputs = (INFRA / "outputs.tf").read_text()
        for name in ("frontend_url", "console_url", "backend_version_url"):
            self.assertIn('output "' + name + '"', outputs)


if __name__ == "__main__":
    unittest.main()
