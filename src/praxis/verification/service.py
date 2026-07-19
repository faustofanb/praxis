from __future__ import annotations

from pathlib import Path

from praxis.changes.classifier import classify_paths
from praxis.workspace.service import WorkspaceService


class VerificationService:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def run(self, changed_files: list[str] | None = None) -> dict:
        WorkspaceService(self.root).require()
        classification = classify_paths(changed_files or [])
        return {
            "checks": [{"id": "workspace", "required": True, "ok": True}],
            "classification": classification,
        }
