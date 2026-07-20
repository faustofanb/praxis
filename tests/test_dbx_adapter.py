from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from praxis.integrations.dbx import DbxAdapter


def test_dbx_adapter_prefers_cli_and_uses_mcp_for_database_target(tmp_path: Path) -> None:
    commands: list[list[str]] = []
    calls: list[tuple[str, dict[str, Any]]] = []

    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {"connections": [{"name": "DEV", "type": "postgres", "database": "app"}]}
            ),
            "",
        )

    def call_tool(name: str, arguments: dict[str, Any]) -> str:
        calls.append((name, arguments))
        if name == "dbx_list_connections":
            return (
                "| ID | Name | Type | Database |\n|---|---|---|---|\n"
                "| abc | DEV | postgres | app |"
            )
        return "| value |\n|---|\n| 1 |\n(1 row)"

    dbx = DbxAdapter(tmp_path, run=run, call_tool=call_tool)

    connections = dbx.list_connections()
    query = dbx.execute("abc", "select 1", database="app")

    assert connections.data["connections"] == [
        {"name": "DEV", "type": "postgres", "database": "app"}
    ]
    assert connections.data["transport"] == "cli"
    assert query.data["rows"] == [{"value": "1"}]
    assert calls == [
        (
            "dbx_execute_query",
            {"connection_name": "abc", "database": "app", "sql": "select 1"},
        ),
    ]
    assert commands == [["dbx", "connections", "list", "--json"]]


def test_dbx_adapter_uses_connection_id_for_uuid(tmp_path: Path) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(name: str, arguments: dict[str, Any]) -> str:
        calls.append((name, arguments))
        return "| value |\n|---|\n| 1 |"

    connection_id = "4b03f613-4dfb-4d50-abfa-3a73188f90cd"
    def missing(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(command[0])

    DbxAdapter(tmp_path, run=missing, call_tool=call_tool).execute(connection_id, "select 1")

    assert calls == [
        ("dbx_execute_query", {"connection_id": connection_id, "sql": "select 1"})
    ]


def test_dbx_adapter_discovers_databases_via_cli(tmp_path: Path) -> None:
    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if command[1:3] == ["connections", "list"]:
            payload = {
                "connections": [
                    {"name": "DEV", "type": "postgres", "database": "app"},
                    {"name": "U9", "type": "sqlserver", "database": "U9"},
                ]
            }
        else:
            payload = {"rows": [{"name": "app" if command[2] == "DEV" else "U9"}]}
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    result = DbxAdapter(tmp_path, run=run).discover()

    assert result.ok
    assert result.data["connections"][0]["databases"] == ["app"]
    assert result.data["connections"][1]["databases"] == ["U9"]


def test_dbx_adapter_reports_missing_mcp_server(tmp_path: Path) -> None:
    def missing_cli(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(command[0])

    def missing(name: str, arguments: dict[str, Any]) -> str:
        raise FileNotFoundError("dbx-mcp-server")

    result = DbxAdapter(tmp_path, run=missing_cli, call_tool=missing).list_connections()

    assert result.code == "DBX_NOT_AVAILABLE"


def test_dbx_adapter_redacts_secret_fields(tmp_path: Path) -> None:
    def missing_cli(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(command[0])

    def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"name": "mom-dev", "password": "secret", "nested": {"token": "secret"}}

    result = DbxAdapter(tmp_path, run=missing_cli, call_tool=call_tool).list_connections()

    assert result.data["connections"]["password"] == "[已脱敏]"
    assert result.data["connections"]["nested"]["token"] == "[已脱敏]"
