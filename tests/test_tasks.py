from __future__ import annotations

from pathlib import Path

from praxis.knowledge.requirements import RequirementService
from praxis.result import Result
from praxis.tasks.service import TaskService
from praxis.workspace.service import WorkspaceService


def test_task_start_is_blocked_when_required_graph_is_unavailable(tmp_path: Path) -> None:
    service = TaskService(tmp_path, context_gate=lambda project, required: Result(False, "STALE"))
    result = service.start("T-1", "Investigate", "backend", graph_required=True)
    assert not result.ok
    assert service.inspect("T-1") is None


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
    assert "Gate implementation complete" in (requirement_path / "执行进度.md").read_text()


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
