from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from praxis.result import Result

Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


class WitrService:
    def __init__(self, root: Path | str, *, run: Runner | None = None):
        self.root = Path(root)
        self.run = run or self._run

    @staticmethod
    def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)

    def diagnose(self, arguments: list[str], *, explicit: bool) -> Result:
        if not explicit:
            return Result(False, "WITR_EXPLICIT_REQUIRED")
        try:
            command = ["witr", *arguments]
            if "--json" not in command:
                command.append("--json")
            process = self.run(command, self.root)
        except FileNotFoundError:
            return Result(False, "WITR_NOT_AVAILABLE")
        if process.returncode:
            return Result(False, "WITR_FAILED", data={"stderr": process.stderr})
        try:
            data = json.loads(process.stdout)
        except json.JSONDecodeError:
            data = {"output": process.stdout}
        return Result(True, data=redact_runtime_data(data))


def redact_runtime_data(value: Any, key: str = "") -> Any:
    if key.lower() in {"password", "secret", "token", "api_key", "access_token"}:
        return "[已脱敏]"
    if isinstance(value, dict):
        return {
            item_key: redact_runtime_data(item, item_key) for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_runtime_data(item) for item in value]
    return value
