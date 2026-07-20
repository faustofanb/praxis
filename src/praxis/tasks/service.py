from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from praxis.codegraph.hooks import CodeGraphHooks
from praxis.naming.requirement import RequirementPathPolicy
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService

ContextGate = Callable[[str, bool], Result]


class TaskService:
    def __init__(self, root: Path | str, *, context_gate: ContextGate | None = None):
        self.root = Path(root)
        self.store = StateStore(self.root)
        self.context_gate = context_gate or self._context_gate

    def _context_gate(self, project_id: str, graph_required: bool) -> Result:
        return CodeGraphHooks(self.root).run(
            "task-context", project_id, graph_required=graph_required
        )

    def start(
        self,
        task_id: str,
        title: str,
        project_id: str,
        *,
        requirement_id: str | None = None,
        graph_required: bool = False,
    ) -> Result:
        context = self.context_gate(project_id, graph_required)
        if not context.ok:
            return context
        task = {
            "id": task_id,
            "title": title,
            "project_id": project_id,
            "requirement_id": requirement_id,
            "graph_required": graph_required,
            "status": "active",
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self.store.set("task", task_id, task)
        self.store.audit("task.start", "OK", {"task_id": task_id})
        return Result(True, data=task, diagnostics=context.diagnostics)

    def inspect(self, task_id: str) -> dict[str, Any] | None:
        return self.store.get("task", task_id)

    def resume(self, task_id: str) -> Result:
        task = self.inspect(task_id)
        if task is None:
            return Result(False, "TASK_NOT_FOUND")
        context = self.context_gate(task["project_id"], task["graph_required"])
        if not context.ok:
            return context
        task["status"] = "active"
        task["updated_at"] = datetime.now(UTC).isoformat()
        self.store.set("task", task_id, task)
        return Result(True, data=task, diagnostics=context.diagnostics)

    def progress(self, task_id: str, message: str) -> Result:
        task = self.inspect(task_id)
        if task is None:
            return Result(False, "TASK_NOT_FOUND")
        requirement_id = task.get("requirement_id")
        if requirement_id:
            requirement = self.store.requirement(requirement_id)
            if not requirement:
                return Result(False, "REQUIREMENT_NOT_FOUND")
            vault = WorkspaceService(self.root).load()["knowledge_root"]
            path = RequirementPathPolicy(self.root / vault).requirement_path(
                requirement_id, requirement["short_name"]
            ) / "执行进度.md"
            timestamp = datetime.now(UTC).isoformat()
            with path.open("a", encoding="utf-8") as progress:
                progress.write(f"\n- {timestamp}: {message}\n")
        task["updated_at"] = datetime.now(UTC).isoformat()
        self.store.set("task", task_id, task)
        self.store.audit("task.progress", "OK", {"task_id": task_id, "message": message})
        return Result(True, data=task)
