from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from praxis.artifacts.service import ArtifactService
from praxis.documents.atomic_writer import atomic_write_text
from praxis.gates.sql import inspect_sql
from praxis.integrations.dbx import DbxAdapter
from praxis.naming.requirement import RequirementPathPolicy
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService

_WRITE_CONTEXT = {
    "requirement_id",
    "stage",
    "purpose",
    "parameters",
    "precheck",
    "postimpact",
    "approval",
}


class Dbx(Protocol):
    def list_connections(self) -> Result: ...

    def execute(self, connection: str, sql: str) -> Result: ...


class DatabaseService:
    def __init__(self, root: Path | str, *, dbx: Dbx | None = None):
        self.root = Path(root)
        self.dbx = dbx or DbxAdapter(self.root)
        self.store = StateStore(self.root)

    def connections(self, project_id: str) -> Result:
        project = WorkspaceService(self.root).project(project_id)
        external = self.dbx.list_connections()
        if not external.ok:
            return external
        return Result(
            True,
            data={
                "registered": list(project.database_connections),
                "production": list(project.production_database_connections),
                "dbx": external.data["connections"],
            },
        )

    def query(
        self,
        project_id: str,
        connection_ref: str,
        sql: str,
        *,
        approved: bool = False,
        read_allowed: bool = True,
        write_context: dict[str, object] | None = None,
    ) -> Result:
        project = WorkspaceService(self.root).project(project_id)
        if connection_ref not in project.database_connections:
            return self._deny("DATABASE_CONNECTION_NOT_REGISTERED", project_id, connection_ref)
        decision = inspect_sql(sql)
        if not decision.ok:
            return self._deny(decision.code, project_id, connection_ref)
        kind = decision.data["kind"]
        if kind == "read" and not read_allowed:
            return self._deny("DATABASE_READ_NOT_AUTHORIZED", project_id, connection_ref)
        if kind == "write":
            if connection_ref in project.production_database_connections:
                return self._deny("DATABASE_PRODUCTION_WRITE_BLOCKED", project_id, connection_ref)
            if not approved:
                return self._deny("DATABASE_WRITE_APPROVAL_REQUIRED", project_id, connection_ref)
            missing = sorted(
                key
                for key in _WRITE_CONTEXT
                if key not in (write_context or {})
                or (write_context or {}).get(key) is None
                or (write_context or {}).get(key) == ""
            )
            if missing:
                return Result(
                    False,
                    "DATABASE_WRITE_CONTEXT_REQUIRED",
                    data={"missing": missing, "connection_ref": connection_ref},
                )

        artifact_id: str | None = None
        if kind == "write":
            assert write_context is not None
            artifact = self._register_sql(connection_ref, sql, write_context)
            if not artifact.ok:
                return artifact
            artifact_id = artifact.data["artifact_id"]

        result = self.dbx.execute(_connection_name(connection_ref), sql)
        audit_id = self.store.audit(
            "database.execute",
            result.code,
            {
                "project_id": project_id,
                "connection_ref": connection_ref,
                "kind": kind,
                "operation": decision.data["operation"],
            },
        )
        return Result(
            result.ok,
            result.code,
            data={
                **result.data,
                "kind": kind,
                "connection_ref": connection_ref,
                "audit_id": audit_id,
                "artifact_id": artifact_id,
            },
            diagnostics=result.diagnostics,
        )

    def _deny(self, code: str, project_id: str, connection_ref: str) -> Result:
        audit_id = self.store.audit(
            "database.denied",
            code,
            {"project_id": project_id, "connection_ref": connection_ref},
        )
        return Result(False, code, data={"connection_ref": connection_ref, "audit_id": audit_id})

    def _register_sql(
        self, connection_ref: str, sql: str, context: dict[str, object]
    ) -> Result:
        requirement = self.store.requirement(str(context["requirement_id"]))
        if not requirement:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        workspace = WorkspaceService(self.root).load()
        requirement_root = RequirementPathPolicy(
            self.root / workspace["knowledge_root"]
        ).requirement_path(requirement["requirement_id"], requirement["short_name"])
        timestamp = datetime.now(UTC)
        path = (
            requirement_root
            / "产出物"
            / "SQL"
            / f"SQL-{timestamp:%Y%m%dT%H%M%S}-{uuid4().hex[:8].upper()}.sql"
        )
        atomic_write_text(path, sql.rstrip() + "\n")
        metadata = {
            key: value for key, value in context.items() if key not in {"requirement_id"}
        }
        metadata["connection_ref"] = connection_ref
        return ArtifactService(self.root).add(
            requirement["requirement_id"],
            "sql",
            path,
            stage=str(context["stage"]),
            metadata=metadata,
        )


def _connection_name(connection_ref: str) -> str:
    prefix = "dbx://"
    if not connection_ref.startswith(prefix) or not connection_ref.removeprefix(prefix):
        raise ValueError("数据库连接必须使用 dbx:// 引用")
    return connection_ref.removeprefix(prefix)
