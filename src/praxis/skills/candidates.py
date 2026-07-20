from __future__ import annotations

import hashlib
import re
import tomllib
from pathlib import Path
from typing import Any

from praxis.portraits.service import PortraitService
from praxis.result import Result
from praxis.workspace.service import WorkspaceService, _quote


class SkillCandidateService:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def generate(self, project_id: str) -> Result:
        portrait = PortraitService(self.root).scan(project_id)
        workspace = WorkspaceService(self.root).load()
        portrait_path = self.root / workspace["vault"] / "portraits" / f"{project_id}.md"
        candidate_id = f"{project_id}-development"
        data = {
            "id": candidate_id,
            "type": "business",
            "version": "0.1.0",
            "status": "pending-review",
            "project_id": project_id,
            "source_portrait": str(portrait_path.relative_to(self.root)),
            "source_hash": hashlib.sha256(portrait_path.read_bytes()).hexdigest(),
            "kind": portrait.data["kind"],
            "build_commands": portrait.data["build_commands"],
            "test_commands": portrait.data["test_commands"],
        }
        path = self._candidate_path(candidate_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._toml(data), encoding="utf-8")
        return Result(True, data=data)

    def promote(self, candidate_id: str, catalog_root: Path | str, *, approved: bool) -> Result:
        if not approved:
            return Result(False, "SKILL_REVIEW_REQUIRED")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", candidate_id):
            return Result(False, "SKILL_ID_INVALID")
        candidate_path = self._candidate_path(candidate_id)
        if not candidate_path.exists():
            return Result(False, "SKILL_CANDIDATE_NOT_FOUND")
        data = tomllib.loads(candidate_path.read_text(encoding="utf-8"))
        target = Path(catalog_root) / "business" / candidate_id
        target.mkdir(parents=True, exist_ok=False)
        metadata = {
            "id": candidate_id,
            "type": "business",
            "version": data["version"],
            "license": "Proprietary",
            "source": f"portrait:{data['source_hash']}",
            "source_version": data["source_hash"][:12],
            "risk": "none",
            "context_budget": 500,
            "required_tools": [],
            "triggers": [data["project_id"], data["kind"]],
        }
        (target / "skill.toml").write_text(self._toml(metadata), encoding="utf-8")
        body = (
            "---\n"
            f"name: {candidate_id}\n"
            f"description: Develop the reviewed {data['project_id']} system using its scanned "
            "build and test facts. Use only for tasks explicitly targeting this system.\n"
            "---\n\n"
            f"# {candidate_id}\n\n"
            f"Source portrait hash: `{data['source_hash']}`.\n\n"
            f"Build commands: {', '.join(data['build_commands']) or 'none detected'}.\n\n"
            f"Test commands: {', '.join(data['test_commands']) or 'none detected'}.\n"
        )
        (target / "SKILL.md").write_text(body, encoding="utf-8")
        data["status"] = "approved"
        candidate_path.write_text(self._toml(data), encoding="utf-8")
        return Result(True, data={"id": candidate_id, "path": str(target)})

    def _candidate_path(self, candidate_id: str) -> Path:
        vault = WorkspaceService(self.root).load()["vault"]
        return self.root / vault / "skill-candidates" / f"{candidate_id}.toml"

    @staticmethod
    def _toml(data: dict[str, Any]) -> str:
        lines = []
        for key, value in data.items():
            if isinstance(value, list):
                values = ", ".join(_quote(str(item)) for item in value)
                lines.append(f"{key} = [{values}]")
            elif isinstance(value, int):
                lines.append(f"{key} = {value}")
            else:
                lines.append(f"{key} = {_quote(str(value))}")
        return "\n".join(lines) + "\n"
