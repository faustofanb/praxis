# Workflow Trust and MOM Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分阶段降低 Praxis 治理操作重量，修复状态、投影、预算和原子性缺陷，并随插件发布四个窄 MOM 业务 Skill。

**Architecture:** 保持 SQLite 为状态权威源，在 `StateStore` 内提供事务化 compare/update 操作；生命周期、Skill 凭证和文档投影继续通过应用服务编排。CLI 增加新入口但保留旧命令兼容，业务规则放入窄 Skill，确定性门禁留在 Python 服务。

**Tech Stack:** Python 3.13、SQLite/WAL、argparse、pytest、Codex Plugin Skills。

## Global Constraints

- 所有代码只在绑定 `WT-REQ-20260722-001--praxis-next` 工作树修改。
- 所有外部命令先经过 RTK；Python/pytest 使用 `UV_CACHE_DIR=/tmp/praxis-next-uv-cache` 与 `uv run --no-sync`。
- 行为改动严格执行 RED → GREEN；不运行未列入收据的全仓回归、覆盖率、lint 或 typecheck。
- required Skill 和用户已批准的 Skill 不得变为 `omitted_budget`；预算不足必须返回明确门禁。
- Skill 不能自动冒充已使用；只有调用方提交的 `--used-skill id=result[:details]` 才能形成完成凭证。
- 不创建泛化 `praxis-workflow-helper` Skill。

---

### Task 1: Idempotent projection and explicit implementation lifecycle

**Files:**
- Modify: `src/praxis/documents/requirements.py`
- Modify: `src/praxis/domain/requirement.py`
- Modify: `src/praxis/knowledge/requirements.py`
- Modify: `src/praxis/application.py`
- Modify: `src/praxis/cli/__init__.py`
- Test: `tests/test_workspace_requirements.py`
- Test: `tests/test_application_dispatch.py`
- Test: `tests/test_interfaces.py`

**Interfaces:**
- Produce: `RequirementService.advance(requirement_id: str) -> Result`
- Produce: `praxis requirement advance <id>`
- Lifecycle: `in_progress -> implemented -> verifying -> completed`

- [ ] **Step 1: Write failing projection and lifecycle tests**

```python
def test_requirement_projection_managed_state_is_idempotent(tmp_path: Path) -> None:
    # Project the same enriched record repeatedly.
    # Assert exactly one START and one END marker remain.

def test_requirement_advance_moves_one_legal_state_and_reports_gate(tmp_path: Path) -> None:
    # Assert captured -> investigating only.
    # Assert response contains source_status, target_status, and missing_gates.

def test_implemented_is_required_before_verifying() -> None:
    # Assert in_progress -> verifying is rejected and
    # in_progress -> implemented -> verifying is accepted.
```

- [ ] **Step 2: Run RED**

Run:

```text
rtk test env UV_CACHE_DIR=/tmp/praxis-next-uv-cache uv run --no-sync pytest -q tests/test_workspace_requirements.py::test_requirement_projection_managed_state_is_idempotent tests/test_workspace_requirements.py::test_requirement_advance_moves_one_legal_state_and_reports_gate tests/test_workspace_requirements.py::test_implemented_is_required_before_verifying tests/test_application_dispatch.py::test_requirement_advance_dispatches_one_transition tests/test_interfaces.py::test_requirement_advance_cli_mapping --no-cov
```

Expected: FAIL because marker normalization, `implemented`, and `advance` do not exist.

- [ ] **Step 3: Implement minimal behavior**

```python
class RequirementStatus(StrEnum):
    IMPLEMENTED = "implemented"

def advance(self, requirement_id: str) -> Result:
    current = self.store.requirement(requirement_id)
    target = next_status(current["status"])
    gate = self._advance_gate(current, target)
    if not gate.ok:
        return gate
    transitioned = self.transition(requirement_id, target)
    return Result(True, data={
        **transitioned.data,
        "source_status": current["status"],
        "target_status": target.value,
        "missing_gates": [],
    })
```

Normalize the existing overview before extracting human sections: remove every managed state block and orphan managed markers, then render one canonical block.

- [ ] **Step 4: Run GREEN**

Run the exact RED command. Expected: all selected tests pass.

### Task 2: Protected Skill budget and atomic multi-project implementation

