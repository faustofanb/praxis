from __future__ import annotations

from pathlib import Path

from praxis.documents.atomic_writer import atomic_write_text
from praxis.result import Result
from praxis.skills.routing import NodeSkillRouter
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService

_START = "<!-- praxis:managed:start -->"
_END = "<!-- praxis:managed:end -->"


class AgentGuidanceService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.store = StateStore(self.root)

    def render(self) -> Result:
        workspace = WorkspaceService(self.root).load()
        managed = self._managed_content(workspace)
        updates: list[tuple[Path, str]] = []
        for name, title in (("AGENTS.md", "Codex"), ("CLAUDE.md", "Claude Code")):
            path = self.root / name
            updated = self._merged_content(path, managed, title)
            if not updated.ok:
                return updated
            updates.append((path, updated.data["content"]))
        for path, content in updates:
            atomic_write_text(path, content)
        files = [str(path) for path, _ in updates]
        data = {"files": files, "managed_markers": [_START, _END]}
        data["audit_id"] = self.store.audit("agent.guidance_rendered", "OK", data)
        return Result(True, data=data)

    def _managed_content(self, workspace: dict) -> str:
        facts = workspace["workspace"]
        projects = workspace.get("projects", [])
        lines = [
            _START,
            "## Praxis 工作流（自动管理）",
            "",
            f"- 工作空间：`{facts['id']}`（{facts['name']}）",
            f"- 权威知识库：`{facts['knowledge_root']}`；聊天记录不能替代需求文档。",
            "- 新需求先登记并生成知识文档；调查和计划阶段不要创建工作树。",
            "- 只有确认需要改代码时，才在第一次代码编辑前创建绑定需求的 Worktrunk 工作树。",
            "- 工作树以仓库 `default_branch` 为本地运行模板；先合并唯一的",
            "  `origin/<template_branch>`，再从更新后的本地模板创建需求分支。",
            "- 仓库声明 `local_files` 时，只从配置的主仓库复制这些 ignored 本地运行文件；",
            "  缺失、越界或符号链接目标异常时必须阻断创建，不得扫描或复制其他 `.env*`。",
            "- 仓库声明 `worktree_setup_commands` 时，在本地文件之后、CodeGraph 之前只执行",
            "  显式 argv 命令；失败必须阻断，离线失败不得回退联网，也不得审计命令输出或环境。",
            "- 需求工作空间命名为 `.worktrees/<需求ID>__<简称>`；仓库末级目录命名为",
            "  `<需求ID>__<简称>__<仓库ID>`，分支命名为 `praxis/<需求ID>__<简称>`。",
            "- 首次生成的简称快照保持稳定；后续标题变化不自动迁移路径或分支，旧 binding 必须",
            "  使用正式迁移命令。阶段名称不得进入目录或分支。",
            "- 禁止在工作空间根目录或未绑定目录修改业务代码。",
            "- 未经本次明确批准，不得启动 reviewer/tester Agent，也不得运行 lint、format、",
            "  typecheck、测试、覆盖率或质量复核。提交、推送、完成、继续不等于批准。",
            "- 使用 Skill 前先执行节点路由；`routed` 仅代表候选，必须记录 `invoked` 和",
            "  `completed`，节点门禁才视为真实使用。",
            "- 状态流转和 `worktree create` 都是 fail-closed；当前节点缺少 route、完成凭证或",
            "  gate 时必须停止，不得自动补路由或绕过。",
            "- 第三方 Skill 缺失时报告来源和缺失项，不得在 bootstrap 中自动安装。",
            "",
            "### Skill 调用协议",
            "",
            "1. 进入节点先运行 `praxis skill route-node --node <节点> --requirement <需求ID>`。",
            "2. 对决定使用的 Skill 运行 `praxis skill invoke <Skill ID> --requirement <需求ID> --node <节点>`。",
            "3. Skill 工作完成后，用返回的 invocation ID 运行 `praxis skill complete <调用ID>`。",
            "4. 离开节点前运行 `praxis skill gate --requirement <需求ID> --node <节点>`。",
            "5. `approval_required` Skill 只有获得本次用户明确批准后才能加 `--approved` 调用。",
            "",
            "## 仓库模板分支",
            "",
            "| 仓库 | 类型 | 路径 | 本地模板 | 上游模板 |",
            "|---|---|---|---|---|",
        ]
        for project in projects:
            upstream = ", ".join(project.get("template_branches", [])) or "未配置"
            lines.append(
                f"| `{project['id']}` | `{project['kind']}` | `{project['path']}` | "
                f"`{project['default_branch']}` | `{upstream}` |"
            )
        lines.extend(("", "## 节点 Skill 策略", ""))
        grouped: dict[str, list[str]] = {}
        for policy in NodeSkillRouter.policies():
            label = {
                "required": "必需",
                "conditional": "条件",
                "approval_required": "需批准",
            }[policy.mode]
            for node in policy.nodes:
                grouped.setdefault(node, []).append(f"`{policy.id}`（{label}）")
        for node, skills in grouped.items():
            lines.append(f"- `{node}`：{', '.join(skills)}")
        sources = self._project_sources(projects)
        lines.extend(("", "## 项目规则与业务 Skill 来源", ""))
        if sources:
            lines.extend(f"- `{item}`" for item in sources)
        else:
            lines.append("- 未发现项目级 `skills` 或规则目录；运行 Praxis 候选扫描后人工审核。")
        lines.extend(("", _END))
        return "\n".join(lines)

    def _project_sources(self, projects: list[dict]) -> list[str]:
        candidates = (
            ".cursor/rules",
            ".cursor/skills",
            ".lingma/rules",
            "skills",
            "docs/skills",
        )
        found = []
        for project in projects:
            project_root = self.root / project["path"]
            for candidate in candidates:
                path = project_root / candidate
                if path.is_dir():
                    found.append(path.relative_to(self.root).as_posix())
        return sorted(set(found))

    @staticmethod
    def _merged_content(path: Path, managed: str, title: str) -> Result:
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        start_count = current.count(_START)
        end_count = current.count(_END)
        if start_count != end_count or start_count > 1:
            return Result(
                False,
                "AGENT_GUIDANCE_MARKERS_INVALID",
                data={"path": str(path)},
            )
        if start_count == 1:
            prefix, remainder = current.split(_START, 1)
            _, suffix = remainder.split(_END, 1)
            content = prefix.rstrip() + "\n\n" + managed + suffix
        elif current.strip():
            content = current.rstrip() + "\n\n" + managed + "\n"
        else:
            content = f"# {title} 项目规则\n\n{managed}\n"
        return Result(True, data={"path": str(path), "content": content})
