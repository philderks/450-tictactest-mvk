#!/usr/bin/env python3
"""Produce a fail-closed, read-only deployment plan for a published release."""
import sys
# A read-only invocation must not create companion-module bytecode caches.
sys.dont_write_bytecode = True

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime


class PlanError(Exception):
    """A bounded, public-safe planning failure (never a raw API response)."""


def parse_version(tag):
    if not isinstance(tag, str) or not re.fullmatch(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", tag):
        raise PlanError("tag must be canonical vMAJOR.MINOR.PATCH")
    try:
        return tuple(int(part) for part in tag[1:].split("."))
    except ValueError:
        raise PlanError("tag version is out of range") from None


def load_releases(api, repo, max_pages=100):
    releases = []
    for page in range(1, max_pages + 1):
        try:
            data = api("repos/{}/releases?per_page=100&page={}".format(repo, page))
        except Exception:
            raise PlanError("GitHub release inventory GET failed") from None
        if not isinstance(data, list) or len(data) > 100 or any(not isinstance(item, dict) for item in data):
            raise PlanError("invalid GitHub release inventory")
        releases.extend(data)
        if len(data) < 100:
            return releases
    raise PlanError("release pagination limit reached; inventory incomplete")


def published_at(release):
    value = release.get("published_at")
    try:
        if not isinstance(value, str):
            raise ValueError()
        instant = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError()
        return instant
    except (ValueError, OverflowError):
        raise PlanError("published release has invalid timezone-aware published_at") from None


def validate_assets(release, tag):
    version = tag[1:]
    artifacts = ["tictactest-{}.jar".format(version),
                 "tictactest-frontend-{}.zip".format(version),
                 "tictactest-runtime-{}.zip".format(version)]
    expected = {name + suffix for name in artifacts for suffix in ("", ".sha256")}
    assets = release.get("assets")
    if not isinstance(assets, list) or any(not isinstance(a, dict) or not isinstance(a.get("name"), str) for a in assets):
        raise PlanError("unsupported release asset contract: six named artifacts required")
    names = [a["name"] for a in assets]
    if len(names) != 6 or set(names) != expected:
        raise PlanError("unsupported release asset contract: six named artifacts required")


def select_releases(releases, tag, mode="auto"):
    target_version = parse_version(tag)
    if mode not in ("auto", "manual"):
        raise PlanError("mode must be auto or manual")
    by_version, by_id = {}, {}
    for row in releases:
        if not isinstance(row, dict):
            raise PlanError("invalid GitHub release record")
        candidate = row.get("tag_name")
        try:
            version = parse_version(candidate)
        except PlanError:
            continue
        if not isinstance(row.get("draft"), bool) or not isinstance(row.get("prerelease"), bool):
            raise PlanError("incomplete GitHub release record")
        if row["draft"] or row["prerelease"]:
            continue
        ident = row.get("id")
        if type(ident) is not int or ident <= 0:
            raise PlanError("invalid published release ID")
        published_at(row)
        if (version in by_version and by_version[version] != row) or (ident in by_id and by_id[ident] != row):
            raise PlanError("ambiguous duplicate published release tag or ID")
        by_version[version] = row
        by_id[ident] = row
    target = by_version.get(target_version)
    if target is None:
        raise PlanError("target must be an actual published stable release")
    validate_assets(target, tag)
    if mode == "manual":
        return target, None
    lower = [version for version in by_version if version < target_version]
    previous = by_version[max(lower)] if lower else None
    if previous is not None and published_at(previous) >= published_at(target):
        raise PlanError("predecessor publication must be strictly earlier than target")
    return target, previous


def valid_sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise PlanError("invalid full 40-hex Git commit/object SHA")
    return value.lower()


def api_object(api, endpoint):
    try:
        data = api(endpoint)
    except Exception:
        raise PlanError("GitHub tag object GET failed") from None
    if not isinstance(data, dict):
        raise PlanError("invalid GitHub tag object response")
    return data


def remote_commit(api, repo, tag, max_hops=8):
    parse_version(tag)
    data = api_object(api, "repos/{}/git/ref/tags/{}".format(repo, tag))
    if data.get("ref") != "refs/tags/" + tag:
        raise PlanError("GitHub tag ref does not match requested tag")
    obj = data.get("object")
    seen = set()
    for _ in range(max_hops + 1):
        if not isinstance(obj, dict):
            raise PlanError("invalid GitHub tag object")
        sha = valid_sha(obj.get("sha"))
        if obj.get("type") == "commit":
            return sha
        if obj.get("type") != "tag":
            raise PlanError("GitHub tag does not resolve to a commit")
        if sha in seen or len(seen) >= max_hops:
            raise PlanError("annotated tag loop or depth limit")
        seen.add(sha)
        data = api_object(api, "repos/{}/git/tags/{}".format(repo, sha))
        if valid_sha(data.get("sha")) != sha:
            raise PlanError("GitHub annotated tag object SHA mismatch")
        obj = data.get("object")
    raise PlanError("annotated tag depth limit")


def parse_diff(raw):
    """Parse --name-status -z without treating tabs/newlines as separators."""
    if raw == b"":
        return []
    if not isinstance(raw, bytes) or not raw.endswith(b"\0"):
        raise PlanError("invalid NUL-delimited Git diff")
    try:
        fields = raw[:-1].decode("utf-8").split("\0")
    except UnicodeDecodeError:
        raise PlanError("Git diff paths must be UTF-8") from None
    changes, index = [], 0
    while index < len(fields):
        status = fields[index]
        index += 1
        rename = re.fullmatch(r"[RC]([0-9]{1,3})", status)
        if rename and int(rename.group(1)) <= 100:
            count = 2
        elif status in ("A", "D", "M", "T", "U", "X", "B"):
            count = 1
        else:
            raise PlanError("invalid Git diff status")
        paths = fields[index:index + count]
        if len(paths) != count or any(not path for path in paths):
            raise PlanError("incomplete Git diff paths")
        change = {"status": status, "path": paths[-1]}
        if count == 2:
            change["old_path"] = paths[0]
        changes.append(change)
        index += count
    return changes


class GitRead:
    """Only read Git; no fetch, checkout, build, hooks, or optional locks."""
    def __init__(self, checkout):
        self.checkout = Path(checkout)

    def run(self, *args, allow_failure=False):
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        # Deny all transports as well as lazy fetching, including on older Git.
        env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="")
        try:
            result = subprocess.run(["git", "--no-replace-objects", "-C", str(self.checkout)] + list(args),
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=30, env=env)
        except (OSError, subprocess.TimeoutExpired):
            raise PlanError("local Git read failed or timed out") from None
        if result.returncode != 0 and not allow_failure:
            raise PlanError("local Git read failed; required refs/history may be missing")
        return result

    def resolve(self, ref):
        raw = self.run("rev-parse", "--verify", ref).stdout
        try:
            return valid_sha(raw.decode("ascii").strip())
        except UnicodeDecodeError:
            raise PlanError("invalid local Git commit SHA") from None

    def ensure_ancestor(self, before, after):
        result = self.run("merge-base", "--is-ancestor", before, after, allow_failure=True)
        if result.returncode != 0:
            raise PlanError("required Git ancestry is absent, divergent, or incomplete")

    def diff(self, before, after):
        return parse_diff(self.run("diff", "--no-ext-diff", "--no-textconv", "--name-status", "-z",
                                   "--find-renames", before, after, "--").stdout)

    def blob(self, commit, path):
        # Only a successful pinned-tree lookup can prove genuine path absence.
        # A missing/corrupt object must never masquerade as an added/deleted file.
        tree = self.run("ls-tree", "-z", "--full-tree", valid_sha(commit), "--", path).stdout
        if not tree:
            return None
        entry = re.fullmatch(rb"[0-7]{6} blob ([0-9a-f]{40})\t" + re.escape(path.encode("utf-8")) + rb"\0", tree)
        if entry is None:
            raise PlanError("invalid required Git blob tree metadata")
        result = self.run("cat-file", "blob", entry.group(1).decode("ascii"))
        try:
            return result.stdout.decode("utf-8")
        except UnicodeDecodeError:
            raise PlanError("required Git blob must be UTF-8") from None


