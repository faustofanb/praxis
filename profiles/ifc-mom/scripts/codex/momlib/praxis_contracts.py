"""Centralized Praxis command declarations used by dispatch, help, and audits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


TASK_ENTRYPOINT = "task"
PRACTICE_ENTRYPOINT = TASK_ENTRYPOINT
DISPATCH_GROUPS = {"context", "req", "project", "etl", "gate", "delivery", "role", "system"}


@dataclass(frozen=True)
class PraxisCommand:
    """A lightweight command contract used for command discovery and reporting."""

    path: str
    kind: str = "praxis"
    deprecated: bool = False


def praxis_usage(path: str) -> str:
    """Render a full command string for a Praxis command path."""
    if not path:
        return TASK_ENTRYPOINT
    parts = path.split(" ", 1)
    group = parts[0]
    if group in DISPATCH_GROUPS and len(parts) > 1:
        return f"{TASK_ENTRYPOINT} {group} -- {parts[1]}"
    return f"{TASK_ENTRYPOINT} {path}"


def _to_path(path: str) -> str:
    return path.strip()


def praxis_commands() -> list[str]:
    """Return canonical user-facing Praxis command forms."""
    return sorted({_to_path(item.path) for item in COMMANDS})


def praxis_command_lines() -> list[str]:
    """Return canonical commands as fully rendered shell text."""
    return [praxis_usage(path) for path in praxis_commands()]


def legacy_aliases() -> list[str]:
    """Commands kept only for compatibility, not primary route."""
    return ["project", "context", "etl", "workflow"]


def praxis_command_count() -> int:
    """Number of canonical Praxis paths, including grouped forms."""
    return len(praxis_commands())


COMMANDS: tuple[PraxisCommand, ...] = (
    PraxisCommand("check"),
    PraxisCommand("index"),
    PraxisCommand("formalism-check"),
    PraxisCommand("evolve propose"),
    PraxisCommand("runtime-eval"),
    PraxisCommand("runtime-eval --benchmark"),
    PraxisCommand("command-audit"),
    PraxisCommand("policy-check"),
    PraxisCommand("adapter-plan"),
    PraxisCommand("trace-summary"),
    PraxisCommand("code-graph build"),
    PraxisCommand("code-graph query [--refresh] <keyword>"),
    PraxisCommand("code-graph check"),
    PraxisCommand("template-check"),
    PraxisCommand("template-render rule|skill <slug> <title> <description> <output>"),
    PraxisCommand("system check"),
    PraxisCommand("system index"),
    PraxisCommand("system praxis-profile"),
    PraxisCommand("system formalism-check"),
    PraxisCommand("system evolve propose"),
    PraxisCommand("system runtime-eval"),
    PraxisCommand("system command-audit"),
    PraxisCommand("system policy-check"),
    PraxisCommand("system adapter-plan"),
    PraxisCommand("system trace-summary"),
    PraxisCommand("system code-graph build"),
    PraxisCommand("system code-graph query [--refresh] <keyword>"),
    PraxisCommand("system code-graph check"),
    PraxisCommand("system template-check"),
    PraxisCommand("system template-render rule|skill <slug> <title> <description> <output>"),
    PraxisCommand("req init <需求名> <用户原始需求原文>"),
    PraxisCommand("req iter <需求名> <analysis|plan|progress> <主题>"),
    PraxisCommand("req iter <需求名> <analysis|plan|progress> <主题> --body-file <阶段正文.md>"),
    PraxisCommand("req check <需求名>"),
    PraxisCommand("req index <需求名>"),
    PraxisCommand("req db-plan <需求名>"),
    PraxisCommand("project <status|verify|run|shell|worktree|start> <project> [<需求名>|<任务名>|<用户原始需求原文>]"),
    PraxisCommand("project preflight <project> <需求名>"),
    PraxisCommand("project finish <project> <需求名>"),
    PraxisCommand("project commit-split <project> <需求名> <结构化提交信息>"),
    PraxisCommand("project deliver <project> <需求名>"),
    PraxisCommand("project cleanup <project> <需求名>"),
    PraxisCommand("project guard <project> <需求名>"),
    PraxisCommand("project change-check <project> <需求名>"),
    PraxisCommand("project migration-check <project> <需求名>"),
    PraxisCommand("context --brief <project> <需求名>"),
    PraxisCommand("context <project> <需求名>"),
    PraxisCommand("etl init"),
    PraxisCommand("etl subject <应用> <系统> <一级菜单> <中文主题> ..."),
    PraxisCommand("etl tree"),
    PraxisCommand("gate guard <project> <需求名>"),
    PraxisCommand("gate change-check <project> <需求名>"),
    PraxisCommand("gate migration-check <project> <需求名>"),
    PraxisCommand("gate ready <project> <需求名>"),
    PraxisCommand("gate validate-verdict quality|delivery <project> <需求名> <json-file>"),
    PraxisCommand("role handoff <quality|delivery|execution|knowledge> <project> <需求名> <summary>"),
    PraxisCommand("role lock <execution|delivery|quality|knowledge> <project> <需求名> <路径1> [路径2...]"),
    PraxisCommand("delivery finish <project> <需求名>"),
    PraxisCommand("delivery commit-split <project> <需求名> <结构化提交信息>"),
    PraxisCommand("delivery deliver <project> <需求名>"),
    PraxisCommand("delivery cleanup <project> <需求名>"),
)


REQUIRED_COMMAND_GROUPS = ["req", "project", "context", "gate", "delivery", "system"]


def validate_required_command_groups(groups: Iterable[str]) -> list[str]:
    """Return validation errors for missing top-level command groups."""
    existing: set[str] = {command.path.split(" ", 1)[0] for command in COMMANDS if " " in command.path}
    return [f"missing praxis command group: {group}" for group in groups if group not in existing]
