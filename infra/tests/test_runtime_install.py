"""Local runtime contracts; no package manager, AWS or systemd mutations."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import hashlib
import zipfile
import os
import shutil
import ast

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "infra/bootstrap"
DEPLOY = ROOT / "infra/scripts/deploy-release.py"


class RuntimeConfigTests(unittest.TestCase):
    def test_deploy_shell_entrypoint_works_from_other_directory(self):
        script = ROOT / "infra/scripts/deploy-release.sh"
        self.assertTrue(script.exists(), "documented deploy entrypoint is missing")
        subprocess.run(["bash", "-n", str(script)], check=True)
        result = subprocess.run(["bash", str(script), "--help"], cwd="/", text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("version", result.stdout)

    def test_installer_pins_packages_and_enables_without_starting(self):
        installer = BOOTSTRAP / "install-runtime.sh"
        self.assertTrue(installer.exists(), "runtime installer is missing")
        subprocess.run(["bash", "-n", str(installer)], check=True)
        text = installer.read_text()
        for pin in ("java-25-amazon-corretto-headless-1:25.0.5.1.2-1.amzn2023.1.x86_64",
                    "nginx-1:1.30.6-1.amzn2023.0.1.x86_64",
                    "8a217c968aba172e0dbf3f34447218dc015bc4d5e59bf51db2f2cd12b7be4f55"):
            self.assertIn(pin, text)
        self.assertIn("sha256sum --check", text)
        self.assertLess(text.index("sha256sum --check"), text.index('install -o root -g root -m 0755 "$stage/ttyd"'))
        self.assertIn("systemctl disable --now nginx.service", text)
        self.assertIn("systemctl mask nginx.service", text)
        self.assertIn("systemctl enable tictactest-console.service tictactest-web.service", text)
        self.assertNotIn("systemctl start", text)
        self.assertNotIn("--now tictactest", text)
        self.assertIn("--shell /sbin/nologin", text)

    def test_services_are_unprivileged_and_loopback_only(self):
        self.assertTrue((BOOTSTRAP / "tictactest-console.service").exists(), "console unit missing")
        self.assertTrue((BOOTSTRAP / "tictactest-web.service").exists(), "web unit missing")
        console = (BOOTSTRAP / "tictactest-console.service").read_text()
        web = (BOOTSTRAP / "tictactest-web.service").read_text()
        for unit in (console, web):
            for directive in ("User=tictactest", "Group=tictactest", "NoNewPrivileges=true",
                              "PrivateTmp=true", "ProtectSystem=strict", "ProtectHome=true",
                              "Restart=on-failure", "WantedBy=multi-user.target"):
                self.assertIn(directive, unit)
        self.assertIn("StateDirectory=tictactest", console)
        # libwebsockets/getifaddrs needs netlink, otherwise -i can bind wildcard.
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK", console)
        self.assertIn("EnvironmentFile=/etc/tictactest/release.env", console)
        self.assertIn("/usr/bin/python3 -B /opt/tictactest/current/runtime/backend-version.py ${JAR_PATH} /var/lib/tictactest/version.txt", console)
        self.assertIn("/usr/local/bin/ttyd -W -O -i 127.0.0.1 -p 7681 -m 4 -b /console /usr/bin/java -Xmx64m -jar ${JAR_PATH}", console)
        self.assertNotIn("/bin/sh", console)
        self.assertIn("RuntimeDirectory=tictactest-web", web)
        self.assertIn("/usr/sbin/nginx -e stderr -c /etc/tictactest/nginx.conf", web)

    def test_proxy_preserves_console_prefix_and_separate_version_routes(self):
        self.assertTrue((BOOTSTRAP / "nginx.conf").exists(), "nginx configuration missing")
        config = (BOOTSTRAP / "nginx.conf").read_text()
        for directive in ("listen 127.0.0.1:8080;", "root /opt/tictactest/current/frontend;",
                          "location /console/", "proxy_pass http://127.0.0.1:7681;",
                          "proxy_set_header Host $http_host;", "proxy_set_header Upgrade $http_upgrade;",
                          "proxy_set_header Connection $connection_upgrade;", "proxy_http_version 1.1;",
                          "location = /backend-version.txt", "alias /var/lib/tictactest/version.txt;",
                          "default_type text/plain;", 'add_header Cache-Control "no-store" always;',
                          "pid /run/tictactest-web/nginx.pid;", "error_log stderr;",
                          "access_log /run/tictactest-web/access.log;"):
            self.assertIn(directive, config)
        self.assertNotIn("listen 80;", config)
        self.assertNotIn("location = /version.txt", config)
        for kind in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi"):
            self.assertIn(f"{kind}_temp_path /run/tictactest-web/", config)


class ReleaseDeployTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(DEPLOY.exists(), "release deployer is missing")
        spec = importlib.util.spec_from_file_location("tictactest_deploy", DEPLOY)
        assert spec is not None and spec.loader is not None
        self.deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.deploy)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.app = self.base / "opt/tictactest"
        self.config = self.base / "etc/tictactest"
        self.config.mkdir(parents=True)
        self.app.mkdir(parents=True)
        self.fixture = self.base / "assets"
        self.fixture.mkdir()
        subprocess.run(["python3", str(ROOT / "scripts/package-web-release.py"), "1.1.0", str(self.fixture)], check=True, capture_output=True)
        # Deliberately tiny synthetic JAR: tests do not execute a JVM or claim a real release.
        self.jar = self.fixture / "tictactest-1.1.0.jar"
        with zipfile.ZipFile(self.jar, "w") as archive:
            archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nImplementation-Version: 1.1.0\n\n")
        self.checksum(self.jar)
        self.jar_hash = hashlib.sha256(self.jar.read_bytes()).hexdigest()
        self.downloads = []
        for name, replacement in (("APP", self.app), ("CONFIG", self.config)):
            patcher = mock.patch.object(self.deploy, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        download = mock.patch.object(self.deploy, "download", side_effect=self.download)
        services = mock.patch.object(self.deploy, "systemctl")
        health = mock.patch.object(self.deploy, "wait_healthy")
        self.download_mock = download.start()
        self.systemctl_mock = services.start()
        self.wait_healthy_mock = health.start()
        for patcher in (download, services, health):
            self.addCleanup(patcher.stop)
        root = mock.patch.object(self.deploy.os, "geteuid", return_value=0)
        root.start()
        self.addCleanup(root.stop)
        quiet = mock.patch("builtins.print")
        quiet.start()
        self.addCleanup(quiet.stop)

    def checksum(self, artifact):
        artifact.with_name(artifact.name + ".sha256").write_text(
            f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {artifact.name}\n")

    def download(self, url, destination):
        name = url.rsplit("/", 1)[-1]
        self.assertEqual(url, "https://github.com/philderks/450-tictactest-mvk/releases/download/v1.1.0/" + name)
        self.downloads.append(name)
        shutil.copyfile(self.fixture / name, destination)

    def test_downloaded_release_is_verified_and_activated_without_changing_jar(self):
        original_config = (ROOT / "frontend/config.js").read_bytes()
        self.deploy.deploy("1.1.0")
        release = self.app / "releases/1.1.0"
        self.assertEqual(len(self.downloads), 6)
        self.assertEqual(set(self.downloads), {p.name for p in self.fixture.iterdir()})
        self.assertEqual((self.app / "current").resolve(), release)
        self.assertEqual(hashlib.sha256((release / self.jar.name).read_bytes()).hexdigest(), self.jar_hash)
        self.assertEqual((release / "frontend/version.txt").read_text(), "1.1.0\n")
        public_config = (release / "frontend/config.js").read_text()
        for expected in ("window.TICTACTEST_CONFIG", "consoleUrl: '/console/'", "backendVersionUrl: '/backend-version.txt'"):
            self.assertIn(expected, public_config)
        self.assertEqual((ROOT / "frontend/config.js").read_bytes(), original_config)
        self.assertEqual((self.config / "release.env").read_text(), f"JAR_PATH={self.app}/current/{self.jar.name}\n")
        for path in release.rglob("*"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o755 if path.is_dir() else 0o644)
        self.wait_healthy_mock.assert_called_once_with("1.1.0")
        self.systemctl_mock.assert_called_with("restart", "tictactest-console.service", "tictactest-web.service")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.deploy.deploy("1.1.0")
        self.assertEqual(len(self.downloads), 6, "immutable redeploy must fail before downloading")

    def test_release_is_readable_even_with_restrictive_callers_umask(self):
        previous_umask = os.umask(0o077)
        try:
            self.deploy.deploy("1.1.0")
        finally:
            os.umask(previous_umask)
        release = self.app / "releases/1.1.0"
        for path in [release, *release.rglob("*")]:
            self.assertEqual(path.stat().st_mode & 0o777, 0o755 if path.is_dir() else 0o644, str(path))

    def test_invalid_versions_are_rejected_before_writes(self):
        for version in ("v1.1.0", "1.1", "01.1.0", "1.1.0-rc1", "../1.1.0", "1.1.0\n", "1.1.0;id"):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "MAJOR.MINOR.PATCH"):
                self.deploy.deploy(version)
        self.assertFalse((self.app / ".deploy.lock").exists())
        self.download_mock.assert_not_called()

    def test_nonroot_deploy_is_rejected(self):
        with mock.patch.object(self.deploy.os, "geteuid", return_value=1000):
            with self.assertRaises(PermissionError):
                self.deploy.deploy("1.1.0")
        self.download_mock.assert_not_called()

    def test_corrupt_artifact_is_rejected_before_any_extraction_or_activation(self):
        self.jar.write_bytes(b"corrupt")
        with mock.patch.object(self.deploy, "extract_archive") as extract:
            with self.assertRaisesRegex(ValueError, "SHA256"):
                self.deploy.deploy("1.1.0")
            extract.assert_not_called()
        self.assertFalse((self.app / "current").exists())
        self.assertFalse((self.config / "release.env").exists())
        self.systemctl_mock.assert_not_called()
        self.assertEqual(list((self.app / "releases").iterdir()), [])

    def test_checksum_cannot_choose_another_filename(self):
        self.jar.with_name(self.jar.name + ".sha256").write_text(f"{self.jar_hash}  ../other.jar\n")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.deploy.verify_checksum(self.jar)

    def test_unsafe_or_unexpected_zip_entries_are_rejected(self):
        import stat
        for name in ("../escape", "/absolute", "nested/file", "unexpected", "symlink"):
            archive = self.base / "malicious.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                entry = zipfile.ZipInfo(name)
                if name == "symlink":
                    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                bundle.writestr(entry, "outside")
            allowed = {name} if name == "symlink" else {"known-file"}
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.deploy.extract_archive(archive, self.base / "extracted", allowed)
            self.assertFalse((self.base / "extracted").exists())

    def test_duplicate_entries_are_rejected(self):
        import warnings
        archive = self.base / "duplicate.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("known-file", "a")
                bundle.writestr("known-file", "b")
        with self.assertRaisesRegex(ValueError, "ZIP entries"):
            self.deploy.extract_archive(archive, self.base / "extracted", {"known-file"})

    def test_jar_manifest_version_must_match_requested_version(self):
        with zipfile.ZipFile(self.jar, "w") as bundle:
            bundle.writestr("META-INF/MANIFEST.MF", "Implementation-Version: 9.9.9\n\n")
        self.checksum(self.jar)
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.deploy.deploy("1.1.0")
        self.systemctl_mock.assert_not_called()
        self.assertFalse((self.app / "releases/1.1.0").exists())

    def test_failed_health_restores_symlink_and_environment_and_checks_rollback(self):
        previous = self.app / "releases/1.0.0"
        previous.mkdir(parents=True)
        (previous / "sentinel").write_text("unchanged")
        (self.app / "current").symlink_to(previous)
        environment = self.config / "release.env"
        old_env = b"JAR_PATH=/opt/tictactest/current/tictactest-1.0.0.jar\n"
        environment.write_bytes(old_env)
        self.wait_healthy_mock.side_effect = [RuntimeError("new release unhealthy"), None]
        with self.assertRaisesRegex(RuntimeError, "new release unhealthy"):
            self.deploy.deploy("1.1.0")
        self.assertEqual((self.app / "current").resolve(), previous)
        self.assertEqual(environment.read_bytes(), old_env)
        self.assertEqual((previous / "sentinel").read_text(), "unchanged")
        self.assertEqual(self.wait_healthy_mock.call_args_list, [mock.call("1.1.0"), mock.call("1.0.0")])
        self.assertEqual(self.systemctl_mock.call_count, 2)
        self.assertTrue((self.app / "releases/1.1.0").is_dir(), "retain failed immutable release for diagnosis")

    def test_failed_initial_release_removes_selection_and_stops_units(self):
        self.wait_healthy_mock.side_effect = RuntimeError("unhealthy")
        with self.assertRaisesRegex(RuntimeError, "unhealthy"):
            self.deploy.deploy("1.1.0")
        self.assertFalse(os.path.lexists(self.app / "current"))
        self.assertFalse((self.config / "release.env").exists())
        self.systemctl_mock.assert_called_with("stop", "tictactest-console.service", "tictactest-web.service")

    def test_health_checks_all_four_loopback_routes(self):
        # Invoke the real implementation, leaving only HTTP and systemctl mocked.
        spec = importlib.util.spec_from_file_location("real_deploy", DEPLOY)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        seen = []
        def response(url, timeout):
            seen.append(url)
            body = b"1.1.0\n" if url.endswith("version.txt") else b"<html>terminal or frontend</html>"
            result = mock.MagicMock()
            result.__enter__.return_value = result
            result.status = 200
            result.read.return_value = body
            return result
        opener = mock.Mock()
        opener.open.side_effect = response
        with mock.patch.object(module.urllib.request, "build_opener", return_value=opener), mock.patch.object(module, "systemctl"), mock.patch.object(module, "check_private_listeners") as listeners:
            module.wait_healthy("1.1.0")
        listeners.assert_called_once_with()
        self.assertEqual(seen, ["http://127.0.0.1:8080" + route for route in ("/", "/version.txt", "/backend-version.txt", "/console/")])

    def test_deployment_rejects_non_loopback_or_missing_listeners(self):
        self.assertTrue(hasattr(self.deploy, "check_private_listeners"),
                        "Health checks must verify real listener addresses, not just HTTP")
        for output in (
            "LISTEN 0 128 0.0.0.0:7681 0.0.0.0:*\nLISTEN 0 511 127.0.0.1:8080 0.0.0.0:*\n",
            "LISTEN 0 128 [::]:7681 [::]:*\nLISTEN 0 511 127.0.0.1:8080 0.0.0.0:*\n",
            "LISTEN 0 511 127.0.0.1:8080 0.0.0.0:*\n",
        ):
            with self.subTest(output=output), mock.patch.object(
                self.deploy.subprocess, "run", return_value=mock.Mock(stdout=output)
            ), self.assertRaisesRegex(ValueError, "loopback"):
                self.deploy.check_private_listeners()
        safe = "LISTEN 0 128 127.0.0.1:7681 0.0.0.0:*\nLISTEN 0 511 127.0.0.1:8080 0.0.0.0:*\n"
        with mock.patch.object(self.deploy.subprocess, "run", return_value=mock.Mock(stdout=safe)):
            self.deploy.check_private_listeners()

    def test_deployment_helper_uses_python39_syntax(self):
        ast.parse(DEPLOY.read_text(), feature_version=(3, 9))


if __name__ == "__main__":
    unittest.main()
