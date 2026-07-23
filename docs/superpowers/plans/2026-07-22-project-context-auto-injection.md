# Workflow Context and MOM Skill Governance Implementation Plan

**Goal:** Make active requirement constraints, implementation/verification state, project database facts, and intent-scoped Skills durable and automatically available to every development entry point.

**Architecture:** Keep the existing requirement lifecycle as the orchestration axis, and add orthogonal delivery facts in `runtime_state`. `RequirementService` owns constraint and delivery mutations, `RequirementProjector` renders managed read-only projections, and `ContextCompiler` remains the single context authority consumed by worktree and Agent entry points. MOM-specific rules stay in the MOM Skill catalog and are selected through project+intent routing.

**Tech Stack:** Python 3.12, dataclasses, SQLite-backed `StateStore`, argparse CLI, Markdown Skill packages, pytest, Ruff.

## Global constraints

- Preserve explicit `context build` and explicit `agent start --context` compatibility.
- Do not add a second context store or a context-consumption receipt.
- Keep database references as `dbx://` identifiers; never store credentials or infer a default connection.
- Do not rewrite an applied SQLite migration; use existing runtime state for new orthogonal facts.
- Keep worktree preview confirmation mandatory and preserve existing deterministic naming.
- Interface-contract freeze and one-basket vertical closure are conditional Skills, not global gates.
- Do not run tests, lint, format, typecheck, reviewers, or builds until the user approves the exact matrix.

---

### Task 1: Structured requirement constraint card and superseding decisions

**Files:**
- Modify: `src/praxis/knowledge/requirements.py`
- Modify: `src/praxis/documents/requirements.py`
- Modify: `src/praxis/cli/__init__.py`
- Modify: `src/praxis/application.py`
- Test: `tests/test_workspace_requirements.py`
- Test: `tests/test_interfaces.py`

**Behavior:**
- `praxis requirement constraint add --requirement REQ --statement TEXT [--supersedes ID] [--source TEXT]`
- `praxis requirement constraint list --requirement REQ` returns active and historical records.
- Adding a constraint validates every superseded ID belongs to the same requirement and is active, then stores one new active record and marks replaced records `superseded` with `superseded_by`.
- `需求总览.md` renders only active statements in a managed “当前有效约束” section; `决策记录.md` renders the full immutable history and explicit replacement links.

- [ ] Write behavior tests for add/list, cross-requirement rejection, atomic replacement, and projection repair.
- [ ] Run the approved focused tests and confirm they fail for missing commands/behavior.
- [ ] Implement a small `RequirementConstraintService` or cohesive methods on `RequirementService` using `runtime_state` plus audit records.
- [ ] Enrich projector input with current constraints during normal and repair projection; never overwrite investigation/plan prose.
- [ ] Re-run the approved focused tests.

### Task 2: Separate implementation, verification, and manual-acceptance facts

**Files:**
- Modify: `src/praxis/knowledge/requirements.py`
- Modify: `src/praxis/governance/service.py`
- Modify: `src/praxis/documents/requirements.py`
- Modify: `src/praxis/cli/__init__.py`
- Modify: `src/praxis/application.py`
- Test: `tests/test_workspace_requirements.py`
- Test: `tests/test_governance.py`
- Test: `tests/test_interfaces.py`

**Behavior:**
- `praxis requirement record-implementation --requirement REQ --project PROJECT [--artifact ART]` records `implementation_status=implemented` independently of lifecycle status.
- `praxis verification decline --requirement REQ --entry ENTRY --user-evidence TEXT --authorized-by-user` records an exact decline receipt and sets only the matching verification fact to `not_authorized` or `declined`.
- Delivery projection reports implementation, verification, and manual acceptance separately. `implemented + verification_not_authorized + awaiting_manual_acceptance` is valid; it never says “verified”.
- Existing approval receipts remain the authority for approved checks. Planning guidance asks once for the exact matrix and reuses it later.

