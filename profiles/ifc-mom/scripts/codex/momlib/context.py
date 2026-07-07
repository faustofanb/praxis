from __future__ import annotations

from typing import Any

from .config import local_database_config, project_config
from . import praxis_contracts


def rule_skill_paths(project: str) -> list[str]:
    """返回主对话恢复上下文时的最小控制面规则。

    需求 README 会引用这里的输出；因此只保留控制面入口，不把项目细则
    和通用导航写进主对话恢复索引。项目规则和 skill 由 worker 子任务读取。
    """
    return [
        "AGENTS.md",
        ".praxis/rules/praxis-workflow.md",
        ".praxis/extensions/ifc-mom/skills/global/mom-agent-workflow/SKILL.md",
    ]


def verify_command(project: str, requirement_name: str | None = None) -> str:
    """生成推荐验证命令；带需求名时会定位对应 worktree。"""
    if project == "docs":
        return "文档类需求按变更内容人工复核。"
    if project == "big-screen":
        return "npm run build:dashboard -- <看板名称> 或 npm run build:report"
    suffix = f" {requirement_name}" if requirement_name else ""
    return praxis_contracts.praxis_usage(f"project verify {project}{suffix}")


def print_next_actions(project: str, requirement_name: str, recommended: str) -> None:
    """打印用户可选择的下一步动作。"""
    actions = [
        ("恢复完整上下文", praxis_contracts.praxis_usage(f"context {project} {requirement_name}")),
        ("执行工作区预检", praxis_contracts.praxis_usage(f"project preflight {project} {requirement_name}")),
        ("进入收口聚合", praxis_contracts.praxis_usage(f"gate ready {project} {requirement_name}")),
    ]
    print("nextActions:")
    for label, command in actions:
        marker = "[推荐] " if label == recommended else ""
        print(f"  - {marker}{label}: {command}")


def context_brief_command(config: dict[str, Any], project: str, requirement_name: str) -> None:
    """打印低噪声恢复摘要；完整角色协议只在 full context 中展开。"""
    project_config(config, project)
    from .docs import requirement_dir

    print("Context brief")
    print(f"  需求目录: {requirement_dir(config, requirement_name)}")
    print(f"  目标项目: {project}")
    print(f"  需求名: {requirement_name}")
    print(f"  推荐验证: {verify_command(project, requirement_name)}")
    print(f"  收口聚合: {praxis_contracts.praxis_usage(f'gate ready {project} {requirement_name}')}")
    print(f"  完整上下文: {praxis_contracts.praxis_usage(f'context {project} {requirement_name}')}")
    print_next_actions(project, requirement_name, "恢复完整上下文")


