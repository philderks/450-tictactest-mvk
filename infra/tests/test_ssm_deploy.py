"""Runner-side SSM contracts with a fake AWS CLI; no network, no AWS."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "infra/scripts/ssm-deploy.py"
COMMIT = "a" * 40
COMMAND = "11111111-2222-3333-4444-555555555555"
INSTANCE = "i-0123456789abcdef0"
ENV = {"AWS_REGION": "us-east-1", "AWS_ACCOUNT_ID": "123456789012", "TICTACTEST_INSTANCE_ID": INSTANCE,
       "TICTACTEST_FRONTEND_URL": "http://192.0.2.1/", "GITHUB_REPOSITORY": "o/r"}
TARGET = {"region": "us-east-1", "account": "123456789012", "instance": INSTANCE}


def load():
    spec = importlib.util.spec_from_file_location("ssm_deploy", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class RemoteCommandTests(unittest.TestCase):
    def test_tools_are_pinned_to_commit_and_checked_before_execution(self):
        lines = load().remote_commands("1.3.0", "frontend", COMMIT, "o/r")
        self.assertEqual(lines[0], "#!/usr/bin/env bash")
        self.assertIn("set -euo pipefail", lines)
        for name in ("deploy-release.sh", "deploy-release.py", "console-smoke.py"):
            digest = hashlib.sha256((ROOT / "infra/scripts" / name).read_bytes()).hexdigest()
            self.assertTrue(any("/o/r/" + COMMIT + "/infra/scripts/" + name in line for line in lines))
            self.assertTrue(any(digest in line and "sha256sum --check --strict" in line for line in lines))
        self.assertEqual(lines[-1], "bash ./deploy-release.sh 1.3.0 --components frontend")
        subprocess.run(["bash", "-n"], input="\n".join(lines), text=True, check=True)

    def test_injection_attempts_are_rejected(self):
        m = load()
        good = ["1.3.0", "both", COMMIT, "o/r"]
        for index, bad in ((0, "1.3.0; id"), (0, "v1.3.0"), (0, "1.3.0\n"), (0, "01.3.0"), (1, "both x"),
                           (2, "main"), (2, COMMIT + "\n"), (3, "o/r;id"), (3, "o/r/x"), (3, "o")):
            values = list(good)
            values[index] = bad
            with self.subTest(bad=bad), self.assertRaises(m.DeployError):
                m.remote_commands(*values)

    def test_tampered_tool_stops_before_the_deployer_runs(self):
        # Real bash execution with a fake curl that delivers modified files.
        lines = load().remote_commands("1.3.0", "both", COMMIT, "o/r")
        with tempfile.TemporaryDirectory() as temp:
            fake = Path(temp) / "curl"
            fake.write_text('#!/bin/bash\nwhile [ "$1" != --output ]; do shift; done\necho tampered > "$2"\n')
            fake.chmod(0o755)
            script = "\n".join(lines).replace("/root/tictactest-deploy", temp + "/stage")
            result = subprocess.run(["bash"], input=script, text=True, capture_output=True,
                                    env={"PATH": temp + ":" + os.environ["PATH"]})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAILED", result.stdout)
            self.assertNotIn("Deployed", result.stdout)
            self.assertEqual([p.name for p in Path(temp).iterdir()], ["curl"])


class AwsTests(unittest.TestCase):
    def test_expired_credentials_explain_renewal_without_leaking(self):
        for code in ("ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId"):
            m = load()
            completed = subprocess.CompletedProcess(
                [], 254, "", "An error occurred (" + code + ") when calling: arn:aws:sts::123456789012:PRIVATE")
            with mock.patch.object(m.subprocess, "run", return_value=completed):
                with self.assertRaises(m.AwsError) as caught:
                    m.aws("us-east-1", "sts", "get-caller-identity")
            self.assertEqual(caught.exception.code, code)
            self.assertIn("erneuern", str(caught.exception))
            self.assertNotIn("PRIVATE", str(caught.exception))
            self.assertNotIn("123456789012", str(caught.exception))

    def test_missing_credentials_and_unusable_answers(self):
        for returncode, stdout, stderr, code in (
                (253, "", "Unable to locate credentials", "NoCredentials"),
                (255, "", "Could not connect PRIVATE", "Unavailable"),
                (0, "not json", "", "InvalidResponse")):
            m = load()
            completed = subprocess.CompletedProcess([], returncode, stdout, stderr)
            with self.subTest(code=code), mock.patch.object(m.subprocess, "run", return_value=completed):
                with self.assertRaises(m.AwsError) as caught:
                    m.aws("us-east-1", "ssm", "x")
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn("PRIVATE", str(caught.exception))

    def test_preflight_checks_account_and_online_target(self):
        online = {"InstanceInformationList": [{"InstanceId": INSTANCE, "PingStatus": "Online"}]}
        for identity, info, ok in (
                ({"Account": "123456789012"}, online, True),
                ({"Account": "999999999999"}, online, False),
                ({"Account": "123456789012"}, {"InstanceInformationList": []}, False),
                ({"Account": "123456789012"}, {"InstanceInformationList": [
                    {"InstanceId": INSTANCE, "PingStatus": "ConnectionLost"}]}, False)):
            m = load()
            with self.subTest(ok=ok), mock.patch.object(m, "aws", side_effect=[identity, info]):
                if ok:
                    m.preflight(TARGET)
                else:
                    with self.assertRaises(m.DeployError):
                        m.preflight(TARGET)


class WaitTests(unittest.TestCase):
    def test_waits_through_invisible_and_running_states(self):
        m = load()
        done = {"Status": "Success", "ResponseCode": 0}
        error = m.AwsError("ssm", "InvocationDoesNotExist")
        clock = Clock()
        with mock.patch.object(m, "aws", side_effect=[error, {"Status": "Pending"}, {"Status": "InProgress"}, done]) as fake:
            self.assertEqual(m.wait(TARGET, COMMAND, sleep=clock.sleep, clock=clock), done)
        for call in fake.call_args_list:
            self.assertIn(COMMAND, call.args)
            self.assertIn(INSTANCE, call.args)

    def test_expired_while_polling_reports_unknown_outcome(self):
        m = load()
        clock = Clock()
        with mock.patch.object(m, "aws", side_effect=m.AwsError("ssm", "ExpiredTokenException")):
            with self.assertRaisesRegex(m.DeployError, COMMAND + " is unknown.*may still run"):
                m.wait(TARGET, COMMAND, sleep=clock.sleep, clock=clock)

    def test_timeout_and_unexpected_status_are_not_success(self):
        for answer in ({"Status": "InProgress"}, {"Status": "Weird"}, {}):
            m = load()
            clock = Clock()
            with self.subTest(answer=answer), mock.patch.object(m, "aws", return_value=answer):
                with self.assertRaisesRegex(m.DeployError, "unknown"):
                    m.wait(TARGET, COMMAND, timeout=60, sleep=clock.sleep, clock=clock)
                self.assertLess(clock.now, 70)

    def test_permanently_invisible_command_fails(self):
        m = load()
        clock = Clock()
        with mock.patch.object(m, "aws", side_effect=m.AwsError("ssm", "InvocationDoesNotExist")):
            with self.assertRaisesRegex(m.DeployError, "unknown"):
                m.wait(TARGET, COMMAND, sleep=clock.sleep, clock=clock)


class DeployTests(unittest.TestCase):
    def run_main(self, arguments, result=None, versions=None, send=None):
        m = load()
        out, err = io.StringIO(), io.StringIO()
        result = result or {"Status": "Success", "ResponseCode": 0, "StandardOutputContent": "Deployed"}
        with mock.patch.dict(os.environ, ENV), mock.patch.object(m, "preflight"), \
                mock.patch.object(m, "public_versions", return_value=versions or {"backend": "1.2.0", "frontend": "1.2.0"}), \
                mock.patch.object(m, "send", side_effect=send or (lambda t, c: COMMAND)) as sender, \
                mock.patch.object(m, "wait", return_value=result), \
                mock.patch.object(m, "verify_public") as verify, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = m.main(arguments)
        return code, out.getvalue(), err.getvalue(), sender, verify

    def test_selective_deploy_expects_untouched_component_to_stay(self):
        for components, expected in (("frontend", {"backend": "1.2.0", "frontend": "1.3.0"}),
                                     ("backend", {"backend": "1.3.0", "frontend": "1.2.0"}),
                                     ("both", {"backend": "1.3.0", "frontend": "1.3.0"})):
            code, out, _, sender, verify = self.run_main(["deploy", "1.3.0", "--components", components, "--commit", COMMIT])
            with self.subTest(components=components):
                self.assertEqual(code, 0)
                self.assertEqual(sender.call_count, 1)
                self.assertEqual(verify.call_args.args[1], expected)
                self.assertIn(COMMAND, out)

    def test_remote_failure_is_red_and_output_cannot_inject_workflow_commands(self):
        for result in ({"Status": "Failed", "ResponseCode": 1, "StandardErrorContent": "::set-output name=x::y\n\x1b[31mx"},
                       {"Status": "Success", "ResponseCode": 3}, {"Status": "TimedOut", "ResponseCode": -1}):
            code, out, err, _, verify = self.run_main(["deploy", "1.3.0", "--components", "both", "--commit", COMMIT], result)
            with self.subTest(result=result):
                self.assertEqual(code, 1)
                verify.assert_not_called()
                self.assertFalse(any(line.startswith("::") for line in out.splitlines()))
                self.assertNotIn("\x1b", out)

    def test_failed_preflight_never_sends(self):
        m = load()
        with mock.patch.dict(os.environ, ENV), mock.patch.object(m, "aws", side_effect=m.AwsError("sts", "ExpiredToken")), \
                mock.patch.object(m, "send") as sender, contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(m.main(["deploy", "1.3.0", "--components", "both", "--commit", COMMIT]), 1)
        sender.assert_not_called()
        self.assertIn("::error::", err.getvalue())

    def test_send_is_one_call_with_fixed_document_and_timeout(self):
        m = load()
        with mock.patch.object(m, "aws", return_value={"Command": {"CommandId": COMMAND}}) as fake:
            self.assertEqual(m.send(TARGET, ["true"]), COMMAND)
        self.assertEqual(fake.call_count, 1)
        arguments = fake.call_args.args
        self.assertIn("AWS-RunShellScript", arguments)
        self.assertEqual(json.loads(arguments[arguments.index("--parameters") + 1]),
                         {"commands": ["true"], "executionTimeout": ["900"]})
        with mock.patch.object(m, "aws", side_effect=m.AwsError("ssm", "Unavailable")) as fake:
            with self.assertRaises(m.DeployError):
                m.send(TARGET, ["true"])
            self.assertEqual(fake.call_count, 1)

    def test_settings_are_validated(self):
        m = load()
        for name, bad in (("AWS_REGION", "us-east-1 --x"), ("AWS_ACCOUNT_ID", ""), ("TICTACTEST_INSTANCE_ID", "i-xyz")):
            with self.subTest(name=name), mock.patch.dict(os.environ, dict(ENV, **{name: bad})):
                with self.assertRaises(m.DeployError):
                    m.load_target()
        for bad in ("file:///etc/passwd", "http://a/b", "http://u@h/", ""):
            with self.subTest(bad=bad), mock.patch.dict(os.environ, dict(ENV, TICTACTEST_FRONTEND_URL=bad)):
                with self.assertRaises(m.DeployError):
                    m.frontend_url()


class VerifyTests(unittest.TestCase):
    def verify(self, versions, body="consoleUrl: '/console/'", layout="split-v1"):
        m = load()
        clock = Clock()
        with mock.patch.object(m, "public_versions", return_value=versions), \
                mock.patch.object(m, "fetch_text", return_value=(body, {"X-TicTacTest-Layout": layout})):
            m.verify_public("http://h", {"backend": "1.2.0", "frontend": "1.3.0"}, sleep=clock.sleep, clock=clock)

    def test_exact_versions_and_infrastructure_config_are_required(self):
        good = {"backend": "1.2.0", "frontend": "1.3.0"}
        self.verify(good)
        for arguments in (({"backend": "1.3.0", "frontend": "1.3.0"},), (good, "localhost"),
                          (good, "'/console/'", None)):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(Exception, "public check failed"):
                self.verify(*arguments)

    def test_running_prints_outputs_and_rejects_bad_text(self):
        m = load()
        out = io.StringIO()
        with mock.patch.dict(os.environ, ENV), mock.patch.object(m, "fetch_text", return_value=("1.2.0", {})), \
                contextlib.redirect_stdout(out):
            self.assertEqual(m.main(["running"]), 0)
        self.assertEqual(out.getvalue(), "backend=1.2.0\nfrontend=1.2.0\n")
        for bad in ("<html>", "1.2.0\nx=y", "", "v1.2.0"):
            with self.subTest(bad=bad), mock.patch.object(m, "fetch_text", return_value=(bad, {})):
                with self.assertRaises(m.DeployError):
                    m.public_versions("http://h")


if __name__ == "__main__":
    unittest.main()