**Files:**
- Modify: `src/praxis/skills/routing.py`
- Modify: `src/praxis/storage/sqlite.py`
- Modify: `src/praxis/knowledge/requirements.py`
- Modify: `src/praxis/application.py`
- Modify: `src/praxis/cli/__init__.py`
- Test: `tests/test_skill_node_routing.py`
- Test: `tests/test_workspace_requirements.py`
- Test: `tests/test_interfaces.py`

**Interfaces:**
- Produce: `StateStore.update_runtime_state(scope, key, updater, *, audit_event, audit_details)`.
- Change: `record_implementation(requirement_id, projects: dict[str, list[str]])`.
- CLI: repeated `--project project_id[=artifact_id,artifact_id]`.

- [ ] **Step 1: Write failing budget and lost-update tests**

```python
def test_approved_and_required_skills_are_never_omitted_by_budget(tmp_path: Path) -> None:
    # Tiny budget; required and approved decisions remain available.
    # Result reports protected_budget and budget_shortfall.

def test_record_implementation_merges_multiple_projects_atomically(tmp_path: Path) -> None:
    # Record backend and mes-pda in one call and assert both survive.
    # Re-run one project and assert the other is unchanged.
```

- [ ] **Step 2: Run RED**

Run:

```text
rtk test env UV_CACHE_DIR=/tmp/praxis-next-uv-cache uv run --no-sync pytest -q tests/test_skill_node_routing.py::test_approved_and_required_skills_are_never_omitted_by_budget tests/test_workspace_requirements.py::test_record_implementation_merges_multiple_projects_atomically tests/test_interfaces.py::test_record_implementation_multi_project_cli_mapping --no-cov
```

Expected: FAIL because protected allocation and multi-project atomic update are absent.

- [ ] **Step 3: Implement minimal behavior**

Allocate protected policies first. A protected decision is required/conditional-required, or approval-required and present in `approved_skills`. Protected entries remain available when installed; optional entries alone may become `omitted_budget`. If protected total exceeds requested budget, return `budget_shortfall` without falsifying availability.

Perform read, merge, upsert, and audit within one `BEGIN IMMEDIATE` transaction. Do not expose a generic arbitrary SQL callback outside `StateStore`.

- [ ] **Step 4: Run GREEN**

Run the exact RED command. Expected: all selected tests pass.

### Task 3: Atomic lifecycle completion and structured Skill results

**Files:**
- Modify: `src/praxis/skills/routing.py`
- Modify: `src/praxis/storage/sqlite.py`
- Modify: `src/praxis/application.py`
- Modify: `src/praxis/cli/__init__.py`
- Modify: `src/praxis/agents/guidance.py`
- Modify: `skills/praxis-requirement-workflow/SKILL.md`
- Modify: `skills/praxis-system-development/SKILL.md`
- Test: `tests/test_skill_node_routing.py`
- Test: `tests/test_application_dispatch.py`
- Test: `tests/test_interfaces.py`

**Interfaces:**
- Produce: `praxis lifecycle complete-node`.
- Preserve: `praxis skill complete-node` as a deprecated compatibility alias.
- Skill result enum: `passed`, `not_applicable`, `approval_missing`, `failed`.

- [ ] **Step 1: Write failing atomicity and gate tests**

```python
def test_lifecycle_complete_node_rolls_back_partial_skill_records(tmp_path: Path) -> None:
    # Include one valid and one invalid Skill; assert neither invocation persists.

def test_approval_missing_keeps_implementation_complete_and_verification_pending(tmp_path: Path) -> None:
    # Assert gate code identifies approval_missing and does not report passed.
```

- [ ] **Step 2: Run RED**

Run:

```text
rtk test env UV_CACHE_DIR=/tmp/praxis-next-uv-cache uv run --no-sync pytest -q tests/test_skill_node_routing.py::test_lifecycle_complete_node_rolls_back_partial_skill_records tests/test_skill_node_routing.py::test_approval_missing_keeps_implementation_complete_and_verification_pending tests/test_application_dispatch.py::test_lifecycle_complete_node_dispatches_atomically tests/test_interfaces.py::test_lifecycle_complete_node_cli_mapping --no-cov
```

Expected: FAIL because current implementation writes invocation records incrementally and accepts arbitrary result strings.

- [ ] **Step 3: Implement minimal behavior**

Parse each `--used-skill` as `<id>=<result>[:details]`. Validate the whole request first, then write all invocation/completion/gate audit records in one transaction. `approval_missing` is an explicit non-passing result and returns a gate that says implementation is complete while verification is awaiting approval.