def worker_rule_skill_paths(project: str) -> list[str]:
    """返回交给角色 agent/subagent 的按项目最小规则和 skill。"""
    mapping = {
        "backend": [
            ".praxis/extensions/ifc-mom/skills/global/mom-database-investigation/SKILL.md",
            ".praxis/extensions/ifc-mom/skills/global/mom-delivery-branch-hygiene/SKILL.md",
            ".praxis/extensions/ifc-mom/skills/global/mom-code-quality-compliance/SKILL.md",
            ".praxis/extensions/ifc-mom/rules/projects/backend/README.md",
            ".praxis/extensions/ifc-mom/skills/projects/backend/README.md",
        ],
        "web": [
            ".praxis/extensions/ifc-mom/skills/global/mom-frontend-pattern-search/SKILL.md",
            ".praxis/extensions/ifc-mom/skills/global/mom-database-investigation/SKILL.md",
            ".praxis/extensions/ifc-mom/skills/global/mom-delivery-branch-hygiene/SKILL.md",
            ".praxis/extensions/ifc-mom/skills/global/mom-code-quality-compliance/SKILL.md",
            ".praxis/extensions/ifc-mom/rules/projects/web/README.md",
            ".praxis/extensions/ifc-mom/skills/projects/web/README.md",
        ],
        "mes-pad": [
            ".praxis/extensions/ifc-mom/skills/global/mom-database-investigation/SKILL.md",
            ".praxis/extensions/ifc-mom/skills/global/mom-delivery-branch-hygiene/SKILL.md",
            ".praxis/extensions/ifc-mom/rules/projects/pda/README.md",
            ".praxis/extensions/ifc-mom/skills/projects/pda/pda-development/SKILL.md",
        ],
        "mes-pda": [
            ".praxis/extensions/ifc-mom/skills/global/mom-database-investigation/SKILL.md",
            ".praxis/extensions/ifc-mom/skills/global/mom-delivery-branch-hygiene/SKILL.md",
            ".praxis/extensions/ifc-mom/rules/projects/pda/README.md",
            ".praxis/extensions/ifc-mom/skills/projects/pda/pda-development/SKILL.md",
        ],
        "tpm-pda": [
            ".praxis/extensions/ifc-mom/skills/global/mom-database-investigation/SKILL.md",
            ".praxis/extensions/ifc-mom/skills/global/mom-delivery-branch-hygiene/SKILL.md",
            ".praxis/extensions/ifc-mom/rules/projects/pda/README.md",
            ".praxis/extensions/ifc-mom/skills/projects/pda/pda-development/SKILL.md",
        ],
        "qms-pad": [
            ".praxis/extensions/ifc-mom/skills/global/mom-database-investigation/SKILL.md",
            ".praxis/extensions/ifc-mom/skills/global/mom-delivery-branch-hygiene/SKILL.md",
            ".praxis/extensions/ifc-mom/rules/projects/pda/README.md",
            ".praxis/extensions/ifc-mom/skills/projects/pda/pda-development/SKILL.md",
        ],
        "wms-pda": [
            ".praxis/extensions/ifc-mom/skills/global/mom-database-investigation/SKILL.md",
            ".praxis/extensions/ifc-mom/skills/global/mom-delivery-branch-hygiene/SKILL.md",
            ".praxis/extensions/ifc-mom/rules/projects/pda/README.md",
            ".praxis/extensions/ifc-mom/skills/projects/pda/pda-development/SKILL.md",
        ],
        "big-screen": [
            ".praxis/extensions/ifc-mom/skills/global/mom-database-investigation/SKILL.md",
            ".praxis/extensions/ifc-mom/skills/global/mom-delivery-branch-hygiene/SKILL.md",
            ".praxis/extensions/ifc-mom/rules/projects/big-screen/README.md",
            ".praxis/extensions/ifc-mom/skills/projects/big-screen/big-screen-development/SKILL.md",
        ],
        "docs": [
            ".praxis/extensions/ifc-mom/skills/global/mom-doc-organization/SKILL.md",
            ".praxis/extensions/ifc-mom/skills/global/mom-tolaria-vault/SKILL.md",
            ".praxis/extensions/ifc-mom/skills/global/mom-praxis-command-contract/SKILL.md",
            ".praxis/extensions/ifc-mom/skills/global/mom-context-budgeting/SKILL.md",
        ],
    }
    return mapping.get(project, [])


