# Published-release deployment planner implementation plan

> **For Hermes:** Use subagent-driven-development to implement each vertical TDD slice, then independent spec and quality/integration reviews.

**Goal:** Produce a deterministic read-only JSON component-deployment plan for an existing published stable release.

**Architecture:** A pure Python3.9 change classifier and a trusted-checkout CLI read GitHub release/tag metadata plus local Git objects. They never check out or execute target-tag files, download/build/deploy application assets, fetch refs, access AWS, write Actions outputs, or mutate live state. Automatic comparison uses the highest lower published stable SemVer; manual selection always chooses both after target validation.

**Tech stack:** Python3.9 stdlib, installed Git, authenticated `gh api --hostname github.com` (read requests only), unittest; existing CI discovers scripts/tests automatically.

## Scope / preflight
- Start from clean refreshed `origin/dev` b7de0c5bdae99be4f141c5c87da5602636be7588 on `feat/auftrag-3-release-planner`; no open PRs at preflight.
- Preserve ignored infrastructure state (baseline SHA256287ba171136702f74268bbc6f6dcae9dd4a7be7d285d165b3542a84106c864a8), tfvars, keys, credentials and all tags.
- No workflow activation/edit, GitHub settings/secrets writes, AWS/SSM, live migration, main promotion or release. Completed reviewed feature may follow the authorized PR->dev lifecycle only.

## Shared interface (two disjoint implementation owners)
Create `scripts/release_changes.py` and `scripts/tests/test_release_changes.py` (classifier owner A).
Create `scripts/plan-release-deploy.py` and `scripts/tests/test_plan_release_deploy.py` (orchestrator owner B).
Parent owns this plan, docs/deployment.md checkpoint, real-read smoke and Git/PR closure.

```python
# release_changes.py; pure, no network/Git/filesystem mutation
version_only_change(before: str, after: str, previous_version: str, target_version: str) -> bool
classify_changes(changes: list, version_only_build: bool = False) -> dict
# changes contain {"status":"M","path":"frontend/app.js"}, or
# {"status":"R100","old_path":"frontend/old.js","path":"src/main/new.java"}.
# Return {"backend":bool,"frontend":bool,"components":"backend|frontend|both|none",
#         "changed_paths":[str,...],"operational_paths":[str,...],"metadata_paths":[str,...]}.
# sorted unique path lists; old/new rename and copy paths both count; unknown raises ValueError.
```

CLI: `python3 scripts/plan-release-deploy.py v1.2.0 --repo philderks/450-tictactest-mvk --mode auto`.
`--mode manual` deliberately selects both (including older supported published targets).
Checkout defaults to current directory; optional `--checkout PATH` only changes where read-only Git runs. Trusted main ref is fixed `refs/remotes/origin/main` (tests can construct it); checkout must already have full required history/tags. CLI errors are bounded plain stderr, nonzero, no partial stdout JSON. Success prints exactly one JSON object containing `schema_version:1`, repo, mode, tag, version, target_commit, previous_tag/previous_commit (null for first/manual), backend/frontend booleans, components, changed_paths, operational_paths, metadata_paths, and a concise reason. Never emit credentials or API bodies.

### Task1: Exact project-version-only exception (A)
RED with a pure version bump, then GREEN. Compare full before/after build text with exactly one strict standalone project `version = 'MAJOR.MINOR.PATCH'` or double-quoted assignment each, matching previous/target versions. The rest of the text must be byte-identical after replacing only the version value. No ignoring every line containing `version`; dependency/plugin updates, duplicate/missing/changed-format assignments or any extra byte changes must return false. Tests include whitespace/comments/unrelated content, malformed/ambiguous assignments and version mismatch.