def validate_repo(repo):
    if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/[A-Za-z0-9_.-]+", repo):
        raise PlanError("repo must be an explicit OWNER/REPO identifier")
    if repo.split("/")[1] in (".", ".."):
        raise PlanError("repo must be an explicit OWNER/REPO identifier")


def trusted_tag(git, api, repo, tag, main):
    remote = remote_commit(api, repo, tag)
    local = git.resolve("refs/tags/{}^{{commit}}".format(tag))
    if local != remote:
        raise PlanError("remote/local release tag commit SHA mismatch")
    git.ensure_ancestor(local, main)
    return local


def plan_release(repo, tag, mode="auto", checkout=None, api=None):
    """Return one plan; api is an injectable callable accepting GET endpoints."""
    validate_repo(repo)
    parse_version(tag)
    if mode not in ("auto", "manual"):
        raise PlanError("mode must be auto or manual")
    if api is None:
        api = GitHubRead()
    target, previous = select_releases(load_releases(api, repo), tag, mode)
    git = GitRead(Path.cwd() if checkout is None else checkout)
    if git.run("rev-parse", "--is-shallow-repository").stdout.strip() != b"false":
        raise PlanError("complete local Git history is required; shallow checkout unsupported")
    main = git.resolve("refs/remotes/origin/main^{commit}")
    target_commit = trusted_tag(git, api, repo, tag, main)
    result = {"schema_version": 1, "repo": repo, "mode": mode,
              "tag": tag, "version": tag[1:], "target_commit": target_commit,
              "previous_tag": None, "previous_commit": None,
              "backend": True, "frontend": True, "components": "both",
              "changed_paths": [], "operational_paths": [], "metadata_paths": []}
    if mode == "manual" or previous is None:
        result["reason"] = ("manual: deploy both components" if mode == "manual" else
                            "first published stable release: deploy both components")
        return result
    previous_tag = previous["tag_name"]
    before = trusted_tag(git, api, repo, previous_tag, main)
    git.ensure_ancestor(before, target_commit)
    changes = git.diff(before, target_commit)
    # Inventory and tag verification stay usable without importing the classifier.
    from release_changes import classify_changes, version_only_change
    version_only = False
    if any(change["path"] == "build.gradle" or change.get("old_path") == "build.gradle" for change in changes):
        old_blob = git.blob(before, "build.gradle")
        new_blob = git.blob(target_commit, "build.gradle")
        if old_blob is not None and new_blob is not None:
            version_only = version_only_change(old_blob, new_blob, previous_tag[1:], tag[1:])
    result.update(classify_changes(changes, version_only_build=version_only))
    result.update(previous_tag=previous_tag, previous_commit=before,
                  reason="published predecessor comparison: " + result["components"])
    return result


