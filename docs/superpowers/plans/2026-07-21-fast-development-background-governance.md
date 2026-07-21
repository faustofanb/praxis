# Praxis Fast Development and Background Governance Implementation Plan

> Requirement: REQ-20260721-003
>
> Authority: `知识库/需求/2026/07/快速开发路径与后台治理__REQ-20260721-003/`

## Goal

Make Git isolation and an active binding the synchronous development boundary. Move dependency setup and CodeGraph indexing behind explicit, observable state without weakening requirement, Skill, approval, or audit gates.

## Task 1: Worktree preview, ensure, and deferred preparation

Files:

- Modify `src/praxis/worktree/service.py`
- Modify `src/praxis/workspace/service.py`
- Modify `src/praxis/application.py`
- Modify `src/praxis/cli/__init__.py`
- Modify `src/praxis/mcp/broker.py`
- Modify `src/praxis/mcp/server.py`

Steps:

1. Add a deterministic preview record containing requirement/repository set, generated names, fingerprint, creation time, and expiry.
2. Add `worktree ensure --preview` and `--confirm <preview_id>`; reject changed or expired snapshots.
3. Run independent repository creation through a bounded thread pool and return per-repository results in stable input order.
4. Split local-file activation from setup. Mark configured setup as deferred by default and expose `worktree prepare` for explicit first-build preparation.
5. Add a fast preflight that validates setup argv, declared package-manager version, executable availability, and lockfile presence without network access or lifecycle scripts.
6. Keep existing `worktree create` compatible by internally using the fast activation path.

## Task 2: Asynchronous CodeGraph lifecycle

Files:

- Modify `src/praxis/codegraph/service.py`
- Add `src/praxis/codegraph/worker.py`
- Modify `src/praxis/worktree/service.py`
- Modify `src/praxis/application.py`
- Modify `src/praxis/cli/__init__.py`

Steps:

1. Add `enqueue`, `run_pending`, and `wait` APIs with queued/running/completed/failed/stale states.
2. Launch a detached worker using the active Python interpreter and `python -m praxis.codegraph.worker`; persist PID and log path without command output or environment data.
3. Update the owning binding's `codegraph_status` from the worker but do not change an active Git binding to blocked on graph failure.
4. Make worktree activation enqueue indexing after returning active state.
5. Let explicit semantic queries wait for a bounded interval or return a diagnostic recommending `rg` fallback.
6. Reuse an existing index only when CodeGraph status proves repository path, revision, pending changes, and index completeness match; otherwise rebuild asynchronously.

## Task 3: Name migration and requirement reopen

Files:

- Modify `src/praxis/domain/requirement.py`
- Modify `src/praxis/storage/sqlite.py`
- Modify `src/praxis/knowledge/requirements.py`
- Modify `src/praxis/worktree/service.py`
- Modify `src/praxis/application.py`
- Modify `src/praxis/cli/__init__.py`

Steps:

1. Add an explicit audited reopen method restricted to `verifying -> in_progress` and require a non-empty reason.
2. Project the reopened state to requirement documents through the existing outbox.
3. Complete a successful name migration with binding `active`, preserving previous blocked status only as audit metadata.
4. Queue CodeGraph rebuild after migration and do not roll back a successful Git/name transaction because background graph indexing fails.

## Task 4: Artifact upsert

Files:

- Modify `src/praxis/artifacts/service.py`

Steps:

1. Normalize and validate the source path once.
2. Find an existing artifact by requirement ID plus normalized source path.
3. Preserve artifact ID and creation time, refresh mutable metadata and hash, and write `artifact.refreshed`; otherwise write `artifact.registered`.
4. Rebuild the requirement artifact index once after the upsert.

## Task 5: Batched Skill lifecycle and route cache

Files:

- Modify `src/praxis/skills/routing.py`
- Modify `src/praxis/application.py`
- Modify `src/praxis/cli/__init__.py`
- Modify `src/praxis/mcp/broker.py`
- Modify `src/praxis/mcp/server.py`

Steps:

1. Hash the normalized routing request, routing policy file, and installed Skill inventory.
2. Reuse an identical node route and emit `skill.route_reused`; invalidate on any input or inventory change.
3. Add `skill complete-node` accepting explicit `skill=outcome` entries.
4. Within one application operation, route, validate selected/required Skills, create and complete each invocation, then run the existing gate.
5. Reject approval-required Skills unless a matching approval receipt already exists.
6. Rename CLI help to state that budgets are token counts.

## Task 6: Scoped approvals and execution budgets

Files:

- Add `src/praxis/governance/service.py`
- Modify `src/praxis/application.py`
- Modify `src/praxis/cli/__init__.py`
- Modify `src/praxis/gates/engine.py`

Steps:

1. Add requirement-scoped approval receipts with scope, exact command/matrix entries, issuer evidence, issue time, and optional expiry.
2. Require a direct-user authorization marker when creating a receipt; do not infer approval from workflow verbs.
3. Add per-requirement/node counters for evidence, recovery, and retry with workspace defaults.
4. Expose budget status and consume operations; allow one recovery and one retry by default.
5. Integrate exact approval matching into verification execution gates while retaining current fail-closed behavior.

## Task 7: Compact agent handoff and parent receipts

Files:

- Modify `src/praxis/agents/service.py`
- Modify `src/praxis/agents/guidance.py`
- Modify `src/praxis/context/service.py`

Steps:

1. Add a compact handoff manifest derived from the requirement, context bundle, worktree binding, allowed capabilities, and routed Skills.
2. Render `fork_turns = "none"` as the default coordination hint for Codex subagents.
3. Mark child sessions read-only for requirement transitions and Skill gates; the parent coordinator remains the single writer.
4. Add a parent receipt operation containing changed paths, decisions, blockers, and requested follow-up, bounded by a compact size limit.
5. Document the threshold for subagent use: at least two independent tasks or one bounded task expected to exceed two minutes.

## Task 8: Timing telemetry and guidance

Files:

- Modify `src/praxis/application.py`
- Modify `src/praxis/agents/guidance.py`
- Modify `README.md`
- Modify `skills/praxis-requirement-workflow/SKILL.md`

Steps:

1. Measure core aggregate operations with `time.monotonic_ns` and add `duration_ms` to their returned data without changing stable utility-command payloads.
2. Emit a compact `operation.timed` audit entry containing operation, result code, duration, requirement/project/binding identifiers when present.
3. Prevent timing telemetry from recording command output, environment variables, SQL, or free-form request text.
4. Update managed guidance and workflow Skill for preview-first naming, deferred setup, background CodeGraph, artifact upsert, scoped approvals, evidence budgets, concise updates, and parent single-writer behavior.

## Task 9: Verification and rollout

Files:

- Modify requirement progress and acceptance documents after evidence exists.
- Update plugin cachebuster only after implementation is stable.

Steps:

1. Perform static import/CLI/diff checks that do not execute the unapproved quality matrix.
2. Ask for one explicit scoped approval before lint, type checks, automated tests, reviewer/tester agents, or MOM/AOTU workflow regression.
3. With approval, run only the named matrix, record timings, and compare synchronous worktree readiness against the previous 55–379 second CodeGraph blocking range.
4. Register stable artifacts once, relying on upsert for later hash refresh.
5. Commit, merge the requirement worktree into `codex/praxis-v3-development`, refresh the personal plugin cache, and report remaining risks.
