# Plan Mode Database Investigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow Plan mode to investigate a registered non-production database without first persisting a formal requirement.

**Architecture:** Add a separate `database investigate` read-only path instead of weakening the existing audited `database query` path. The new path validates the project portrait connection, blocks production and non-read SQL, automatically verifies `current_database()`, executes the bounded investigation query, and returns an unpersisted scope receipt.

**Tech Stack:** Python 3.13, argparse, Praxis `Result`, DBX adapter, pytest, Ruff.

## Global Constraints

- Only project-registered `dbx://` connections are eligible.
- Production connections, writes, DDL, locking reads, connection mutation, and default database guessing stay blocked.
- `select current_database()` runs before the requested query.
- Plan-mode investigation does not write Praxis state, requirement documents, artifacts, or audit events.
- Existing `database query` behavior remains unchanged.
- The result declares `persisted: false`; evidence must be attached to a formal requirement after promotion.

---

### Task 1: Read-only investigation service

**Files:**
- Modify: `src/praxis/database/service.py`
- Test: `tests/test_database.py`

**Interfaces:**
- Consumes: `DatabaseService`, `Dbx.execute`, project database connection facts.
- Produces: `DatabaseService.investigate(project_id, connection_ref, sql, purpose) -> Result`.

- [x] **Step 1: Write the failing service tests**

```python
def test_plan_investigation_prechecks_database_and_does_not_persist_state(tmp_path):
    result = DatabaseService(tmp_path, dbx=dbx).investigate(
        "backend", "dbx://mom-dev/app", "select * from orders limit 5",
        purpose="追溯一期订单口径",
    )
    assert result.ok
    assert result.data["scope"]["persisted"] is False
    assert dbx.executed[0][1] == "select current_database()"
    assert len(StateStore(tmp_path).audit_events()) == before
```

```python
def test_plan_investigation_blocks_production_and_write_sql(tmp_path):
    assert service.investigate(
        "backend", "dbx://mom-prod", "select 1", purpose="调查"
    ).code == "DATABASE_PRODUCTION_READ_APPROVAL_REQUIRED"
    assert service.investigate(
        "backend", "dbx://mom-dev", "update orders set status='x' where id=1",
        purpose="调查",
    ).code == "DATABASE_INVESTIGATION_READ_ONLY"
```

- [x] **Step 2: Run tests to verify RED**

Run:

```bash
uv run --no-sync pytest -q --no-cov \
  tests/test_database.py::test_plan_investigation_prechecks_database_and_does_not_persist_state \
  tests/test_database.py::test_plan_investigation_blocks_production_and_write_sql
```

Expected: FAIL because `DatabaseService.investigate` does not exist.

- [x] **Step 3: Implement the minimal service**

```python
def investigate(self, project_id, connection_ref, sql, *, purpose):
    project = WorkspaceService(self.root).project(project_id)
    # validate registered/non-production/read-only/purpose
    # execute current_database(), compare explicit target database, then query
    # return an INV receipt without StateStore writes
```

- [x] **Step 4: Run the focused tests to verify GREEN**

Run the Step 2 command.

Expected: both tests pass.

### Task 2: CLI and application dispatch

**Files:**
- Modify: `src/praxis/cli/__init__.py`
- Modify: `src/praxis/application.py`
- Test: `tests/test_interfaces.py`
- Test: `tests/test_application_dispatch.py`

**Interfaces:**
- Consumes: `DatabaseService.investigate`.
- Produces: `praxis database investigate --project --connection --purpose --sql`.

- [x] **Step 1: Add failing CLI and dispatch tests**

```python
args = _parser().parse_args([
    "database", "investigate", "--project", "backend",
    "--connection", "dbx://BL_DMS_DB/app",
    "--purpose", "追溯一期", "--sql", "select 1",
])
assert _operation(args) == (
    "database.investigate",
    {
        "project_id": "backend",
        "connection_ref": "dbx://BL_DMS_DB/app",
        "purpose": "追溯一期",
        "sql": "select 1",
    },
)
```

- [x] **Step 2: Run tests to verify RED**

Run:

```bash
uv run --no-sync pytest -q --no-cov \
  tests/test_interfaces.py tests/test_application_dispatch.py
```

Expected: FAIL because the command and operation do not exist.

- [x] **Step 3: Add the parser mapping and application dispatch**

```python
if operation == "database.investigate":
    return DatabaseService(self.root).investigate(
        values["project_id"],
        values["connection_ref"],
        values["sql"],
        purpose=values["purpose"],
    )
```

- [x] **Step 4: Run the interface and dispatch tests**

Expected: tests pass.

### Task 3: Workflow and DBX instructions

**Files:**
- Modify: `skills/praxis-requirement-workflow/SKILL.md`
- Modify: `skills/dbx-database-investigation/SKILL.md`
- Modify: `src/praxis/agents/guidance.py`
- Test: `tests/test_agent_guidance.py`

**Interfaces:**
- Consumes: `database investigate`.
- Produces: consistent instructions for Plan-mode database evidence.

- [x] **Step 1: Add a failing guidance assertion**

```python
assert "database investigate" in agents
assert "规划模式" in agents
```

- [x] **Step 2: Run the guidance test to verify RED**

Run:

```bash
uv run --no-sync pytest -q --no-cov tests/test_agent_guidance.py
```

Expected: FAIL because managed guidance lacks the command.

- [x] **Step 3: Update the managed guidance and both Skills**

Document the planning exception, non-production/read-only boundary, automatic database identity check, and `persisted: false` receipt.

- [x] **Step 4: Run the guidance test and Skill validators**

Expected: test and validators pass.

### Task 4: Verification, delivery, and installation

**Files:**
- Modify: `.codex-plugin/plugin.json` through the cachebuster helper.

**Interfaces:**
- Consumes: completed Tasks 1-3.
- Produces: committed, pushed, installed Praxis plugin.

- [x] **Step 1: Run authorized verification**

```bash
uv run --no-sync pytest -q --no-cov \
  tests/test_database.py tests/test_interfaces.py \
  tests/test_application_dispatch.py tests/test_agent_guidance.py
uv run --no-sync ruff check <modified-python-files>
```

- [x] **Step 2: Validate Skills and plugin**

Run `quick_validate.py` for both modified Skills and `validate_plugin.py` for the plugin.

- [x] **Step 3: Refresh cachebuster and record the code-change artifact**

Use `update_plugin_cachebuster.py`, then refresh the Praxis implementation artifact.

- [ ] **Step 4: Commit, merge, and push**

Commit on the requirement branch, fast-forward `codex/praxis-v3-development`, rerun focused verification on the merged result, and push it.

- [ ] **Step 5: Reinstall and smoke-test**

Install `praxis-next@personal`, rebuild the installed version environment from `uv.lock`, and run the installed CLI against a fake DBX adapter test plus parser/version checks.
