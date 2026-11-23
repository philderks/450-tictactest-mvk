"""Offline first-boot contracts; never run the installer or contact AWS."""
import base64
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


INFRA = Path(__file__).resolve().parents[1]
FILES = {
    "install_runtime_b64": "install-runtime.sh",
    "nginx_conf_b64": "nginx.conf",
    "console_unit_b64": "tictactest-console.service",
    "web_unit_b64": "tictactest-web.service",
}


class BootstrapTests(unittest.TestCase):
    def sources(self):
        local = INFRA / "bootstrap.tf"
        template = INFRA / "bootstrap/user-data.sh.tftpl"
        self.assertTrue(local.is_file(), "bootstrap user_data local is missing")
        self.assertTrue(template.is_file(), "first-boot shell template is missing")
        return local.read_text(), template.read_text()

    def rendered(self):
        local, template = self.sources()
        # Deliberately limited to this four-file contract, not a Terraform interpreter.
        entries = re.findall(
            r'^\s*(\w+)\s*=\s*base64encode\(file\("\$\{path.module\}/bootstrap/([^"/]+)"\)\)\s*$',
            local, re.MULTILINE,
        )
        self.assertEqual(len(entries), 4)
        self.assertEqual(dict(entries), FILES)
        values = {
            key: base64.b64encode((INFRA / "bootstrap" / name).read_bytes()).decode("ascii")
            for key, name in entries
        }
        self.assertEqual(re.findall(r"\$\{([^}]+)\}", template), list(FILES))
        rendered = re.sub(r"\$\{([^}]+)\}", lambda match: values[match[1]], template)
        self.assertNotIn("${", rendered)
        return rendered

    def test_local_maps_exactly_four_existing_runtime_files(self):
        local, _ = self.sources()
        self.assertRegex(local, r'bootstrap_user_data\s*=\s*templatefile\("\$\{path.module\}/bootstrap/user-data\.sh\.tftpl",\s*\{')
        # A closed local/mapping prevents unnoticed version inputs or other behavior.
        entries = "\n".join(
            rf'\s*{key}\s*=\s*base64encode\(file\("\$\{{path.module\}}/bootstrap/{re.escape(name)}"\)\)'
            for key, name in FILES.items()
        )
        self.assertRegex(local, r'(?s)^locals\s*\{\s*bootstrap_user_data\s*=\s*templatefile\("\$\{path.module\}/bootstrap/user-data\.sh\.tftpl",\s*\{' + entries + r'\s*\}\)\s*\}\s*$')
        self.rendered()

    def test_decode_commands_preserve_every_source_byte(self):
        rendered = self.rendered()
        commands = re.findall(
            r'''^printf '%s' '([A-Za-z0-9+/=]+)' \| base64 --decode > "\$bootstrap_dir/([^"/]+)"$''',
            rendered, re.MULTILINE,
        )
        self.assertEqual(len(commands), 4)
        self.assertEqual([name for _, name in commands], list(FILES.values()))
        with tempfile.TemporaryDirectory() as directory:
            # Execute only the four real printf/decode pipelines in an isolated directory.
            lines = [line for line in rendered.splitlines() if line.startswith("printf ")]
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", 'bootstrap_dir=$1\n' + "\n".join(lines), "bootstrap-test", directory],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({path.name for path in Path(directory).iterdir()}, set(FILES.values()))
            for encoded, name in commands:
                with self.subTest(file=name):
                    original = (INFRA / "bootstrap" / name).read_bytes()
                    self.assertEqual(base64.b64decode(encoded, validate=True), original)
                    self.assertEqual((Path(directory) / name).read_bytes(), original)

    def test_rendered_script_is_valid_bash_under_ec2_size_limit(self):
        rendered = self.rendered()
        self.assertTrue(rendered.startswith("#!/usr/bin/env bash\n"))
        result = subprocess.run(["bash", "-n"], input=rendered, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(len(rendered.encode("utf-8")), 16 * 1024)

    def test_wrapper_only_stages_runtime_and_runs_installer(self):
        _, template = self.sources()
        expected = [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "umask 022",
            "bootstrap_dir=/usr/local/share/tictactest-bootstrap",
            'install -d -o root -g root -m 0755 "$bootstrap_dir"',
            *[
                "printf '%s' '${" + key + "}' | base64 --decode > \"$bootstrap_dir/" + name + '"'
                for key, name in FILES.items()
            ],
            'bash "$bootstrap_dir/install-runtime.sh"',
        ]
        self.assertEqual(template.splitlines(), expected)
        # The wrapper cannot select/download an application; only the existing runtime is embedded.
        for forbidden in ("release.env", "/opt/tictactest/current", "releases/download", ".jar", "curl ", "wget "):
            self.assertNotIn(forbidden, template)

    def test_console_has_explicit_lab_environment(self):
        unit = (INFRA / "bootstrap/tictactest-console.service").read_text()
        self.assertRegex(unit, r"(?m)^Environment=TICTACTEST_ENV=lab$")

    def test_instance_attaches_user_data_without_replacement_or_lifecycle_workarounds(self):
        main = (INFRA / "main.tf").read_text()
        instance = main.split('resource "aws_instance" "server" {', 1)[1]
        instance = instance.split('\nresource "', 1)[0]
        self.assertRegex(instance, r'(?m)^\s*user_data\s*=\s*local\.bootstrap_user_data\s*$')
        self.assertRegex(instance, r'(?m)^\s*user_data_replace_on_change\s*=\s*false\s*$')
        self.assertNotRegex(instance, r'\b(user_data_base64|create_before_destroy|ignore_changes)\b')
        self.assertRegex(instance, r'(?im)^\s*#.*stop/start.*first.boot')


if __name__ == "__main__":
    unittest.main()