def context_command(config: dict[str, Any], project: str, requirement_name: str) -> None:
    """打印继续处理某个需求时最小需要加载的上下文。"""
    project_config(config, project)
    from .docs import requirement_dir

    print(f"需求目录: {requirement_dir(config, requirement_name)}")
    print(f"目标项目: {project}")
    print()
    print("主对话控制面:")
    print("  当前用户直接对话默认就是 Main Agent；只有收到明确的 role_agent 子任务输入时，才按非主角色处理。")
    print("  Main Agent 只负责需求拆解、文档迭代、角色派发、锁协调、验收记录和最终决策。")
    print("  需求拆解优先派发 Requirement Agent；代码编写和测试必须交给 Execution Agent，避免主对话加载实现细节。")
    print("  质量复核交给 Quality Agent；交付就绪审计交给 Delivery Agent。")
    print("  过程说明必须标注 subagent 状态：planned/active/blocked/completed/waived；异常时及时接管或重派。")
    print("  需求落点确认后只检查需求相关路径状态；不要用根目录全局 git status 作为业务需求默认状态检查。")
    print()
    print("角色 Agent 子任务上下文:")
    print("  角色 Agent 是职责协议，实际仍通过 subagent/worker 等运行时承载。")
    print("  role_agent 必须明确为 requirement/execution/quality/delivery；运行时仍可使用 explorer/worker/default。")
    print("  Execution Agent 按任务落点读取以下最小规则/skill；Quality Agent 按变更落点引用对应项目规则做独立复核。")
    print("  role agent 与主对话使用同一工作区，不是隔离副本；必须遵守派发时声明的读写范围和写锁，不得覆盖他人改动。")
    print("  role agent 禁止继续派发 subagent/Agent/worker；需要继续拆分时回报 BLOCKED 或 CHECKPOINT，由主对话重新派发。")
    print("  Codeup Git 操作优先使用 task/rtk 工作流入口；必须手工执行时用 rtk git 或 /usr/bin/git，禁止裸 git。")
    print("  实现/调查任务先输出简短实施计划、关键风险/待确认项、拟运行验证命令和文档回写位置，再开始改动。")
    print("  按任务类型显式使用项目 skill；Superpowers 可用时作为辅助，不作为工作流前置依赖。")
    print("  非平凡实现先给短设计；缺陷修复先给失败证据或定位依据；完成前必须给验证证据或无法验证原因。")
    print("  主对话必须自动规划 subagent/worker 拆分；若运行时策略要求用户显式授权才能 spawn，则标记 waived/blocked 并本地接管。")
    print("  长任务、多项目、大日志或大 diff 必须使用 .praxis/extensions/ifc-mom/skills/global/mom-context-budgeting/SKILL.md 控制上下文预算。")
    if project in {"backend", "web"}:
        print("  后端/Web 编码必须使用 .praxis/extensions/ifc-mom/skills/global/mom-code-quality-compliance/SKILL.md，回报同域样例、规则、自检和偏离说明。")
    if project in {"mes-pad", "mes-pda", "tpm-pda", "qms-pad", "wms-pda"}:
        print("  PDA 编码必须展开 .praxis/extensions/ifc-mom/rules/projects/pda/README.md 对应细则，并回报同域样例、API/路由/store/样式/性能检查证据。")
    if project == "big-screen":
        print("  大屏编码必须展开 .praxis/extensions/ifc-mom/rules/projects/big-screen/README.md 对应细则，并回报看板注册、ECharts 生命周期、数据窗口、资源和构建检查证据。")
    print("  角色协议入口：.praxis/extensions/ifc-mom/skills/global/mom-agent-workflow/SKILL.md")
    for path in worker_rule_skill_paths(project):
        print(f"  {path}")
    local_db = local_database_config(config)
    print("  涉及真实数据、表关系、字段来源、报表口径、SQL、迁移或数据修复时，先用 dbx MCP 做真实库只读调查：")
    print("    - 先 dbx_list_connections 确认连接；默认只查 LOCAL/DEV，PRO 或疑似生产库必须先获明确许可。")
    if local_db["database"]:
        print(
            "    - "
            f"本 workspace 本地数据库: connection={local_db['connection']}, "
            f"database={local_db['database']}, schema={local_db['schema']}；"
            "每次查询前确认 current_database()，dbx 查询必须命中该库。"
        )
    else:
        print("    - 本 workspace 未配置 [database.local].database；查库前必须向用户确认目标库名。")
    print("    - 通过 dbx_list_tables/dbx_execute_query 确认表结构、索引/约束、字典/主数据、样例数据、数据分布和异常样本。")
    print("    - 需要表字段、索引或约束细节时，用 information_schema 或 pg_catalog 只读 SQL 查询。")
    print("    - Code Graph、源码和历史文档只作为定位辅助，数据口径结论必须回到真实库确认。")
    print("    - 调查结论写入 01-需求分析拆解/ 或 04-产出物/关联信息调查/；无法连接数据库时记录原因和待人工确认项。")
    print("  涉及迁移脚本、DDL、菜单授权、低代码模型/应用设计或 MagicAPI 迁移 SQL 时：")
    print("    - 开发/调查阶段只写需求目录中间产物；新需求使用 04-产出物/SQL/，老需求已有中间文档时才沿用。")
    print("    - 正式 Flyway 迁移目录只能在收尾环节、且中间产物确认并完成差异复核后写入。")
    print("  跨模块或不熟悉代码时，worker 先查 Praxis Code Graph：")
    print("    - 先运行 task system -- code-graph check；失败或过期时先运行 task system -- code-graph build。")
    print("    - 使用 task system -- code-graph query --refresh <关键词> 定位候选文件，再精读源码。")
    print("    - 不得仅因图谱过期直接降级为源码 grep；只有 build/query 失败时才记录原因并用源码搜索兜底。")
    print("    - 图谱结论必须回到源码、SQL 或需求文档确认。")
    print("  调查完成后必须新增或更新 01-需求分析拆解/ 的证据化分析文件，写清来源、路径/表字段、样例数据、结论和未决项。")
    print()
    print("验证命令:")
    print(f"  {verify_command(project, requirement_name)}")
    print_next_actions(project, requirement_name, "执行工作区预检")
