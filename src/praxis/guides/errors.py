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
