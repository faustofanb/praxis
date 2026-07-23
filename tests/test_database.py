from __future__ import annotations

from pathlib import Path

import pytest

from praxis.database.service import DatabaseService
from praxis.gates.sql import inspect_sql
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService


@pytest.mark.parametrize(
    ("sql", "ok", "kind", "code"),
    [
        ("select * from orders where id = 1", True, "read", "OK"),
        ("with recent as (select * from orders) select * from recent", True, "read", "OK"),
        ("select * from orders for update", False, "blocked", "SQL_LOCKING_READ_BLOCKED"),
        ("update orders set status = 'done' where id = 1", True, "write", "OK"),
        ("delete from orders where id = 1", True, "write", "OK"),
        ("update orders set status = 'done'", False, "blocked", "SQL_WHERE_REQUIRED"),
        ("delete from orders", False, "blocked", "SQL_WHERE_REQUIRED"),
        ("drop table orders", False, "blocked", "SQL_DDL_BLOCKED"),
        ("select 1; delete from orders where id = 1", False, "blocked", "SQL_MULTIPLE_STATEMENTS"),
        ("call rebuild_reports()", False, "blocked", "SQL_UNSUPPORTED"),
    ],
)
def test_sql_policy_is_conservative(sql: str, ok: bool, kind: str, code: str) -> None:
    result = inspect_sql(sql)

    assert result.ok is ok
    assert result.code == code
    assert result.data["kind"] == kind


class FakeDbx:
    def __init__(self, *, current_database: str = "app") -> None:
        self.executed: list[tuple[str, str]] = []
        self.current_database = current_database

    def list_connections(self) -> Result:
        return Result(True, data={"connections": [{"name": "mom-dev"}, {"name": "mom-prod"}]})

    def discover(self) -> Result:
        return self.list_connections()

    def execute(self, connection: str, sql: str, *, database: str | None = None) -> Result:
        target = f"{connection}/{database}" if database else connection
        self.executed.append((target, sql))
        if sql == "select current_database()":
            return Result(
                True,
                data={"rows": [{"current_database": self.current_database}]},
            )
        return Result(True, data={"rows": [{"value": 1}]})


def _workspace(root: Path) -> str:
    WorkspaceService(root).init(
        "demo",
        "演示工作空间",
        projects=[
            Project(
                id="backend",
                name="后端服务",
                kind="python",
                path=".",
                default_branch="main",
                database_connections=("dbx://mom-dev", "dbx://mom-prod"),
                production_database_connections=("dbx://mom-prod",),
            )
        ],
    )
    requirement = StateStore(root).create_requirement(
        "数据库修复任务", "修复数据", ["demo"], []
    )
    return requirement["requirement_id"]


def _write_context(requirement_id: str) -> dict[str, object]:
    return {
        "requirement_id": requirement_id,
        "stage": "database",
        "purpose": "修复订单状态",
        "parameters": {},
        "precheck": "已核对目标记录",
        "postimpact": "复核一条记录状态",
        "approval": "人工批准",
    }


def test_database_read_requires_registered_connection(tmp_path: Path) -> None:
    _workspace(tmp_path)
    dbx = FakeDbx()
    database = DatabaseService(tmp_path, dbx=dbx)

    result = database.query("backend", "dbx://mom-dev", "select 1")
    unknown = database.query("backend", "dbx://other", "select 1")

    assert result.ok
    assert dbx.executed == [("mom-dev", "select 1")]
    assert unknown.code == "DATABASE_CONNECTION_NOT_REGISTERED"


def test_database_discovery_is_audited(tmp_path: Path) -> None:
    _workspace(tmp_path)

    result = DatabaseService(tmp_path, dbx=FakeDbx()).discover()

    event = StateStore(tmp_path).audit_events()[0]
    assert result.ok
    assert (event["event"], event["details"]["count"]) == ("database.discovered", 2)


def test_database_read_routes_connection_and_database_from_target_reference(tmp_path: Path) -> None:
    _workspace(tmp_path)
    workspace = WorkspaceService(tmp_path)
    workspace.set_database_connections(
        "backend", ("dbx://4b03f613-4dfb-4d50-abfa-3a73188f90cd/app",)
    )
    dbx = FakeDbx()

    result = DatabaseService(tmp_path, dbx=dbx).query(
        "backend",
        "dbx://4b03f613-4dfb-4d50-abfa-3a73188f90cd/app",
        "select 1",
    )

    assert result.ok
    assert dbx.executed == [("4b03f613-4dfb-4d50-abfa-3a73188f90cd/app", "select 1")]


