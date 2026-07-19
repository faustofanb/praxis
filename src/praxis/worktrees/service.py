from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from praxis.errors import PraxisError
from praxis.tasks.service import TaskService
from praxis.workspace.service import WorkspaceService


@dataclass
class WorktreeRecord:
    project_id: str
    task_id: str
    path: Path


@dataclass
class CleanupResult:
    ok: bool
    code: str = "OK"
    message: str = ""


class WorktreeService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.dir = self.root / ".praxis" / "state" / "worktrees"

    def _record_path(self, project_id: str, task_id: str) -> Path:
        return self.dir / f"{project_id}--{task_id}.json"

    def create(self, project_id: str, task_id: str) -> WorktreeRecord:
        workspace = WorkspaceService(self.root)
        project = workspace.project(project_id)
        TaskService(self.root).inspect(task_id)
        repo = (self.root / project["path"]).resolve()
        if not (repo / ".git").exists():
            raise PraxisError("REPO_NOT_FOUND", "项目不是 Git 仓库。", 2, {"project": project_id})
        record_path = self._record_path(project_id, task_id)
        if record_path.exists():
            return self.reuse(project_id, task_id)
        target = self.root / ".praxis" / "worktrees" / f"{project_id}-{task_id}"
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", str(target), "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        self.dir.mkdir(parents=True, exist_ok=True)
        data = {
            "project_id": project_id,
            "task_id": task_id,
            "path": str(target.relative_to(self.root)),
            "owner": task_id,
        }
        record_path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))
        return WorktreeRecord(project_id, task_id, target)

    def reuse(self, project_id: str, task_id: str) -> WorktreeRecord:
        path = self._record_path(project_id, task_id)
        if not path.exists():
            return self.create(project_id, task_id)
        data = json.loads(path.read_text())
        if data.get("owner") != task_id:
            raise PraxisError("WORKTREE_OWNER_MISMATCH", "工作树所有者不匹配。", 2)
        return WorktreeRecord(project_id, task_id, self.root / data["path"])

    def cleanup(self, project_id: str, task_id: str) -> CleanupResult:
        record = self.reuse(project_id, task_id)
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=record.path,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.stdout.strip():
            return CleanupResult(False, "WORKTREE_DIRTY", "工作树存在未提交改动，拒绝 cleanup。")
        return CleanupResult(True)
