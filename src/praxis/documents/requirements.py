from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from praxis.documents.atomic_writer import atomic_write_text
from praxis.naming.requirement import RequirementPathPolicy, requirement_document

_MANAGED_STATE_START = "<!-- PRAXIS:MANAGED:STATE:START -->"
_MANAGED_STATE_END = "<!-- PRAXIS:MANAGED:STATE:END -->"

_STATUS_ZH = {
    "captured": "已捕获",
    "investigating": "调查中",
    "analyzed": "已分析",
    "planned": "已规划",
    "ready": "可执行",
    "in_progress": "进行中",
    "implemented": "已实施",
    "verifying": "验证中",
    "blocked": "已阻塞",
    "completed": "已完成",
    "cancelled": "已取消",
    "archived": "已归档",
}


class RequirementProjector:
    def __init__(self, knowledge_root: Path):
        self.policy = RequirementPathPolicy(knowledge_root)

    def project(self, record: dict[str, Any]) -> Path:
        target, _ = self.policy.migrate_layout(
            record["requirement_id"], record["short_name"]
        )
        target.mkdir(parents=True, exist_ok=True)
        self._ensure_structure(target, record)
        overview = target / requirement_document("overview")
        existing = overview.read_text(encoding="utf-8") if overview.is_file() else ""
        atomic_write_text(overview, self._overview(record, existing))
        atomic_write_text(
            target / requirement_document("decisions"), self._decisions(record)
        )
        progress = target / requirement_document("progress")
        if not progress.exists():
            atomic_write_text(progress, self._progress(record))
        with (target / requirement_document("events")).open(
            "a", encoding="utf-8", newline="\n"
        ) as stream:
            stream.write(
                json.dumps(
                    {
                        "event": "requirement.projected",
                        "requirement_id": record["requirement_id"],
                        "status": record["status"],
                        "time": record["updated_at"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
        return target

    def _ensure_structure(self, target: Path, record: dict[str, Any]) -> None:
        for directory in ("SQL", "数据库迁移", "脚本", "补丁", "测试报告", "其他"):
            (target / "产出物" / directory).mkdir(parents=True, exist_ok=True)
        files = {
            requirement_document("original_request"): self._original_request(record),
            requirement_document("analysis"): self._analysis(),
            requirement_document("plan"): self._plan(),
            requirement_document("acceptance"): self._acceptance(),
            requirement_document("changes"): "# 变更记录\n\n暂无变更。\n",
            requirement_document("relations"): self._relations(record),
            requirement_document("artifacts"): (
                "需求编号: " + record["requirement_id"] + "\n产出物: []\n"
            ),
        }
        for name, content in files.items():
            path = target / name
            if not path.exists():
                atomic_write_text(path, content)

    @staticmethod
    def _overview(record: dict[str, Any], existing: str = "") -> str:
        systems = "\n".join(f"  - {value}" for value in record["systems"]) or "  []"
        domains = "\n".join(f"  - {value}" for value in record["domains"]) or "  []"
        conclusion = _section(_without_managed_state(existing), "当前结论") or "待调查。"
        active_constraints = record.get("constraints", {}).get("active", [])
        constraints = (
            "\n".join(
                f"- {item['statement']} (`{item['constraint_id']}`)"
                for item in active_constraints
            )
            or "暂无。"
        )
        delivery = record.get("delivery", {})
        blocking = "需求已阻塞。" if record["status"] == "blocked" else "暂无。"
        return f"""---
需求编号: {record["requirement_id"]}
需求简称: {record["short_name"]}
需求状态: {_STATUS_ZH[record["status"]]}
业务域:
{domains}
关联系统:
{systems}
创建时间: {record["created_at"]}
更新时间: {record["updated_at"]}
---

# {record["short_name"]}

## 当前结论

{conclusion}

{_MANAGED_STATE_START}

## 当前阶段

{_STATUS_ZH[record["status"]]}。

## 当前阻塞

{blocking}

## 当前有效约束

{constraints}

## 交付状态

- 实施状态：{delivery.get("implementation_status", "not_recorded")}
- 验证状态：{delivery.get("verification_status", "not_recorded")}
- 人工验收：{delivery.get("manual_acceptance_status", "awaiting_manual_acceptance")}

{_MANAGED_STATE_END}

## 文档导航

- [原始需求](./01-原始需求.md)
- [调查分析](./02-调查分析.md)
- [实施计划](./03-实施计划.md)
- [执行进度](./04-执行进度.md)
- [决策记录](./05-决策记录.md)
- [验收结论](./06-验收结论.md)
"""

    @staticmethod
    def _decisions(record: dict[str, Any]) -> str:
        items = record.get("constraints", {}).get("historical", [])
        if not items:
            return "# 决策记录\n\n暂无。\n"
        lines = ["# 决策记录", ""]
        for item in items:
            lines.extend(
                (
                    f"## {item['constraint_id']}",
                    "",
                    f"- 结论：{item['statement']}",
                    f"- 状态：{item['status']}",
                    f"- 来源：{item.get('source') or '未记录'}",
                    f"- 覆盖：{', '.join(item.get('supersedes', [])) or '无'}",
                    f"- 被覆盖为：{item.get('superseded_by') or '无'}",
                    "",
                )
            )
        return "\n".join(lines)

    @staticmethod
    def _original_request(record: dict[str, Any]) -> str:
        quoted = "\n".join(f"> {line}" for line in record["original_request"].splitlines())
        return f"""# 原始需求

## 首次提出

### 提出时间

{record["created_at"]}

### 用户原文

{quoted}

## 后续补充
"""

    @staticmethod
    def _analysis() -> str:
        sections = (
            "需求目标",
            "业务背景",
            "当前实现",
            "涉及业务域",
            "涉及系统和仓库",
            "涉及模块",
            "业务规则",
            "数据口径",
            "接口与数据流",
            "现有能力复用",
            "代码图谱调查",
            "数据库调查",
            "影响范围",
            "风险分析",
            "待确认事项",
            "调查证据",
            "分析结论",
        )
        return (
            "# 调查分析\n\n"
            + "\n\n".join(f"## {index}、{title}" for index, title in enumerate(sections, 1))
            + "\n"
        )

    @staticmethod
    def _plan() -> str:
        return """# 实施计划

## 一、总体目标

## 二、范围说明

## 三、不在本次范围内的内容

## 四、阶段划分

## 五、阶段依赖

## 六、风险与回退方案

## 七、验证矩阵（计划阶段确认）

| 项目 | 分类 | 精确命令/方式 | 环境依赖 | 授权状态 | 证据 |
|---|---|---|---|---|---|
| 聚焦测试 | 可自动化 | 填写已批准的最小测试命令 | 本地依赖/配置 | 待确认 | 待执行 |
| 最小编译 | 可自动化 | 填写 `minimum-module-compile` 精确命令 | 模块工具链 | 待确认 | 待执行 |
| 行为级验证 | 需环境 | 填写环境操作或明确不执行 | 测试环境/服务 | 待确认 | 待执行 |
| 完整回归、lint、typecheck | 需独立授权 | 未获批不得执行 | 额外工具链 | 未授权 | 不执行 |
"""

    @staticmethod
    def _progress(record: dict[str, Any]) -> str:
        return f"""# 执行进度

## 总体进度

需求状态：{_STATUS_ZH[record["status"]]}。

## 当前阶段

{_STATUS_ZH[record["status"]]}。

## 已完成事项

暂无。

## 进行中事项

暂无。

## 阻塞事项

暂无。

## 最近一次更新

{record["updated_at"]}。
"""

    @staticmethod
    def _acceptance() -> str:
        sections = (
            "验收范围",
            "功能验收",
            "异常场景验收",
            "数据校验",
            "构建结果",
            "测试结果",
            "类型与代码质量检查",
            "影响范围复核",
            "性能验证",
            "遗留问题",
            "最终结论",
        )
        return (
            "# 验收结论\n\n"
            + "\n\n".join(f"## {index}、{title}" for index, title in enumerate(sections, 1))
            + "\n"
        )

    @staticmethod
    def _relations(record: dict[str, Any]) -> str:
        systems = "\n".join(f"  - {value}" for value in record["systems"]) or "  []"
        domains = "\n".join(f"  - {value}" for value in record["domains"]) or "  []"
        return f"""需求编号: {record["requirement_id"]}
关联系统:
{systems}
业务域:
{domains}
关联仓库: []
历史需求: []
"""


def _section(content: str, heading: str) -> str:
    marker = f"## {heading}"
    if marker not in content:
        return ""
    tail = content.split(marker, 1)[1]
    body = tail.split("\n## ", 1)[0]
    return body.strip()


def _without_managed_state(content: str) -> str:
    if _MANAGED_STATE_START in content:
        prefix = content.split(_MANAGED_STATE_START, 1)[0]
        suffix = (
            content.rsplit(_MANAGED_STATE_END, 1)[1]
            if _MANAGED_STATE_END in content
            else ""
        )
        content = prefix + suffix
    return content.replace(_MANAGED_STATE_START, "").replace(_MANAGED_STATE_END, "")
