"""Read-only release planner: synthetic API fixtures, real temporary Git."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "plan-release-deploy.py"
sys.path.insert(0, str(SCRIPT.parent))


def load_planner():
    if not SCRIPT.is_file():
        raise AssertionError("release planner does not exist yet")
    spec = importlib.util.spec_from_file_location("plan_release_deploy", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def release(tag, ident=1, published="2026-01-01T00:00:00Z", **updates) -> dict:
    version = tag[1:]
    names = ["tictactest-{}.jar".format(version),
             "tictactest-frontend-{}.zip".format(version),
             "tictactest-runtime-{}.zip".format(version)]
    data = dict(id=ident, tag_name=tag, draft=False, prerelease=False,
                published_at=published,
                assets=[{"name": name + suffix} for name in names for suffix in ("", ".sha256")])
    data.update(updates)
    return data


class FakeAPI:
    """Explicit synthetic GET fixtures; not a substitute for live API evidence."""
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, endpoint):
        self.calls.append(endpoint)
        if endpoint not in self.routes:
            raise AssertionError("unexpected GET " + endpoint)
        result = self.routes[endpoint]
        if isinstance(result, Exception):
            raise result
        return result


class InventoryTests(unittest.TestCase):
    def test_selects_highest_lower_published_stable_semver_independent_of_order(self):
        p = load_planner()
        target = release("v2.0.0", 20, "2026-03-01T00:00:00+00:00")
        previous = release("v1.10.0", 10)
        rows = [release("v1.11.0", 11, draft=True), previous,
                release("v1.12.0", 12, prerelease=True), target,
                release("v1.2.0", 2), release("nightly", 30),
                release("v01.20.0", 31), release("v3.0.0", 40)]
        for ordered in (rows, list(reversed(rows))):
            self.assertEqual(p.select_releases(ordered, "v2.0.0", "auto"), (target, previous))
        self.assertEqual(p.select_releases(rows, "v1.2.0", "manual"), (rows[4], None))
        self.assertEqual(p.select_releases([target], "v2.0.0", "auto"), (target, None))

    def test_rejects_unpublished_ambiguous_and_out_of_order_releases(self):
        p = load_planner()
        target = release("v1.2.0", 2, "2026-03-01T00:00:00Z")
        invalid = [
            [dict(target, draft=True)], [dict(target, prerelease=True)], [],
            [dict(target, published_at=None)], [dict(target, published_at="2026-03-01T00:00:00")],
            [dict(target, published_at="invalid")],
            [target, dict(target, id=3)],
            [target, release("v1.1.0", 2)],
            [target, release("v1.1.0", 1, "2026-03-02T00:00:00Z")],
            [target, release("v1.1.0", 1, "2026-03-01T00:00:00Z")],
        ]
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(p.PlanError):
                p.select_releases(rows, "v1.2.0", "auto")
        self.assertEqual(p.select_releases([target, dict(target)], "v1.2.0", "auto"), (target, None))

    def test_target_requires_six_exact_assets_including_historical_contract(self):
        p = load_planner()
        target = release("v1.0.1")
        for assets in ([], target["assets"][:2], target["assets"][:-1],
                       target["assets"] + [target["assets"][0]],
                       [{"name": "almost-" + a["name"]} for a in target["assets"]]):
            with self.subTest(assets=assets), self.assertRaisesRegex(p.PlanError, "unsupported.*contract"):
                p.select_releases([dict(target, assets=assets)], "v1.0.1", "manual")

    def test_inventory_reads_all_pages_and_refuses_truncation(self):
        p = load_planner()
        page = [release("v0.0.{}".format(i), i + 1) for i in range(100)]
        api = FakeAPI({"repos/o/r/releases?per_page=100&page=1": page,
                       "repos/o/r/releases?per_page=100&page=2": [release("v1.2.0", 200)]})
        self.assertEqual(len(p.load_releases(api, "o/r")), 101)
        self.assertEqual(len(api.calls), 2)
        with self.assertRaisesRegex(p.PlanError, "pagination"):
            p.load_releases(api, "o/r", max_pages=1)
        for response in ({"message": "PRIVATE"}, None, ["bad"]):
            with self.subTest(response=response), self.assertRaises(p.PlanError):
                p.load_releases(FakeAPI({"repos/o/r/releases?per_page=100&page=1": response}), "o/r")


class GitFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="release-planner-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Release Test")
        self.git("config", "user.email", "release-test@example.invalid")
        self.write("build.gradle", b"version = '1.0.0'\r\n")
        self.write("src/main/java/App.java", b"old\n")
        self.write("frontend/delete me.txt", b"delete\n")
        self.write("frontend/old name.txt", b"unchanged content for rename\n")
        self.base = self.commit("base")
        self.git("tag", "v1.0.0")
        self.write("build.gradle", b"version = '1.1.0'\r\n")
        self.target = self.commit("target")
        self.git("tag", "-a", "v1.1.0", "-m", "annotated target")
        self.git("update-ref", "refs/remotes/origin/main", self.target)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root)] + list(args),
                              check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    def write(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit(self, message):
        self.git("add", "--all")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD").decode().strip()

    def api(self, rows=None):
        if rows is None:
            rows = [release("v1.1.0", 2, "2026-02-01T00:00:00Z"), release("v1.0.0", 1)]
        annotation = self.git("rev-parse", "refs/tags/v1.1.0").decode().strip()
        return FakeAPI({
            "repos/o/r/releases?per_page=100&page=1": rows,
            "repos/o/r/git/ref/tags/v1.0.0": {"ref": "refs/tags/v1.0.0", "object": {"type": "commit", "sha": self.base}},
            "repos/o/r/git/ref/tags/v1.1.0": {"ref": "refs/tags/v1.1.0", "object": {"type": "tag", "sha": annotation}},
            "repos/o/r/git/tags/" + annotation: {"sha": annotation, "object": {"type": "commit", "sha": self.target}},
        })


class GitReadTests(GitFixture):
    def test_partial_clone_missing_blob_must_not_trigger_an_implicit_fetch(self):
        p = load_planner()
        remote = self.root / "fixture-remote.git"
        self.git("clone", "--bare", str(self.root), str(remote))
        self.git("config", "remote.origin.url", remote.as_uri())
        self.git("config", "remote.origin.promisor", "true")
        self.git("config", "core.repositoryformatversion", "1")
        self.git("config", "extensions.partialClone", "origin")
        blob = self.git("rev-parse", self.base + ":build.gradle").decode().strip()
        object_path = self.root / ".git/objects" / blob[:2] / blob[2:]
        object_path.unlink()
        object_dir = self.root / ".git/objects"
        before = {str(path.relative_to(object_dir)): path.read_bytes()
                  for path in object_dir.rglob("*") if path.is_file()}
        with self.assertRaisesRegex(p.PlanError, "Git.*read|history"):
            p.GitRead(self.root).blob(self.base, "build.gradle")
        after = {str(path.relative_to(object_dir)): path.read_bytes()
                 for path in object_dir.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_git_transport_is_disabled_even_with_inherited_git_overrides(self):
        p = load_planner()
        with mock.patch.object(p.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"", b"")) as run:
            with mock.patch.dict(os.environ, {"GIT_DIR": "/not-the-checkout", "GIT_CONFIG_COUNT": "1", "GIT_ALLOW_PROTOCOL": "ssh:file"}):
                p.GitRead(self.root).run("rev-parse", "--is-shallow-repository")
        env = run.call_args.kwargs["env"]
        self.assertEqual(env.get("GIT_ALLOW_PROTOCOL"), "")
        self.assertNotIn("GIT_DIR", env)
        self.assertNotIn("GIT_CONFIG_COUNT", env)
        self.assertEqual(env["GIT_OPTIONAL_LOCKS"], "0")

    def test_reads_pinned_commits_blobs_and_ancestry(self):
        p = load_planner()
        git = p.GitRead(self.root)
        self.assertEqual(git.resolve("refs/tags/v1.1.0^{commit}"), self.target)
        self.assertEqual(git.blob(self.base, "build.gradle"), "version = '1.0.0'\r\n")
        self.assertIsNone(git.blob(self.base, "missing.gradle"))
        git.ensure_ancestor(self.base, self.target)
        with self.assertRaises(p.PlanError):
            git.ensure_ancestor(self.target, self.base)
        with self.assertRaises(p.PlanError):
            git.resolve("refs/remotes/missing/main^{commit}")

    def test_real_diff_preserves_nul_delimited_rename_deletion_and_weird_names(self):
        p = load_planner()
        weird = "frontend/ü\nwith\ttabs and spaces.txt"
        (self.root / "frontend/old name.txt").rename(self.root / weird)
        (self.root / "frontend/delete me.txt").unlink()
        end = self.commit("paths")
        changes = p.GitRead(self.root).diff(self.base, end)
        self.assertIn({"status": "R100", "old_path": "frontend/old name.txt", "path": weird}, changes)
        self.assertIn({"status": "D", "path": "frontend/delete me.txt"}, changes)
        self.assertIn({"status": "M", "path": "build.gradle"}, changes)
        self.assertEqual(p.parse_diff(b"C100\0old\0new\0"), [{"status": "C100", "old_path": "old", "path": "new"}])
        for raw in (b"M\0path", b"R100\0old\0", b"M\0\0", b"Q\0file\0", b"R101\0a\0b\0", b"M\0\xff\0", b"\0"):
            with self.subTest(raw=raw), self.assertRaises(p.PlanError):
                p.parse_diff(raw)

    def test_remote_peels_annotated_and_lightweight_tags_and_checks_loops(self):
        p = load_planner()
        api = self.api()
        self.assertEqual(p.remote_commit(api, "o/r", "v1.0.0"), self.base)
        self.assertEqual(p.remote_commit(api, "o/r", "v1.1.0"), self.target)
        endpoint = "repos/o/r/git/ref/tags/v1.1.0"
        annotation = api.routes[endpoint]["object"]["sha"]
        api.routes["repos/o/r/git/tags/" + annotation]["object"] = {"type": "tag", "sha": annotation}
        with self.assertRaisesRegex(p.PlanError, "loop|depth"):
            p.remote_commit(api, "o/r", "v1.1.0")
        for obj in ({"type": "commit", "sha": "abc"}, {"type": "tree", "sha": self.base}):
            api.routes[endpoint]["object"] = obj
            with self.subTest(obj=obj), self.assertRaises(p.PlanError):
                p.remote_commit(api, "o/r", "v1.1.0")


class PlanTests(GitFixture):
    def retarget(self):
        self.target = self.commit("replacement target")
        self.git("tag", "-d", "v1.1.0")
        self.git("tag", "-a", "v1.1.0", "-m", "target", self.target)
        self.git("update-ref", "refs/remotes/origin/main", self.target)

    def test_auto_classifies_all_four_decisions_with_real_commit_diffs(self):
        p = load_planner()
        for extra, expected in (({}, "none"), ({"frontend/index.html": b"web"}, "frontend"),
                                ({"src/main/java/App.java": b"new"}, "backend"),
                                ({"frontend/index.html": b"web", "src/main/java/App.java": b"new"}, "both")):
            with self.subTest(expected=expected):
                self.git("reset", "--hard", self.base)
                self.write("build.gradle", b"version = '1.1.0'\r\n")
                self.write("README.md", b"metadata")
                for path, data in extra.items():
                    self.write(path, data)
                self.retarget()
                result = p.plan_release("o/r", "v1.1.0", checkout=self.root, api=self.api())
                self.assertEqual(result["components"], expected)
                self.assertEqual(result["previous_tag"], "v1.0.0")
                self.assertEqual(result["previous_commit"], self.base)
                self.assertEqual(result["changed_paths"], sorted(["README.md", "build.gradle"] + list(extra)))
                self.assertIn("build.gradle", result["metadata_paths"])
                self.assertIn("README.md", result["metadata_paths"])

    def test_plugin_edit_cannot_qualify_as_version_only(self):
        p = load_planner()
        self.write("build.gradle", b"plugins { id 'new.plugin' }\r\nversion = '1.1.0'\r\n")
        self.retarget()
        self.assertEqual(p.plan_release("o/r", "v1.1.0", checkout=self.root, api=self.api())["components"], "backend")

    def test_genuinely_deleted_build_gradle_is_a_backend_change(self):
        p = load_planner()
        (self.root / "build.gradle").unlink()
        self.retarget()
        result = p.plan_release("o/r", "v1.1.0", checkout=self.root, api=self.api())
        self.assertEqual(result["components"], "backend")
        self.assertEqual(result["changed_paths"], ["build.gradle"])
        self.assertNotIn("build.gradle", result["metadata_paths"])
        self.assertIsNone(p.GitRead(self.root).blob(self.target, "build.gradle"))

    def test_genuinely_added_build_gradle_is_a_backend_change(self):
        p = load_planner()
        (self.root / "build.gradle").unlink()
        self.base = self.commit("baseline without build.gradle")
        self.git("tag", "-f", "v1.0.0", self.base)
        self.write("build.gradle", b"version = '1.1.0'\r\n")
        self.retarget()
        result = p.plan_release("o/r", "v1.1.0", checkout=self.root, api=self.api())
        self.assertEqual(result["components"], "backend")
        self.assertEqual(result["changed_paths"], ["build.gradle"])
        self.assertNotIn("build.gradle", result["metadata_paths"])
        self.assertIsNone(p.GitRead(self.root).blob(self.base, "build.gradle"))

    def test_shallow_history_and_missing_local_baseline_fail_closed(self):
        p = load_planner()
        self.git("tag", "-d", "v1.0.0")
        with self.assertRaises(p.PlanError):
            p.plan_release("o/r", "v1.1.0", checkout=self.root, api=self.api())
        self.git("tag", "v1.0.0", self.base)
        (self.root / ".git/shallow").write_text(self.base + "\n")
        with self.assertRaisesRegex(p.PlanError, "shallow"):
            p.plan_release("o/r", "v1.1.0", checkout=self.root, api=self.api())

    def test_unpublished_raw_git_tags_never_become_predecessors(self):
        p = load_planner()
        self.git("tag", "v1.0.99", self.base)
        result = p.plan_release("o/r", "v1.1.0", checkout=self.root, api=self.api())
        self.assertEqual(result["previous_tag"], "v1.0.0")

    def test_line_ending_change_is_not_a_version_only_exemption(self):
        p = load_planner()
        self.write("build.gradle", b"version = '1.1.0'\n")
        self.retarget()
        result = p.plan_release("o/r", "v1.1.0", checkout=self.root, api=self.api())
        self.assertEqual(result["components"], "backend")
        self.assertNotIn("build.gradle", result["metadata_paths"])

    def test_auto_reports_metadata_and_operational_changes_without_deploying(self):
        p = load_planner()
        self.write("infra/main.tf", b"# operational change\n")
        self.write("docs/release.md", b"documentation\n")
        self.retarget()
        result = p.plan_release("o/r", "v1.1.0", checkout=self.root, api=self.api())
        self.assertEqual(result["components"], "none")
        self.assertEqual(result["operational_paths"], ["infra/main.tf"])
        self.assertEqual(result["metadata_paths"], ["build.gradle", "docs/release.md"])

    def test_baseline_remote_mismatch_or_divergence_fails_closed(self):
        p = load_planner()
        api = self.api()
        api.routes["repos/o/r/git/ref/tags/v1.0.0"]["object"]["sha"] = self.target
        with self.assertRaisesRegex(p.PlanError, "mismatch"):
            p.plan_release("o/r", "v1.1.0", checkout=self.root, api=api)
        self.git("checkout", "--detach", self.base)
        self.write("branch-only", b"divergent")
        other = self.commit("divergent baseline")
        self.git("tag", "-f", "v1.0.0", other)
        api = self.api()
        api.routes["repos/o/r/git/ref/tags/v1.0.0"]["object"]["sha"] = other
        with self.assertRaisesRegex(p.PlanError, "ancestry"):
            p.plan_release("o/r", "v1.1.0", checkout=self.root, api=api)

    def test_first_release_validates_remote_tag_and_deploys_both_without_comparison(self):
        p = load_planner()
        api = self.api([release("v1.1.0", 2)])
        result = p.plan_release("o/r", "v1.1.0", checkout=self.root, api=api)
        self.assertEqual(result, {
            "schema_version": 1, "repo": "o/r", "mode": "auto", "tag": "v1.1.0", "version": "1.1.0",
            "target_commit": self.target, "previous_tag": None, "previous_commit": None,
            "backend": True, "frontend": True, "components": "both", "changed_paths": [],
            "operational_paths": [], "metadata_paths": [], "reason": "first published stable release: deploy both components"})
        self.assertNotIn("repos/o/r/git/ref/tags/v1.0.0", api.calls)

    def test_manual_older_published_release_skips_predecessor_and_deploys_both(self):
        p = load_planner()
        api = self.api()
        result = p.plan_release("o/r", "v1.0.0", "manual", self.root, api)
        self.assertEqual(result["target_commit"], self.base)
        self.assertEqual(result["components"], "both")
        self.assertEqual(result["changed_paths"], [])
        self.assertIsNone(result["previous_tag"])
        self.assertIsNone(result["previous_commit"])
        self.assertNotIn("repos/o/r/git/ref/tags/v1.1.0", api.calls)

    def test_rejects_bad_identifiers_before_get_or_git(self):
        p = load_planner()
        for repo, tag in (("https://github.com/o/r", "v1.1.0"), ("o/r/extra", "v1.1.0"),
                          ("o/r\n", "v1.1.0"), ("o/..", "v1.1.0"), ("o/r", "v01.1.0")):
            api = FakeAPI({})
            with self.subTest(repo=repo, tag=tag), self.assertRaises(p.PlanError):
                p.plan_release(repo, tag, checkout=self.root, api=api)
            self.assertEqual(api.calls, [])

    def test_remote_sha_missing_main_and_untrusted_history_fail_closed(self):
        p = load_planner()
        api = self.api([release("v1.1.0", 2)])
        endpoint = "repos/o/r/git/ref/tags/v1.1.0"
        api.routes[endpoint]["object"] = {"type": "commit", "sha": self.base}
        with self.assertRaisesRegex(p.PlanError, "mismatch"):
            p.plan_release("o/r", "v1.1.0", checkout=self.root, api=api)
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        with self.assertRaisesRegex(p.PlanError, "ancestry"):
            p.plan_release("o/r", "v1.1.0", checkout=self.root, api=self.api())
        self.git("update-ref", "-d", "refs/remotes/origin/main")
        with self.assertRaises(p.PlanError):
            p.plan_release("o/r", "v1.1.0", checkout=self.root, api=self.api())


class TransportTests(unittest.TestCase):
    def test_gh_transport_uses_explicit_get_timeout_and_no_debug_or_prompts(self):
        p = load_planner()
        endpoint = "repos/o/r/releases?per_page=100&page=1"
        result = subprocess.CompletedProcess([], 0, stdout=b'[{"id": 9}]', stderr=b"PRIVATE")
        with mock.patch.object(p.subprocess, "run", return_value=result) as run, mock.patch.dict(os.environ, {"GH_DEBUG": "api", "DEBUG": "api"}):
            self.assertEqual(p.GitHubRead()(endpoint), [{"id": 9}])
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["gh", "api", "--hostname", "github.com", "--method", "GET", endpoint])
        self.assertGreater(kwargs["timeout"], 0)
        self.assertLessEqual(kwargs["timeout"], 60)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn("GH_DEBUG", kwargs["env"])
        self.assertNotIn("DEBUG", kwargs["env"])
        self.assertEqual(kwargs["env"]["GH_PROMPT_DISABLED"], "1")
        self.assertFalse(kwargs.get("shell", False))

    def test_gh_failures_do_not_expose_response_bodies(self):
        p = load_planner()
        cases = [subprocess.CompletedProcess([], 1, b"PRIVATE BODY", b"PRIVATE TOKEN"),
                 subprocess.CompletedProcess([], 0, b"PRIVATE INVALID JSON", b""),
                 subprocess.TimeoutExpired("gh", 30, output=b"PRIVATE"), OSError("PRIVATE OS ERROR")]
        for result in cases:
            with self.subTest(result=type(result).__name__):
                side_effect = result if isinstance(result, Exception) else None
                with mock.patch.object(p.subprocess, "run", side_effect=side_effect, return_value=result), self.assertRaises(p.PlanError) as error:
                    p.GitHubRead()("repos/o/r/releases?per_page=100&page=1")
                self.assertNotIn("PRIVATE", str(error.exception))
                self.assertLess(len(str(error.exception)), 250)


class CLITests(GitFixture):
    def test_missing_required_blob_fails_before_emitting_json(self):
        p = load_planner()
        api = self.api()
        # Corrupt only the independently initialized, owned temporary fixture.
        blob = self.git("rev-parse", self.base + ":build.gradle").decode().strip()
        (self.root / ".git/objects" / blob[:2] / blob[2:]).unlink()
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = p.main(["v1.1.0", "--repo", "o/r", "--checkout", str(self.root)], api=api)
        self.assertNotEqual(code, 0, "missing required blob must not yield a backend JSON plan: " + stdout.getvalue())
        self.assertEqual(stdout.getvalue(), "")
        self.assertRegex(stderr.getvalue(), "release plan error: .*Git.*read|history")
        self.assertEqual(len(stderr.getvalue().splitlines()), 1)
        self.assertLessEqual(len(stderr.getvalue()), 300)

    def test_invalid_utf8_required_blob_fails_before_emitting_json(self):
        p = load_planner()
        self.write("build.gradle", b"version = '1.1.0'\r\n// PRIVATE malformed \xff\n")
        self.target = self.commit("invalid UTF-8 build metadata")
        self.git("tag", "-d", "v1.1.0")
        self.git("tag", "-a", "v1.1.0", "-m", "target", self.target)
        self.git("update-ref", "refs/remotes/origin/main", self.target)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = p.main(["v1.1.0", "--repo", "o/r", "--checkout", str(self.root)], api=self.api())
        self.assertNotEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("required Git blob must be UTF-8", stderr.getvalue())
        self.assertNotIn("PRIVATE", stderr.getvalue())
        self.assertEqual(len(stderr.getvalue().splitlines()), 1)
        self.assertLessEqual(len(stderr.getvalue()), 300)

    def test_help_describes_canonical_tag_and_has_no_mutable_main_override(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--help"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=False, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"vMAJOR.MINOR.PATCH", result.stdout)
        self.assertNotIn(b"--main", result.stdout)
        self.assertEqual(result.stderr, b"")

    def test_cli_prints_one_deterministic_json_line_and_leaves_git_state_unchanged(self):
        p = load_planner()
        self.write("untracked local note", b"do not touch")
        self.write("src/main/java/App.java", b"local dirty worktree")
        def snapshot():
            paths = [path for path in self.root.rglob("*") if path.is_file()]
            return {str(path.relative_to(self.root)): path.read_bytes() for path in paths}
        before = snapshot()
        outputs = []
        for _ in range(2):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = p.main(["v1.1.0", "--repo", "o/r", "--checkout", str(self.root)], api=self.api())
            self.assertEqual(code, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(len(stdout.getvalue().splitlines()), 1)
            self.assertEqual(json.loads(stdout.getvalue())["target_commit"], self.target)
            outputs.append(stdout.getvalue())
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(before, snapshot())

    def test_cli_escapes_weird_rename_paths_without_losing_old_or_deleted_paths(self):
        p = load_planner()
        new_path = "src/main/java/ü\nwith\ttab and space.java"
        (self.root / "frontend/old name.txt").rename(self.root / new_path)
        (self.root / "frontend/delete me.txt").unlink()
        self.target = self.commit("cross-component rename")
        self.git("tag", "-d", "v1.1.0")
        self.git("tag", "-a", "v1.1.0", "-m", "target", self.target)
        self.git("update-ref", "refs/remotes/origin/main", self.target)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = p.main(["v1.1.0", "--repo", "o/r", "--checkout", str(self.root)], api=self.api())
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)
        plan = json.loads(stdout.getvalue())
        self.assertEqual(plan["components"], "both")
        self.assertEqual(plan["changed_paths"], sorted(["build.gradle", "frontend/delete me.txt", "frontend/old name.txt", new_path]))

    def test_cli_failures_have_bounded_private_errors_and_no_partial_json(self):
        p = load_planner()
        api = FakeAPI({"repos/o/r/releases?per_page=100&page=1": RuntimeError("PRIVATE TOKEN " * 1000)})
        for args in (["v1.1.0", "--repo", "o/r"], ["v1.1.0", "--repo", "o/r", "--main-ref", "HEAD"],
                     ["v01.1.0", "--repo", "o/r"], ["v1.1.0", "--repo", "https://github.com/o/r"],
                     ["v1.1.0", "--repo", "o/r", "--mode", "nope"]):
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(args=args), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = p.main(args, api=api)
            self.assertNotEqual(code, 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertNotIn("PRIVATE", stderr.getvalue())
            self.assertLessEqual(len(stderr.getvalue()), 300)
            self.assertEqual(len(stderr.getvalue().splitlines()), 1)


class RunningBaseTests(GitFixture):
    """A selective plan is only safe when the host really runs the assumed base."""
    def three_releases(self, middle, last):
        rows = [release("v1.0.0", 1), release("v1.1.0", 2, "2026-02-01T00:00:00Z"),
                release("v1.2.0", 3, "2026-03-01T00:00:00Z")]
        self.git("reset", "-q", "--hard", self.base)
        commits = []
        for version, files in (("1.1.0", middle), ("1.2.0", last)):
            self.write("build.gradle", "version = '{}'\r\n".format(version).encode())
            for path, data in files.items():
                self.write(path, data)
            commits.append(self.commit(version))
        self.target = commits[0]
        self.git("tag", "-d", "v1.1.0")
        self.git("tag", "-a", "v1.1.0", "-m", "middle", commits[0])
        self.git("tag", "-f", "v1.2.0", commits[1])
        self.git("update-ref", "refs/remotes/origin/main", commits[1])
        api = self.api(rows)
        api.routes["repos/o/r/git/ref/tags/v1.2.0"] = {
            "ref": "refs/tags/v1.2.0", "object": {"type": "commit", "sha": commits[1]}}
        return api, commits[1]

    def plan(self, p, api, backend, frontend, tag="v1.2.0", **options):
        return p.plan_release("o/r", tag, checkout=self.root, api=api,
                              running={"backend": backend, "frontend": frontend}, **options)

    def test_mixed_versions_are_fine_when_unselected_component_is_unchanged(self):
        p = load_planner()
        api, _ = self.three_releases({"src/main/java/App.java": b"1.1"}, {"frontend/index.html": b"1.2"})
        result = self.plan(p, api, "1.1.0", "1.0.0")
        self.assertEqual(result["components"], "frontend")
        self.assertEqual(result["running"], {"backend": "1.1.0", "frontend": "1.0.0"})
        api, _ = self.three_releases({"frontend/index.html": b"1.1"}, {"frontend/index.html": b"1.2"})
        self.assertEqual(self.plan(p, api, "1.0.0", "1.1.0")["components"], "frontend")

    def test_missed_release_of_an_unselected_component_fails(self):
        p = load_planner()
        api, _ = self.three_releases({"src/main/java/App.java": b"1.1"}, {"frontend/index.html": b"1.2"})
        with self.assertRaisesRegex(p.PlanError, "backend.*1.0.0.*manual"):
            self.plan(p, api, "1.0.0", "1.0.0")

    def test_automatic_downgrade_is_refused_for_every_component(self):
        p = load_planner()
        api, _ = self.three_releases({"src/main/java/App.java": b"1.1"}, {"frontend/index.html": b"1.2"})
        for backend, frontend in (("1.2.0", "1.0.0"), ("1.0.0", "1.2.0")):
            with self.subTest(backend=backend), self.assertRaisesRegex(p.PlanError, "newer"):
                self.plan(p, api, backend, frontend, tag="v1.1.0")

    def test_unpublished_or_malformed_running_versions_fail(self):
        p = load_planner()
        api, _ = self.three_releases({}, {"frontend/index.html": b"1.2"})
        for backend in ("0.9.0", "v1.0.0", "1.0", "", "1.0.0\n", None):
            with self.subTest(backend=backend), self.assertRaises(p.PlanError):
                self.plan(p, api, backend, "1.0.0")

    def test_running_base_is_only_meaningful_for_automatic_plans(self):
        p = load_planner()
        api, _ = self.three_releases({}, {})
        with self.assertRaises(p.PlanError):
            self.plan(p, api, "1.0.0", "1.0.0", mode="manual")

    def test_expected_commit_must_match_the_release_tag(self):
        p = load_planner()
        api, commit = self.three_releases({}, {"frontend/index.html": b"1.2"})
        plan = p.plan_release("o/r", "v1.2.0", checkout=self.root, api=api, expected_commit=commit)
        self.assertEqual(plan["target_commit"], commit)
        for wrong in (self.base, "main", ""):
            with self.subTest(wrong=wrong), self.assertRaises(p.PlanError):
                p.plan_release("o/r", "v1.2.0", checkout=self.root, api=api, expected_commit=wrong)

    def test_cli_needs_both_running_versions(self):
        p = load_planner()
        api, commit = self.three_releases({}, {"frontend/index.html": b"1.2"})
        base = ["v1.2.0", "--repo", "o/r", "--checkout", str(self.root)]
        for extra, code in ((["--running-backend", "1.1.0"], 1), (["--running-frontend", "1.1.0"], 1),
                            (["--running-backend", "1.1.0", "--running-frontend", "1.1.0",
                              "--expect-commit", commit], 0)):
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(extra=extra), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(p.main(base + extra, api=api), code)


class VersionTests(unittest.TestCase):
    def test_canonical_versions_are_compared_numerically(self):
        p = load_planner()
        self.assertGreater(p.parse_version("v1.10.0"), p.parse_version("v1.2.0"))
        for value in ("1.2.0", "v01.2.0", "v1.2", "v1.2.3-rc1", "v1.2.3+meta", "v1.2.3\n", "V1.2.3", " v1.2.3"):
            with self.subTest(value=value), self.assertRaises(p.PlanError):
                p.parse_version(value)


if __name__ == "__main__":
    unittest.main()
