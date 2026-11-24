#!/usr/bin/env python3
"""Deploy verified components on an explicitly prepared split runtime.

Usage: sudo python3 deploy-release.py VERSION [--components backend|frontend|both]
Run install-runtime.sh and explicitly prepare/load split nginx first. Immutable
backend/frontend caches are verified before reuse; legacy releases are read-only.
This command never migrates nginx, builds, or executes release code as root.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

APP = Path("/opt/tictactest")
CONFIG = Path("/etc/tictactest")
REPOSITORY = "https://github.com/philderks/450-tictactest-mvk"
UNITS = ("tictactest-console.service", "tictactest-web.service")
CONTENTS = {
    "runtime": {"backend-version.py", "serve-backend-version.py", "start-console.sh", "README.md"},
    "frontend": {"index.html", "style.css", "app.js", "config.js", "version.txt"},
}


def download(url, destination):
    subprocess.run([
        "curl", "--fail", "--silent", "--show-error", "--location", "--retry", "3", "--connect-timeout", "15",
        "--max-time", "180", "--proto", "=https", "--tlsv1.2", "--output", str(destination), url,
    ], check=True)


def verify_checksum(artifact):
    checksum = artifact.with_name(artifact.name + ".sha256").read_text(encoding="ascii")
    match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *]" + re.escape(artifact.name) + r"\n?", checksum)
    if not match or hashlib.sha256(artifact.read_bytes()).hexdigest() != match.group(1).lower():
        raise ValueError("SHA256 verification failed: " + artifact.name)


def extract_archive(archive, target, allowed):
    # No extractall: reject paths, duplicates, symlinks, devices and unexpected content.
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        names = [member.filename for member in members]
        if len(names) != len(allowed) or set(names) != allowed:
            raise ValueError("Unexpected ZIP entries: " + archive.name)
        if sum(member.file_size for member in members) > 16 * 1024 * 1024:
            raise ValueError("ZIP content too large: " + archive.name)
        for member in members:
            kind = stat.S_IFMT(member.external_attr >> 16)
            if (member.is_dir() or kind not in (0, stat.S_IFREG) or member.flag_bits & 1
                    or member.filename in (".", "..") or "/" in member.filename or "\\" in member.filename
                    or "\x00" in member.filename):
                raise ValueError("Unsafe ZIP entry: " + member.filename)
        target.mkdir(mode=0o755)
        target.chmod(0o755)
        for member in members:
            path = target / member.filename
            path.write_bytes(bundle.read(member))
            path.chmod(0o644)


def systemctl(*arguments, timeout=10.0):
    subprocess.run(["systemctl", *arguments], check=True, timeout=timeout)


def atomic_write(path, data):
    fd, name = tempfile.mkstemp(prefix=".release-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            os.fchmod(output.fileno(), 0o644)
        os.replace(name, path)
    finally:
        if os.path.lexists(name):
            os.unlink(name)


def switch_current(target, name="current"):
    temporary = APP / ("." + name + "-next")
    try:
        temporary.symlink_to(target)
        os.replace(temporary, APP / name)
    finally:
        temporary.unlink(missing_ok=True)


def check_application_listeners(timeout=5.0):
    result = subprocess.run(
        ["ss", "-H", "-lnt", "( sport = :80 or sport = :7681 or sport = :8080 )"],
        check=True, capture_output=True, text=True, timeout=timeout,
    )
    addresses = [line.split()[3] for line in result.stdout.splitlines() if line.strip()]
    if len(addresses) != 3 or set(addresses) != {"0.0.0.0:80", "127.0.0.1:7681", "127.0.0.1:8080"}:
        raise ValueError("Expected public HTTP and loopback-only backends; got " + str(sorted(addresses)))


def validate_public_config(body, headers):
    text = body.decode("utf-8")
    expected = (r"\s*window\.TICTACTEST_CONFIG\s*=\s*\{\s*"
                r"consoleUrl\s*:\s*['\"]/console/['\"]\s*,\s*"
                r"backendVersionUrl\s*:\s*['\"]/backend-version\.txt['\"]\s*,?\s*\}\s*;\s*")
    if (headers.get("X-TicTacTest-Layout") != "split-v1"
            or "no-store" not in {part.strip().lower() for part in headers.get("Cache-Control", "").split(",")}
            or re.fullmatch(expected, text) is None):
        raise ValueError("Proxy has not loaded split-v1 same-origin /config.js")


def service_active(unit):
    result = subprocess.run(["systemctl", "is-active", "--quiet", unit], timeout=5, check=False)
    if result.returncode not in (0, 3):
        raise RuntimeError("Cannot determine service state: " + unit)
    return result.returncode == 0


@contextmanager
def http_deadline(timeout):
    # Linux CLI: socket timeouts alone do not bound slow-drip headers/bodies.
    # Restore the caller's alarm instead of leaving process-global state changed.
    if timeout <= 0:
        raise TimeoutError("health deadline exhausted")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    def expired(signum, frame):
        raise TimeoutError("HTTP health operation deadline exhausted")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(timeout, previous_timer[0]) if previous_timer[0] > 0 else timeout)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, max(0.000001, previous_timer[0] - (time.monotonic() - started)), previous_timer[1])


class NoHealthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoHealthRedirect())


def fetch_local(route, timeout, opener=None):
    if opener is None:
        opener = local_opener()
    with http_deadline(timeout):
        with opener.open("http://127.0.0.1:8080" + route, timeout=timeout) as response:
            body = response.read(1024 * 1024 + 1)
            if response.status != 200 or not body or len(body) > 1024 * 1024:
                raise ValueError("Unhealthy route: " + route)
            return body, response.headers


def probe_loaded_layout(timeout=5.0):
    body, headers = fetch_local("/config.js", timeout)
    validate_public_config(body, headers)


def require_split_nginx():
    """Refuse implicit migration; an operator must install the split config."""
    text = (CONFIG / "nginx.conf").read_text(encoding="utf-8")
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    route = re.search(r"location\s*=\s*/config\.js\s*\{(.*?)^\s*\}", text, re.S | re.M)
    if (re.findall(r"\broot\s+([^;]+);", text) != ["/opt/tictactest/frontend-current/frontend"]
            or route is None):
        raise ValueError("Install split nginx configuration before deployment")
    block = route.group(1)
    returned = re.search(r'return\s+200\s+"([^"\n]*)"\s*;', block)
    if (returned is None or not re.search(r'add_header\s+X-TicTacTest-Layout\s+"split-v1"\s+always;', block)
            or not re.search(r'add_header\s+Cache-Control\s+"no-store"\s+always;', block)):
        raise ValueError("Install split nginx /config.js before deployment")
    validate_public_config(returned.group(1).encode("utf-8"),
                           {"X-TicTacTest-Layout": "split-v1", "Cache-Control": "no-store"})


def remaining(deadline, cap=None):
    budget = deadline - time.monotonic()
    if budget <= 0:
        raise TimeoutError("health deadline exhausted")
    return min(budget, cap) if cap is not None else budget


def wait_healthy(backend_version, frontend_version=None, timeout=60.0):
    _wait_healthy(backend_version, frontend_version, time.monotonic() + timeout)


def _wait_healthy(backend_version, frontend_version, deadline):
    if frontend_version is None:
        frontend_version = backend_version
    # Start the shared budget before synchronous opener setup, which can block.
    # Do not honor HTTP_PROXY for host-local health probes.
    with http_deadline(remaining(deadline)):
        opener = local_opener()
    last_error = None
    while time.monotonic() < deadline:
        try:
            systemctl("is-active", "--quiet", *UNITS, timeout=remaining(deadline, 10))
            check_application_listeners(timeout=remaining(deadline, 5))
            for route in ("/", "/version.txt", "/backend-version.txt", "/console/", "/config.js"):
                body, headers = fetch_local(route, remaining(deadline, 2), opener)
                remaining(deadline)
                expected = {"/version.txt": frontend_version, "/backend-version.txt": backend_version}.get(route)
                if expected is not None and body.decode("utf-8").strip() != expected:
                    raise ValueError("Wrong version at " + route)
                if route == "/config.js":
                    validate_public_config(body, headers)
            remaining(deadline)
            return
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            last_error = error
            if time.monotonic() < deadline:
                time.sleep(min(1, remaining(deadline)))
    raise RuntimeError("Release health checks failed: " + str(last_error))


def probe_console(timeout):
    result = subprocess.run([
        sys.executable, str(Path(__file__).resolve().with_name("console-smoke.py")),
        "http://127.0.0.1:8080/console/", "--timeout", str(timeout),
    ], capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise RuntimeError("JVM console probe failed: " + result.stdout + result.stderr)


def check_selected_health(backend_version, frontend_version, backend_selected):
    deadline = time.monotonic() + 60
    _wait_healthy(backend_version, frontend_version, deadline)
    if backend_selected:
        probe_console(remaining(deadline))
    remaining(deadline)


def manifest_version(jar_path):
    with zipfile.ZipFile(jar_path) as jar:
        manifests = [info for info in jar.infolist() if info.filename == "META-INF/MANIFEST.MF"]
        if len(manifests) != 1 or manifests[0].file_size > 1024 * 1024:
            raise ValueError("Missing, ambiguous or oversized JAR manifest metadata")
        main = jar.read(manifests[0]).decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").split("\n\n", 1)[0]
    lines = []
    for line in main.splitlines():
        if line.startswith(" "):
            if not lines:
                raise ValueError("Malformed JAR manifest metadata continuation")
            lines[-1] += line[1:]
        else:
            lines.append(line)
    attributes = {}
    for line in lines:
        key, separator, value = line.partition(": ")
        key = key.lower()
        if not separator or key in attributes:
            raise ValueError("Ambiguous or malformed JAR manifest metadata")
        attributes[key] = value
    return attributes.get("implementation-version", "")


def component_tree(root, component, version):
    """Hash a fixed, non-symlink tree; never follow untrusted cache entries."""
    directory = "runtime" if component == "backend" else "frontend"
    expected = {directory + "/" + name for name in CONTENTS[directory]}
    if component == "backend":
        expected.add("tictactest-" + version + ".jar")
    if (root.is_symlink() or not root.is_dir() or stat.S_IMODE(root.stat().st_mode) != 0o755
            or root.stat().st_uid != os.getuid()):
        raise ValueError("Unsafe component cache: " + str(root))
    actual = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("Unsafe symlink or owner in component cache: " + str(path))
        if relative == directory:
            if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o755:
                raise ValueError("Unsafe component cache directory")
        elif relative in expected or relative == ".receipt.json":
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o644 or info.st_nlink != 1:
                raise ValueError("Unsafe component cache file: " + str(path))
            if relative != ".receipt.json":
                actual.add(relative)
        else:
            raise ValueError("Unexpected entry in component cache: " + str(path))
    if actual != expected:
        raise ValueError("Incomplete component cache: " + str(root))
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(expected)}
    metadata = (manifest_version(root / ("tictactest-" + version + ".jar")) if component == "backend"
                else (root / "frontend/version.txt").read_text().strip())
    if metadata != version:
        raise ValueError("Packaged version metadata does not match requested release")
    return hashes


def tree_digest(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def write_receipt(root, component, version, assets):
    files = component_tree(root, component, version)
    receipt = {"format": 1, "component": component, "version": version,
               "files": files, "tree_sha256": tree_digest(files), "artifacts": assets}
    atomic_write(root / ".receipt.json", (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii"))


def validate_cache(root, component, version):
    files = component_tree(root, component, version)
    try:
        receipt = json.loads((root / ".receipt.json").read_text(encoding="ascii"))
    except (OSError, ValueError) as error:
        raise ValueError("Missing or invalid component cache receipt: " + str(root)) from error
    if (not isinstance(receipt, dict) or set(receipt) != {"format", "component", "version", "files", "tree_sha256", "artifacts"}
            or type(receipt.get("format")) is not int or receipt.get("format") != 1
            or receipt.get("component") != component or receipt.get("version") != version
            or receipt.get("files") != files or receipt.get("tree_sha256") != tree_digest(files)):
        raise ValueError("Tampered component cache: " + str(root))
    artifacts = receipt["artifacts"]
    names = ({"tictactest-" + version + ".jar", "tictactest-runtime-" + version + ".zip"} if component == "backend"
             else {"tictactest-frontend-" + version + ".zip"})
    canonical = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    if (not isinstance(artifacts, dict) or set(artifacts) != names
            or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in artifacts.values())
            or (root / ".receipt.json").read_bytes() != canonical):
        raise ValueError("Tampered component cache receipt: " + str(root))


def validate_legacy(root, version):
    """Read only an explicitly split legacy selection; never upgrade it in place."""
    expected = {"tictactest-" + version + ".jar"}
    expected.update(directory + "/" + name for directory, names in CONTENTS.items() for name in names)
    actual = set()
    for path in [root] + list(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        info = path.lstat()
        directory = name in (".", "runtime", "frontend")
        if (info.st_uid != os.getuid()
                or directory and (not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o755)
                or not directory and (name not in expected or not stat.S_ISREG(info.st_mode)
                                      or stat.S_IMODE(info.st_mode) != 0o644 or info.st_nlink != 1)):
            raise ValueError("Unsafe legacy selection: " + str(path))
        if not directory:
            actual.add(name)
    if actual != expected:
        raise ValueError("Incomplete legacy selection")
    if (manifest_version(root / ("tictactest-" + version + ".jar")) != version
            or (root / "frontend/version.txt").read_text().strip() != version):
        raise ValueError("Legacy version metadata does not match selection")


class DeploymentRollbackError(RuntimeError):
    def __init__(self, deployment_error, rollback_error):
        self.deployment_error = deployment_error
        self.rollback_error = rollback_error
        super().__init__(str(deployment_error) + "; rollback failed: " + str(rollback_error))


def validate_component_directory(path):
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o755
            or info.st_uid != os.getuid()):
        raise ValueError("Unsafe deployment directory: " + str(path))


def ensure_component_directory(path):
    if not os.path.lexists(path):
        path.mkdir(mode=0o755)
        path.chmod(0o755)
    validate_component_directory(path)


def deploy(version, components="both"):
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        raise ValueError("version must be strict MAJOR.MINOR.PATCH (without v)")
    if components not in ("backend", "frontend", "both"):
        raise ValueError("components must be backend, frontend or both")
    if os.geteuid() != 0:
        raise PermissionError("Run the deployer as root.")
    if not APP.is_dir() or not CONFIG.is_dir():
        raise ValueError("Run install-runtime.sh first.")
    if (APP.is_symlink() or CONFIG.is_symlink() or not APP.is_absolute() or not CONFIG.is_absolute()
            or any(path.stat().st_mode & 0o022 or path.stat().st_uid != os.getuid() for path in (APP, CONFIG))):
        raise ValueError("Unsafe application/configuration root")
    selected = ("backend", "frontend") if components == "both" else (components,)
    descriptor = os.open(str(APP / ".deploy.lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        info = os.fstat(lock.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o022
                or info.st_uid != os.getuid()):
            raise ValueError("Unsafe deployment lock")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require_split_nginx()
        previous = {}
        for name in ("current", "frontend-current"):
            path = APP / name
            if os.path.lexists(path) and not path.is_symlink():
                raise ValueError(name + " must be a symlink")
            previous[name] = os.readlink(path) if path.is_symlink() else None
        environment = CONFIG / "release.env"
        if os.path.lexists(environment):
            info = environment.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_nlink != 1
                    or info.st_uid != os.getuid()):
                raise ValueError("Unsafe release.env")
        previous_env = environment.read_bytes() if environment.exists() else None
        initial = all(target is None for target in previous.values()) and previous_env is None
        previous_versions = {}
        if not initial:
            if any(target is None for target in previous.values()) or previous_env is None:
                raise ValueError("Inconsistent or unmigrated legacy selections; migrate frontend pointer/nginx separately")
            previous_paths = {}
            # Validate both selections' parents before trusting either leaf tree.
            for component, name in (("backend", "current"), ("frontend", "frontend-current")):
                # Follow only the selection link; do not normalize away symlink parents.
                path = APP / previous[name]
                if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", path.name):
                    raise ValueError("Unsafe component selection: " + str(path))
                if path.parent == APP / "deployments" / component:
                    validate_component_directory(APP / "deployments")
                    validate_component_directory(path.parent)
                elif path.parent == APP / "releases":
                    validate_component_directory(path.parent)
                else:
                    raise ValueError("Unsafe component selection: " + str(path))
                previous_paths[component] = path
            for component, path in previous_paths.items():
                if path.parent == APP / "releases":
                    validate_legacy(path, path.name)
                else:
                    validate_cache(path, component, path.name)
                previous_versions[component] = path.name
            values = [line.partition("=")[2] for line in previous_env.decode("utf-8").splitlines()
                      if line.startswith("JAR_PATH=")]
            expected_jar = (APP / "current").resolve() / ("tictactest-" + previous_versions["backend"] + ".jar")
            if len(values) != 1 or not Path(values[0]).is_absolute() or Path(values[0]).resolve() != expected_jar:
                raise ValueError("release.env does not match selected backend")
        if initial and components != "both":
            raise ValueError("An initial deployment requires both components")
        active = {unit: service_active(unit) for unit in UNITS}
        if initial and active[UNITS[0]]:
            raise ValueError("Empty selections with a running console are not a prepared initial host")
        if active[UNITS[1]]:
            probe_loaded_layout()
        ensure_component_directory(APP / "deployments")
        roots = {}
        missing = []
        for component in selected:
            root = APP / "deployments" / component
            ensure_component_directory(root)
            roots[component] = root / version
            if os.path.lexists(roots[component]):
                validate_cache(roots[component], component, version)
            else:
                missing.append(component)
        jar_name = "tictactest-" + version + ".jar"
        with tempfile.TemporaryDirectory(prefix=".staging-", dir=str(APP / "deployments")) as temp:
            stage = Path(temp)
            artifacts = []
            if "backend" in missing:
                artifacts += [jar_name, "tictactest-runtime-" + version + ".zip"]
            if "frontend" in missing:
                artifacts += ["tictactest-frontend-" + version + ".zip"]
            for name in artifacts:
                for asset in (name, name + ".sha256"):
                    download(REPOSITORY + "/releases/download/v" + version + "/" + asset, stage / asset)
            # No extraction until ALL selected downloads have passed their checksum.
            for name in artifacts:
                verify_checksum(stage / name)
            for component in missing:
                content = stage / component
                content.mkdir(mode=0o755)
                content.chmod(0o755)
                if component == "backend":
                    shutil.copyfile(stage / jar_name, content / jar_name)
                    (content / jar_name).chmod(0o644)
                    extract_archive(stage / ("tictactest-runtime-" + version + ".zip"), content / "runtime", CONTENTS["runtime"])
                    metadata = manifest_version(content / jar_name)
                else:
                    extract_archive(stage / ("tictactest-frontend-" + version + ".zip"), content / "frontend", CONTENTS["frontend"])
                    metadata = (content / "frontend/version.txt").read_text().strip()
                if metadata != version:
                    raise ValueError("Packaged version metadata does not match requested release")
                names = ([jar_name, "tictactest-runtime-" + version + ".zip"] if component == "backend"
                         else ["tictactest-frontend-" + version + ".zip"])
                write_receipt(content, component, version, {name: hashlib.sha256((stage / name).read_bytes()).hexdigest() for name in names})
            for component in missing:
                os.rename(stage / component, roots[component])
        backend_version = version if "backend" in selected else previous_versions["backend"]
        frontend_version = version if "frontend" in selected else previous_versions["frontend"]
        activated = []
        try:
            if "backend" in selected:
                atomic_write(environment, ("JAR_PATH=" + str(roots["backend"] / jar_name) + "\n").encode("utf-8"))
                switch_current(roots["backend"])
            if "frontend" in selected:
                switch_current(roots["frontend"], "frontend-current")
            if "backend" in selected:
                if initial and not active[UNITS[0]]:
                    activated.append(UNITS[0])
                systemctl("restart", UNITS[0])
            if initial and not active[UNITS[1]]:
                activated.append(UNITS[1])
                systemctl("start", UNITS[1])
            check_selected_health(backend_version, frontend_version, "backend" in selected)
        except BaseException as deployment_error:
            try:
                if "backend" in selected:
                    if previous_env is None:
                        environment.unlink(missing_ok=True)
                    else:
                        atomic_write(environment, previous_env)
                for name, target in previous.items():
                    if (name == "current" and "backend" not in selected
                            or name == "frontend-current" and "frontend" not in selected):
                        continue
                    if target is None:
                        (APP / name).unlink(missing_ok=True)
                    else:
                        switch_current(target, name)
                if initial:
                    if activated:
                        systemctl("stop", *activated)
                else:
                    if "backend" in selected:
                        systemctl("restart", UNITS[0])
                    check_selected_health(previous_versions["backend"], previous_versions["frontend"], "backend" in selected)
            except BaseException as rollback_error:
                raise DeploymentRollbackError(deployment_error, rollback_error) from deployment_error
            raise
        print("Deployed " + components + " " + version)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--components", choices=("backend", "frontend", "both"), default="both")
    args = parser.parse_args()
    try:
        deploy(args.version, args.components)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        parser.exit(1, "Deployment failed: " + str(error) + "\n")


if __name__ == "__main__":
    main()
