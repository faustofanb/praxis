from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from praxis.result import Result


class GateEvent(StrEnum):
    REQUIREMENT_CAPTURED = "requirement_captured"
    REQUIREMENT_READY = "requirement_ready"
    WORKTREE_PRE_START = "worktree_pre_start"
    WORKTREE_POST_START = "worktree_post_start"
    BEFORE_AGENT = "before_agent"
    BEFORE_TOOL = "before_tool"
    AFTER_EDIT = "after_edit"
    COMMIT_MESSAGE = "commit_message"
    PRE_COMMIT = "pre_commit"
    PRE_MERGE = "pre_merge"
    PRE_RELEASE = "pre_release"
    DATABASE_WRITE = "database_write"
    DEPLOYMENT = "deployment"
    TASK_START = "task_start"
    CHANGE_PREFLIGHT = "change_preflight"
    VERIFY = "verify"
    WORKTREE_PRE_MERGE = "worktree_pre_merge"
    DELIVERY = "delivery"
    WORKSPACE_SCAN = "workspace_scan"


Gate = Callable[[dict[str, object]], Result]


class GateEngine:
    def __init__(self):
        self._gates: dict[GateEvent, list[Gate]] = {event: [] for event in GateEvent}

    def register(self, event: GateEvent, gate: Gate) -> None:
        self._gates[event].append(gate)

    def run(self, event: GateEvent, context: dict[str, object] | None = None) -> Result:
        results = []
        for gate in self._gates[event]:
            result = gate(context or {})
            results.append(result.to_dict())
            if not result.ok:
                return Result(False, result.code, data={"event": event, "results": results})
        return Result(True, data={"event": event, "results": results})
