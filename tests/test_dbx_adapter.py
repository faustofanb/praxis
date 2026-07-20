from __future__ import annotations

from pathlib import Path
from typing import Any

from praxis.integrations.dbx import DbxAdapter


def test_dbx_adapter_uses_mcp_tools_and_database_target(tmp_path: Path) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(name: str, arguments: dict[str, Any]) -> str:
        calls.append((name, arguments))
        if name == "dbx_list_connections":
            return (
                "| ID | Name | Type | Database |\n|---|---|---|---|\n"
                "| abc | DEV | postgres | app |"
            )
        return "| value |\n|---|\n| 1 |\n(1 row)"

    dbx = DbxAdapter(tmp_path, call_tool=call_tool)

    connections = dbx.list_connections()
    query = dbx.execute("abc", "select 1", database="app")

    assert connections.data["connections"] == [
        {"id": "abc", "name": "DEV", "type": "postgres", "database": "app"}
    ]
    assert query.data["rows"] == [{"value": "1"}]
    assert calls == [
        ("dbx_list_connections", {}),
        (
            "dbx_execute_query",
            {"connection_name": "abc", "database": "app", "sql": "select 1"},
        ),
    ]


def test_dbx_adapter_uses_connection_id_for_uuid(tmp_path: Path) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(name: str, arguments: dict[str, Any]) -> str:
        calls.append((name, arguments))
        return "| value |\n|---|\n| 1 |"

    connection_id = "4b03f613-4dfb-4d50-abfa-3a73188f90cd"
    DbxAdapter(tmp_path, call_tool=call_tool).execute(connection_id, "select 1")

    assert calls == [
        ("dbx_execute_query", {"connection_id": connection_id, "sql": "select 1"})
    ]


def test_dbx_adapter_discovers_databases_via_mcp(tmp_path: Path) -> None:
    def call_tool(name: str, arguments: dict[str, Any]) -> str:
        if name == "dbx_list_connections":
            return (
                "| ID | Name | Type | Database |\n|---|---|---|---|\n"
                "| pg-id | DEV | postgres | app |\n"
                "| ms-id | U9 | sqlserver | U9 |"
            )
        database = "app" if arguments.get("connection_name") == "pg-id" else "U9"
        return f"| name |\n|---|\n| {database} |\n(1 row)"

    result = DbxAdapter(tmp_path, call_tool=call_tool).discover()

    assert result.ok
    assert result.data["connections"][0]["databases"] == ["app"]
    assert result.data["connections"][1]["databases"] == ["U9"]


def test_dbx_adapter_reports_missing_mcp_server(tmp_path: Path) -> None:
    def missing(name: str, arguments: dict[str, Any]) -> str:
        raise FileNotFoundError("dbx-mcp-server")

    result = DbxAdapter(tmp_path, call_tool=missing).list_connections()

    assert result.code == "DBX_NOT_AVAILABLE"


def test_dbx_adapter_redacts_secret_fields(tmp_path: Path) -> None:
    def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"name": "mom-dev", "password": "secret", "nested": {"token": "secret"}}

    result = DbxAdapter(tmp_path, call_tool=call_tool).list_connections()

    assert result.data["connections"]["password"] == "[已脱敏]"
    assert result.data["connections"]["nested"]["token"] == "[已脱敏]"
