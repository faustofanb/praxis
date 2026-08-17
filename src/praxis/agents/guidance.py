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
            "- 操作细则（fast_fix、RTK、TDD、命令预算、证据指纹缓存、subagent、investigate）",
            "  以内置 `praxis-requirement-workflow` Skill 为唯一权威源，进入节点时按需加载；",
            "  本文件只保留不随任务变化的指针与不变式。",
            "- 入口：Praxis 操作优先使用已提供的 Praxis MCP；MCP 不可用时先执行",
            "  `praxis doctor --json` 查看 CLI fallback.path 再使用可解析的 `praxis` CLI。",
            "  DBX 调查只使用已提供的 DBX MCP 工具，不调用或回退到 DBX CLI。",
            "- 新需求先登记并生成知识文档；需求知识目录使用 `<需求ID>__<简称>`，",
            "  文档使用固定数字前缀；调查和计划阶段不要创建工作树。",
            "- 只有确认需要改代码时，才在第一次代码编辑前创建绑定需求的 Worktrunk 工作树；",
            "  先 `worktree preview` 固定工作空间、末级目录与分支，",
            "  再 `worktree ensure --confirm <preview_id>`。工作树以仓库 `default_branch`",
            "  为本地运行模板，先合并唯一 `origin/<template_branch>` 再从模板创建需求分支。",
            "- 需求工作空间 `.worktrees/<需求ID>__<简称>`，仓库末级目录 "
            "`<需求ID>__<简称>__<仓库ID>`、",
            "  分支 `praxis/<需求ID>__<简称>`；简称快照保持稳定，阶段名称不得进入目录或分支。",
            "- 禁止在工作空间根目录或未绑定目录修改业务代码；",
            "  pre-commit 在主仓库无 binding 且检测到业务代码改动时阻断，",
            "  提示‘请走 praxis 工作树’。",
            "- 功能、缺陷修复、重构和行为变更默认执行 TDD（RED→GREEN→重构），聚焦 TDD 授权",
            "  不包含完整回归、lint、format、typecheck、覆盖率、构建或代码复核；",
            "  TDD GREEN 后调用 `minimum-module-compile` 编译最小受影响模块。",
            "- 完整回归、lint、typecheck、覆盖率、质量复核、reviewer/tester Agent 与收尾 Skill",
            "  始终需要独立验证授权；“提交”“推送”“完成”“继续”不等于批准。",
            "- 用户明确说“快速修复”“只改这里”“不要跑测试”等时，按 `praxis-requirement-workflow`",
            "  Skill 的 fast_fix 例外处理并记录 `mode=fast_fix`；否则回到标准流程。",
            "- 高风险改动（事务、锁、原生 SQL、并发、公共接口、共享服务、",
            "  跨模块、结构迁移、高扇出）",
            "  必须在编辑前调用 `codegraph-impact-analysis`；Plan Mode 无 binding 时用",
            "  `praxis codegraph investigate <target> --project <项目>",
            "  --purpose <目的>` 只读查询。",
            "- 数据库调查必须从 context 已登记的 DBX 引用中显式选择连接，禁止默认库猜测；",
            "  对结构或数据作出判断前先执行 `select current_database()` 核对目标库。",
            "- 需求按 `in_progress → implemented → verifying → completed` 推进，",
            "  `requirement advance` 一次只前进一个状态；",
            "  状态流转与 `worktree create` 均 fail-closed，",
            "  当前节点缺少 route、完成凭证或 gate 时必须停止，不得自动补路由或绕过。",
            "- 产出物在代码稳定后登记，相同需求+路径 upsert；实施完成不等于验证通过，",
            "  用户明确不执行某项验证时登记 decline receipt，不把 declined 或未执行投影为 passed。",
            "- 需求从 verifying 回开发使用带原因的 `requirement reopen`。",
            "- 所有外部命令先由 RTK 代理；普通文本搜索使用 `rg`，机器 JSON 用 `rtk proxy`。",
            "",
            "### Skill 调用协议",
            "",
            "1. 进入节点先运行 `praxis skill route-node --node <节点> --requirement <需求ID>`。",
            "2. 对决定使用的 Skill 运行 `praxis skill invoke <Skill ID> "
            "--requirement <需求ID> --node <节点>`。",
            "3. Skill 工作完成后，用返回的 invocation ID 运行 `praxis skill complete <调用ID>`。",
            "4. 多 Skill 节点优先运行 `praxis lifecycle complete-node --requirement <需求ID>`",
            "  并逐项传入 `--used-skill <id>=<result>:<outcome>`，例如",
            "  `--used-skill 'skill-id=passed:结果说明'`（外层单引号，值内冒号用半角 `:`）。",
            "5. `approval_missing` 只表示验证待批准，不能记录为 completed 或 passed。",
            "6. `approval_required` Skill 只有获得本次用户明确批准后才能加 `--approved` 调用。",
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
                "conditional_required": "命中后必需",
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
