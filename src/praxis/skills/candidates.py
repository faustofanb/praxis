from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from praxis.documents.atomic_writer import atomic_write_text
from praxis.portraits.service import PortraitService
from praxis.result import Result
from praxis.workspace.service import WorkspaceService, _quote


class SkillCandidateService:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def generate(self, project_id: str) -> Result:
        portrait = PortraitService(self.root).scan(project_id)
        portrait_path = PortraitService(self.root).path(project_id)
        project = WorkspaceService(self.root).project(project_id)
        candidate_id = f"business.{project.system_id}.{project_id}.development"
        data = {
            "id": candidate_id,
            "type": "business",
            "version": "0.1.0",
            "status": "pending-review",
            "project_id": project_id,
            "source_portrait": str(portrait_path.relative_to(self.root)),
            "source_hash": portrait.data["input_hash"],
            "kind": portrait.data["kind"],
            "build_commands": portrait.data["build_commands"],
            "test_commands": portrait.data["test_commands"],
        }
        path = self._candidate_path(candidate_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, self._toml(data))
        return Result(True, data=data)

    def promote(self, candidate_id: str, catalog_root: Path | str, *, approved: bool) -> Result:
        if not approved:
            return Result(False, "SKILL_REVIEW_REQUIRED")
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*", candidate_id):
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
        atomic_write_text(target / "skill.toml", self._toml(metadata))
        body = (
            "---\n"
            f"name: {candidate_id}\n"
            f"description: 使用经审核的系统画像开发 {data['project_id']}，"
            "仅适用于明确关联该仓库的任务。\n"
            "---\n\n"
            f"# {data['project_id']}系统开发\n\n"
            "## 一、技能用途\n\n"
            f"在明确关联 `{data['project_id']}` 仓库的需求中复用已确认的工程事实。\n\n"
            "## 二、适用业务域\n\n由需求登记的业务域决定。\n\n"
            "## 三、适用场景\n\n该仓库的调查、实现、测试与审查。\n\n"
            "## 四、不适用场景\n\n其他仓库或未登记系统。\n\n"
            "## 五、所需输入\n\n需求编号、任务阶段、修改范围和验证方式。\n\n"
            "## 六、提供能力\n\n提供画像中已扫描的构建与测试事实。\n\n"
            "## 七、依赖工具\n\n由当前工作空间门禁决定。\n\n"
            "## 八、业务约束\n\n不得推断或新增未经确认的业务规则。\n\n"
            "## 九、数据约束\n\n不得保存数据库凭据或秘密原文。\n\n"
            "## 十、风险\n\n不授予数据库写入或部署权限。\n\n"
            "## 十一、验证方法\n\n"
            f"构建命令：{', '.join(data['build_commands']) or '未检测到'}。\n\n"
            f"测试命令：{', '.join(data['test_commands']) or '未检测到'}。\n\n"
            "## 十二、知识来源\n\n"
            f"系统画像内容哈希：`{data['source_hash']}`。\n"
        )
        atomic_write_text(target / "SKILL.md", body)
        data["status"] = "approved"
        atomic_write_text(candidate_path, self._toml(data))
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
