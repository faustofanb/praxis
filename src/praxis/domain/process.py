from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class CommandIntent(StrEnum):
    INSPECT = "inspect"
    BUILD = "build"
    TEST = "test"
    EDIT = "edit"
    DATABASE_READ = "database_read"
    DATABASE_WRITE = "database_write"
    DEPLOY = "deploy"


@dataclass(slots=True, frozen=True)
class ProcessRequest:
    argv: tuple[str, ...]
    cwd: Path
    intent: CommandIntent
    timeout_seconds: float = 300
    environment: dict[str, str] | None = None
