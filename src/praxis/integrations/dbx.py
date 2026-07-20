from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from praxis.integrations.process import ProcessRunner, Runner
from praxis.result import Result

_SECRET_KEYS = {"password", "password_ref", "secret", "token", "access_token", "api_key"}


class DbxAdapter:
    """Thin adapter over the documented @dbx-app/cli JSON commands."""

    def __init__(self, root: Path | str, *, run: Runner | None = None):
        self.runner = ProcessRunner(root, run=run)

    def list_connections(self) -> Result:
        result = self.runner.run(["dbx", "connections", "list", "--json"], machine_output=True)
        return self._json_result(result, "connections")

    def execute(self, connection: str, sql: str) -> Result:
        result = self.runner.run(
            ["dbx", "query", connection, sql, "--json"], machine_output=True
        )
        return self._json_result(result)

    @staticmethod
    def _json_result(result: Result, key: str | None = None) -> Result:
        if not result.ok:
            code = "DBX_NOT_AVAILABLE" if result.code == "COMMAND_NOT_AVAILABLE" else "DBX_FAILED"
            return Result(False, code, data={"stderr": result.data.get("stderr", "")})
        try:
            payload = _redact(json.loads(result.data["stdout"]))
        except (json.JSONDecodeError, TypeError):
            return Result(False, "DBX_INVALID_RESPONSE")
        if key:
            if isinstance(payload, dict) and key in payload:
                payload = payload[key]
            return Result(True, data={key: payload})
        return Result(True, data=payload if isinstance(payload, dict) else {"result": payload})


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[已脱敏]" if key.lower() in _SECRET_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