- [ ] Write focused tests for orthogonal states, exact decline matching, unauthorized receipt rejection, and honest projection wording.
- [ ] Run the approved focused tests and confirm RED.
- [ ] Add delivery-state aggregation and decline receipts without changing `RequirementStatus` transitions.
- [ ] Include active approval/decline matrices in requirement display and managed projection.
- [ ] Re-run the approved focused tests.

### Task 3: Precise business Skill routing and SkillDock discovery

**Files:**
- Modify: `src/praxis/skills/registry.py`
- Modify: `src/praxis/skills/routing.py`
- Test: `tests/test_skill_node_routing.py`

**Behavior:**
- Project base Skills ending in `.development` remain project-automatic.
- Other business Skills with non-empty triggers require both the project match and a case-insensitive intent match.
- Triggerless project Skills remain project-automatic for backward compatibility.
- Installed Skill discovery includes `~/.skilldock/skills`.

- [ ] Add tests proving unrelated MES_PDA intent omits UniApp API generation, matching OpenAPI intent includes it, `.development` remains automatic, and SkillDock packages are discoverable.
- [ ] Run the approved routing test and confirm RED.
- [ ] Add `intent` to `SkillRoutingContext` and implement minimal trigger matching after project filtering.
- [ ] Re-run the approved routing test.

### Task 4: P0 constraints, approvals, project/database facts, and isolated context identity

**Files:**
- Modify: `src/praxis/context/service.py`
- Modify: `src/praxis/application.py`
- Modify: `src/praxis/cli/__init__.py`
- Test: `tests/test_context.py`
- Test: `tests/test_interfaces.py`

**Behavior:**
- `ContextBuildRequest.intent` carries the current task intent into Skill routing.
- Priority-0 fragments contain active requirement constraints, exact verification approvals/declines, project ID/kind/path, registered DBX references, production markers, and the explicit-selection/`current_database()` rule.
- `critical_facts` is a compact projection of the same data.
- Current-context identity and fingerprint include requirement, project, stage, workflow node, role, and intent.

- [ ] Test that P0 facts survive missing portrait and a tight optional budget, and that projects/nodes/intents cannot share a current-context entry.
- [ ] Run the approved focused context/interface tests and confirm RED.
- [ ] Implement the fragments, result projection, CLI `--intent`, and isolated cache identity.
- [ ] Re-run the approved focused tests.

### Task 5: Automatic worktree and Agent consumption

**Files:**
- Modify: `src/praxis/application.py`
- Modify: `src/praxis/agents/service.py`
- Modify: `src/praxis/cli/__init__.py`
- Test: `tests/test_application_dispatch.py`
- Test: `tests/test_broker_agents_artifacts.py`
- Test: `tests/test_lifecycle.py`

**Behavior:**
- Successful `worktree ensure` repository items automatically build coder contexts and return `context_bundles`; a failed context build reports the error but does not destroy an already-safe worktree.
- `agent start` makes `--context` optional, infers the project from the binding when absent, and preserves explicit context IDs.
- Handoff contains critical facts. The prepared launch command includes a portable initial prompt that requires reading handoff and context paths before work.
- Existing preview token, final path, branch, and confirmation behavior does not change.

- [ ] Add orchestration and naming-regression tests.
- [ ] Run the approved focused tests and confirm RED only for new context behavior.
- [ ] Implement shared automatic compiler calls and launch prompt wiring.
- [ ] Re-run the approved focused tests.

### Task 6: Code-change artifacts and managed guidance

**Files:**
- Modify: `src/praxis/artifacts/service.py`
- Modify: `src/praxis/agents/guidance.py`
- Modify: `skills/praxis-requirement-workflow/SKILL.md`
- Modify: `skills/dbx-database-investigation/SKILL.md`
- Test: `tests/test_broker_agents_artifacts.py`
- Test: `tests/test_agent_guidance.py`

**Behavior:**
- `code-change` is a supported artifact type with repository, branch, diff statistics, changed-file hashes, and normal integrity verification.
- Guidance requires reading the context bundle returned by ensure, recording exact verification approval during planning, preserving preview confirmation, and checking `current_database()` before schema/data assumptions.

