from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class RequirementStatus(StrEnum):
    CAPTURED = "captured"
    INVESTIGATING = "investigating"
    ANALYZED = "analyzed"
    PLANNED = "planned"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    VERIFYING = "verifying"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


_NEXT_STATUS: dict[RequirementStatus, frozenset[RequirementStatus]] = {
    RequirementStatus.CAPTURED: frozenset({RequirementStatus.INVESTIGATING}),
    RequirementStatus.INVESTIGATING: frozenset({RequirementStatus.ANALYZED}),
    RequirementStatus.ANALYZED: frozenset({RequirementStatus.PLANNED}),
    RequirementStatus.PLANNED: frozenset({RequirementStatus.READY}),
    RequirementStatus.READY: frozenset({RequirementStatus.IN_PROGRESS}),
    RequirementStatus.IN_PROGRESS: frozenset(
        {RequirementStatus.IMPLEMENTED, RequirementStatus.BLOCKED}
    ),
    RequirementStatus.IMPLEMENTED: frozenset(
        {RequirementStatus.VERIFYING, RequirementStatus.BLOCKED}
    ),
    RequirementStatus.VERIFYING: frozenset(
        {RequirementStatus.COMPLETED, RequirementStatus.BLOCKED}
    ),
    RequirementStatus.BLOCKED: frozenset({RequirementStatus.IN_PROGRESS}),
    RequirementStatus.COMPLETED: frozenset({RequirementStatus.ARCHIVED}),
    RequirementStatus.CANCELLED: frozenset(),
    RequirementStatus.ARCHIVED: frozenset(),
}

_ADVANCE_STATUS = {
    RequirementStatus.CAPTURED: RequirementStatus.INVESTIGATING,
    RequirementStatus.INVESTIGATING: RequirementStatus.ANALYZED,
    RequirementStatus.ANALYZED: RequirementStatus.PLANNED,
    RequirementStatus.PLANNED: RequirementStatus.READY,
    RequirementStatus.READY: RequirementStatus.IN_PROGRESS,
    RequirementStatus.IN_PROGRESS: RequirementStatus.IMPLEMENTED,
    RequirementStatus.IMPLEMENTED: RequirementStatus.VERIFYING,
    RequirementStatus.VERIFYING: RequirementStatus.COMPLETED,
    RequirementStatus.COMPLETED: RequirementStatus.ARCHIVED,
}


def next_requirement_status(status: RequirementStatus) -> RequirementStatus | None:
    return _ADVANCE_STATUS.get(status)


@dataclass(slots=True, frozen=True)
class Requirement:
    requirement_id: str
    short_name: str
    status: RequirementStatus = RequirementStatus.CAPTURED

    def transition(self, target: RequirementStatus) -> Requirement:
        if target == RequirementStatus.CANCELLED and self.status not in {
            RequirementStatus.COMPLETED,
            RequirementStatus.CANCELLED,
            RequirementStatus.ARCHIVED,
        }:
            return replace(self, status=target)
        if target not in _NEXT_STATUS[self.status]:
            raise ValueError(f"非法需求状态转换：{self.status.value} -> {target.value}")
        return replace(self, status=target)

    def reopen(self, expected_source: RequirementStatus | None = None) -> Requirement:
        if self.status not in {
            RequirementStatus.VERIFYING,
            RequirementStatus.IMPLEMENTED,
        }:
            raise ValueError("只有验证中或已实施的需求可以重开到开发中")
        if expected_source is not None and self.status is not expected_source:
            raise ValueError(
                f"指定的回退来源 {expected_source.value} 与当前状态 {self.status.value} 不一致"
            )
        return replace(self, status=RequirementStatus.IN_PROGRESS)