class GitHubRead:
    """GitHub GET transport compatible with gh 2.4; never log API bodies."""
    def __call__(self, endpoint):
        env = os.environ.copy()
        env.pop("GH_DEBUG", None)
        env.pop("DEBUG", None)
        env.update(GH_PROMPT_DISABLED="1", GIT_TERMINAL_PROMPT="0", GH_PAGER="cat", PAGER="cat")
        try:
            result = subprocess.run(["gh", "api", "--hostname", "github.com", "--method", "GET", endpoint],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=30, env=env)
        except (OSError, subprocess.TimeoutExpired):
            raise PlanError("GitHub GET failed or timed out") from None
        if result.returncode != 0:
            raise PlanError("GitHub GET failed; check authentication, access, and connectivity")
        try:
            return json.loads(result.stdout)
        except (ValueError, UnicodeDecodeError):
            raise PlanError("GitHub GET returned invalid JSON") from None


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise PlanError("invalid command line; use --help")


def main(argv=None, api=None):
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("tag", help="published stable tag, exactly vMAJOR.MINOR.PATCH")
    parser.add_argument("--repo", required=True, help="explicit OWNER/REPO on github.com")
    parser.add_argument("--mode", choices=("auto", "manual"), default="auto")
    parser.add_argument("--checkout", default=None, help="local checkout (default: current directory)")
    try:
        args = parser.parse_args(argv)
        plan = plan_release(args.repo, args.tag, args.mode, args.checkout, api)
        output = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except PlanError as error:
        print("release plan error: " + str(error)[:240].replace("\n", " ").replace("\r", " "), file=sys.stderr)
        return 1
    except Exception:
        # Do not expose exceptions from transports, Git, or release metadata.
        print("release plan error: planning failed safely", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
