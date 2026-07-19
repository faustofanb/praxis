from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from praxis.errors import ConflictError, WorkspaceNotFound
from praxis.paths import workspace_file
from praxis.profiles.resolver import ProfileResolver
from praxis.tomlutil import dumps_toml, load_toml


def _project_dict(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "type": raw["type"],
        "path": raw["path"],
        **{k: v for k, v in raw.items() if k not in {"id", "type", "path"}},
    }


class WorkspaceService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.path = workspace_file(self.root)

    def require(self) -> dict[str, Any]:
        if not self.path.exists():
            raise WorkspaceNotFound(str(self.root))
        return load_toml(self.path)

    def init(
        self,
        profile_id: str = "base",
        projects: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if self.path.exists():
            current = self.inspect()
            requested_projects = {p["id"]: _project_dict(p) for p in (projects or [])}
            projects_conflict = projects is not None and current["projects"] != requested_projects
            if current["profile_id"] != profile_id or projects_conflict:
                raise ConflictError(
                    "WORKSPACE_CONFLICT",
                    "workspace 已存在，拒绝覆盖不同 profile 或项目事实。",
                    {"profile_id": current["profile_id"]},
                )
            return current
        self.path.parent.mkdir(parents=True, exist_ok=True)
        facts = {
            "schema_version": "1.0",
            "workspace_id": str(uuid.uuid4()),
            "profile_id": profile_id,
            "locale": "zh-CN",
        }
        project_table = {p["id"]: _project_dict(p) for p in (projects or [])}
        data = {**facts, "projects": json.dumps(project_table, ensure_ascii=False, sort_keys=True)}
        self.path.write_text(dumps_toml(data))
        return self.inspect()

    def inspect(self) -> dict[str, Any]:
        data = self.require()
        projects = (
            json.loads(data.get("projects", "{}"))
            if isinstance(data.get("projects"), str)
            else data.get("projects", {})
        )
        return {
            "workspace_id": data["workspace_id"],
            "profile_id": data["profile_id"],
            "locale": data.get("locale", "zh-CN"),
            "projects": projects,
        }

    def check(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        data = self.require()
        diagnostics: list[dict[str, Any]] = []
        resolved = ProfileResolver().resolve(data["profile_id"]).to_dict()
        cache = self.root / ".praxis" / "cache" / "resolved-profile.json"
        if not cache.exists():
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(resolved, ensure_ascii=False, sort_keys=True, indent=2))
            diagnostics.append(
                {"code": "CACHE_REBUILT", "message": "已重建 resolved profile cache。"}
            )
        self._validate_state_json()
        projects = self.inspect()["projects"]
        missing = [pid for pid, item in projects.items() if not (self.root / item["path"]).exists()]
        for pid in missing:
            diagnostics.append(
                {"code": "PROJECT_PATH_MISSING", "message": "项目路径不存在。", "project": pid}
            )
        return {
            "profile": data["profile_id"],
            "projects": projects,
            "cache": str(cache.relative_to(self.root)),
        }, diagnostics

    def _validate_state_json(self) -> None:
        from json import JSONDecodeError

        from praxis.errors import PraxisError

        state_root = self.root / ".praxis" / "state"
        if not state_root.exists():
            return
        for path in sorted(state_root.rglob("*.json")):
            try:
                json.loads(path.read_text())
            except JSONDecodeError as exc:
                raise PraxisError(
                    "STATE_JSON_INVALID",
                    "workspace state JSON 无法读取。",
                    2,
                    {"path": str(path.relative_to(self.root))},
                ) from exc

    def project(self, project_id: str) -> dict[str, Any]:
        projects = self.inspect()["projects"]
        if project_id not in projects:
            from praxis.errors import PraxisError

            raise PraxisError("PROJECT_NOT_FOUND", "未找到指定项目。", 2, {"project": project_id})
        return projects[project_id]
