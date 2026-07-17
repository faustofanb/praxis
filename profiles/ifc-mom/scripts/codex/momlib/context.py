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
    print("快速需求控制面:")
    print("  当前主对话直接完成调查和代码修改；不默认派发 subagent/worker。")
    print("  同名需求恢复已有目录和工作树；业务聚合只用于检索候选，不同需求名默认独立新建。")
    print("  代码修改必须在工作树中进行；仅当有实际留档产出时才建立或更新需求目录。")
    print("  调查只覆盖本次修改的调用链、样例和必要数据源；完成后直接修改最小代码面。")
    print("  默认只做语法或解析检查；不默认执行 TDD、完整测试、预检、全局校验或收口门禁。")
    print()
    print("按需规则:")
    print("  仅在当前调查或代码修改确实涉及项目规则时读取对应规则/skill，不做完整上下文、详细计划或角色拆分。")
    if project in {"mes-pad", "mes-pda", "tpm-pda", "qms-pad", "wms-pda"}:
        print("  PDA 编码必须展开 .praxis/extensions/ifc-mom/rules/projects/pda/README.md 对应细则，并回报同域样例、API/路由/store/样式/性能检查证据。")
    if project == "big-screen":
        print("  大屏编码必须展开 .praxis/extensions/ifc-mom/rules/projects/big-screen/README.md 对应细则，并回报看板注册、ECharts 生命周期、数据窗口、资源和构建检查证据。")
    print("  角色协议入口：.praxis/extensions/ifc-mom/skills/global/mom-agent-workflow/SKILL.md")
    for path in worker_rule_skill_paths(project):
        print(f"  {path}")
    local_db = local_database_config(config)
    print("  涉及真实数据、表关系、字段来源、报表口径、SQL、迁移或数据修复时，先用 dbx MCP 做必要的只读调查：")
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
    print("    - 用 dbx_list_tables/dbx_execute_query 确认本次改动需要的表、字段或样例即可。")
    print("    - 调查结论仅在需求目录确有留档产出时写入；否则在交付说明中简述来源和结论。")
    print("  涉及迁移脚本、DDL、菜单授权、低代码模型/应用设计或 MagicAPI 迁移 SQL 时：")
    print("    - 开发/调查阶段只写需求目录中间产物；新需求使用 04-产出物/SQL/，老需求已有中间文档时才沿用。")
    print("    - 正式 Flyway 迁移目录只能在收尾环节、且中间产物确认并完成差异复核后写入。")
    print("  跨模块或不熟悉代码时，可用 CodeGraph 定位；不可用或过期时直接用源码搜索；过期图谱会自动排队异步刷新，缺失图谱不自动初始化。")
    print("  调查完成后不强制新增分析文件；只有需要留档的调查结论才写入需求目录。")
    print()
    print("验证命令:")
    print(f"  {verify_command(project, requirement_name)}")
    print_next_actions(project, requirement_name, "执行工作区预检")
