from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from praxis.integrations.process import ProcessRunner, Runner
from praxis.result import Result

_SECRET_KEYS = {"password", "password_ref", "secret", "token", "access_token", "api_key"}
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.I,
)
_CallTool = Callable[[str, dict[str, Any]], Any]


class DbxAdapter:
    """DBX CLI first, with MCP for database-scoped targets and fallback."""

    def __init__(
        self,
        root: Path | str,
        *,
        run: Runner | None = None,
        call_tool: _CallTool | None = None,
    ):
        self.root = Path(root)
        self.runner = ProcessRunner(root, run=run)
        self.call_tool = call_tool or self._call_tool

    def list_connections(self) -> Result:
        cli = self.runner.run(["dbx", "connections", "list", "--json"], machine_output=True)
        if cli.ok:
            try:
                payload = json.loads(cli.data["stdout"])
                connections = (
                    payload.get("connections", payload) if isinstance(payload, dict) else payload
                )
                return Result(
                    True, data={"connections": _redact(connections), "transport": "cli"}
                )
            except (json.JSONDecodeError, TypeError):
                pass
        try:
            payload = self.call_tool("dbx_list_connections", {})
            connections = _payload(payload)
            if isinstance(connections, str):
                connections = _markdown_rows(connections)
            return Result(
                True,
                data={
                    "connections": _redact(connections),
                    "transport": "mcp",
                    "cli_code": cli.code,
                },
            )
        except FileNotFoundError:
            return Result(False, "DBX_NOT_AVAILABLE")
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            return Result(False, "DBX_FAILED", data={"message": str(error)})

    def discover(self) -> Result:
        connections = self.list_connections()
        if not connections.ok:
            return connections
        discovered = []
        for connection in connections.data["connections"]:
            if not isinstance(connection, dict):
                continue
            item = dict(connection)
            db_type = str(item.get("type", "")).casefold()
            query = _database_inventory_query(db_type)
            if not query:
                item["databases"] = [item["database"]] if item.get("database") else []
                discovered.append(item)
                continue
            target = str(item.get("id") or item.get("name") or "")
            result = self.execute(target, query)
            item["databases"] = (
                [str(row["name"]) for row in result.data.get("rows", []) if row.get("name")]
                if result.ok
                else ([str(item["database"])] if item.get("database") else [])
            )
            discovered.append(item)
        return Result(
            True,
            data={"connections": discovered, "transport": connections.data["transport"]},
        )

    def execute(self, connection: str, sql: str, *, database: str | None = None) -> Result:
        if database is None:
            cli = self.runner.run(
                ["dbx", "query", connection, sql, "--json"], machine_output=True
            )
            if cli.ok:
                try:
                    payload = json.loads(cli.data["stdout"])
                    if not isinstance(payload, dict):
                        payload = {"result": payload}
                    return Result(True, data={**_redact(payload), "transport": "cli"})
                except (json.JSONDecodeError, TypeError):
                    pass
        arguments: dict[str, Any] = {"sql": sql}
        key = "connection_id" if _UUID.fullmatch(connection) else "connection_name"
        arguments[key] = connection
        if database:
            arguments["database"] = database
        try:
            payload = _payload(self.call_tool("dbx_execute_query", arguments))
            if isinstance(payload, str):
                payload = {"rows": _markdown_rows(payload)}
            elif isinstance(payload, list):
                payload = {"rows": payload}
            if not isinstance(payload, dict):
                payload = {"result": payload}
            return Result(True, data={**_redact(payload), "transport": "mcp"})
        except FileNotFoundError:
            return Result(False, "DBX_NOT_AVAILABLE")
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            return Result(False, "DBX_FAILED", data={"message": str(error)})

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return anyio.run(self._call_tool_async, name, arguments)

    async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> Any:
        parameters = StdioServerParameters(
            command="dbx-mcp-server",
            env={"DBX_MCP_ALLOW_WRITES": "0"},
            cwd=self.root,
        )
        with Path(os.devnull).open("w") as errlog:
            async with (
                stdio_client(parameters, errlog=errlog) as streams,
                ClientSession(*streams) as session,
            ):
                await session.initialize()
                return await session.call_tool(name, arguments)


def _payload(value: Any) -> Any:
    structured = getattr(value, "structuredContent", None)
    if structured is not None:
        return structured
    content = getattr(value, "content", None)
    if content is not None:
        texts = [item.text for item in content if getattr(item, "text", None)]
        return "\n".join(texts)
    return value


def _markdown_rows(value: str) -> list[dict[str, str]]:
    table = [line.strip() for line in value.splitlines() if line.strip().startswith("|")]
    if len(table) < 2:
        raise ValueError("DBX MCP 返回了无法识别的表格")
    headers = [cell.strip().casefold() for cell in table[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in table[2:]:
        values = [cell.strip() for cell in line.strip("|").split("|")]
        if len(values) == len(headers):
            rows.append(dict(zip(headers, values, strict=True)))
    return rows


def _database_inventory_query(db_type: str) -> str | None:
    if db_type in {"postgres", "postgresql"}:
        return (
            "SELECT datname AS name FROM pg_database "
            "WHERE datistemplate = false ORDER BY datname"
        )
    if db_type in {"sqlserver", "mssql"}:
        return "SELECT name FROM sys.databases ORDER BY name"
    return None


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[已脱敏]" if key.lower() in _SECRET_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
