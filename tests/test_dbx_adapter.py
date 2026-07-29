from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from praxis.integrations.dbx import DbxAdapter


def test_dbx_adapter_uses_mcp_without_invoking_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def reject_cli(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("DBX CLI must not be called")

    monkeypatch.setattr(subprocess, "run", reject_cli)

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
    assert connections.data["transport"] == "mcp"
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
    def call_tool(name: str, arguments: dict[str, Any]) -> object:
        if name == "dbx_list_connections":
            return [
                {"name": "DEV", "type": "postgres", "database": "app"},
                {"name": "U9", "type": "sqlserver", "database": "U9"},
            ]
        target = arguments["connection_name"]
        return {"rows": [{"name": "app" if target == "DEV" else "U9"}]}

    result = DbxAdapter(tmp_path, call_tool=call_tool).discover()

    assert result.ok
    assert result.data["transport"] == "mcp"
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