### Task2: Pure path decisions (A)
One RED/GREEN case at a time: backend-only, frontend-only, both, neither; additions/deletions/type changes/renames/copies; both rename sides, newlines/spaces/Unicode as data. Reject malformed status/path/traversal/absolute/backslash ambiguity and unknown paths instead of silently choosing none.
- backend: src/main/**, scripts/{start-console.sh,backend-version.py,serve-backend-version.py,runtime-README.md}, build.gradle except exact version-only change, settings.gradle, gradle.properties, gradlew[.bat], gradle/**, .devcontainer/** (conservative toolchain).
- frontend: frontend/**.
- both: scripts/package-web-release.py, .github/workflows/release.yml.
- metadata/no deploy: docs/**, README.md, CHANGELOG.md, RELEASE.md, LICENSE[.md], .gitignore, .gitattributes, .editorconfig, .github/ISSUE_TEMPLATE/**, .github/PULL_REQUEST_TEMPLATE/**, .github/pull_request_template.md, .github/dependabot.yml.
- test-only/no deploy: src/test/**, src/e2eTest/**, scripts/tests/**, infra/tests/**, .github/scripts/**, exact .github/workflows/{ci.yml,coverage-gate.yml,devcontainer.yml}.
- operational/no app deploy: remaining infra/**, scripts/plan-release-deploy.py, scripts/release_changes.py, exact .github/workflows/deploy.yml. Surface operational_paths so a later workflow/operator cannot mistake them for migrated guest config.

### Task3: Published release inventory and trust (B)
RED/GREEN independently with injected read API and real temporary Git histories, not production API substitutes presented as real observations. Strict canonical vMAJOR.MINOR.PATCH, strict repo owner/name, no normalization. Enumerate releases with explicit per_page100/page=N until short/empty page; finite limit fails explicitly instead of truncation. Filter drafts/prereleases and unrelated noncanonical tag families; validate selected target exists once as a published stable release with a real publication timestamp and the exact six expected release asset names. Reject ambiguous duplicate tags/semvers, malformed required metadata, API failures and incomplete histories. Old genuine releases before frontend packaging cannot meet today's six-asset contract: fail clearly, don't fabricate missing assets.
Resolve lightweight/annotated tag commits through GitHub git/ref/tags and bounded git/tags object peeling; compare selected remote tag commit with local `rev-parse refs/tags/TAG^{commit}`, and require target main ancestry. No mutable `target_commitish=main` shortcuts. Prior release is highest lower eligible SemVer, independent of API ordering and nearest raw Git tag; verify remote/local predecessor commit, predecessor->target ancestry and strictly earlier publication time. Divergent/out-of-order/ambiguous baselines fail. First release with no predecessor selects both. Manual target validates the same published tag/assets/commit/main contract, then both without computing a predecessor.

### Task4: Real Git diff and JSON CLI (B)
RED/GREEN using actual owned temporary repositories: `git diff --no-ext-diff --no-textconv --name-status -z --find-renames OLD NEW --`; parse NUL fields rather than lines, capture copies/renames with both paths; safe argv (no shell). Read only the two build.gradle blobs using pinned validated commit SHAs, never execute Gradle or tag code. Feed shared classifier and version-only decision, emit stable deterministic JSON with explicitly named no-op. Disable external diff/textconv and gh debug/prompt output; force public GitHub host. GitHub metadata APIs and gh failures must fail before producing a plan. Each Git/API operation has a finite subprocess timeout; no credentials/state/tfvars/private-key reads. Keep API injectable for tests; CLI real transport remains gh, never a stub.

### Task5: Parent integration and real read-only smoke
Run `python3 -B -m unittest discover -s scripts/tests -v`, all118 infra tests and Node4; both modules/testfiles Python3.9 AST, git diff --check. Existing CI picks up new tests; no workflow edit needed.
Run actual CLI against published v1.2.0 in real checkout with real GitHub reads, expect predecessor v1.1.0, frontend-only (build.gradle version-only exclusion; actual frontend blue-accent change). Run manual v1.1.0 -> both, and v1.0.1 -> explicit missing-asset failure (historical release lacks frontend bundle). Preserve no-op/main-push behavior as future workflow acceptance, not a claim that a workflow exists. Compare state hash/tags/checkouts before/after; no download/build/deploy.

### Task6: Review and closure
Independent spec review then quality/final integration review, repair important gaps with RED/GREEN. Document actual inputs/results and still-pending workflow/live gates. Verify reviewed blobs/manifest, focused short commits, secret-pattern scan. Authorized completed-feature PR->dev: exact head CI, merge API pinned head, read back PR/dev SHA, merge-SHA CI/artifacts, then prove ancestry and remove only finished feature branch. Main/dev/gh-pages stay; no new tag or live changes. Report scoped completed vs next workflow stage concisely.

Official API/Git references consulted: GitHub REST releases (published release enumeration and pagination), Git references (annotated vs lightweight tag objects), git-diff -z/--name-status/rename semantics. A real API read is not an AWS/runner/deployment acceptance test.
