from __future__ import annotations

from pathlib import Path

from praxis.workspace.service import WorkspaceService


class ProjectRegistry:
    def __init__(self, root: Path | str):
        self.workspace = WorkspaceService(root)

    def list(self) -> list[dict]:
        return list(self.workspace.inspect()["projects"].values())

    def inspect(self, project_id: str) -> dict:
        return self.workspace.project(project_id)
