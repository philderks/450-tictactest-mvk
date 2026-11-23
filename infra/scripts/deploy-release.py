#!/usr/bin/env python3
"""Deploy a fixed public TicTacTest release as root; never build on the host.

Usage: sudo python3 deploy-release.py 1.1.0
Run install-runtime.sh first. Releases are immutable: an existing version is refused.
Only the copied frontend/config.js is customized. No public listener is created.
"""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
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
        "curl", "--fail", "--location", "--retry", "3", "--connect-timeout", "15",
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
            if member.is_dir() or kind not in (0, stat.S_IFREG) or member.flag_bits & 1:
                raise ValueError("Unsafe ZIP entry: " + member.filename)
        target.mkdir(mode=0o755)
        target.chmod(0o755)
        for member in members:
            path = target / member.filename
            path.write_bytes(bundle.read(member))
            path.chmod(0o644)


def systemctl(*arguments):
    subprocess.run(["systemctl", *arguments], check=True)


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


def switch_current(target):
    temporary = APP / ".current-next"
    try:
        temporary.symlink_to(target)
        os.replace(temporary, APP / "current")
    finally:
        temporary.unlink(missing_ok=True)


def check_application_listeners():
    result = subprocess.run(
        ["ss", "-H", "-lnt", "( sport = :80 or sport = :7681 or sport = :8080 )"],
        check=True, capture_output=True, text=True,
    )
    addresses = {line.split()[3] for line in result.stdout.splitlines() if line.strip()}
    if addresses != {"0.0.0.0:80", "127.0.0.1:7681", "127.0.0.1:8080"}:
        raise ValueError("Expected public HTTP and loopback-only backends; got " + str(sorted(addresses)))


def wait_healthy(version):
    # Do not honor HTTP_PROXY for host-local health probes.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last_error = None
    for _ in range(30):
        try:
            systemctl("is-active", "--quiet", *UNITS)
            check_application_listeners()
            for route in ("/", "/version.txt", "/backend-version.txt", "/console/"):
                with opener.open("http://127.0.0.1:8080" + route, timeout=2) as response:
                    body = response.read()
                    if response.status != 200 or not body:
                        raise ValueError("Unhealthy route: " + route)
                    if route.endswith("version.txt") and body.decode("utf-8").strip() != version:
                        raise ValueError("Wrong version at " + route)
            return
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            last_error = error
            time.sleep(1)
    raise RuntimeError("Release health checks failed: " + str(last_error))


def deploy(version):
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        raise ValueError("version must be strict MAJOR.MINOR.PATCH (without v)")
    if os.geteuid() != 0:
        raise PermissionError("Run the deployer as root.")
    if not APP.is_dir() or not CONFIG.is_dir():
        raise ValueError("Run install-runtime.sh first.")
    with (APP / ".deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        releases = APP / "releases"
        releases.mkdir(mode=0o755, exist_ok=True)
        releases.chmod(0o755)
        release = releases / version
        if os.path.lexists(release):
            raise ValueError("Immutable release already exists: " + str(release))
        current = APP / "current"
        if current.exists() and not current.is_symlink():
            raise ValueError("current must be a symlink")
        previous = os.readlink(current) if current.is_symlink() else None
        environment = CONFIG / "release.env"
        previous_env = environment.read_bytes() if environment.exists() else None
        with tempfile.TemporaryDirectory(prefix=".staging-", dir=str(releases)) as temp:
            stage = Path(temp)
            artifacts = ["tictactest-" + version + ".jar"] + [
                "tictactest-" + component + "-" + version + ".zip" for component in CONTENTS
            ]
            for name in artifacts:
                for asset in (name, name + ".sha256"):
                    download(REPOSITORY + "/releases/download/v" + version + "/" + asset, stage / asset)
            # Check every artifact before extracting either ZIP or touching the running release.
            for name in artifacts:
                verify_checksum(stage / name)
            content = stage / "release"
            content.mkdir(mode=0o755)
            content.chmod(0o755)
            jar_name = artifacts[0]
            shutil.copyfile(stage / jar_name, content / jar_name)
            (content / jar_name).chmod(0o644)
            for component, allowed in CONTENTS.items():
                extract_archive(stage / ("tictactest-" + component + "-" + version + ".zip"), content / component, allowed)
            # Inspect metadata without executing downloaded release scripts as root.
            with zipfile.ZipFile(content / jar_name) as jar:
                main = jar.read("META-INF/MANIFEST.MF").decode("utf-8").replace("\r\n", "\n").split("\n\n", 1)[0]
            backend = next((line.partition(":")[2].strip() for line in main.splitlines()
                            if line.startswith("Implementation-Version:")), "")
            frontend = (content / "frontend/version.txt").read_text().strip()
            if backend != version or frontend != version:
                raise ValueError("Packaged version metadata does not match requested release")
            (content / "frontend/config.js").write_text(
                "window.TICTACTEST_CONFIG = {\n"
                "  consoleUrl: '/console/',\n"
                "  backendVersionUrl: '/backend-version.txt',\n"
                "};\n", encoding="utf-8")
            # A root-run deploy owns these files; services receive read-only access.
            os.rename(content, release)
        try:
            atomic_write(environment, ("JAR_PATH=" + str(APP / "current" / jar_name) + "\n").encode("utf-8"))
            switch_current(release)
            systemctl("restart", *UNITS)
            wait_healthy(version)
        except BaseException:
            # Restore both runtime selection inputs, not merely the symlink.
            if previous_env is None:
                environment.unlink(missing_ok=True)
            else:
                atomic_write(environment, previous_env)
            if previous is None:
                current.unlink(missing_ok=True)
                systemctl("stop", *UNITS)
            else:
                switch_current(previous)
                systemctl("restart", *UNITS)
                wait_healthy(Path(previous).name)
            raise
        print("Deployed " + version + "; frontend, backend metadata and HTTP console healthy on loopback:8080")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    args = parser.parse_args()
    try:
        deploy(args.version)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        parser.exit(1, "Deployment failed: " + str(error) + "\n")


if __name__ == "__main__":
    main()
