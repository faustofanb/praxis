from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from praxis.errors import ConflictError, PraxisError
from praxis.workspace.service import WorkspaceService


class TaskService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.dir = self.root / ".praxis" / "state" / "tasks"

    def _path(self, task_id: str) -> Path:
        return self.dir / f"{task_id}.json"

    def _create(self, request: dict[str, Any], kind: str) -> dict[str, Any]:
        WorkspaceService(self.root).require()
        task_id = request.get("id") or request.get("task_id")
        if not task_id:
            raise PraxisError("TASK_ID_REQUIRED", "必须提供任务 ID。", 2)
        path = self._path(task_id)
        if path.exists():
            raise ConflictError("TASK_CONFLICT", "任务 ID 已存在。", {"task": task_id})
        self.dir.mkdir(parents=True, exist_ok=True)
        record = {
            "schema_version": "1.0",
            "id": task_id,
            "title": request.get("title", ""),
            "kind": kind,
            "status": "active",
        }
        path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2))
        return record

    def quick_start(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._create(request, "quick")

    def formal_start(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._create(request, "formal")

    def resume(self, task_id: str) -> dict[str, Any]:
        return self.inspect(task_id)

    def quick_check(self, task_id: str) -> dict[str, Any]:
        record = self.inspect(task_id)
        record["checked"] = True
        self._path(task_id).write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2)
        )
        return record

    def inspect(self, task_id: str) -> dict[str, Any]:
        path = self._path(task_id)
        if not path.exists():
            raise PraxisError("TASK_NOT_FOUND", "未找到指定任务。", 2, {"task": task_id})
        return json.loads(path.read_text())