- [ ] Add focused artifact/guidance tests and confirm RED under the approved matrix.
- [ ] Implement the minimal artifact metadata validation and concise managed guidance.
- [ ] Re-run the approved focused tests.

### Task 7: Install intent-scoped MOM Backend and MES_PDA Skills

**MOM requirement:** `REQ-20260722-003`

**Files in MOM knowledge catalog:**
- Modify: `knowledge/skills/business/business.mom.backend.development/SKILL.md`
- Modify: `knowledge/skills/business/business.mom.backend.development/skill.toml`
- Modify: `knowledge/skills/business/business.mom.mes-pda.development/SKILL.md`
- Modify: `knowledge/skills/business/business.mom.mes-pda.development/skill.toml`
- Modify: `knowledge/skills/business/business.mom.mes-pda.uniapp-api-generation/SKILL.md`
- Modify: `knowledge/skills/business/business.mom.mes-pda.uniapp-api-generation/skill.toml`
- Add: `knowledge/skills/business/business.mom.api-contract-freeze/{SKILL.md,skill.toml,agents/openai.yaml}`
- Add: `knowledge/skills/business/business.mom.backend.work-report-extension/{SKILL.md,skill.toml,agents/openai.yaml}`

**Behavior:**
- Backend base Skill covers PDA/PAD/admin controller placement, shared call-site inventory, isolation, transactions, audit time base, Flyway safety, JavaDoc/comments, and conditional DBX handoff.
- MES_PDA base Skill uses the repository-declared pnpm version/scripts and covers routing completeness, H5 native-module guards, queued scans, error parsing, time formatting, and mobile layout.
- UniApp generation checks operationId, generates only `mesPda`, prohibits manual generated-type maintenance, and flags broad diffs.
- Contract freeze and work-report vertical slice are separate trigger-rich Skills. The latter follows scan → SXRL → aging record → in-furnace display → SXCL → audit for one basket before batch/partial-failure expansion.

- [ ] Route and complete MOM requirement investigation/planning nodes before catalog edits.
- [ ] Inspect repository package scripts and existing report call sites; put only verified facts in Skills.
- [ ] Stage Skill packages with `apply_patch`, then install into the MOM managed catalog.
- [ ] Use `praxis skill verify` and representative project+intent routing only if included in the approved verification matrix.

### Task 8: Documentation and honest completion

**Files:**
- Modify: `README.md`
- Update: Praxis requirement progress/acceptance documents through projection-safe APIs.
- Update: MOM requirement progress/acceptance documents through projection-safe APIs.

- [ ] Document constraints, delivery dimensions, verification decline, automatic context bundles, optional Agent context, and database critical facts.
- [ ] Run only the exact user-approved pytest/Ruff/Skill verification matrix.
- [ ] Record each result as passed, failed, declined, not authorized, or awaiting manual acceptance; do not extrapolate to unrun checks.

## Verification matrix to request before implementation

- Focused pytest: `uv run pytest -q tests/test_workspace_requirements.py tests/test_governance.py tests/test_skill_node_routing.py tests/test_context.py tests/test_interfaces.py tests/test_application_dispatch.py tests/test_broker_agents_artifacts.py tests/test_lifecycle.py tests/test_agent_guidance.py`
- Ruff: only modified Python files, exact list resolved after implementation.
- MOM Skill checks: `praxis skill verify` plus representative backend, MES_PDA UI-only, OpenAPI generation, and work-report routing cases.
- No Maven, pnpm build, lint, typecheck, application tests, or DBX query is needed because this change edits the Praxis plugin and MOM knowledge Skills, not MOM business code.

## Self-review

- Every user-requested item is either implemented here or explicitly assigned to MOM `REQ-20260722-003`.
- Worktree preview remains the single mandatory naming confirmation.
- “Implemented” cannot imply “verified”; a decline receipt cannot imply a pass.
- Current constraints and database facts are P0 and cannot be silently omitted by optional context budgeting.