- [ ] **Step 4: Run GREEN**

Run the exact RED command. Expected: all selected tests pass.

### Task 4: Add and update narrow MOM Skills

**Files:**
- Create: `skills/add-mom-magic-api/`
- Create: `skills/build-mes-pda-readonly-overview/`
- Create: `skills/api-permission-migration/`
- Create: `skills/uniapp-api-generation/`
- Create: `tests/test_magic_migration_validator.py`
- Modify: `skills/praxis-system-development/references/node-routing.toml`

**Interfaces:**
- Validator: `validate_magic_migration.py <migration.sql> [--expected-group ...] [--expected-menu-route ...]`.
- Exit 0 when contracts pass; exit 1 with stable diagnostic codes when they fail.

- [ ] **Step 1: Initialize the two new Skill folders**

Use `skill-creator/scripts/init_skill.py` with `scripts,references,assets` for `add-mom-magic-api`, and `references,assets` for `build-mes-pda-readonly-overview`. Generate quoted `agents/openai.yaml` interface fields.

- [ ] **Step 2: Write the failing validator test**

Run:

```text
rtk test env UV_CACHE_DIR=/tmp/praxis-next-uv-cache uv run --no-sync pytest -q tests/test_magic_migration_validator.py --no-cov
```

Expected: FAIL until the validator rejects damaged `$magic$` JSON, wrong group/path, tenant request parameters, mismatched permission URI/menu route, missing tenant grants, and non-string Snowflake output.

- [ ] **Step 3: Implement Skill resources**

Keep `SKILL.md` procedural and concise. Put Magic conventions and menu/permission details in one-level `references/`; put deterministic checks in the validator; provide one SQL template asset. The PDA Skill provides structure and behavior assets without freezing business colors or fields.

Bundle updated `api-permission-migration` and `uniapp-api-generation` skills with explicit Magic/handwritten API routing rules. Never edit generated `apiDefinitions.ts` or `globals.d.ts` for a single Magic endpoint.

- [ ] **Step 4: Run GREEN and Skill validation**

Run the exact validator test command, then:

```text
rtk proxy env UV_CACHE_DIR=/tmp/praxis-next-uv-cache uv run --no-sync python /Users/fausto/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/add-mom-magic-api
rtk proxy env UV_CACHE_DIR=/tmp/praxis-next-uv-cache uv run --no-sync python /Users/fausto/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/build-mes-pda-readonly-overview
rtk proxy env UV_CACHE_DIR=/tmp/praxis-next-uv-cache uv run --no-sync python /Users/fausto/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/api-permission-migration
rtk proxy env UV_CACHE_DIR=/tmp/praxis-next-uv-cache uv run --no-sync python /Users/fausto/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/uniapp-api-generation
```

### Task 5: Focused verification, release, and installation

**Files:**
- Modify: `.codex-plugin/plugin.json` through the cachebuster helper.
- Update: requirement artifacts and progress through Praxis CLI.

- [ ] **Step 1: Run focused regression**

```text
rtk test env UV_CACHE_DIR=/tmp/praxis-next-uv-cache uv run --no-sync pytest -q tests/test_workspace_requirements.py tests/test_skill_node_routing.py tests/test_application_dispatch.py tests/test_interfaces.py tests/test_magic_migration_validator.py --no-cov
```

- [ ] **Step 2: Run minimum Python compile**

```text
rtk err env UV_CACHE_DIR=/tmp/praxis-next-uv-cache uv run --no-sync python -m compileall -q src/praxis skills/add-mom-magic-api/scripts
```

- [ ] **Step 3: Validate plugin**

```text
rtk proxy python3 /Users/fausto/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
```

- [ ] **Step 4: Commit and publish**

Stage only planned files, commit with `REQ-20260722-001`, push the requirement branch, fast-forward the configured development branch, and push it.

- [ ] **Step 5: Update cachebuster and reinstall**

Run the plugin-creator cachebuster helper, read the personal marketplace name with its helper, commit/push the manifest update, then run:

```text
codex plugin add praxis-next@personal
```

- [ ] **Step 6: Installed-state smoke**

Start a fresh local CLI process from the installed plugin and verify version/help, `requirement advance`, `lifecycle complete-node`, and the four bundled Skill folders. Record exact outputs; do not claim full regression.
