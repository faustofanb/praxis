"""错误码自助目录：为 praxis 错误码提供中文含义与恢复动作。"""

from __future__ import annotations

from praxis.result import Result

_ERROR_CATALOG: dict[str, dict[str, str]] = {
    "REQUIREMENT_NOT_FOUND": {
        "hint": "需求不存在：ID 拼写错误或未登记。",
        "next_step": "先 `praxis requirement show <ID> --json` 核对 ID，或 `praxis requirement new --name <简称> --request <需求>` 登记。",  # noqa: E501
    },
    "REQUIREMENT_ADVANCE_BLOCKED": {
        "hint": "状态推进被阻塞：缺失门禁或前置产出物。",
        "next_step": "查看返回的 missing_gates，补齐对应文档或门禁后再 `praxis requirement advance <ID>`。",  # noqa: E501
    },
    "REQUIREMENT_IMPLEMENTATION_RESET_REQUIRED": {
        "hint": "空列表会清空该项目已登记产出物，已 fail-closed 拒绝。",
        "next_step": "确认清空加 `--reset`；或传入完整 artifact 列表（`--project <项目>=<ART-ID,...>`）重试。",  # noqa: E501
    },
    "REQUIREMENT_REOPEN_STATUS_INVALID": {
        "hint": "当前状态不能直接 reopen 回开发。",
        "next_step": "implemented 用 `praxis requirement reopen <ID> --from implemented --reason <原因>` 单步回 in_progress；verifying 直接 reopen；其他状态先推进到 implemented/verifying。小步修复可走 fast 通道：`praxis fix start <需求ID> --repository <仓库> --small`。",  # noqa: E501
    },
    "SKILL_NODE_GATE_BLOCKED": {
        "hint": "节点 Skill 门禁未完成。",
        "next_step": "`praxis skill route-node --node <节点> --requirement <ID>` 查看 required 列表，逐项 invoke/complete 后 `praxis lifecycle complete-node --requirement <ID> --node <节点> --used-skill '<skill-id>=passed:说明'`。",  # noqa: E501
    },
    "SKILL_ROUTE_NOT_FOUND": {
        "hint": "该节点/需求缺少 Skill 路由记录。",
        "next_step": "先 `praxis skill route-node --node <节点> --requirement <ID>` 生成路由，再继续。",  # noqa: E501
    },
    "USER_APPROVAL_REQUIRED": {
        "hint": "操作需要用户明确批准。",
        "next_step": "向用户说明并征得批准后重试；批准类 Skill 需带 `--approved-skill` 或按 SKILL.md 约定。",  # noqa: E501
    },
    "WORKTREE_TEMPLATE_DIRTY": {
        "hint": "模板分支工作区有未提交变更，无法从干净模板创建工作树。",
        "next_step": "检查主工作区 `git status`，提交或清理未提交内容后重试 `praxis worktree ensure`。",  # noqa: E501
    },
    "WORKTREE_BINDING_INVALID": {
        "hint": "需求工作树绑定无效：不在绑定工作树内编辑。",
        "next_step": "进入需求绑定工作树（`.worktrees/<需求ID>__<简称>/...`）后操作。",
    },
    "WORKTREE_PREVIEW_EXPIRED": {
        "hint": "工作树预览已过期。",
        "next_step": "重新 `praxis worktree preview <ID> --repository <仓库ID>` 生成新 preview_id。",  # noqa: E501
    },
    "WORKTREE_BINDING_NOT_FOUND": {
        "hint": "未找到需求对应的工作树绑定。",
        "next_step": "先 `praxis worktree preview` + `worktree ensure --confirm` 创建绑定。",
    },
    "ARTIFACT_SOURCE_INVALID": {
        "hint": "产出物源路径无效：需要完整工作树相对路径。",
        "next_step": "使用形如 `.worktrees/<需求ID>__<简称>/<需求ID>__<简称>__<仓库ID>/<相对路径>` 的源路径重试。",  # noqa: E501
    },
    "APPROVAL_EXPIRY_INVALID": {
        "hint": "批准过期时间格式无效。",
        "next_step": "使用 ISO 8601 格式（如 2026-08-18T00:00:00+08:00）重试。",
    },
    "RTK_NOT_AVAILABLE": {
        "hint": "RTK 代理不可用。",
        "next_step": "确认 RTK 已安装且错误仅来自 RTK 自身时，按 SKILL.md 记录降级。",
    },
    "CODEGRAPH_NOT_AVAILABLE": {
        "hint": "CodeGraph 索引不可用。",
        "next_step": "检查索引状态 `praxis codegraph status --json`，必要时先同步索引再继续。",
    },
    "DBX_NOT_AVAILABLE": {
        "hint": "DBX 数据库连接不可用。",
        "next_step": "核对 project 的 DBX 引用登记（praxis.toml）与连接可达性。",
    },
    "OPERATION_NOT_FOUND": {
        "hint": "操作未在分发表中注册。",
        "next_step": "检查命令拼写或版本（`praxis version`）；升级后重试。",
    },
    # ---- fast-lane / fix 通道错误码（REQ-20260818-002 补齐） ----
    "FAST_LANE_BUDGET_EXCEEDED": {
        "hint": "fast-lane 预算超限。",
        "next_step": "降低改动范围或分批处理；预算以耗时/文件数为准。",
    },
    "FAST_LANE_BUSINESS_FILES_INVALID": {
        "hint": "fast-lane 候选文件不属于允许的业务文件范围。",
        "next_step": "核对候选文件是否命中业务文件白名单（.sql/.java 等），排除生成物与配置。",
    },
    "FAST_LANE_CANDIDATE": {
        "hint": "fast-lane 生成候选修复方案。",
        "next_step": "候选非错误；确认后继续执行。",
    },
    "FAST_LANE_CONFIRMED": {
        "hint": "fast-lane 已确认修复方案。",
        "next_step": "已确认，继续按流程实施。",
    },
    "FAST_LANE_DIFF_CHECK_FAILED": {
        "hint": "fast-lane diff 校验失败。",
        "next_step": "核对修改是否在允许范围内（文件数/行数/高风险路径），缩小改动后重试。",
    },
    "FAST_LANE_DOWNGRADED": {
        "hint": "fast-lane 已降级（不满足条件，回退标准流程）。",
        "next_step": "查看降级原因，按标准流程处理。",
    },
    "FAST_LANE_EVIDENCE_REQUIRED": {
        "hint": "fast-lane 需要证据（如 RED/GREEN 记录）。",
        "next_step": "补齐对应证据后再继续。",
    },
    "FAST_LANE_FINISH_NOT_READY": {
        "hint": "fast-lane 尚未达到 finish 条件。",
        "next_step": "确认 RED/GREEN 已记录、diff 已登记后再 finish。",
    },
    "FAST_LANE_GREEN_FAILED": {
        "hint": "fast-lane GREEN 失败。",
        "next_step": "修复实现使测试通过，重新执行 GREEN。",
    },
    "FAST_LANE_IMPLEMENTED": {
        "hint": "fast-lane 已实施完成。",
        "next_step": "继续执行验证与收尾。",
    },
    "FAST_LANE_IMPLEMENTED_VERIFICATION_INCONCLUSIVE": {
        "hint": "fast-lane 实施后验证不具结论性。",
        "next_step": "补充证据或重新验证，不能将不明确结果记为 passed。",
    },
    "FAST_LANE_NEW_TYPE_DIAGNOSTICS": {
        "hint": "fast-lane 检测到新增类型诊断。",
        "next_step": "修复新增诊断或说明其非回归。",
    },
    "FAST_LANE_NOT_FOUND": {
        "hint": "fast-lane 记录不存在。",
        "next_step": "先 `praxis fast start` 建立记录再操作。",
    },
    "FAST_LANE_PROJECT_NOT_FOUND": {
        "hint": "fast-lane 项目不存在。",
        "next_step": "核对 repository_id 是否在 praxis.toml 登记。",
    },
    "FAST_LANE_RED_AFTER_IMPLEMENTATION": {
        "hint": "fast-lane 实施后 RED 不应出现。",
        "next_step": "检查实现是否引入回退。",
    },
    "FAST_LANE_RED_INVALID": {
        "hint": "fast-lane RED 记录无效（未先失败）。",
        "next_step": "先观察测试失败再实施（TDD RED 前提）。",
    },
    "FAST_LANE_RED_NOT_READY": {
        "hint": "fast-lane RED 尚未就绪。",
        "next_step": "先运行聚焦测试确认 RED。",
    },
    "FAST_LANE_RED_RECORDED": {
        "hint": "fast-lane RED 已记录。",
        "next_step": "继续实施（GREEN）。",
    },
    "FAST_LANE_REPRODUCTION_REQUIRED": {
        "hint": "fast-lane 需要复现问题。",
        "next_step": "先复现故障再实施修复。",
    },
    "FAST_LANE_SINGLE_PROJECT_REQUIRED": {
        "hint": "fast-lane 只支持单项目。",
        "next_step": "拆分需求或指定单一项目。",
    },
    "FAST_LANE_TEST_COMMAND_INVALID": {
        "hint": "fast-lane 测试命令无效。",
        "next_step": "核对 test_commands 配置格式。",
    },
    "FAST_LANE_TYPECHECK_AMBIGUOUS": {
        "hint": "fast-lane typecheck 命令配置不唯一。",
        "next_step": "在 praxis.toml 只保留一条 typecheck_commands。",
    },
    "FAST_LANE_TYPECHECK_COMMAND_INVALID": {
        "hint": "fast-lane typecheck 命令不可解析。",
        "next_step": "核对 typecheck_commands 的引号与空格。",
    },
    "FAST_LANE_TYPECHECK_NOT_CONFIGURED": {
        "hint": "仓库缺少 typecheck_commands 配置。",
        "next_step": "在 praxis.toml 的 [[systems.repositories]] 段添加 typecheck_commands，例如 typecheck_commands = [\"mvn ... compile\"]。",  # noqa: E501
    },
    "FAST_LANE_WORKTREE_UNAVAILABLE": {
        "hint": "fast-lane 工作树不可用。",
        "next_step": "检查绑定状态（active/bound_active）与路径。",
    },
    "SMALL_FIX_BINARY_DIFF_UNSUPPORTED": {
        "hint": "小修复不支持二进制文件 diff。",
        "next_step": "排除二进制文件或改走标准流程。",
    },
    "SMALL_FIX_DIFF_CHECK_FAILED": {
        "hint": "小修复 diff 校验失败。",
        "next_step": "核对文件数/行数/高风险路径，缩小改动后重试。",
    },
    "SMALL_FIX_DOWNGRADED": {
        "hint": "小修复已降级回标准流程。",
        "next_step": "查看降级原因（隔离工作树非干净等），按标准流程处理。",
    },
    "SMALL_FIX_FLAG_REQUIRED": {
        "hint": "小修复需要 --small 标志。",
        "next_step": "`praxis fix start <需求ID> --repository <仓库> --small` 重试。",
    },
    "SMALL_FIX_GOVERNANCE_BUDGET_EXCEEDED": {
        "hint": "小修复治理预算超限。",
        "next_step": "降低改动范围或分批处理。",
    },
    "SMALL_FIX_GOVERNANCE_RATIO_EXCEEDED": {
        "hint": "小修复治理比例超限。",
        "next_step": "控制改动文件与行数在阈值内。",
    },
    "SMALL_FIX_GREEN_FAILED": {
        "hint": "小修复 GREEN 失败。",
        "next_step": "修复实现使测试通过，重新执行 GREEN。",
    },
    "SMALL_FIX_IMPLEMENTED": {
        "hint": "小修复已实施完成。",
        "next_step": "继续执行验证与收尾。",
    },
    "SMALL_FIX_IMPLEMENTED_VERIFICATION_INCONCLUSIVE": {
        "hint": "小修复实施后验证不具结论性。",
        "next_step": "补充证据或重新验证，不将不明确结果记为 passed。",
    },
    "SMALL_FIX_NEW_TYPE_DIAGNOSTICS": {
        "hint": "小修复检测到新增类型诊断。",
        "next_step": "修复新增诊断或说明其非回归。",
    },
    "SMALL_FIX_NOT_STARTED": {
        "hint": "小修复尚未开始。",
        "next_step": "先 `praxis fix start` 建立记录。",
    },
    "SMALL_FIX_PROJECT_NOT_FOUND": {
        "hint": "小修复项目不存在。",
        "next_step": "核对 repository_id 是否在 praxis.toml 登记。",
    },
    "SMALL_FIX_REPOSITORY_MISMATCH": {
        "hint": "小修复记录与请求的仓库不一致。",
        "next_step": "核对当前记录仓库与 --repository 是否一致。",
    },
    "SMALL_FIX_REQUIREMENT_STATUS_INVALID": {
        "hint": "小修复不接受当前需求状态。",
        "next_step": "支持 in_progress/ready/verifying/completed（completed 自动回退 in_progress）；其他状态先推进。",  # noqa: E501
    },
    "SMALL_FIX_SCOPED_TYPECHECK_FAILED": {
        "hint": "小修复 scoped typecheck 失败。",
        "next_step": "修复新增诊断后重试。",
    },
    "SMALL_FIX_SINGLE_REPOSITORY_REQUIRED": {
        "hint": "小修复只支持单仓库需求。",
        "next_step": "拆分需求或指定单一仓库。",
    },
    "SMALL_FIX_STARTED": {
        "hint": "小修复已开始。",
        "next_step": "继续实施与验证。",
    },
    "SMALL_FIX_TEST_COMMAND_INVALID": {
        "hint": "小修复测试命令无效。",
        "next_step": "核对 test_commands 配置格式。",
    },
    "SMALL_FIX_WORKTREE_REPOSITORY_MISMATCH": {
        "hint": "复用的工作树绑定与目标仓库不一致。",
        "next_step": "`--worktree` 的 binding 必须属于 --repository 指定的仓库，核对后重试。",
    },
    "SMALL_FIX_WORKTREE_UNAVAILABLE": {
        "hint": "小修复工作树不可用。",
        "next_step": "检查绑定状态（active/bound_active）与路径。",
    },
}

# 高频错误码之外的兜底提示
_DEFAULT_ENTRY: dict[str, str] = {
    "hint": "praxis 命令执行失败，请查看返回的 code 与 data 字段。",
    "next_step": "运行 `praxis errors <CODE>` 查看该错误码的含义与恢复动作。",
}


def lookup(code: str) -> Result:
    entry = _ERROR_CATALOG.get(code)
    if entry is None:
        return Result(False, "ERROR_NOT_FOUND", data={"code": code, **_DEFAULT_ENTRY})
    return Result(True, data={"code": code, **entry})


def all_entries() -> Result:
    return Result(True, data={"count": len(_ERROR_CATALOG), "entries": _ERROR_CATALOG})
