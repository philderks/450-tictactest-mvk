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
        self.assertIn("--components {backend,frontend,both}", result.stdout)

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

    def test_services_are_unprivileged_with_private_console(self):
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
        self.assertIn("CapabilityBoundingSet=CAP_NET_BIND_SERVICE", web)
        self.assertIn("AmbientCapabilities=CAP_NET_BIND_SERVICE", web)
        self.assertIn("/usr/sbin/nginx -e stderr -c /etc/tictactest/nginx.conf", web)

    def test_proxy_preserves_console_prefix_and_separate_version_routes(self):
        self.assertTrue((BOOTSTRAP / "nginx.conf").exists(), "nginx configuration missing")
        config = (BOOTSTRAP / "nginx.conf").read_text()
        for directive in ("listen 127.0.0.1:8080;", "root /opt/tictactest/frontend-current/frontend;",
                          "location /console/", "proxy_pass http://127.0.0.1:7681;",
                          "proxy_set_header Host $http_host;", "proxy_set_header Upgrade $http_upgrade;",
                          "proxy_set_header Connection $connection_upgrade;", "proxy_http_version 1.1;",
                          "location = /config.js", 'add_header X-TicTacTest-Layout "split-v1" always;',
                          "window.TICTACTEST_CONFIG", "consoleUrl: '/console/'", "backendVersionUrl: '/backend-version.txt'",
                          "location = /backend-version.txt", "alias /var/lib/tictactest/version.txt;",
                          "default_type text/plain;", 'add_header Cache-Control "no-store" always;',
                          "pid /run/tictactest-web/nginx.pid;", "error_log stderr;",
                          "access_log /run/tictactest-web/access.log;"):
            self.assertIn(directive, config)
        self.assertEqual(
            {line.strip() for line in config.splitlines() if line.strip().startswith("listen ")},
            {"listen 0.0.0.0:80;", "listen 127.0.0.1:8080;"},
        )
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
        self.app.chmod(0o755)
        self.config.chmod(0o755)
        shutil.copyfile(BOOTSTRAP / "nginx.conf", self.config / "nginx.conf")
        active = mock.patch.object(self.deploy, "service_active", side_effect=lambda unit: (self.app / "current").exists(), create=True)
        active.start()
        self.addCleanup(active.stop)
        layout = mock.patch.object(self.deploy, "probe_loaded_layout", create=True)
        self.layout_mock = layout.start()
        self.addCleanup(layout.stop)
        probe = mock.patch.object(self.deploy, "probe_console", create=True)
        self.probe_mock = probe.start()
        self.addCleanup(probe.stop)
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
        health = mock.patch.object(self.deploy, "_wait_healthy")
        self.download_mock = download.start()
        self.systemctl_mock = services.start()
        self.health_mock = health.start()
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
        version = name.removeprefix("tictactest-").removeprefix("frontend-").removeprefix("runtime-").split(".jar")[0].split(".zip")[0]
        self.assertEqual(url, "https://github.com/philderks/450-tictactest-mvk/releases/download/v" + version + "/" + name)
        self.downloads.append(name)
        shutil.copyfile(self.fixture / name, destination)

    def add_release(self, version):
        subprocess.run(["python3", str(ROOT / "scripts/package-web-release.py"), version, str(self.fixture)],
                       check=True, capture_output=True)
        jar = self.fixture / ("tictactest-" + version + ".jar")
        with zipfile.ZipFile(jar, "w") as archive:
            archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nImplementation-Version: " + version + "\n\n")
        self.checksum(jar)

    def test_frontend_only_preserves_backend_and_never_restarts_units(self):
        self.deploy.deploy("1.1.0")
        original = os.readlink(self.app / "current")
        env = (self.config / "release.env").read_bytes()
        self.add_release("1.2.0")
        self.systemctl_mock.reset_mock()
        self.health_mock.reset_mock()
        self.downloads.clear()
        self.probe_mock.reset_mock()
        self.deploy.deploy("1.2.0", "frontend")
        self.probe_mock.assert_not_called()
        self.assertEqual(os.readlink(self.app / "current"), original)
        self.assertEqual((self.config / "release.env").read_bytes(), env)
        self.assertEqual((self.app / "frontend-current").resolve(), self.app / "deployments/frontend/1.2.0")
        self.assertEqual(len(self.downloads), 2)
        self.assertTrue(all("frontend" in name for name in self.downloads))
        self.systemctl_mock.assert_not_called()
        self.health_mock.assert_called_once_with("1.1.0", "1.2.0", mock.ANY)

    def test_verified_cache_can_reselect_without_downloading_or_rewriting(self):
        self.deploy.deploy("1.1.0")
        original = self.app / "deployments/frontend/1.1.0"
        receipt = (original / ".receipt.json").read_bytes() if (original / ".receipt.json").exists() else None
        self.add_release("1.2.0")
        self.deploy.deploy("1.2.0", "frontend")
        self.downloads.clear()
        self.deploy.deploy("1.1.0", "frontend")
        self.assertEqual(self.downloads, [])
        self.assertEqual((self.app / "frontend-current").resolve(), original)
        self.assertIsNotNone(receipt)
        self.assertEqual((original / ".receipt.json").read_bytes(), receipt)

    def select_legacy_component(self, component):
        legacy = self.app / "releases/1.1.0"
        legacy.mkdir(parents=True)
        legacy.parent.chmod(0o755)
        backend = self.app / "deployments/backend/1.1.0"
        frontend = self.app / "deployments/frontend/1.1.0"
        shutil.copyfile(backend / self.jar.name, legacy / self.jar.name)
        shutil.copytree(backend / "runtime", legacy / "runtime")
        shutil.copytree(frontend / "frontend", legacy / "frontend")
        for path in [legacy, *legacy.rglob("*")]:
            path.chmod(0o755 if path.is_dir() else 0o644)
        name = "current" if component == "backend" else "frontend-current"
        (self.app / name).unlink()
        (self.app / name).symlink_to("releases/1.1.0")
        if component == "backend":
            (self.config / "release.env").write_text("JAR_PATH=" + str(self.app / "current" / self.jar.name) + "\n")
        return legacy

    def assert_unsafe_current_parent_rejected(self, relative_parent, selected, fault="permissions"):
        self.deploy.deploy("1.1.0")
        if relative_parent == "releases":
            self.select_legacy_component("backend" if selected == "frontend" else "frontend")
        self.add_release("1.2.0")
        parent = self.app / relative_parent
        if fault == "permissions":
            parent.chmod(0o777)
        elif fault in ("symlink", "legacy-alias"):
            if fault == "legacy-alias":
                component = relative_parent.rsplit("/", 1)[-1]
                self.select_legacy_component(component)
                name = "current" if component == "backend" else "frontend-current"
                (self.app / name).unlink()
                (self.app / name).symlink_to(relative_parent + "/1.1.0")
            outside = self.base / "displaced-parent"
            parent.rename(outside)
            parent.symlink_to(self.app / "releases" if fault == "legacy-alias" else outside)
        original_stat = Path.stat
        original_lstat = Path.lstat
        def with_parent_owner(path, info):
            if fault == "owner" and path == parent:
                fields = list(info)
                fields[4] = os.getuid() ^ 1
                return os.stat_result(fields)
            return info
        def parent_stat(path, *args, **kwargs):
            return with_parent_owner(path, original_stat(path, *args, **kwargs))
        def parent_lstat(path, *args, **kwargs):
            return with_parent_owner(path, original_lstat(path, *args, **kwargs))
        selections = {name: (os.readlink(self.app / name), (self.app / name).lstat().st_ino)
                      for name in ("current", "frontend-current")}
        environment = self.config / "release.env"
        old_env = environment.read_bytes()
        old_env_inode = environment.stat().st_ino
        parent_info = parent.lstat()
        self.downloads.clear()
        self.systemctl_mock.reset_mock()
        self.health_mock.reset_mock()
        self.probe_mock.reset_mock()
        with mock.patch.object(Path, "stat", autospec=True, side_effect=parent_stat), \
             mock.patch.object(Path, "lstat", autospec=True, side_effect=parent_lstat), \
             mock.patch.object(self.deploy, "validate_cache", wraps=self.deploy.validate_cache) as cache, \
             mock.patch.object(self.deploy, "validate_legacy", wraps=self.deploy.validate_legacy) as legacy:
            if fault == "owner":
                self.assertEqual(parent.lstat().st_uid, os.getuid() ^ 1)
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                self.deploy.deploy("1.2.0", selected)
        cache.assert_not_called()
        legacy.assert_not_called()
        self.assertEqual({name: (os.readlink(self.app / name), (self.app / name).lstat().st_ino)
                          for name in selections}, selections)
        self.assertEqual(environment.read_bytes(), old_env)
        self.assertEqual(environment.stat().st_ino, old_env_inode)
        for attribute in ("st_mode", "st_uid", "st_gid", "st_ino"):
            self.assertEqual(getattr(parent.lstat(), attribute), getattr(parent_info, attribute),
                             "validation must not repair or replace the unsafe parent")
        self.assertEqual(self.downloads, [])
        self.systemctl_mock.assert_not_called()
        self.health_mock.assert_not_called()
        self.probe_mock.assert_not_called()
        self.assertFalse((self.app / "deployments" / selected / "1.2.0").exists())

    def test_frontend_only_rejects_writable_existing_backend_parent(self):
        self.assert_unsafe_current_parent_rejected("deployments/backend", "frontend")

    def test_backend_only_rejects_writable_existing_frontend_parent(self):
        self.assert_unsafe_current_parent_rejected("deployments/frontend", "backend")

    def test_frontend_only_rejects_wrong_owner_of_existing_backend_parent(self):
        self.assert_unsafe_current_parent_rejected("deployments/backend", "frontend", "owner")

    def test_backend_only_rejects_wrong_owner_of_existing_frontend_parent(self):
        self.assert_unsafe_current_parent_rejected("deployments/frontend", "backend", "owner")

    def test_existing_shared_deployment_root_is_validated_before_leaf_trees(self):
        self.assert_unsafe_current_parent_rejected("deployments", "frontend")

    def test_existing_shared_deployment_root_owner_is_validated_before_leaf_trees(self):
        self.assert_unsafe_current_parent_rejected("deployments", "backend", "owner")

    def test_frontend_only_rejects_writable_existing_legacy_backend_parent(self):
        self.assert_unsafe_current_parent_rejected("releases", "frontend")

    def test_backend_only_rejects_wrong_owner_of_existing_legacy_frontend_parent(self):
        self.assert_unsafe_current_parent_rejected("releases", "backend", "owner")

    def test_frontend_only_rejects_backend_parent_symlink_even_into_valid_legacy_release(self):
        self.assert_unsafe_current_parent_rejected("deployments/backend", "frontend", "legacy-alias")

    def test_backend_only_rejects_frontend_parent_symlink_even_into_valid_legacy_release(self):
        self.assert_unsafe_current_parent_rejected("deployments/frontend", "backend", "legacy-alias")

    def test_selection_cannot_normalize_away_a_symlink_parent(self):
        self.deploy.deploy("1.1.0")
        self.add_release("1.2.0")
        alias = self.app / "parent-alias"
        alias.symlink_to(self.app / "deployments")
        current = self.app / "current"
        current.unlink()
        current.symlink_to("parent-alias/../deployments/backend/1.1.0")
        original = os.readlink(current)
        self.downloads.clear()
        self.systemctl_mock.reset_mock()
        with mock.patch.object(self.deploy, "validate_cache", wraps=self.deploy.validate_cache) as cache:
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                self.deploy.deploy("1.2.0", "frontend")
        cache.assert_not_called()
        self.assertEqual(os.readlink(current), original)
        self.assertTrue(alias.is_symlink())
        self.assertEqual(self.downloads, [])
        self.systemctl_mock.assert_not_called()

    def test_existing_shared_deployment_root_symlink_is_rejected_without_repair(self):
        self.assert_unsafe_current_parent_rejected("deployments", "frontend", "symlink")

    def test_existing_legacy_parent_symlink_is_rejected_without_repair(self):
        self.assert_unsafe_current_parent_rejected("releases", "backend", "symlink")

    def test_existing_parent_validation_does_not_create_missing_directory(self):
        missing = self.app / "missing-parent"
        with mock.patch.object(Path, "mkdir") as mkdir, mock.patch.object(Path, "chmod") as chmod:
            with self.assertRaises(FileNotFoundError):
                self.deploy.validate_component_directory(missing)
        mkdir.assert_not_called()
        chmod.assert_not_called()
        self.assertFalse(missing.exists())

    def test_safe_legacy_parent_preserves_mixed_tuple_and_verified_cache_reuse(self):
        self.deploy.deploy("1.1.0")
        legacy = self.select_legacy_component("backend")
        original = {path.relative_to(legacy).as_posix(): path.read_bytes()
                    for path in legacy.rglob("*") if path.is_file()}
        environment = self.config / "release.env"
        old_env = environment.read_bytes()
        self.add_release("1.2.0")
        self.deploy.deploy("1.2.0", "frontend")
        self.downloads.clear()
        self.systemctl_mock.reset_mock()
        self.probe_mock.reset_mock()
        self.deploy.deploy("1.1.0", "frontend")
        self.assertEqual(self.downloads, [])
        self.assertEqual(os.readlink(self.app / "current"), "releases/1.1.0")
        self.assertEqual((self.app / "frontend-current").resolve(), self.app / "deployments/frontend/1.1.0")
        self.assertEqual(environment.read_bytes(), old_env)
        self.assertEqual(legacy.parent.stat().st_mode & 0o7777, 0o755)
        self.assertEqual({path.relative_to(legacy).as_posix(): path.read_bytes()
                          for path in legacy.rglob("*") if path.is_file()}, original)
        self.systemctl_mock.assert_not_called()
        self.probe_mock.assert_not_called()

    def test_active_backend_tampering_blocks_frontend_change_before_download(self):
        self.deploy.deploy("1.1.0")
        jar = self.app / "deployments/backend/1.1.0" / self.jar.name
        with zipfile.ZipFile(jar, "a") as bundle:
            bundle.writestr("injected.class", "tamper")
        self.add_release("1.2.0")
        self.downloads.clear()
        self.systemctl_mock.reset_mock()
        before = os.readlink(self.app / "frontend-current")
        with self.assertRaisesRegex(ValueError, "cache"):
            self.deploy.deploy("1.2.0", "frontend")
        self.assertEqual(os.readlink(self.app / "frontend-current"), before)
        self.assertEqual(self.downloads, [])
        self.systemctl_mock.assert_not_called()
        self.assertTrue(jar.exists(), "never delete original tampered cache")

    def test_unmigrated_nginx_is_rejected_before_download_or_selection(self):
        config = self.config / "nginx.conf"
        config.write_text(config.read_text().replace("frontend-current/frontend", "current/frontend"))
        with self.assertRaisesRegex(ValueError, "split"):
            self.deploy.deploy("1.1.0")
        self.assertEqual(self.downloads, [])
        self.assertFalse(os.path.lexists(self.app / "current"))
        self.systemctl_mock.assert_not_called()

    def test_running_proxy_must_prove_loaded_split_config_before_preparation(self):
        self.deploy.deploy("1.1.0")
        self.add_release("1.2.0")
        self.downloads.clear()
        self.systemctl_mock.reset_mock()
        self.layout_mock.side_effect = ValueError("loaded split-v1 header missing")
        before = os.readlink(self.app / "frontend-current")
        with self.assertRaisesRegex(ValueError, "loaded split-v1"):
            self.deploy.deploy("1.2.0", "frontend")
        self.assertEqual(self.downloads, [])
        self.assertEqual(os.readlink(self.app / "frontend-current"), before)
        self.systemctl_mock.assert_not_called()

    def test_bad_actual_game_probe_fails_initial_deployment(self):
        self.probe_mock.side_effect = RuntimeError("JVM did not reach game prompt")
        with self.assertRaisesRegex(RuntimeError, "game prompt"):
            self.deploy.deploy("1.1.0")
        self.probe_mock.assert_called_once()
        self.assertFalse(os.path.lexists(self.app / "current"))
        self.assertFalse(os.path.lexists(self.app / "frontend-current"))
        self.assertFalse((self.config / "release.env").exists())
        self.assertTrue((self.app / "deployments/backend/1.1.0").is_dir())

    def test_rollback_failure_reports_original_and_restore_health_errors(self):
        self.deploy.deploy("1.1.0")
        self.add_release("1.2.0")
        self.health_mock.side_effect = [RuntimeError("new unhealthy"), RuntimeError("old unhealthy")]
        with self.assertRaisesRegex(RuntimeError, "new unhealthy.*rollback failed.*old unhealthy") as caught:
            self.deploy.deploy("1.2.0")
        self.assertEqual(str(caught.exception.deployment_error), "new unhealthy")
        self.assertEqual(str(caught.exception.rollback_error), "old unhealthy")
        self.assertEqual((self.app / "current").resolve().name, "1.1.0")
        self.assertEqual((self.app / "frontend-current").resolve().name, "1.1.0")

    def test_frontend_failure_restores_mixed_tuple_without_touching_backend_or_units(self):
        self.deploy.deploy("1.1.0")
        self.add_release("1.2.0")
        self.deploy.deploy("1.2.0", "frontend")
        self.add_release("1.3.0")
        for name, target in (("current", "deployments/backend/1.1.0"),
                             ("frontend-current", "deployments/frontend/1.2.0")):
            (self.app / name).unlink()
            (self.app / name).symlink_to(target)
        environment = self.config / "release.env"
        old_env = b"# exact previous environment\n" + environment.read_bytes()
        environment.write_bytes(old_env)
        backend_inode = (self.app / "current").lstat().st_ino
        env_inode = environment.stat().st_ino
        self.systemctl_mock.reset_mock()
        self.probe_mock.reset_mock()
        self.health_mock.reset_mock()
        self.health_mock.side_effect = [RuntimeError("frontend bad"), None]
        with self.assertRaisesRegex(RuntimeError, "frontend bad"):
            self.deploy.deploy("1.3.0", "frontend")
        self.assertEqual(os.readlink(self.app / "current"), "deployments/backend/1.1.0")
        self.assertEqual(os.readlink(self.app / "frontend-current"), "deployments/frontend/1.2.0")
        self.assertEqual(environment.read_bytes(), old_env)
        self.assertEqual((self.app / "current").lstat().st_ino, backend_inode)
        self.assertEqual(environment.stat().st_ino, env_inode)
        self.systemctl_mock.assert_not_called()
        self.probe_mock.assert_not_called()
        self.assertEqual(self.health_mock.call_args_list,
                         [mock.call("1.1.0", "1.3.0", mock.ANY), mock.call("1.1.0", "1.2.0", mock.ANY)])

    def test_failed_initial_does_not_stop_a_preexisting_web_unit(self):
        self.health_mock.side_effect = RuntimeError("unhealthy")
        with mock.patch.object(self.deploy, "service_active", side_effect=lambda unit: unit.endswith("web.service")):
            with self.assertRaisesRegex(RuntimeError, "unhealthy"):
                self.deploy.deploy("1.1.0")
        self.assertEqual(self.systemctl_mock.call_args_list,
                         [mock.call("restart", "tictactest-console.service"), mock.call("stop", "tictactest-console.service")])
        self.assertFalse(os.path.lexists(self.app / "current"))
        self.assertFalse(os.path.lexists(self.app / "frontend-current"))

    def test_explicitly_split_legacy_selection_can_rollback_without_migration(self):
        self.deploy.deploy("1.1.0")
        legacy = self.app / "releases/1.1.0"
        legacy.mkdir(parents=True)
        legacy.parent.chmod(0o755)  # Prepared legacy parent, independent of the test runner's umask.
        backend = self.app / "deployments/backend/1.1.0"
        frontend = self.app / "deployments/frontend/1.1.0"
        shutil.copyfile(backend / self.jar.name, legacy / self.jar.name)
        shutil.copytree(backend / "runtime", legacy / "runtime")
        shutil.copytree(frontend / "frontend", legacy / "frontend")
        for path in [legacy, *legacy.rglob("*")]:
            path.chmod(0o755 if path.is_dir() else 0o644)
        for name in ("current", "frontend-current"):
            (self.app / name).unlink()
            (self.app / name).symlink_to("releases/1.1.0")
        environment = self.config / "release.env"
        old_env = ("JAR_PATH=" + str(self.app / "current" / self.jar.name) + "\n# legacy bytes\n").encode()
        environment.write_bytes(old_env)
        original = {p.relative_to(legacy).as_posix(): p.read_bytes() for p in legacy.rglob("*") if p.is_file()}
        self.add_release("1.2.0")
        self.health_mock.side_effect = [RuntimeError("new unhealthy"), None]
        with self.assertRaisesRegex(RuntimeError, "new unhealthy"):
            self.deploy.deploy("1.2.0", "backend")
        self.assertEqual(os.readlink(self.app / "current"), "releases/1.1.0")
        self.assertEqual(os.readlink(self.app / "frontend-current"), "releases/1.1.0")
        self.assertEqual(environment.read_bytes(), old_env)
        self.assertEqual({p.relative_to(legacy).as_posix(): p.read_bytes() for p in legacy.rglob("*") if p.is_file()}, original)

    def test_symlinked_component_parent_is_rejected_without_writing_outside_app(self):
        outside = self.base / "outside"
        outside.mkdir()
        (self.app / "deployments").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.deploy.deploy("1.1.0")
        self.assertEqual(list(outside.iterdir()), [])
        self.assertTrue((self.app / "deployments").is_symlink())
        self.assertEqual(self.downloads, [])

    def test_symlinked_lock_cannot_redirect_root_write(self):
        outside = self.base / "outside-lock"
        outside.write_bytes(b"sentinel")
        (self.app / ".deploy.lock").symlink_to(outside)
        with self.assertRaises((OSError, ValueError)):
            self.deploy.deploy("1.1.0")
        self.assertEqual(outside.read_bytes(), b"sentinel")
        self.assertEqual(self.downloads, [])

    def test_symlinked_app_root_is_rejected_before_lock_or_download(self):
        actual = self.app.with_name("actual")
        self.app.rename(actual)
        self.app.symlink_to(actual)
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.deploy.deploy("1.1.0")
        self.assertFalse((actual / ".deploy.lock").exists())
        self.assertEqual(self.downloads, [])

    def test_environment_symlink_is_rejected_before_reading_or_changing_selection(self):
        self.deploy.deploy("1.1.0")
        self.add_release("1.2.0")
        env = self.config / "release.env"
        outside = self.base / "external.env"
        outside.write_bytes(env.read_bytes())
        env.unlink()
        env.symlink_to(outside)
        self.downloads.clear()
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.deploy.deploy("1.2.0", "frontend")
        self.assertEqual(self.downloads, [])
        self.assertTrue(env.is_symlink())

    def test_writable_application_root_is_rejected_without_repair(self):
        self.app.chmod(0o777)
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.deploy.deploy("1.1.0")
        self.assertEqual(self.app.stat().st_mode & 0o777, 0o777)
        self.assertFalse((self.app / ".deploy.lock").exists())
        self.assertEqual(self.downloads, [])

    def test_backend_only_downloads_four_assets_and_preserves_frontend_selection(self):
        self.deploy.deploy("1.1.0")
        self.add_release("1.2.0")
        front = os.readlink(self.app / "frontend-current")
        front_inode = (self.app / "frontend-current").lstat().st_ino
        self.downloads.clear()
        self.systemctl_mock.reset_mock()
        self.health_mock.reset_mock()
        self.probe_mock.reset_mock()
        self.deploy.deploy("1.2.0", "backend")
        self.assertEqual(len(self.downloads), 4)
        self.assertFalse(any("frontend" in name for name in self.downloads))
        self.assertEqual(os.readlink(self.app / "frontend-current"), front)
        self.assertEqual((self.app / "frontend-current").lstat().st_ino, front_inode)
        self.systemctl_mock.assert_called_once_with("restart", "tictactest-console.service")
        self.health_mock.assert_called_once_with("1.2.0", "1.1.0", mock.ANY)
        self.probe_mock.assert_called_once()
        self.assertGreater(self.probe_mock.call_args.args[0], 0)
        self.assertLessEqual(self.probe_mock.call_args.args[0], 60)
        self.assertEqual((self.config / "release.env").read_text(),
                         "JAR_PATH=" + str(self.app / "deployments/backend/1.2.0/tictactest-1.2.0.jar") + "\n")

    def test_both_failure_restores_previous_mixed_tuple_with_raw_symlinks_and_env(self):
        self.deploy.deploy("1.1.0")
        self.add_release("1.2.0")
        self.deploy.deploy("1.2.0", "frontend")
        self.add_release("1.3.0")
        for name, target in (("current", "deployments/backend/1.1.0"),
                             ("frontend-current", "deployments/frontend/1.2.0")):
            (self.app / name).unlink()
            (self.app / name).symlink_to(target)
        environment = self.config / "release.env"
        old_env = b"# exact MIXED environment\n" + environment.read_bytes()
        environment.write_bytes(old_env)
        self.health_mock.reset_mock()
        self.systemctl_mock.reset_mock()
        self.health_mock.side_effect = [RuntimeError("new mixed unhealthy"), None]
        with self.assertRaisesRegex(RuntimeError, "new mixed unhealthy"):
            self.deploy.deploy("1.3.0")
        self.assertEqual(os.readlink(self.app / "current"), "deployments/backend/1.1.0")
        self.assertEqual(os.readlink(self.app / "frontend-current"), "deployments/frontend/1.2.0")
        self.assertEqual(environment.read_bytes(), old_env)
        self.assertEqual(self.health_mock.call_args_list,
                         [mock.call("1.3.0", "1.3.0", mock.ANY), mock.call("1.1.0", "1.2.0", mock.ANY)])
        self.assertEqual(self.systemctl_mock.call_args_list,
                         [mock.call("restart", "tictactest-console.service")] * 2)

    def test_malformed_cache_receipt_is_a_safe_rejection_not_an_internal_crash(self):
        self.deploy.deploy("1.1.0")
        cache = self.app / "deployments/frontend/1.1.0"
        receipt = cache / ".receipt.json"
        receipt.write_text("[]\n")
        before = os.readlink(self.app / "frontend-current")
        self.downloads.clear()
        with self.assertRaisesRegex(ValueError, "cache"):
            self.deploy.deploy("1.1.0", "frontend")
        self.assertEqual(os.readlink(self.app / "frontend-current"), before)
        self.assertEqual(receipt.read_text(), "[]\n")
        self.assertEqual(self.downloads, [])

    def test_cache_receipt_cannot_gain_unverified_fields(self):
        import json
        self.deploy.deploy("1.1.0")
        receipt = self.app / "deployments/frontend/1.1.0/.receipt.json"
        data = json.loads(receipt.read_text())
        data["unverified"] = "not from the deployer"
        receipt.write_text(json.dumps(data))
        self.downloads.clear()
        with self.assertRaisesRegex(ValueError, "cache"):
            self.deploy.deploy("1.1.0", "frontend")
        self.assertEqual(self.downloads, [])

    def test_public_config_cannot_override_same_origin_values_after_valid_assignment(self):
        good = b"window.TICTACTEST_CONFIG = {consoleUrl: '/console/', backendVersionUrl: '/backend-version.txt'};"
        headers = {"X-TicTacTest-Layout": "split-v1", "Cache-Control": "no-store"}
        with self.assertRaisesRegex(ValueError, "split-v1"):
            self.deploy.validate_public_config(good + b"window.TICTACTEST_CONFIG.consoleUrl = 'https://evil.test/';", headers)

    def test_empty_selections_with_running_console_are_not_a_prepared_initial_host(self):
        with mock.patch.object(self.deploy, "service_active", side_effect=lambda unit: unit.endswith("console.service")):
            with self.assertRaisesRegex(ValueError, "running console"):
                self.deploy.deploy("1.1.0")
        self.assertEqual(self.downloads, [])
        self.systemctl_mock.assert_not_called()

    def test_selective_initial_deploy_is_rejected_before_download(self):
        for component in ("backend", "frontend"):
            with self.subTest(component=component), self.assertRaisesRegex(ValueError, "initial.*both"):
                self.deploy.deploy("1.1.0", component)
        self.assertEqual(self.downloads, [])
        self.systemctl_mock.assert_not_called()
        self.assertFalse(os.path.lexists(self.app / "current"))

    def test_incomplete_legacy_tuple_is_rejected_before_download(self):
        legacy = self.app / "releases/1.0.0"
        legacy.mkdir(parents=True)
        (legacy / "sentinel").write_bytes(b"never modify")
        (self.app / "current").symlink_to("releases/1.0.0")
        for component in ("backend", "frontend", "both"):
            with self.subTest(component=component), self.assertRaisesRegex(ValueError, "unmigrated legacy"):
                self.deploy.deploy("1.1.0", component)
        self.assertEqual((legacy / "sentinel").read_bytes(), b"never modify")
        self.assertEqual(os.readlink(self.app / "current"), "releases/1.0.0")
        self.assertEqual(self.downloads, [])
        self.systemctl_mock.assert_not_called()

    def test_invalid_component_does_not_create_lock(self):
        for component in ("all", "Backend", "", "../backend"):
            with self.subTest(component=component), self.assertRaisesRegex(ValueError, "components"):
                self.deploy.deploy("1.1.0", component)
        self.assertFalse((self.app / ".deploy.lock").exists())
        self.assertEqual(self.downloads, [])

    def test_concurrent_deployment_lock_is_nonblocking(self):
        import fcntl
        with (self.app / ".deploy.lock").open("w") as held:
            os.fchmod(held.fileno(), 0o600)
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.deploy.deploy("1.1.0")
        self.assertEqual(self.downloads, [])
        self.systemctl_mock.assert_not_called()

    def test_extra_or_symlinked_dormant_cache_is_rejected_without_repair(self):
        self.deploy.deploy("1.1.0")
        self.add_release("1.2.0")
        self.deploy.deploy("1.2.0", "frontend")
        self.deploy.deploy("1.1.0", "frontend")
        cache = self.app / "deployments/frontend/1.2.0"
        original = (cache / "frontend/index.html").read_bytes()
        self.downloads.clear()
        self.systemctl_mock.reset_mock()
        for symlink in (False, True):
            extra = cache / "extra"
            if symlink:
                extra.symlink_to(self.base / "not-a-cache-file")
            else:
                extra.write_bytes(b"tampered extra")
            with self.subTest(symlink=symlink), self.assertRaisesRegex(ValueError, "cache"):
                self.deploy.deploy("1.2.0", "frontend")
            self.assertTrue(os.path.lexists(extra))
            self.assertEqual((cache / "frontend/index.html").read_bytes(), original)
            extra.unlink()  # Test fixture restoration, never performed by the deployer.
        self.assertEqual(self.downloads, [])
        self.systemctl_mock.assert_not_called()

    def test_every_selected_checksum_precedes_all_extraction(self):
        for asset in ("tictactest-1.1.0.jar", "tictactest-runtime-1.1.0.zip", "tictactest-frontend-1.1.0.zip"):
            path = self.fixture / asset
            original = path.read_bytes()
            path.write_bytes(b"corrupt")
            with self.subTest(asset=asset), mock.patch.object(self.deploy, "extract_archive") as extract:
                with self.assertRaisesRegex(ValueError, "SHA256"):
                    self.deploy.deploy("1.1.0")
                extract.assert_not_called()
            self.assertFalse(os.path.lexists(self.app / "current"))
            self.assertFalse(os.path.lexists(self.app / "frontend-current"))
            path.write_bytes(original)
        self.systemctl_mock.assert_not_called()

    def test_frontend_metadata_is_checked_before_publishing_either_component(self):
        archive = self.fixture / "tictactest-frontend-1.1.0.zip"
        with zipfile.ZipFile(archive) as bundle:
            files = {name: bundle.read(name) for name in bundle.namelist()}
        files["version.txt"] = b"9.9.9\n"
        with zipfile.ZipFile(archive, "w") as bundle:
            for name, data in files.items():
                bundle.writestr(name, data)
        self.checksum(archive)
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.deploy.deploy("1.1.0")
        self.assertFalse((self.app / "deployments/backend/1.1.0").exists())
        self.assertFalse((self.app / "deployments/frontend/1.1.0").exists())
        self.systemctl_mock.assert_not_called()

    def test_console_wrapper_uses_sibling_script_python_and_bounded_capture(self):
        spec = importlib.util.spec_from_file_location("console_wrapper_deploy", DEPLOY)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with mock.patch.object(module.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            module.probe_console(7.5)
        self.assertEqual(run.call_args.args[0], [module.sys.executable, str(DEPLOY.with_name("console-smoke.py")),
                                               "http://127.0.0.1:8080/console/", "--timeout", "7.5"])
        self.assertEqual(run.call_args.kwargs, {"capture_output": True, "text": True, "timeout": 7.5, "check": False})
        with mock.patch.object(module.subprocess, "run", return_value=mock.Mock(returncode=1, stdout="bad JVM", stderr="no prompt")):
            with self.assertRaisesRegex(RuntimeError, "bad JVMno prompt"):
                module.probe_console(2)

    def test_bad_backend_game_probe_restores_previous_mixed_selection(self):
        self.deploy.deploy("1.1.0")
        self.add_release("1.2.0")
        self.deploy.deploy("1.2.0", "frontend")
        self.add_release("1.3.0")
        previous_env = (self.config / "release.env").read_bytes()
        self.probe_mock.reset_mock()
        self.probe_mock.side_effect = [RuntimeError("bad JVM"), None]
        self.systemctl_mock.reset_mock()
        self.health_mock.reset_mock()
        with self.assertRaisesRegex(RuntimeError, "bad JVM"):
            self.deploy.deploy("1.3.0", "backend")
        self.assertEqual((self.app / "current").resolve().name, "1.1.0")
        self.assertEqual((self.app / "frontend-current").resolve().name, "1.2.0")
        self.assertEqual((self.config / "release.env").read_bytes(), previous_env)
        self.assertEqual(self.probe_mock.call_count, 2)
        self.assertEqual(self.health_mock.call_args_list,
                         [mock.call("1.3.0", "1.2.0", mock.ANY), mock.call("1.1.0", "1.2.0", mock.ANY)])
        self.assertEqual(self.systemctl_mock.call_args_list,
                         [mock.call("restart", "tictactest-console.service")] * 2)

    def test_cache_owned_by_another_identity_is_unsafe_even_when_modes_match(self):
        self.deploy.deploy("1.1.0")
        root = self.app / "deployments/frontend/1.1.0"
        with mock.patch.object(self.deploy.os, "getuid", return_value=os.getuid() ^ 1):
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                self.deploy.validate_cache(root, "frontend", "1.1.0")

    def test_cli_reports_bounded_subprocess_timeout_without_traceback(self):
        import contextlib
        import io
        stderr = io.StringIO()
        with mock.patch.object(self.deploy.sys, "argv", [str(DEPLOY), "1.1.0", "--components", "backend"]), \
             mock.patch.object(self.deploy, "deploy", side_effect=subprocess.TimeoutExpired("systemctl", 10)), \
             contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                self.deploy.main()
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("Deployment failed:", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_application_root_owned_by_another_identity_is_rejected_before_lock(self):
        with mock.patch.object(self.deploy.os, "getuid", return_value=os.getuid() ^ 1):
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                self.deploy.deploy("1.1.0")
        self.assertFalse((self.app / ".deploy.lock").exists())
        self.assertEqual(self.downloads, [])

    def test_local_health_never_follows_a_redirect_away_from_config_route(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b"healthy"
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(self.deploy.urllib.request, "build_opener", return_value=opener) as build:
            self.deploy.fetch_local("/config.js", 1)
        redirects = [handler for handler in build.call_args.args
                     if isinstance(handler, self.deploy.urllib.request.HTTPRedirectHandler)]
        self.assertEqual(len(redirects), 1, "host-local health must explicitly disable redirect following")
        request = self.deploy.urllib.request.Request("http://127.0.0.1:8080/config.js")
        self.assertIsNone(redirects[0].redirect_request(request, None, 302, "Found", {}, "https://external.test/config.js"))

    def test_initial_both_installs_separate_immutable_components(self):
        self.deploy.deploy("1.1.0", components="both")
        backend = self.app / "deployments/backend/1.1.0"
        frontend = self.app / "deployments/frontend/1.1.0"
        self.assertEqual((self.app / "current").resolve(), backend)
        self.assertEqual((self.app / "frontend-current").resolve(), frontend)
        self.assertEqual((frontend / "frontend/version.txt").read_text(), "1.1.0\n")
        self.assertEqual(hashlib.sha256((backend / self.jar.name).read_bytes()).hexdigest(), self.jar_hash)
        self.assertFalse((backend / "frontend").exists())
        self.assertFalse((frontend / "runtime").exists())
        self.assertEqual((self.config / "release.env").read_text(), f"JAR_PATH={backend}/{self.jar.name}\n")
        self.assertEqual(len(self.downloads), 6)

    def test_downloaded_release_is_verified_and_activated_without_changing_jar(self):
        original_config = (ROOT / "frontend/config.js").read_bytes()
        self.deploy.deploy("1.1.0")
        backend = self.app / "deployments/backend/1.1.0"
        frontend = self.app / "deployments/frontend/1.1.0"
        self.assertEqual(len(self.downloads), 6)
        self.assertEqual(set(self.downloads), {p.name for p in self.fixture.iterdir()})
        self.assertEqual((self.app / "current").resolve(), backend)
        self.assertEqual(hashlib.sha256((backend / self.jar.name).read_bytes()).hexdigest(), self.jar_hash)
        self.assertEqual((frontend / "frontend/version.txt").read_text(), "1.1.0\n")
        self.assertEqual((frontend / "frontend/config.js").read_bytes(), original_config)
        self.assertEqual((ROOT / "frontend/config.js").read_bytes(), original_config)
        self.assertEqual((self.config / "release.env").read_text(), f"JAR_PATH={backend}/{self.jar.name}\n")
        for release in (backend, frontend):
            for path in release.rglob("*"):
                self.assertEqual(path.stat().st_mode & 0o777, 0o755 if path.is_dir() else 0o644)
        self.health_mock.assert_called_once_with("1.1.0", "1.1.0", mock.ANY)
        self.assertEqual(self.systemctl_mock.call_args_list,
                         [mock.call("restart", "tictactest-console.service"), mock.call("start", "tictactest-web.service")])

    def test_release_is_readable_even_with_restrictive_callers_umask(self):
        previous_umask = os.umask(0o077)
        try:
            self.deploy.deploy("1.1.0")
        finally:
            os.umask(previous_umask)
        release = self.app / "deployments"
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
        self.assertEqual(list((self.app / "deployments/backend").iterdir()), [])
        self.assertEqual(list((self.app / "deployments/frontend").iterdir()), [])

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

    def test_zip_paths_are_rejected_even_if_accidentally_allowlisted(self):
        archive = self.base / "traversal.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("../escape", "outside")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.deploy.extract_archive(archive, self.base / "extracted", {"../escape"})
        self.assertFalse((self.base / "extracted").exists())
        self.assertFalse((self.base / "escape").exists())

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

    def test_ambiguous_jar_manifest_metadata_is_rejected(self):
        with zipfile.ZipFile(self.jar, "w") as bundle:
            bundle.writestr("META-INF/MANIFEST.MF", "Implementation-Version: 1.1.0\nImplementation-Version: 9.9.9\n\n")
        self.checksum(self.jar)
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.deploy.deploy("1.1.0")
        self.assertFalse(os.path.lexists(self.app / "current"))
        self.systemctl_mock.assert_not_called()

    def test_jar_manifest_version_must_match_requested_version(self):
        with zipfile.ZipFile(self.jar, "w") as bundle:
            bundle.writestr("META-INF/MANIFEST.MF", "Implementation-Version: 9.9.9\n\n")
        self.checksum(self.jar)
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.deploy.deploy("1.1.0")
        self.systemctl_mock.assert_not_called()
        self.assertFalse((self.app / "deployments/backend/1.1.0").exists())

    def test_failed_health_restores_symlink_and_environment_and_checks_rollback(self):
        self.add_release("1.0.0")
        self.deploy.deploy("1.0.0")
        previous = self.app / "deployments/backend/1.0.0"
        environment = self.config / "release.env"
        old_env = environment.read_bytes()
        self.health_mock.reset_mock()
        self.systemctl_mock.reset_mock()
        self.health_mock.side_effect = [RuntimeError("new release unhealthy"), None]
        with self.assertRaisesRegex(RuntimeError, "new release unhealthy"):
            self.deploy.deploy("1.1.0")
        self.assertEqual((self.app / "current").resolve(), previous)
        self.assertEqual(environment.read_bytes(), old_env)
        self.assertEqual(self.health_mock.call_args_list, [mock.call("1.1.0", "1.1.0", mock.ANY), mock.call("1.0.0", "1.0.0", mock.ANY)])
        self.assertEqual(self.systemctl_mock.call_count, 2)
        self.assertTrue((self.app / "deployments/backend/1.1.0").is_dir(), "retain failed immutable component for diagnosis")

    def test_failed_initial_release_removes_selection_and_stops_units(self):
        self.health_mock.side_effect = RuntimeError("unhealthy")
        with self.assertRaisesRegex(RuntimeError, "unhealthy"):
            self.deploy.deploy("1.1.0")
        self.assertFalse(os.path.lexists(self.app / "current"))
        self.assertFalse((self.config / "release.env").exists())
        self.systemctl_mock.assert_called_with("stop", "tictactest-console.service", "tictactest-web.service")

    def test_health_checks_all_loopback_routes_and_distinct_component_versions(self):
        # Invoke the real implementation, leaving only HTTP and systemctl mocked.
        spec = importlib.util.spec_from_file_location("real_deploy", DEPLOY)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        seen = []
        def response(url, timeout):
            seen.append(url)
            body = (b"1.2.0\n" if url.endswith("/version.txt") else
                    b"1.1.0\n" if url.endswith("/backend-version.txt") else
                    b"window.TICTACTEST_CONFIG = {consoleUrl: '/console/', backendVersionUrl: '/backend-version.txt'};"
                    if url.endswith("/config.js") else b"<html>terminal or frontend</html>")
            result = mock.MagicMock()
            result.__enter__.return_value = result
            result.status = 200
            result.headers = {"X-TicTacTest-Layout": "split-v1", "Cache-Control": "no-store"}
            result.read.return_value = body
            return result
        opener = mock.Mock()
        opener.open.side_effect = response
        with mock.patch.object(module.urllib.request, "build_opener", return_value=opener), mock.patch.object(module, "systemctl"), mock.patch.object(module, "check_application_listeners") as listeners:
            module.wait_healthy("1.1.0", "1.2.0")
        self.assertEqual(listeners.call_count, 1)
        self.assertEqual(seen, ["http://127.0.0.1:8080" + route for route in ("/", "/version.txt", "/backend-version.txt", "/console/", "/config.js")])

    def test_health_has_one_finite_budget_and_bounds_each_operation(self):
        spec = importlib.util.spec_from_file_location("deadline_deploy", DEPLOY)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        clock = [0.0]
        budgets = []
        def service(*args, **kwargs):
            budgets.append(kwargs["timeout"])
            clock[0] += 0.1
        def opening(url, timeout):
            budgets.append(timeout)
            clock[0] += timeout
            raise TimeoutError("unreachable")
        opener = mock.Mock()
        opener.open.side_effect = opening
        with mock.patch.object(module.time, "monotonic", side_effect=lambda: clock[0]), \
             mock.patch.object(module.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)), \
             mock.patch.object(module, "systemctl", side_effect=service), \
             mock.patch.object(module, "check_application_listeners", side_effect=service), \
             mock.patch.object(module.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(RuntimeError, "health"):
                module.wait_healthy("1.1.0", "1.2.0", timeout=3)
        self.assertLessEqual(clock[0], 3.01)
        self.assertTrue(budgets)
        self.assertTrue(all(0 < budget <= 3 for budget in budgets))

    def test_http_operation_cannot_extend_total_health_deadline(self):
        import time
        spec = importlib.util.spec_from_file_location("hard_deadline_deploy", DEPLOY)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        opener = mock.Mock()
        def stalled(url, timeout):
            time.sleep(0.2)
            raise TimeoutError("ignores socket timeout, like a slow-drip response")
        opener.open.side_effect = stalled
        start = time.monotonic()
        with mock.patch.object(module, "systemctl"), mock.patch.object(module, "check_application_listeners"), \
             mock.patch.object(module.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(RuntimeError, "health"):
                module.wait_healthy("1.1.0", timeout=0.05)
        self.assertLess(time.monotonic() - start, 0.15)

    def test_deployment_rejects_exposed_backends_or_missing_public_http(self):
        self.assertTrue(hasattr(self.deploy, "check_application_listeners"),
                        "Health checks must verify the public proxy and private backends")
        private = "LISTEN 0 128 127.0.0.1:7681 0.0.0.0:*\nLISTEN 0 511 127.0.0.1:8080 0.0.0.0:*\n"
        public = "LISTEN 0 511 0.0.0.0:80 0.0.0.0:*\n"
        for output in (
            private,
            private.replace("127.0.0.1:7681", "0.0.0.0:7681") + public,
            private.replace("127.0.0.1:7681", "[::]:7681") + public,
            private.replace("127.0.0.1:8080", "0.0.0.0:8080") + public,
            public,
            private + public + public,
        ):
            with self.subTest(output=output), mock.patch.object(
                self.deploy.subprocess, "run", return_value=mock.Mock(stdout=output)
            ), self.assertRaisesRegex(ValueError, "loopback"):
                self.deploy.check_application_listeners()
        with mock.patch.object(self.deploy.subprocess, "run", return_value=mock.Mock(stdout=private + public)):
            self.deploy.check_application_listeners()

    def test_deployment_helper_uses_python39_syntax(self):
        ast.parse(DEPLOY.read_text(), feature_version=(3, 9))


class HealthDeadlineTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("shared_deadline_deploy", DEPLOY)
        assert spec is not None and spec.loader is not None
        self.deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.deploy)

    def test_blocking_opener_setup_is_bounded_and_restores_callers_alarm(self):
        import time
        signal = self.deploy.signal
        previous_handler = signal.getsignal(signal.SIGALRM)
        previous_timer = signal.getitimer(signal.ITIMER_REAL)
        started = time.monotonic()
        caller_handler = mock.Mock()
        try:
            signal.signal(signal.SIGALRM, caller_handler)
            signal.setitimer(signal.ITIMER_REAL, 1.0, 2.0)
            with mock.patch.object(self.deploy, "local_opener", side_effect=lambda: time.sleep(0.2)), \
                 mock.patch.object(self.deploy, "systemctl") as service, \
                 mock.patch.object(self.deploy, "check_application_listeners") as listeners, \
                 mock.patch.object(self.deploy, "fetch_local") as fetch:
                with self.assertRaisesRegex((RuntimeError, TimeoutError), "health"):
                    self.deploy.wait_healthy("1.1.0", timeout=0.03)
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 0.15, "synchronous opener initialization escaped the health deadline")
            self.assertIs(signal.getsignal(signal.SIGALRM), caller_handler)
            restored = signal.getitimer(signal.ITIMER_REAL)
            self.assertAlmostEqual(restored[0], 1.0 - elapsed, delta=0.02)
            self.assertEqual(restored[1], 2.0)
            caller_handler.assert_not_called()
            service.assert_not_called()
            listeners.assert_not_called()
            fetch.assert_not_called()
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
            if previous_timer[0] > 0:
                signal.setitimer(signal.ITIMER_REAL,
                                 max(0.000001, previous_timer[0] - (time.monotonic() - started)), previous_timer[1])

    def test_backend_console_receives_only_original_budget_after_setup_and_http(self):
        clock = [100.0]
        def advance(seconds):
            clock[0] += seconds
        def fetch(route, timeout, opener):
            advance(1)
            return b"1.1.0", {}
        with mock.patch.object(self.deploy.time, "monotonic", side_effect=lambda: clock[0]), \
             mock.patch.object(self.deploy, "local_opener", side_effect=lambda: advance(3)), \
             mock.patch.object(self.deploy, "systemctl", side_effect=lambda *args, **kwargs: advance(10)) as service, \
             mock.patch.object(self.deploy, "check_application_listeners", side_effect=lambda timeout: advance(5)), \
             mock.patch.object(self.deploy, "fetch_local", side_effect=fetch), \
             mock.patch.object(self.deploy, "validate_public_config"), \
             mock.patch.object(self.deploy, "probe_console") as probe:
            self.deploy.check_selected_health("1.1.0", "1.1.0", True)
        probe.assert_called_once_with(160.0 - clock[0])
        self.assertEqual(clock[0], 123.0)
        service.assert_called_once_with("is-active", "--quiet", *self.deploy.UNITS, timeout=10)

    def test_selected_health_never_accepts_late_success_from_either_phase(self):
        for backend_selected, late_phase in ((False, "http"), (True, "console")):
            with self.subTest(backend_selected=backend_selected, late_phase=late_phase):
                clock = [0.0]
                def late_success(*args):
                    clock[0] = 61.0
                with mock.patch.object(self.deploy.time, "monotonic", side_effect=lambda: clock[0]), \
                     mock.patch.object(self.deploy, "_wait_healthy", side_effect=late_success if late_phase == "http" else None) as health, \
                     mock.patch.object(self.deploy, "probe_console", side_effect=late_success if late_phase == "console" else None) as probe:
                    with self.assertRaisesRegex(TimeoutError, "health"):
                        self.deploy.check_selected_health("1.1.0", "1.2.0", backend_selected)
                health.assert_called_once_with("1.1.0", "1.2.0", 60.0)
                if backend_selected:
                    probe.assert_called_once_with(60.0)
                else:
                    probe.assert_not_called()

    def test_standalone_health_rechecks_budget_after_config_validation(self):
        clock = [0.0]
        def validate(*args):
            clock[0] = 3.0
        with mock.patch.object(self.deploy.time, "monotonic", side_effect=lambda: clock[0]), \
             mock.patch.object(self.deploy, "local_opener"), \
             mock.patch.object(self.deploy, "systemctl"), \
             mock.patch.object(self.deploy, "check_application_listeners"), \
             mock.patch.object(self.deploy, "fetch_local", return_value=(b"1.1.0", {})), \
             mock.patch.object(self.deploy, "validate_public_config", side_effect=validate):
            with self.assertRaisesRegex(RuntimeError, "health"):
                self.deploy.wait_healthy("1.1.0", timeout=2)

    def test_frontend_health_cannot_succeed_at_61_seconds_after_opener_setup(self):
        clock = [0.0]
        service_attempts = []
        budgets = []

        def consume(duration, timeout):
            budgets.append(timeout)
            clock[0] += min(duration, timeout)
            if duration > timeout:
                raise TimeoutError("health operation timed out")

        def setup_opener():
            clock[0] += 3
            return mock.sentinel.opener

        def service(*args, timeout):
            self.assertEqual(args, ("is-active", "--quiet", *self.deploy.UNITS))
            service_attempts.append(clock[0])
            consume(10 if len(service_attempts) <= 4 else 4, timeout)
            if len(service_attempts) <= 4:
                raise subprocess.TimeoutExpired("systemctl", timeout)

        def fetch(route, timeout, opener):
            self.assertIs(opener, mock.sentinel.opener)
            consume(1.6, timeout)
            body = {"/version.txt": b"1.2.0", "/backend-version.txt": b"1.1.0",
                    "/config.js": b"window.TICTACTEST_CONFIG = {consoleUrl: '/console/', backendVersionUrl: '/backend-version.txt'};"}.get(route, b"healthy")
            return body, {"X-TicTacTest-Layout": "split-v1", "Cache-Control": "no-store"}

        with mock.patch.object(self.deploy.time, "monotonic", side_effect=lambda: clock[0]), \
             mock.patch.object(self.deploy.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)), \
             mock.patch.object(self.deploy, "local_opener", side_effect=setup_opener), \
             mock.patch.object(self.deploy, "systemctl", side_effect=service), \
             mock.patch.object(self.deploy, "check_application_listeners", side_effect=lambda timeout: consume(2, timeout)), \
             mock.patch.object(self.deploy, "fetch_local", side_effect=fetch), \
             mock.patch.object(self.deploy, "probe_console") as probe:
            with self.assertRaisesRegex((RuntimeError, TimeoutError), "health",
                                        msg="frontend-only health returned success after opener setup consumed its original budget"):
                self.deploy.check_selected_health("1.1.0", "1.2.0", False)
        self.assertLessEqual(clock[0], 60)
        self.assertTrue(all(0 < budget <= 10 for budget in budgets))
        probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
