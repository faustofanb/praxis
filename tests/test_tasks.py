from __future__ import annotations

from pathlib import Path

from praxis.knowledge.requirements import RequirementService
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.tasks.service import TaskService
from praxis.workspace.service import WorkspaceService


def test_task_start_is_blocked_when_required_graph_is_unavailable(tmp_path: Path) -> None:
    service = TaskService(tmp_path, context_gate=lambda project, required: Result(False, "STALE"))
    result = service.start("T-1", "Investigate", "backend", graph_required=True)
    assert not result.ok
    assert service.inspect("T-1") is None
    gate = StateStore(tmp_path).audit_events()[0]
    assert (gate["event"], gate["code"], gate["details"]["event"]) == (
        "gate.run",
        "STALE",
        "task_start",
    )


def test_high_risk_task_requires_graph_before_any_failure(tmp_path: Path) -> None:
    required_values: list[bool] = []

    def gate(project: str, required: bool) -> Result:
        required_values.append(required)
        return Result(not required, "OK" if not required else "CODEGRAPH_NOT_FRESH")

    service = TaskService(tmp_path, context_gate=gate)

    result = service.start(
        "T-RISK",
        "修改 FOR UPDATE 事务锁并核对共享调用链影响范围",
        "backend",
    )

    assert not result.ok
    assert result.code == "CODEGRAPH_NOT_FRESH"
    assert required_values == [True]
    assert service.inspect("T-RISK") is None


def test_task_progress_updates_state_and_requirement_context(tmp_path: Path) -> None:
    WorkspaceService(tmp_path).init("demo", "family", "knowledge", [])
    requirement = RequirementService(tmp_path).create("任务进度记录", "原始需求", [], [])
    requirement_id = requirement.data["requirement_id"]
    requirement_path = Path(requirement.data["path"])
    service = TaskService(tmp_path, context_gate=lambda project, required: Result(True))

    assert service.start("T-1", "Implement", "backend", requirement_id=requirement_id).ok
    assert service.progress("T-1", "Gate implementation complete").ok
    task = service.inspect("T-1")
    assert task is not None and task["status"] == "active"
    assert "Gate implementation complete" in (requirement_path / "04-执行进度.md").read_text()


def test_task_resume_rechecks_context_freshness(tmp_path: Path) -> None:
    calls = 0

    def gate(project: str, required: bool) -> Result:
        nonlocal calls
        calls += 1
        return Result(True)

    service = TaskService(tmp_path, context_gate=gate)
    service.start("T-1", "Implement", "backend")
    service.resume("T-1")
    assert calls == 2
