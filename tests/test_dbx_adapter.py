from __future__ import annotations

import subprocess
from pathlib import Path

from praxis.integrations.dbx import DbxAdapter


def test_dbx_adapter_uses_documented_json_cli_contract(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        stdout = (
            '[{"name":"mom-dev"}]'
            if command[1:3] == ["connections", "list"]
            else '{"rows":[{"value":1}]}'
        )
        return subprocess.CompletedProcess(command, 0, stdout, "")

    dbx = DbxAdapter(tmp_path, run=run)

    connections = dbx.list_connections()
    query = dbx.execute("mom-dev", "select 1")

    assert connections.data["connections"] == [{"name": "mom-dev"}]
    assert query.data["rows"] == [{"value": 1}]
    assert commands == [
        ["dbx", "connections", "list", "--json"],
        ["dbx", "query", "mom-dev", "select 1", "--json"],
    ]


def test_dbx_adapter_reports_missing_binary(tmp_path: Path) -> None:
    def missing(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(command[0])

    result = DbxAdapter(tmp_path, run=missing).list_connections()

    assert result.code == "DBX_NOT_AVAILABLE"


def test_dbx_adapter_redacts_secret_fields(tmp_path: Path) -> None:
    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            '{"name":"mom-dev","password":"secret","nested":{"token":"secret"}}',
            "",
        )

    result = DbxAdapter(tmp_path, run=run).list_connections()

    assert result.data["connections"]["password"] == "[已脱敏]"
    assert result.data["connections"]["nested"]["token"] == "[已脱敏]"
