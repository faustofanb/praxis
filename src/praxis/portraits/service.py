from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from praxis.result import Result
from praxis.workspace.service import WorkspaceService


class PortraitService:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def scan(self, project_id: str) -> Result:
        workspace = WorkspaceService(self.root)
        project = workspace.project(project_id)
        repo = (self.root / project.path).resolve()
        build_commands: list[str] = []
        test_commands: list[str] = []
        deployment_commands = list(project.deployment_commands)
        if (repo / "pom.xml").exists():
            build_commands.append("mvn package")
            test_commands.append("mvn test")
        if (repo / "pyproject.toml").exists():
            build_commands.append("uv build")
            test_commands.append("uv run pytest")
        if (repo / "package.json").exists():
            build_commands.append("pnpm build")
            test_commands.append("pnpm test")
        if (repo / "Dockerfile").exists():
            deployment_commands.append("docker build .")
        branches = self._branches(repo)
        data: dict[str, Any] = {
            "project_id": project_id,
            "kind": project.kind,
            "scan_mode": "static",
            "build_commands": build_commands,
            "test_commands": test_commands,
            "deployment_commands": deployment_commands,
            "database_connections": list(project.database_connections),
            "release_branches": sorted(
                {
                    *project.release_branches,
                    *(name for name in branches if name.startswith("release/")),
                }
            ),
            "template_branches": sorted(
                {
                    *project.template_branches,
                    *(name for name in branches if name.startswith("template/")),
                }
            ),
        }
        vault = self.root / workspace.load()["vault"] / "portraits"
        vault.mkdir(parents=True, exist_ok=True)
        type_definition = vault.parent / "system-portrait.md"
        if not type_definition.exists():
            type_definition.write_text(
                "---\ntype: Type\ntitle: SystemPortrait\nicon: factory\n---\n# SystemPortrait\n",
                encoding="utf-8",
            )
        (vault / f"{project_id}.md").write_text(self._markdown(data), encoding="utf-8")
        return Result(True, data=data)

    @staticmethod
    def _branches(repo: Path) -> list[str]:
        process = subprocess.run(
            ["git", "branch", "--format=%(refname:short)"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
        return sorted(line for line in process.stdout.splitlines() if line)

    @staticmethod
    def _markdown(data: dict[str, Any]) -> str:
        frontmatter = ["---", "type: SystemPortrait"]
        frontmatter.extend(
            f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in data.items()
        )
        return "\n".join([*frontmatter, "---", "", f"# {data['project_id']} system portrait", ""])
