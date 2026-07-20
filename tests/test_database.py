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
    def __init__(self) -> None:
        self.executed: list[tuple[str, str]] = []

    def list_connections(self) -> Result:
        return Result(True, data={"connections": [{"name": "mom-dev"}, {"name": "mom-prod"}]})

    def discover(self) -> Result:
        return self.list_connections()

    def execute(self, connection: str, sql: str, *, database: str | None = None) -> Result:
        target = f"{connection}/{database}" if database else connection
        self.executed.append((target, sql))
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
