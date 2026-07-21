from __future__ import annotations

import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from praxis.documents.atomic_writer import atomic_write_text
from praxis.result import Result

_WORKSPACE_ID = re.compile(r"^[a-z][a-z0-9-]{2,31}$")
_STABLE_ID = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


@dataclass(frozen=True)
class Project:
    id: str
    kind: str
    path: str
    default_branch: str
    name: str = ""
    system_id: str = ""
    database_connections: tuple[str, ...] = ()
    production_database_connections: tuple[str, ...] = ()
    deployment_commands: tuple[str, ...] = ()
    release_branches: tuple[str, ...] = ()
    template_branches: tuple[str, ...] = ()
    local_files: tuple[str, ...] = ()
    lint_commands: tuple[str, ...] = ()
    typecheck_commands: tuple[str, ...] = ()
    test_commands: tuple[str, ...] = ()


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _array(values: list[str] | tuple[str, ...]) -> str:
    return "[" + ", ".join(_quote(value) for value in values) + "]"


class WorkspaceService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.path = self.root / "praxis.toml"

    def init(
        self,
        workspace_id: str,
        name: str,
        knowledge_root: str = "知识库",
        projects: list[Project] | None = None,
    ) -> Result:
        if not _WORKSPACE_ID.fullmatch(workspace_id):
            raise ValueError("工作空间编号必须是3到32位小写ASCII、数字或连字符")
        if not name.strip():
            raise ValueError("工作空间中文名称不能为空")
        for project in projects or []:
            self._validate_project(project)
        payload = {
            "schema_version": 3,
            "workspace": {
                "id": workspace_id,
                "name": name.strip(),
                "language": "zh-CN",
                "knowledge_root": knowledge_root,
                "artifact_root": "产出物",
                "generated_root": "生成内容",
                "state_root": ".praxis",
                "worktree_root": ".worktrees",
            },
            "systems": [
                {
                    "id": workspace_id,
                    "name": name.strip(),
                    "domains": [],
                    "repositories": [
                        {
                            **{
                                key: list(value) if isinstance(value, tuple) else value
                                for key, value in asdict(project).items()
                                if key != "system_id"
                            }
                        }
                        for project in projects or []
                    ],
                }
            ]
            if projects
            else [],
        }
        self._write(payload)
        return Result(True, data={"workspace_id": workspace_id})

    def add_system(
        self,
        system_id: str,
        name: str,
        domains: list[str] | None = None,
    ) -> Result:
        payload = self.load(raw=True)
        if not _STABLE_ID.fullmatch(system_id):
            raise ValueError("业务系统编号必须使用小写ASCII、数字或连字符")
        if not name.strip():
            raise ValueError("业务系统中文名称不能为空")
        if any(system["id"] == system_id for system in payload.get("systems", [])):
            raise ValueError(f"业务系统已存在：{system_id}")
        payload.setdefault("systems", []).append(
            {
                "id": system_id,
                "name": name.strip(),
                "domains": domains or [],
                "repositories": [],
            }
        )
        self._write(payload)
        return Result(True, data={"system_id": system_id})

    def add_project(self, system_id: str, project: Project) -> Result:
        self._validate_project(project)
        payload = self.load(raw=True)
        system = next(
            (item for item in payload.get("systems", []) if item["id"] == system_id), None
        )
        if not system:
            raise KeyError(system_id)
        if any(item["id"] == project.id for item in system.get("repositories", [])):
            raise ValueError(f"仓库已存在：{project.id}")
        item = asdict(project)
        item.pop("system_id")
        for key, value in tuple(item.items()):
            if isinstance(value, tuple):
                item[key] = list(value)
        system.setdefault("repositories", []).append(item)
        self._write(payload)
        return Result(True, data={"system_id": system_id, "project_id": project.id})

    def load(self, *, raw: bool = False) -> dict[str, Any]:
        payload = tomllib.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 3:
            raise ValueError("Praxis V3 requires schema_version = 3")
        if raw:
            return payload
        workspace = payload["workspace"]
        payload["workspace_id"] = workspace["id"]
        payload["vault"] = workspace["knowledge_root"]
        payload["knowledge_root"] = workspace["knowledge_root"]
        payload["projects"] = [
            {**project, "system_id": system["id"]}
            for system in payload.get("systems", [])
            for project in system.get("repositories", [])
        ]
        return payload

    def project(self, project_id: str) -> Project:
        for raw in self.load().get("projects", []):
            if raw["id"] != project_id:
                continue
            tuple_fields = {
                key: tuple(raw.get(key, []))
                for key in (
                    "database_connections",
                    "production_database_connections",
                    "deployment_commands",
                    "release_branches",
                    "template_branches",
                    "local_files",
                    "lint_commands",
                    "typecheck_commands",
                    "test_commands",
                )
            }
            facts = {key: value for key, value in raw.items() if key not in tuple_fields}
            project = Project(**facts, **tuple_fields)
            self._validate_project(project)
            return project
        raise KeyError(project_id)

    def inspect(self) -> Result:
        return Result(True, data=self.load())

    def set_database_connections(
        self,
        project_id: str,
        references: tuple[str, ...] | list[str],
        production: tuple[str, ...] | list[str] = (),
    ) -> Result:
        payload = self.load(raw=True)
        project = next(
            (
                repository
                for system in payload.get("systems", [])
                for repository in system.get("repositories", [])
                if repository["id"] == project_id
            ),
            None,
        )
        if project is None:
            raise KeyError(project_id)
        candidate = Project(
            id=project["id"],
            name=project.get("name", ""),
            kind=project["kind"],
            path=project["path"],
            default_branch=project["default_branch"],
            database_connections=tuple(references),
            production_database_connections=tuple(production),
        )
        self._validate_project(candidate)
        project["database_connections"] = list(references)
        if production:
            project["production_database_connections"] = list(production)
        else:
            project.pop("production_database_connections", None)
        self._write(payload)
        return Result(True, data={"project_id": project_id, "registered": list(references)})

    @staticmethod
    def _validate_project(project: Project) -> None:
        invalid = [
            reference
            for reference in project.database_connections
            if not _valid_dbx_reference(reference)
        ]
        if invalid:
            raise ValueError("数据库连接必须只保存 dbx:// 连接引用")
        unknown_production = set(project.production_database_connections) - set(
            project.database_connections
        )
        if unknown_production:
            raise ValueError("生产数据库连接必须先登记为普通连接引用")
        if len(set(project.local_files)) != len(project.local_files):
            raise ValueError("本地文件白名单不能包含重复路径")
        invalid_local_files = [
            value for value in project.local_files if not _valid_local_file(value)
        ]
        if invalid_local_files:
            raise ValueError("本地文件必须使用仓库内的规范相对路径")

    def _write(self, payload: dict[str, Any]) -> None:
        workspace = payload["workspace"]
        lines = [
            "schema_version = 3",
            "",
            "[workspace]",
            *(f"{key} = {_quote(str(value))}" for key, value in workspace.items()),
        ]
        for system in payload.get("systems", []):
            lines.extend(
                [
                    "",
                    "[[systems]]",
                    f"id = {_quote(system['id'])}",
                    f"name = {_quote(system['name'])}",
                    f"domains = {_array(system.get('domains', []))}",
                ]
            )
            for project in system.get("repositories", []):
                lines.extend(
                    [
                        "",
                        "[[systems.repositories]]",
                        f"id = {_quote(project['id'])}",
                        f"name = {_quote(project.get('name') or project['id'])}",
                        f"kind = {_quote(project['kind'])}",
                        f"path = {_quote(project['path'])}",
                        f"default_branch = {_quote(project['default_branch'])}",
                    ]
                )
                for key in (
                    "database_connections",
                    "production_database_connections",
                    "deployment_commands",
                    "release_branches",
                    "template_branches",
                    "local_files",
                    "lint_commands",
                    "typecheck_commands",
                    "test_commands",
                ):
                    values = project.get(key, [])
                    if values:
                        lines.append(f"{key} = {_array(values)}")
        atomic_write_text(self.path, "\n".join(lines) + "\n")


def _valid_dbx_reference(reference: str) -> bool:
    parsed = urlsplit(reference)
    if parsed.scheme != "dbx" or not parsed.netloc or parsed.query or parsed.fragment:
        return False
    database = parsed.path.removeprefix("/")
    return "/" not in database


def _valid_local_file(value: str) -> bool:
    if not value or value != value.strip() or "\\" in value:
        return False
    segments = value.split("/")
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and not re.match(r"^[A-Za-z]:", value)
        and all(segment not in {"", ".", ".."} for segment in segments)
    )
