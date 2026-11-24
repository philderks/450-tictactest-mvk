# Split Component Deployer Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Locally implement independent frontend/backend selection, verified reusable component caches and reliable rollback without changing the running EC2 or publishing a release.

**Architecture:** Preserve `current` for backend/runtime compatibility and introduce `frontend-current`; cache verified components separately under `deployments/backend/<version>` and `deployments/frontend/<version>`. Serve public configuration from an exact infrastructure-owned nginx route. Verify a real Java prompt through ttyd WebSocket inside the locked activation transaction, rather than accepting version metadata as JVM health.

**Tech Stack:** Python stdlib compatible with Python3.9, Bash wrapper, nginx/systemd configuration, unittest, pinned existing ttyd and genuine previously published JARs for isolated local probes.

---

## Scope/gates
- Pre-flight: clean refreshed dev, scoped `feat/auftrag-3-split-deployer`, current state/tag preserved. No AWS/SSM/GitHub-setting writes, server installation, service restarts, `tofu plan/apply`, new releases or main promotion in this slice.
- Revision: strict vertical RED→GREEN cycles per behavior. Spec review first, then independent quality review; important gaps return to implementer, maximum three nonconverging rounds before escalation.
- Abort: unexpected live-state/tag mutation, scope violation or unavailable essential verification dependency. Preserve evidence and report the exact blocker; do not substitute synthetic results for genuine integration.
- Completion: local real-file transaction tests + real ttyd/JVM probe, full regressions, Python3.9 syntax, Bash/nginx template contracts, real offline user-data rendering/size, independent reviews, reviewed feature PR into dev and exact-head/merge CI. Live migration stays explicitly pending.

### Task 1: Component cache and activation transaction (implementer A)
**Files:** modify `infra/scripts/deploy-release.py`; update `infra/tests/test_runtime_install.py` and optionally create `infra/tests/test_component_deploy.py`. No other files owned.
1. Write a failing frontend-only behavior test against the missing selector, verify meaningful RED, then minimally implement `deploy(version, components='both')` and CLI `--components {backend,frontend,both}`. Retain the one-version CLI default for existing callers.
2. Prepare only selected artifacts: frontend ZIP+SHA; backend JAR/runtimeZIP+SHAs; both all six. Verify all selected hashes before extraction, retain existing strict archive/input/root/permission guards, inspect actual manifest/version metadata without executing downloaded scripts as root.
3. Store immutable verified component trees separately, record a deterministic file/digest receipt, reject altered/unsafe cached trees and reuse valid existing versions for rollback without deleting old releases. Keep legacy `releases/` untouched.
4. Write failing tuple-selection tests, then implement snapshots of raw backend/frontend symlink targets, exact release.env bytes and actual selected versions. Change only selected inputs. Use an absolute immutable JAR_PATH for the selected backend. Reject selective first deployment and inconsistent/legacy-unmigrated layouts before activation.
5. Expected nginx contract: root `/opt/tictactest/frontend-current/frontend`; exact `/config.js` route returns same-origin public config and header `X-TicTacTest-Layout: split-v1`. Existing running installations must prove the new loaded layout before activation; an initial empty host may be provisioned by both-mode with prepared nginx config. No automatic migration of a running legacy host in deploy().
6. Frontend-only never restarts/stops either unit, including failure/rollback. Backend-only restarts only console. Both restarts console; starts/restarts web only when required for first deployment, not as a substitute for selecting frontend files. Unselected bytes, selectors and processes must remain untouched.
7. Health accepts independent expected backend/frontend versions, still verifies exact public80/private7681/8080 listeners and existing routes, plus the infrastructure config route. Add `probe_console(timeout)` wrapper invoking adjacent `console-smoke.py` via the current Python interpreter; invoke only for backend/both changes, never frontend-only. Cap operation timeouts to one monotonic health deadline (default60s); no nested retries that silently exceed it.
8. Fail health/activation under host lock, restore the entire prior mixed tuple/environment, verify restored health, preserve a failed status even if rollback succeeds, and expose rollback failure separately. Restore missing initial selections and stop only units activated by an initial failed attempt. Preserve failed prepared trees for diagnosis.
9. Adapt old assertions only for deliberately changed interfaces/layout. Preserve all old meaningful security checks: invalid values before writes, nonroot, checksum before extraction/activation, filename binding, unsafe/duplicate ZIP, manifest mismatch, umask077, no-root release-script execution, listener safety and first-deploy cleanup.
10. Run targeted cycles and all infra/support/Node regressions; log RED/GREEN evidence privately. No commits/cloud actions.

