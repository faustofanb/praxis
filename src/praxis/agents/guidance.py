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
            "- Praxis 操作优先使用已提供的 Praxis MCP；"
            "MCP 不可用时才检查可解析的 `praxis` CLI。",
            "- 当前入口由 context 注入；MCP 不可用时先执行 "
            "`praxis doctor --json` 查看 CLI fallback.path，"
            "CLI 可解析但 MCP 会话缺失时使用该路径。",
            "- 项目包装脚本只有在当前工作区明确声明且文件存在时才允许调用；",
            "  禁止凭历史上下文推断 `scripts/codex/task.py` 或其他仓库相对入口。",
            "- DBX 调查只使用已提供的 DBX MCP 工具，不调用或回退到 DBX CLI。",
            "- 新需求先登记并生成知识文档；调查和计划阶段不要创建工作树。",
            "- 需求知识目录使用 `<需求ID>__<简称>`，文档使用固定数字前缀；旧工作空间先运行",
            "  `repair requirement-layout` 幂等迁移，冲突时不得覆盖。",
            "- 只有确认需要改代码时，才在第一次代码编辑前创建绑定需求的 Worktrunk 工作树。",
            "- 创建前先执行 `worktree preview`，展示并固定工作空间、末级目录和分支；",
            "  多仓用 `worktree ensure --confirm <preview_id>` 一次并行准备。",
            "- 工作树以仓库 `default_branch` 为本地运行模板；先合并唯一的",
            "  `origin/<template_branch>`，再从更新后的本地模板创建需求分支。",
            "- 仓库声明 `local_files` 时，只从配置的主仓库复制这些 ignored 本地运行文件；",
            "  缺失、越界或符号链接目标异常时必须阻断创建，不得扫描或复制其他 `.env*`。",
            "- 仓库声明 `worktree_setup_commands` 时，创建只做无网络快速 preflight；",
            "  依赖安装默认延迟到首次构建前显式执行 `worktree prepare`。",
            "- 显式准备命令使用 `pnpm` 时，必须按仓库 `package.json#packageManager` 的精确版本",
            "  执行；只复用已安装版本，版本未声明、不可用或不匹配时阻断，禁止联网补装。",
            "- 需求工作空间命名为 `.worktrees/<需求ID>__<简称>`；仓库末级目录命名为",
            "  `<需求ID>__<简称>__<仓库ID>`，分支命名为 `praxis/<需求ID>__<简称>`。",
            "- 首次生成的简称快照保持稳定；后续标题变化不自动迁移路径或分支，旧 binding 必须",
            "  使用正式迁移命令。阶段名称不得进入目录或分支。",
            "- 禁止在工作空间根目录或未绑定目录修改业务代码。",
            "- pre-commit 在主仓库无 binding 且检测到业务代码改动时阻断，"
            "  并提示‘请走 praxis 工作树’。",
            "- Git 工作树与 binding active 后即可编码；CodeGraph 后台排队，普通文本搜索默认",
            "  使用 `rg`（不是 `grep` 或“rg-grep”）；RTK 可用时使用 `rtk rg`，",
            "  低风险局部任务才允许回退。",
            "- 高风险改动必须在编辑前调用 `codegraph-impact-analysis`：事务、锁、原生 SQL、",
            "  并发、公共接口、共享服务、跨模块、结构迁移和高扇出改动先等待新鲜索引，再用",
            "  `codegraph_explore` 保存调用路径和 Blast Radius；不得等连续错误后才刷新。",
            "- investigating 节点遇到跨模块、公共接口或影响范围调查时也必须路由 CodeGraph。",
            "  Plan Mode 无需求和 binding 时，使用 `praxis codegraph investigate <target>",
            "  --project <项目> --purpose <目的>` 只读查询项目画像中的现有有效索引；结果返回",
            "  `persisted: false`，不得初始化或同步索引，也不能替代实施阶段需求工作树 binding",
            "  上的正式 `codegraph-impact-analysis` 审计。",
            "- 所有外部命令必须先由 RTK 代理：优先专用子命令（如 `rtk rg`、`rtk mvn`），",
            "  其余按输出类型使用 `rtk test`、`rtk err` 或保留原始输出的 `rtk proxy`；",
            "  机器 JSON、交互式命令和无专用适配命令也必须先用 `rtk proxy`。",
            "- 只有错误明确来自 RTK 自身执行失败时才允许直接命令降级；必须记录原 RTK 命令、",
            "  RTK 错误和降级命令。被代理的编译或测试自身失败不得通过直跑掩盖。",
            "- `worktree ensure` 成功后自动生成当前项目的 coder context；启动 Agent 时必须先读取",
            "  handoff 和 context，不得依赖聊天记忆补齐项目、约束或验证授权。",
            "- 数据库调查必须从 context 的已登记 DBX 引用中显式选择连接，禁止依赖默认数据库；",
            "  对结构或数据作出判断前先执行 `select current_database()` 核对目标库。",
            "- 规划模式禁止正式登记需求时，可用 `praxis database investigate` 调查项目画像已登记的",
            "  连接，包括已登记的生产连接；该入口只接受有目的的只读 SQL、自动核验当前库且返回",
            "  `persisted: false`。仍禁止生产写入、锁定读取、改连接、默认库猜测，且不得把临时结论",
            "  伪装成正式需求证据。",
            "- 功能、缺陷修复、重构和行为变更默认执行 TDD：先运行计划中列明的聚焦测试并观察",
            "  预期失败（RED），再写最小实现使其通过（GREEN），之后才重构；开发开始前把精确",
            "  命令保存为 `development_tdd` approval receipt。先写实现后补测试不得算作 TDD。",
            "- 聚焦 TDD 授权不包含完整回归、lint、format、typecheck、覆盖率、构建或代码复核；",
            "  这些操作仍需独立验证授权。用户明确拒绝或适用例外时必须留痕，不得声称完成 TDD。",
            "- TDD GREEN 后必须调用 `minimum-module-compile`：只编译最小受影响模块并记录项目、",
            "  模块、精确命令和 exit code；禁止扩大为全仓构建，无法确定安全命令时必须暂停。",
            "- 除已登记的 `development_tdd` 聚焦命令外，未经本次明确批准，不得启动",
            "  reviewer/tester Agent，也不得运行 lint、format、typecheck、其他测试、覆盖率或",
            "  质量复核。提交、推送、完成、继续不等于批准。",
            "- 使用 Skill 前先执行节点路由；`routed` 仅代表候选，必须记录 `invoked` 和",
            "  `completed`，节点门禁才视为真实使用。",
            "- 已实际完成节点 Skill 时使用 `lifecycle complete-node --used-skill` 原子提交",
            "  `passed/not_applicable/approval_missing/failed`；未列出的 Skill 不得自动",
            "  冒充已使用。",
            "- `--used-skill` 示例：`--used-skill 'skill-id=passed:结果说明'`；外层使用单引号，",
            "  值内冒号必须使用半角 `:`，避免全角标点或 shell 拆词。",
            "- 需求按 `in_progress → implemented → verifying → completed` 推进；使用",
            "  `requirement advance` 一次只前进一个状态并显示缺失门禁。",
            "  路由缓存只复用指纹完全相同的决策，不缓存人工批准。",
            "- 产出物在代码稳定后登记；相同需求+路径的 `artifact add` 是 upsert，不重复建立条目；",
            "  Praxis 将独立快照归档到需求 `产出物/`，源路径漂移不能替代归档完整性校验。",
            "- 需求从 verifying 回开发使用带原因的 `requirement reopen`，不通过 blocked 绕行。",
            "- 未经直接用户授权不得生成 approval receipt；有收据时也只匹配当前需求的精确验证项。",
            "- 实施完成不等于验证通过；分别记录实施、验证和人工验收状态。用户明确不执行某项",
            "  验证时登记 decline receipt，不能把 declined 或未执行投影为 passed。",
            "",
            "### 禁止机械执行命令",
            "",
            "- 命令必须用于消除一个会影响实现决策或交付结论的具体不确定性。执行前必须能说明：",
            "  要验证的具体风险、成功和失败分别导致什么行动、是否已有等价证据，以及是否有更小、",
            "  更直接的验证方式；成功和失败都不改变下一步时禁止执行。",
            "- 禁止为了满足 TDD、编译或 Skill 门禁创建只验证实现细节的测试：不得用反射测试证明",
            "  注解存在，不得用读取源码或正则匹配源码冒充行为测试，也不得只验证工具函数如何调用",
            "  另一个函数。真实验证需要 Spring、MyBatis 或数据库且用户选择快速修复时，记录未运行",
            "  集成验证，不创建替代性假测试；删除抽象时一并删除只服务于该抽象的测试。",
            "- 用户明确说“快速修复”“只改这里”“不要走标准流程”“就加个注解”“不要跑测试”或",
            "  “别写测试脚本”时，单文件且无数据库结构、API 契约或公共接口变更的修改进入 fast_fix，",
            "  并在执行扩展前记录 `mode=fast_fix`、`tests=declined_by_user`、",
            "  `compile=not_requested`、`scope=target_file_only`。",
            "- fast_fix 默认不运行测试、编译、全量类型检查和质量复核；"
            "  只查看目标代码及一个相似写法、",
            "  修改目标文件、做一次与风险直接相关的检查，并如实汇报未执行的验证。",
            "- 证据按工作树、HEAD 和目标文件指纹缓存；指纹未变化时必须复用 "
            "  CodeGraph、模块编译、",
            "  类型错误基线、接口签名、SQL 结构和调用路径证据，不得重复查询或机械重跑。",
            "- 极小修改预算为 0–2 条命令、1–2 分钟；单页面或单方法小修复为 3–5 条命令、",
            "  3–5 分钟。超过软预算必须先说明新增命令消除什么新风险；"
            "  fast_fix 超过 5 条命令或 3 分钟",
            "  时停止并说明原因。",
            "- fast_fix 收尾使用一次 `praxis fix record <需求ID> --file <文件> "
            "--verification <declined|direct> --reason <原因>`；该命令一次登记验证省略、证据、",
            "  单个代码变更产出物和 implementation，不逐个执行 reopen、route、invoke、complete、",
            "  gate、artifact、record 或 advance。",
            "- 同一问题默认最多一次恢复和一次重试；超出 budget 后停止循环并报告。",
            "- 只在存在两个以上独立任务，或一个边界清晰且预计超过两分钟的任务时使用 subagent；",
            "  默认 `fork_turns=none` + 精简交接包，父节点单写需求状态与 Skill gate。",
            "- 过程更新只报告“已完成、当前阻塞、下一步”，不重复执行无新证据的状态/路由命令。",
            "- 高频 CLI 默认输出紧凑摘要；自动化需要完整字段时显式使用 `--json`，需要紧凑",
            "  单行机器结果时使用 `--summary`，不要把完整路由和画像重复注入聊天上下文。",
            "- 状态流转和 `worktree create` 都是 fail-closed；当前节点缺少 route、完成凭证或",
            "  gate 时必须停止，不得自动补路由或绕过。",
            "- 第三方 Skill 缺失时报告来源和缺失项，不得在 bootstrap 中自动安装。",
            "",
            "### Skill 调用协议",
            "",
            "1. 进入节点先运行 `praxis skill route-node --node <节点> --requirement <需求ID>`。",
            "2. 对决定使用的 Skill 运行 `praxis skill invoke <Skill ID> "
            "--requirement <需求ID> --node <节点>`。",
            "3. Skill 工作完成后，用返回的 invocation ID 运行 `praxis skill complete <调用ID>`。",
            "4. 多 Skill 节点优先运行 `praxis lifecycle complete-node --requirement <需求ID>`",
            "  并逐项传入 `--used-skill <id>=<result>:<outcome>`；单项流程仍可显式运行 gate。",
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
