from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from praxis.errors import ConflictError, PraxisError
from praxis.workspace.service import WorkspaceService


class RequirementService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.dir = self.root / ".praxis" / "state" / "requirements"
        self.docs = self.root / "docs" / "requirements"

    def _path(self, req_id: str) -> Path:
        return self.dir / f"{req_id}.json"

    def create(self, req_id: str, task_id: str, title: str) -> dict[str, Any]:
        WorkspaceService(self.root).require()
        if self._path(req_id).exists():
            raise ConflictError("REQUIREMENT_CONFLICT", "需求 ID 已存在。", {"requirement": req_id})
        self.dir.mkdir(parents=True, exist_ok=True)
        self.docs.mkdir(parents=True, exist_ok=True)
        doc_path = self.docs / f"{req_id}.md"
        doc_path.write_text(f"# {title}\n\n- 任务：{task_id}\n")
        record = {
            "schema_version": "1.0",
            "id": req_id,
            "task_id": task_id,
            "title": title,
            "status": "draft",
            "document": str(doc_path.relative_to(self.root)),
        }
        self._path(req_id).write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2)
        )
        return record

    def inspect(self, req_id: str) -> dict[str, Any]:
        path = self._path(req_id)
        if not path.exists():
            raise PraxisError(
                "REQUIREMENT_NOT_FOUND", "未找到指定需求。", 2, {"requirement": req_id}
            )
        return json.loads(path.read_text())

    def transition(self, req_id: str, status: str) -> dict[str, Any]:
        record = self.inspect(req_id)
        record["status"] = status
        self._path(req_id).write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2)
        )
        return record

    def close(self, req_id: str) -> dict[str, Any]:
        return self.transition(req_id, "closed")
