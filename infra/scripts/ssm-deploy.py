#!/usr/bin/env python3
"""Run one published release deployment on EC2 through SSM Run Command.

Subcommands (used by .github/workflows/deploy.yml):
  running    print the publicly reported component versions
  preflight  check credentials, account and SSM reachability; changes nothing
  deploy     send exactly one command, wait for its result, verify over HTTP

The target comes from environment variables, never from the command line. No
credential, account ID, ARN or raw AWS error message is printed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
# The three operational files that must sit next to each other on the host.
TOOLS = ("deploy-release.sh", "deploy-release.py", "console-smoke.py")
VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
EXECUTION_TIMEOUT = 900
TERMINAL = {"Success", "Cancelled", "TimedOut", "Failed"}
PENDING = {"Pending", "InProgress", "Delayed", "Cancelling"}
EXPIRED = {"ExpiredToken", "ExpiredTokenException", "RequestExpired", "InvalidClientTokenId",
           "UnrecognizedClientException", "AuthFailure", "SignatureDoesNotMatch"}
RENEW = ("Learner-Lab-Zugangsdaten abgelaufen oder ungueltig. Alle drei Environment-Secrets "
         "erneuern und danach diesen Release manuell deployen (Run workflow).")


class DeployError(Exception):
    """A bounded failure that is safe to show in public workflow logs."""


class AwsError(DeployError):
    def __init__(self, operation, code):
        self.code = code
        text = operation + " failed: " + code
        if code in EXPIRED or code == "NoCredentials":
            text += ". " + RENEW
        elif code in ("AccessDenied", "AccessDeniedException"):
            text += ". Lab-Session beendet oder Recht fehlt; bei beendeter Session: " + RENEW
        super().__init__(text)


def setting(name, pattern):
    value = os.environ.get(name, "")
    if not re.fullmatch(pattern, value):
        raise DeployError("missing or malformed environment variable " + name)
    return value


def load_target():
    return {
        "region": setting("AWS_REGION", r"[a-z]{2}(?:-[a-z]+)+-[0-9]"),
        "account": setting("AWS_ACCOUNT_ID", r"[0-9]{12}"),
        "instance": setting("TICTACTEST_INSTANCE_ID", r"i-[0-9a-f]{8,17}"),
    }


def frontend_url():
    return setting("TICTACTEST_FRONTEND_URL", r"https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?/?").rstrip("/")


def aws(region, *arguments):
    """Call the AWS CLI and report only the error code, never the raw message."""
    operation = " ".join(arguments[:2])
    environment = dict(os.environ, AWS_PAGER="", AWS_MAX_ATTEMPTS="3")
    environment.pop("AWS_DEBUG", None)
    try:
        result = subprocess.run(
            ["aws", *arguments, "--region", region, "--output", "json", "--no-cli-pager",
             "--cli-connect-timeout", "10", "--cli-read-timeout", "30"],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120, env=environment)
    except (OSError, subprocess.TimeoutExpired):
        raise AwsError(operation, "Unavailable") from None
    if result.returncode != 0:
        match = re.search(r"An error occurred \(([A-Za-z0-9.]+)\)", result.stderr)
        if match:
            code = match.group(1)
        elif "Unable to locate credentials" in result.stderr or "Partial credentials" in result.stderr:
            code = "NoCredentials"
        else:
            code = "Unavailable"
        raise AwsError(operation, code)
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise AwsError(operation, "InvalidResponse") from None


def preflight(target):
    identity = aws(target["region"], "sts", "get-caller-identity")
    if identity.get("Account") != target["account"]:
        raise DeployError("credentials belong to a different AWS account than expected")
    # STS still answers after a lab session ended, so also ask for something useful.
    data = aws(target["region"], "ssm", "describe-instance-information",
               "--filters", "Key=InstanceIds,Values=" + target["instance"])
    rows = [row for row in data.get("InstanceInformationList", [])
            if row.get("InstanceId") == target["instance"]]
    if len(rows) != 1 or rows[0].get("PingStatus") != "Online":
        raise DeployError("instance is not online in SSM; is the lab session running?")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_text(url, timeout=5):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with opener.open(request, timeout=timeout) as response:
        return response.read(4096).decode("utf-8").strip(), response.headers


def public_versions(base):
    versions = {}
    for component, route in (("backend", "/backend-version.txt"), ("frontend", "/version.txt")):
        try:
            text, _ = fetch_text(base + route)
        except (OSError, ValueError, urllib.error.HTTPError):
            raise DeployError("cannot read the running {} version".format(component)) from None
        if not re.fullmatch(VERSION, text):
            raise DeployError("running {} version is malformed".format(component))
        versions[component] = text
    return versions


def remote_commands(version, components, commit, repository, directory=HERE):
    """Build the shell lines; every interpolated value is validated first."""
    if not re.fullmatch(VERSION, version):
        raise DeployError("version must be MAJOR.MINOR.PATCH without v")
    if components not in ("backend", "frontend", "both"):
        raise DeployError("components must be backend, frontend or both")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise DeployError("commit must be a full SHA")
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repository):
        raise DeployError("repository must be OWNER/REPO")
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", "umask 077",
             "stage=$(mktemp -d /root/tictactest-deploy.XXXXXX)",
             "trap 'rm -rf -- \"$stage\"' EXIT", 'cd "$stage"']
    base = "https://raw.githubusercontent.com/{}/{}/infra/scripts/".format(repository, commit)
    for name in TOOLS:
        digest = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        lines.append("curl --fail --silent --show-error --retry 3 --connect-timeout 15 --max-time 60 "
                     "--proto '=https' --tlsv1.2 --output {} {}".format(name, base + name))
        lines.append("printf '%s  %s\\n' {} {} | sha256sum --check --strict -".format(digest, name))
    lines.append("bash ./deploy-release.sh {} --components {}".format(version, components))
    return lines


def send(target, commands):
    # Never retried: a lost answer must not start a second deployment.
    parameters = {"commands": commands, "executionTimeout": [str(EXECUTION_TIMEOUT)]}
    data = aws(target["region"], "ssm", "send-command", "--document-name", "AWS-RunShellScript",
               "--instance-ids", target["instance"], "--timeout-seconds", "60",
               "--comment", "tictactest release deployment", "--parameters", json.dumps(parameters))
    command = data.get("Command", {}).get("CommandId", "")
    if not re.fullmatch(r"[0-9a-f-]{36}", command):
        raise DeployError("SSM accepted the request without a usable CommandId; check the host state")
    return command


def wait(target, command, timeout=EXECUTION_TIMEOUT + 120, sleep=time.sleep, clock=time.monotonic):
    """Poll exactly this command on exactly this instance until it is terminal."""
    started = clock()
    failures = 0
    while clock() - started < timeout:
        try:
            result = aws(target["region"], "ssm", "get-command-invocation",
                         "--command-id", command, "--instance-id", target["instance"])
            failures = 0
        except AwsError as error:
            # A fresh invocation may not be visible yet; other errors get few retries.
            failures += 1
            fresh = error.code == "InvocationDoesNotExist" and clock() - started < 30
            if not fresh and (error.code not in ("Unavailable", "InvalidResponse", "ThrottlingException")
                              or failures > 5):
                raise DeployError("outcome of {} is unknown, the command may still run. {}".format(
                    command, error)) from None
            sleep(3)
            continue
        status = result.get("Status")
        if status in TERMINAL:
            return result
        if status not in PENDING:
            raise DeployError("outcome of {} is unknown: unexpected SSM status".format(command))
        sleep(3)
    raise DeployError("outcome of {} is unknown: polling timed out".format(command))


def show(text):
    """Print remote output so it can never act as a workflow command."""
    for line in text.splitlines()[-200:]:
        clean = "".join(character if character.isprintable() else " " for character in line)
        print("remote| " + clean[:500])


def verify_public(base, expected, timeout=60, sleep=time.sleep, clock=time.monotonic):
    started = clock()
    last = "no response"
    while clock() - started < timeout:
        try:
            versions = public_versions(base)
            body, headers = fetch_text(base + "/config.js")
            if versions != expected:
                last = "wrong versions: " + json.dumps(versions, sort_keys=True)
            elif headers.get("X-TicTacTest-Layout") != "split-v1" or "/console/" not in body:
                last = "infrastructure config.js is missing"
            else:
                return
        except (DeployError, OSError, ValueError) as error:
            last = str(error) if isinstance(error, DeployError) else "config.js not reachable"
        sleep(2)
    raise DeployError("public check failed: " + last)


def deploy(version, components, commit):
    target = load_target()
    base = frontend_url()
    repository = setting("GITHUB_REPOSITORY", r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+")
    commands = remote_commands(version, components, commit, repository)
    preflight(target)
    expected = {"backend": version, "frontend": version}
    if components != "both":
        untouched = "frontend" if components == "backend" else "backend"
        expected[untouched] = public_versions(base)[untouched]
    command = send(target, commands)
    print("SSM CommandId: " + command, flush=True)
    started = time.monotonic()
    result = wait(target, command)
    show(result.get("StandardOutputContent", ""))
    show(result.get("StandardErrorContent", ""))
    print("SSM status: {} after {:.0f}s".format(result["Status"], time.monotonic() - started))
    if result["Status"] != "Success" or result.get("ResponseCode") != 0:
        raise DeployError("deployment failed on the host; see remote output above")
    verify_public(base, expected)
    print("Verified backend {backend} and frontend {frontend}".format(**expected))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("running")
    commands.add_parser("preflight")
    run = commands.add_parser("deploy")
    run.add_argument("version")
    run.add_argument("--components", choices=("backend", "frontend", "both"), required=True)
    run.add_argument("--commit", required=True, help="trusted commit that provides the host tools")
    args = parser.parse_args(argv)
    try:
        if args.action == "running":
            versions = public_versions(frontend_url())
            print("backend={backend}\nfrontend={frontend}".format(**versions))
        elif args.action == "preflight":
            preflight(load_target())
            print("Credentials, account and SSM target are valid")
        else:
            deploy(args.version, args.components, args.commit)
    except DeployError as error:
        # Workflow commands are read from stdout as well as stderr.
        print("::error::" + str(error).replace("\n", " ").replace("\r", " ")[:600], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
