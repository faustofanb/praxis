from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PraxisError(Exception):
    code: str
    message: str
    exit_code: int = 2
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


class WorkspaceNotFound(PraxisError):
    def __init__(self, path: str):
        super().__init__("WORKSPACE_NOT_FOUND", "未找到 Praxis workspace。", 2, {"path": path})


class ConflictError(PraxisError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(code, message, 3, details or {})
