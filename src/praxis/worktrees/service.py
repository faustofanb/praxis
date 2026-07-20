from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
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
    def __init__(
        self,
        root: Path | str,
        run: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ):
        self.root = Path(root)
        self.dir = self.root / ".praxis" / "state" / "worktrees"
        self.run = run or self._run

    @staticmethod
    def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)

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
        command = [
            "wt",
            "switch",
            "--create",
            task_id,
            "--base",
            "HEAD",
            "--no-cd",
            "--format=json",
        ]
        result = self.run(command, repo)
        if result.returncode != 0:
            raise PraxisError(
                "WORKTRUNK_CREATE_FAILED",
                "Worktrunk 创建工作树失败。",
                2,
                {"project": project_id, "stderr": result.stderr.strip()},
            )
        try:
            payload = json.loads(result.stdout)
            target_value = payload.get("path") or payload.get("worktree", {}).get("path")
            target = Path(target_value)
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise PraxisError(
                "WORKTRUNK_OUTPUT_INVALID",
                "Worktrunk 未返回有效的工作树路径。",
                2,
                {"project": project_id},
            ) from error
        if not target.is_absolute():
            target = (repo / target).resolve()
        self.dir.mkdir(parents=True, exist_ok=True)
        data = {
            "project_id": project_id,
            "task_id": task_id,
            "path": str(target),
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
        path_value = Path(data["path"])
        path = path_value if path_value.is_absolute() else self.root / path_value
        return WorktreeRecord(project_id, task_id, path)

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