def test_plan_investigation_prechecks_database_and_does_not_persist_audit(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)
    WorkspaceService(tmp_path).set_database_connections(
        "backend",
        ("dbx://mom-dev/app", "dbx://mom-prod"),
        ("dbx://mom-prod",),
    )
    before = len(StateStore(tmp_path).audit_events())
    dbx = FakeDbx()

    result = DatabaseService(tmp_path, dbx=dbx).investigate(
        "backend",
        "dbx://mom-dev/app",
        "select * from orders limit 5",
        purpose="追溯一期订单口径",
    )

    assert result.ok
    assert result.data["scope"] == {
        "investigation_id": result.data["scope"]["investigation_id"],
        "mode": "planning_read_only",
        "project_id": "backend",
        "connection_ref": "dbx://mom-dev/app",
        "purpose": "追溯一期订单口径",
        "verified_database": "app",
        "query_hash": result.data["scope"]["query_hash"],
        "persisted": False,
    }
    assert result.data["scope"]["investigation_id"].startswith("INV-")
    assert dbx.executed == [
        ("mom-dev/app", "select current_database()"),
        ("mom-dev/app", "select * from orders limit 5"),
    ]
    assert len(StateStore(tmp_path).audit_events()) == before


def test_plan_investigation_blocks_production_and_write_sql(tmp_path: Path) -> None:
    _workspace(tmp_path)
    dbx = FakeDbx()
    database = DatabaseService(tmp_path, dbx=dbx)

    production = database.investigate(
        "backend",
        "dbx://mom-prod",
        "select 1",
        purpose="调查生产结构",
    )
    write = database.investigate(
        "backend",
        "dbx://mom-dev",
        "update orders set status = 'done' where id = 1",
        purpose="调查更新逻辑",
    )
    missing_purpose = database.investigate(
        "backend",
        "dbx://mom-dev",
        "select 1",
        purpose="",
    )

    assert production.code == "DATABASE_PRODUCTION_INVESTIGATION_BLOCKED"
    assert write.code == "DATABASE_INVESTIGATION_READ_ONLY"
    assert missing_purpose.code == "DATABASE_INVESTIGATION_PURPOSE_REQUIRED"
    assert dbx.executed == []


def test_plan_investigation_blocks_explicit_database_mismatch(tmp_path: Path) -> None:
    _workspace(tmp_path)
    WorkspaceService(tmp_path).set_database_connections(
        "backend",
        ("dbx://mom-dev/app",),
    )
    dbx = FakeDbx(current_database="postgres")

    result = DatabaseService(tmp_path, dbx=dbx).investigate(
        "backend",
        "dbx://mom-dev/app",
        "select 1",
        purpose="核对目标库",
    )

    assert result.code == "DATABASE_TARGET_MISMATCH"
    assert result.data["expected_database"] == "app"
    assert result.data["actual_database"] == "postgres"
    assert dbx.executed == [("mom-dev/app", "select current_database()")]


def test_database_write_needs_approval_and_never_targets_production(tmp_path: Path) -> None:
    requirement_id = _workspace(tmp_path)
    dbx = FakeDbx()
    database = DatabaseService(tmp_path, dbx=dbx)
    sql = "update orders set status = 'done' where id = 1"

    denied = database.query("backend", "dbx://mom-dev", sql)
    missing_context = database.query("backend", "dbx://mom-dev", sql, approved=True)
    approved = database.query(
        "backend",
        "dbx://mom-dev",
        sql,
        approved=True,
        write_context=_write_context(requirement_id),
    )
    production = database.query(
        "backend",
        "dbx://mom-prod",
        sql,
        approved=True,
        write_context=_write_context(requirement_id),
    )

    assert denied.code == "DATABASE_WRITE_APPROVAL_REQUIRED"
    assert missing_context.code == "DATABASE_WRITE_CONTEXT_REQUIRED"
    assert approved.ok
    assert approved.data["artifact_id"].startswith("ART-")
    assert production.code == "DATABASE_PRODUCTION_WRITE_BLOCKED"
    assert dbx.executed == [("mom-dev", sql)]
