"""Read the single user-facing command registry."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Iterable


TASK_ENTRYPOINT = "task"
DISPATCH_GROUPS = {"context", "req", "project", "etl", "docs", "gate", "delivery", "role", "system"}
ROOT_DIR = Path(__file__).resolve().parents[3]
COMMANDS_FILE = ROOT_DIR / ".praxis" / "commands.toml"


def praxis_usage(path: str) -> str:
    """Render a canonical command path as shell text."""
    path = path.strip()
    if not path:
        return TASK_ENTRYPOINT
    group, _, rest = path.partition(" ")
    return f"{TASK_ENTRYPOINT} {group} -- {rest}" if rest and group in DISPATCH_GROUPS else f"{TASK_ENTRYPOINT} {path}"


def _registered_argv() -> list[str]:
    if not COMMANDS_FILE.is_file():
        return []
    payload = tomllib.loads(COMMANDS_FILE.read_text(encoding="utf-8"))
    return [str(item["argv"]).strip() for item in payload.get("command", []) if item.get("argv")]


def praxis_command_lines() -> list[str]:
    return sorted(set(_registered_argv()))


def praxis_commands() -> list[str]:
    """Return command paths derived from `.praxis/commands.toml`."""
    paths: list[str] = []
    for argv in praxis_command_lines():
        path = argv.removeprefix(f"{TASK_ENTRYPOINT} ")
        if " -- " in path:
            group, rest = path.split(" -- ", 1)
            path = f"{group} {rest}"
        paths.append(path)
    return paths


def praxis_command_count() -> int:
    return len(praxis_commands())


REQUIRED_COMMAND_GROUPS = ["req", "project", "context", "gate", "delivery", "system"]


def validate_required_command_groups(groups: Iterable[str]) -> list[str]:
    existing = {command.split(" ", 1)[0] for command in praxis_commands() if command}
    return [f"missing praxis command group: {group}" for group in groups if group not in existing]
