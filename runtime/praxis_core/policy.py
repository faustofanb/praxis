from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, NamedTuple, Sequence


class TaskPolicy(NamedTuple):
    path: str
    requires_requirement: bool
    requires_worktree: bool
    verification_level: str
    database_investigation: bool
    quality_review: str
    checks: tuple[str, ...]


VALID_MODES = {"quick", "formal"}
VALID_VERIFICATION_LEVELS = {"L0", "L1", "L2"}
RISK_PATH_PARTS = {
    "db",
    "database",
    "migration",
    "migrations",
    "flyway",
    "permission",
    "permissions",
    "auth",
    "report",
    "reports",
    "contract",
    "contracts",
}
RISK_SUFFIXES = {".sql"}


def resolve_task_policy(
    *,
    mode: str,
    project_kind: str,
    changed_files: Sequence[str] = (),
    manifest_task: dict[str, Any] | None = None,
) -> TaskPolicy:
    """Resolve one task into an executable verification and isolation contract."""
    if mode not in VALID_MODES:
        raise ValueError(f"unsupported task mode: {mode}")
    if not project_kind:
        raise ValueError("project_kind is required")

    task = manifest_task or {}
    level = str(task.get("verification_level") or ("L0" if mode == "quick" else "L1"))
    if level not in VALID_VERIFICATION_LEVELS:
        raise ValueError(f"unsupported verification level: {level}")
    database_investigation = bool(task.get("database_investigation", False))

    if mode == "quick":
        requires_requirement = bool(task.get("requires_requirement", False))
        if (
            level != "L0"
            or requires_requirement
            or database_investigation
            or any(_is_risky_path(path) for path in changed_files)
        ):
            raise ValueError("quick task exceeds L0 boundary; use formal task mode")
        return TaskPolicy(
            path="quick",
            requires_requirement=False,
            requires_worktree=bool(task.get("requires_worktree", project_kind != "docs")),
            verification_level="L0",
            database_investigation=False,
            quality_review="requires-authorization" if task.get("quality_review") is True else "waived-small-change",
            checks=_manifest_gates(task, ("changed-files", "syntax", "focused-contract-test")),
        )

    requires_worktree = bool(task.get("requires_worktree", project_kind != "docs"))
    quality_review = "requires-authorization" if level == "L2" or task.get("quality_review") is True else "optional"
    default_checks = {
        "L0": ("changed-files", "syntax"),
        "L1": ("changed-files", "syntax", "project-verify"),
        "L2": ("changed-files", "syntax", "project-verify", "risk-gates"),
    }[level]
    checks = _manifest_gates(task, default_checks)
    return TaskPolicy(
        path="formal",
        requires_requirement=True,
        requires_worktree=requires_worktree,
        verification_level=level,
        database_investigation=database_investigation,
        quality_review=quality_review,
        checks=checks,
    )


def _manifest_gates(task: dict[str, Any], default: tuple[str, ...]) -> tuple[str, ...]:
    raw_gates = task.get("gates")
    if raw_gates is None:
        return default
    if not isinstance(raw_gates, list) or not raw_gates or not all(isinstance(gate, str) and gate for gate in raw_gates):
        raise ValueError("task gates must be a non-empty string list")
    return tuple(raw_gates)


def _is_risky_path(raw_path: str) -> bool:
    path = PurePosixPath(raw_path.replace("\\", "/"))
    lowered_parts = {part.lower() for part in path.parts}
    return path.suffix.lower() in RISK_SUFFIXES or bool(lowered_parts & RISK_PATH_PARTS)
