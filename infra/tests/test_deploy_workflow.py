"""Static guards for the deployment workflow's triggers and secret boundaries."""
from pathlib import Path
import re
import unittest

TEXT = (Path(__file__).resolve().parents[2] / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
PLAN, DEPLOY = TEXT.split("\n  deploy:\n")


class DeployWorkflowTests(unittest.TestCase):
    def test_only_release_completion_and_manual_runs_trigger(self):
        block = TEXT[TEXT.index("\non:\n"):TEXT.index("\npermissions:")]
        self.assertEqual(re.findall(r"^  ([a-z_]+):", block, re.M), ["workflow_run", "workflow_dispatch"])
        self.assertIn("workflows: [Release]", block)

    def test_plan_is_guarded_and_has_no_secrets(self):
        self.assertIn("github.ref == 'refs/heads/main'", PLAN)
        self.assertIn("workflow_run.conclusion == 'success'", PLAN)
        self.assertIn("head_repository.full_name == github.repository", PLAN)
        self.assertNotIn("secrets.", PLAN)
        self.assertIn("--expect-commit", PLAN)

    def test_secrets_only_in_environment_job_and_minimal_permissions(self):
        self.assertIn("environment: learner-lab", DEPLOY)
        self.assertEqual(set(re.findall(r"secrets\.(\w+)", TEXT)),
                         {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"})
        self.assertEqual(re.findall(r"permissions:\n((?:  .*\n)+)", TEXT), ["  contents: read\n"])

    def test_deployments_are_serialized_and_never_cancelled(self):
        self.assertIn("group: tictactest-learner-lab", DEPLOY)
        self.assertIn("cancel-in-progress: false", DEPLOY)
        self.assertIn("if: needs.plan.outputs.components != 'none'", DEPLOY)

    def test_no_expression_is_interpolated_into_shell_and_no_infrastructure_command(self):
        for script in re.findall(r"run: \|\n((?:          .*\n|\n)+)", TEXT) + re.findall(r"run: ([^|\n].*)", TEXT):
            self.assertNotIn("${{", script)
            self.assertNotRegex(script, r"tofu|terraform|gradlew|set -x|printenv")

    def test_tools_come_from_the_workflow_commit_not_from_the_release_tag(self):
        self.assertEqual(re.findall(r"ref: (.*)", TEXT), ["${{ github.sha }}"] * 2)
        self.assertIn('--commit "$GITHUB_SHA"', DEPLOY)


if __name__ == "__main__":
    unittest.main()