Example behavior assertion (fixture helpers defined by implementer):
```python
backend_before = current.readlink()
env_before = environment.read_bytes()
module.deploy('1.2.0', components='frontend')
self.assertEqual(current.readlink(), backend_before)
self.assertEqual(environment.read_bytes(), env_before)
services.assert_not_called()
self.assertEqual(frontend_version(), '1.2.0')
```

### Task 2: Genuine ttyd/JVM start probe (implementer B; disjoint files)
**Files:** create `infra/scripts/console-smoke.py`, `infra/tests/test_console_smoke.py` only.
1. TDD a stdlib Python3.9 API `probe_console(base_url, timeout=10.0)` and CLI `console-smoke.py URL --timeout SECONDS`, returning success only after real stdout contains the game's `where to put the next CROSS` prompt. No game moves or existing-session interference.
2. Read pinned ttyd1.7.7 primary client/server source to implement its actual `/console/token`, `/console/ws`, `tty` subprotocol, AuthToken/terminal-size handshake and output-command framing. Do not guess protocol or disable Origin checking.
3. Validate HTTP/HTTPS URL, preserve prefix, bypass proxies for local health, enforce a single monotonic deadline, validate WebSocket accept/subprotocol, mask outgoing client frames, handle ping/control/fragmentation, bound header/frame/transcript sizes and always close the owned socket/session.
4. Test with real isolated local HTTP/WebSocket fixtures: successful prompt, no prompt/early close/bad Java output, token/upgrade failure, framing/fragmentation, timeout and cleanup. No new third-party runtime dependency. Never execute downloaded app scripts as root.
5. If useful, run only a separate ephemeral loopback ttyd process with fixed verified existing `/home/phil/.local/share/tictactest-webconsole/ttyd.x86_64`; never touch existing preview ports/processes. Record actual results separately from synthetic protocol fixture evidence. Parent owns final real-JAR integration.
6. Interface with A: sibling CLI path fixed; args URL then `--timeout`; exit0 only prompt success, otherwise bounded diagnostic/nonzero. Do not edit A's deployer/tests or parent nginx/docs. No commits/cloud actions.

### Task 3: nginx configuration and integration (parent)
**Files:** modify `infra/bootstrap/nginx.conf`; new `infra/tests/test_split_nginx.py`; later docs/deployment.md.
1. Write failing config contract for separate frontend root, infrastructure-owned no-store config route and split-v1 header; retain existing listener/proxy/metadata/hardening behavior.
2. Run RED, implement only root and exact config route, run GREEN. This edits source only, not `/etc` or the EC2.
3. Review A spec, then A/B combined code quality. Do not accept self-report alone: exercise filesystem transaction cases, cache reuse/corruption, mixed rollback, selected restart boundaries and JVM probe failures.
4. Run real published release JAR(s) with fixed verified ttyd on unused local loopback ports in an isolated nonroot test process; prove new client reaches prompt and rejects bad startup. Close all processes/sockets in finally; do not repoint existing previews.
5. Run `python3 -B -m unittest discover -s infra/tests -v`, `python3 -B -m unittest discover -s scripts/tests -v`, `node --test scripts/tests/frontend.test.cjs`, Bash syntax, Python3.9 AST, offline `tofu fmt/validate` and genuine template rendering under16KiB. Do not call cloud plan/apply.
6. Explain required future migration (new frontend pointer/config, three adjacent operational scripts including smoke client, controlled local infrastructure reconciliation). Record observed tests, not a fictional live rollout. Mark classifier/workflow/real release cases still pending.
7. Final independent integration review, local checks, approved complete feature commit/push/PR→dev, exact-head CI then verified merge/cleanup. Preserve state/tag and current public1.2.0. Main/live migration requires a later explicit decision.
