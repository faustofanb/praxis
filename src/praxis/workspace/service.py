from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from praxis.result import Result


@dataclass(frozen=True)
class Project:
    id: str
    kind: str
    path: str
    default_branch: str
    database_connections: tuple[str, ...] = ()
    deployment_commands: tuple[str, ...] = ()
    release_branches: tuple[str, ...] = ()
    template_branches: tuple[str, ...] = ()


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class WorkspaceService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.path = self.root / "praxis.toml"

    def init(
        self,
        workspace_id: str,
        product_family: str,
        vault: str,
        projects: list[Project],
    ) -> Result:
        lines = [
            "schema_version = 2",
            f"workspace_id = {_quote(workspace_id)}",
            f"product_family = {_quote(product_family)}",
            f"vault = {_quote(vault)}",
        ]
        for project in projects:
            lines.extend(
                [
                    "",
                    "[[projects]]",
                    f"id = {_quote(project.id)}",
                    f"kind = {_quote(project.kind)}",
                    f"path = {_quote(project.path)}",
                    f"default_branch = {_quote(project.default_branch)}",
                ]
            )
            for key in (
                "database_connections",
                "deployment_commands",
                "release_branches",
                "template_branches",
            ):
                values = getattr(project, key)
                if values:
                    rendered = ", ".join(_quote(value) for value in values)
                    lines.append(f"{key} = [{rendered}]")
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return Result(True, data={"workspace_id": workspace_id})

    def load(self) -> dict[str, Any]:
        payload = tomllib.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 2:
            raise ValueError("Praxis V2 requires schema_version = 2")
        return payload

    def project(self, project_id: str) -> Project:
        for raw in self.load().get("projects", []):
            if raw["id"] == project_id:
                lists = {
                    key: tuple(raw.get(key, []))
                    for key in (
                        "database_connections",
                        "deployment_commands",
                        "release_branches",
                        "template_branches",
                    )
                }
                facts = {key: value for key, value in raw.items() if key not in lists}
                return Project(**facts, **lists)
        raise KeyError(project_id)

    def inspect(self) -> Result:
        payload = self.load()
        payload["projects"] = [
            asdict(self.project(item["id"])) for item in payload.get("projects", [])
        ]
        return Result(True, data=payload)
