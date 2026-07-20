from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from praxis.documents.atomic_writer import atomic_write_text
from praxis.naming.requirement import RequirementPathPolicy

_STATUS_ZH = {
    "captured": "已捕获",
    "investigating": "调查中",
    "analyzed": "已分析",
    "planned": "已规划",
    "ready": "可执行",
    "in_progress": "进行中",
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
        target = self.policy.requirement_path(record["requirement_id"], record["short_name"])
        target.mkdir(parents=True, exist_ok=True)
        self._ensure_structure(target, record)
        atomic_write_text(target / "需求总览.md", self._overview(record))
        atomic_write_text(target / "执行进度.md", self._progress(record))
        with (target / "事件记录.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
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
            "原始需求.md": self._original_request(record),
            "调查分析.md": self._analysis(),
            "实施计划.md": self._plan(),
            "验收结论.md": self._acceptance(),
            "变更记录.md": "# 变更记录\n\n暂无变更。\n",
            "关联关系.yaml": self._relations(record),
            "产出物清单.yaml": "需求编号: " + record["requirement_id"] + "\n产出物: []\n",
        }
        for name, content in files.items():
            path = target / name
            if not path.exists():
                atomic_write_text(path, content)

    @staticmethod
    def _overview(record: dict[str, Any]) -> str:
        systems = "\n".join(f"  - {value}" for value in record["systems"]) or "  []"
        domains = "\n".join(f"  - {value}" for value in record["domains"]) or "  []"
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

待调查。

## 当前阶段

{_STATUS_ZH[record["status"]]}。

## 当前阻塞

暂无。

## 文档导航

- [原始需求](./原始需求.md)
- [调查分析](./调查分析.md)
- [实施计划](./实施计划.md)
- [执行进度](./执行进度.md)
- [验收结论](./验收结论.md)
"""

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
