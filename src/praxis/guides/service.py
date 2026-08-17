"""任务导向引导：按当前工作区状态输出 AI 下一步该执行的命令序列。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from praxis.result import Result
from praxis.workspace.service import WorkspaceService

_SCENARIOS = {
    "new-requirement": [
        ("登记需求", "praxis requirement new --name <简称> --request \"用户原始需求\" --system <系统ID> --domain <业务域>"),  # noqa: E501
        ("进入调查", "praxis skill route-node --node investigating --requirement <需求ID>"),  # noqa: E501
        ("按 SKILL.md 完成调查并写入 02-调查分析.md", "praxis lifecycle complete-node --requirement <需求ID> --node investigating --used-skill '<skill-id>=passed:结果说明'"),  # noqa: E501
        ("推进分析/计划", "praxis requirement advance <需求ID>"),
    ],
    "create-worktree": [
        ("确认需要改代码", "praxis requirement show <需求ID> --json"),
        ("预览工作树（固定空间/目录/分支）", "praxis worktree preview <需求ID> --repository <仓库ID>"),  # noqa: E501
        ("创建绑定工作树", "praxis worktree ensure <需求ID> --repository <仓库ID> --confirm <preview_id>"),  # noqa: E501
        ("进入工作树开发", "cd .worktrees/<需求ID>__<简称>/<需求ID>__<简称>__<仓库ID>"),  # noqa: E501
    ],
    "tdd": [
        ("先写/改测试断言并观察失败（RED）", "/Users/fausto/plugins/praxis-next/.venv/bin/python -m pytest -q <聚焦测试文件> -o addopts=''"),  # noqa: E501
        ("写最小实现使其通过（GREEN）", "同上命令复跑"),
        ("最小模块编译", "/Users/fausto/plugins/praxis-next/.venv/bin/python -m compileall -q src/praxis"),  # noqa: E501
        ("登记实施", "praxis requirement record-implementation <需求ID>"),
    ],
    "verify": [
        ("完成验证矩阵中已批准项", "按实施计划验证矩阵逐项执行"),
        ("登记未批准项为 decline", "praxis verification decline --requirement <需求ID> --entry \"<验证项>\" --user-evidence \"<原因>\""),  # noqa: E501
        ("完成节点门禁", "praxis lifecycle complete-node --requirement <需求ID> --node <节点> --used-skill '<skill-id>=passed:说明'"),  # noqa: E501
        ("推进状态", "praxis requirement advance <需求ID>"),
    ],
    "fast-fix": [
        ("确认触发 fast_fix 条件（见 praxis-requirement-workflow SKILL.md）", "用户说“快速修复”等表达，且满足单文件/低风险条件"),  # noqa: E501
        ("只改目标文件", "修改 <目标文件>"),
        ("收尾登记", "praxis fix record <需求ID> --file <文件> --verification <declined|direct> --reason <原因>"),  # noqa: E501
    ],
}

SCENARIOS = frozenset(_SCENARIOS)


class GuideService:
    """按工作区状态与场景输出下一步命令序列（纯前端，不经过 application 分发表）。"""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def render(self, scenario: str | None = None) -> Result:
        workspace = WorkspaceService(self.root).load()
        if not workspace.get("workspace"):
            return Result(
                False,
                "WORKSPACE_NOT_FOUND",
                data={"message": "当前目录不是 praxis 工作空间，先运行 `praxis init`"},
            )

        if scenario:
            if scenario not in _SCENARIOS:
                return Result(False, "GUIDE_SCENARIO_INVALID", data={"valid": sorted(_SCENARIOS)})
            return Result(True, data={"scenario": scenario, "steps": _SCENARIOS[scenario]})

        facts = workspace["workspace"]
        current = self._current_step(facts)
        return Result(
            True,
            data={
                "workspace_id": facts["id"],
                "current_step": current,
                "scenarios": sorted(_SCENARIOS),
            },
        )

    def _current_step(self, facts: dict[str, Any]) -> str:
        requirements_root = self.root / facts.get("knowledge_root", "知识库") / "需求"
        has_requirements = requirements_root.is_dir() and any(requirements_root.iterdir())
        if not has_requirements:
            return "尚未登记需求——先 `praxis guide --scenario new-requirement`"
        return (
            "已登记需求——按当前节点推进：`praxis requirement show <需求ID> --json` "
            "查看状态，再用 `praxis skill route-node --node <节点>` 获取门禁"
        )
