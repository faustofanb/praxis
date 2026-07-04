from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from .config import project_config
from .context import rule_skill_paths, verify_command
from .names import safe_path_leaf, today
from .paths import ROOT_DIR
from .process import fail


ITER_PHASES = {
    "analysis": ("01-需求分析拆解", "分析"),
    "plan": ("02-任务规划", "规划"),
    "progress": ("03-开发进度", "进度"),
}

RAW_REQUIREMENT_PLACEHOLDERS = {
    "用户原始需求",
    "原始需求",
    "需求原文",
    "待补充",
    "见上",
    "见上文",
    "如上",
    "同上",
}
GENERIC_REQUIREMENT_NAMES = {"task", "todo", "tmp", "temp", "demo", "test", "fix", "bug", "需求", "任务"}
BUSINESS_OBJECT_KEYWORDS = [
    "金属平衡",
    "挤压产出",
    "合金产出",
    "设备采购申请",
    "采购申请",
    "备件领用",
    "SAP接口",
    "SAP",
    "MagicAPI",
    "低代码",
    "菜单授权",
    "迁移",
    "Flyway",
    "模具",
    "冲具",
    "点检",
    "报废",
    "库存",
    "报表",
]
BUSINESS_DOMAIN_RULES = [
    ("purchase", "purchase-requisition", "采购申请", ["设备采购申请", "采购申请"]),
    ("equipment", "spare-part-requisition", "备件领用", ["备件领用"]),
    ("mes-extrusion", "metal-balance", "金属平衡", ["金属平衡", "挤压产出", "合金产出"]),
    ("integration", "sap-interface", "SAP接口", ["SAP接口", "SAP"]),
    ("reporting", "business-report", "业务报表", ["报表", "驾驶舱"]),
]
DOMAIN_GENERATED_START = "<!-- praxis:domain-index:start -->"
DOMAIN_GENERATED_END = "<!-- praxis:domain-index:end -->"
TOLARIA_SKIP_DIRS = {".git", ".obsidian", ".tolaria", ".tolaria-rename-txn", ".vscode", "attachments", "附件"}
TOLARIA_REQUIRED_FIELDS = {"type", "title", "created", "tags"}


def docs_root(config: dict[str, Any]) -> Path:
    """返回 docs 子仓库目录，并确保目录存在。"""
    docs = project_config(config, "docs")
    root = ROOT_DIR / docs.get("path", "docs")
    root.mkdir(parents=True, exist_ok=True)
    return root


def requirement_root(config: dict[str, Any]) -> Path:
    """返回需求文档归档根目录。"""
    root = docs_root(config) / "02-req"
    root.mkdir(parents=True, exist_ok=True)
    return root


def domain_root(config: dict[str, Any]) -> Path:
    """返回业务聚合知识沉淀根目录。"""
    root = docs_root(config) / "01-domain"
    root.mkdir(parents=True, exist_ok=True)
    return root


def requirement_dir(config: dict[str, Any], requirement_name: str) -> Path:
    """按日期和简短中文需求名生成标准需求目录路径。"""
    month = today()[:7]
    return requirement_root(config) / month / f"{today()}-{safe_path_leaf(requirement_name)}"


def find_requirement_dir(config: dict[str, Any], requirement_name: str) -> Path:
    """按需求名查找已存在的需求目录，优先返回最近创建的同名目录。"""
    safe_name = safe_path_leaf(requirement_name)
    root = requirement_root(config)
    candidates = sorted(root.glob(f"*/*-{safe_name}"))
    if not candidates:
        candidates = sorted(docs_root(config).glob(f"20??-??/*-{safe_name}"))
    if candidates:
        return candidates[-1]
    return requirement_dir(config, requirement_name)


def timestamp() -> str:
    """返回需求迭代文件名使用的时间戳。"""
    return dt.datetime.now().strftime("%Y-%m-%d-%H%M")


def write_file_once(path: Path, content: str) -> None:
    """只在文件不存在时写入模板，避免覆盖用户已经补充的需求内容。"""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def yaml_value(value: str) -> str:
    """返回适合 Tolaria frontmatter 的 YAML 字符串值。"""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def tolaria_frontmatter(
    doc_type: str,
    title: str,
    created_at: str,
    tags: list[str],
    fields: dict[str, str] | None = None,
) -> str:
    """生成 Tolaria 兼容的 YAML frontmatter，作为既有文档结构的补充索引。"""
    lines = [
        "---",
        f"type: {yaml_value(doc_type)}",
        f"title: {yaml_value(title)}",
        f"created: {yaml_value(created_at)}",
    ]
    for key, value in (fields or {}).items():
        lines.append(f"{key}: {yaml_value(value)}")
    lines.append("tags:")
    lines.extend(f"  - {yaml_value(tag)}" for tag in tags)
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def workspace_root_for_docs(config: dict[str, Any]) -> Path:
    """按 docs 项目路径推导工作区根目录，用于写 `.praxis/out` 报告。"""
    root = docs_root(config)
    if root.name == "docs":
        return root.parent
    return root


def tolaria_report_dir(config: dict[str, Any]) -> Path:
    """返回 Tolaria 检查报告目录。"""
    path = workspace_root_for_docs(config) / ".praxis" / "out" / "tolaria"
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_frontmatter(text: str) -> tuple[dict[str, str], int]:
    """读取 Markdown 文件头 YAML frontmatter 的一层标量字段。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, 0
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            fields: dict[str, str] = {}
            for line in lines[1:index]:
                if ":" not in line or line.startswith(" "):
                    continue
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip().strip('"')
            return fields, index + 1
    return {}, 0


def markdown_first_h1(text: str, start_line: int = 0) -> str:
    """返回 frontmatter 之后的第一个 H1 标题。"""
    for line in text.splitlines()[start_line:]:
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return ""


def should_skip_tolaria_path(path: Path) -> bool:
    """过滤 Tolaria 本地缓存、Git 目录、附件目录等非笔记路径。"""
    return any(part in TOLARIA_SKIP_DIRS for part in path.parts)


def iter_tolaria_markdown_files(root: Path) -> list[Path]:
    """列出可纳入 Tolaria 检查的 Markdown 笔记。"""
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.md") if path.is_file() and not should_skip_tolaria_path(path))


def tolaria_scan_roots(config: dict[str, Any], args: list[str]) -> tuple[str, list[Path]]:
    """解析 Tolaria check/publish 目标。"""
    docs = docs_root(config)
    if not args or args == ["--all"]:
        roots = [path for path in [docs / "02-req", docs / "03-etl"] if path.exists()]
        return "--all", roots
    target = " ".join(args)
    req_dir = find_requirement_dir(config, target)
    if not req_dir.is_dir():
        fail(f"requirement docs not found: {target}")
    return target, [req_dir]


def tolaria_issue(path: Path, code: str, message: str) -> dict[str, str]:
    """构造 Tolaria 检查问题记录。"""
    return {"path": path.as_posix(), "code": code, "message": message}


def tolaria_check(config: dict[str, Any], args: list[str]) -> Path:
    """扫描 docs 中 Tolaria 元数据缺口，只写检查报告，不修改文档。"""
    target, roots = tolaria_scan_roots(config, args)
    docs = docs_root(config)
    issues: list[dict[str, str]] = []
    scanned = 0
    for root in roots:
        for path in iter_tolaria_markdown_files(root):
            scanned += 1
            text = path.read_text(encoding="utf-8")
            fields, body_start = parse_frontmatter(text)
            relative = path.relative_to(docs)
            if not fields:
                issues.append(tolaria_issue(relative, "missing_frontmatter", "missing YAML frontmatter"))
            else:
                for key in sorted(TOLARIA_REQUIRED_FIELDS - fields.keys()):
                    issues.append(tolaria_issue(relative, f"missing_{key}", f"missing frontmatter field: {key}"))
            if not markdown_first_h1(text, body_start):
                issues.append(tolaria_issue(relative, "missing_h1", "missing first H1 title"))

    report = {
        "schemaVersion": 1,
        "target": target,
        "scanned": scanned,
        "issueCount": len(issues),
        "issues": issues,
    }
    report_path = tolaria_report_dir(config) / "tolaria-check.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Tolaria check report: {report_path}")
    return report_path


def write_file_if_missing(path: Path, content: str) -> None:
    """只写缺失的 Tolaria 类型和视图文件，避免覆盖用户维护内容。"""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def publish_tolaria_types_and_views(config: dict[str, Any]) -> list[Path]:
    """发布 MOM docs vault 的基础 Type 和 saved view。"""
    docs = docs_root(config)
    outputs = [
        docs / "types" / "requirement.md",
        docs / "types" / "requirement-stage.md",
        docs / "types" / "etl-asset.md",
        docs / "views" / "active-requirements.yml",
        docs / "views" / "etl-assets.yml",
        docs / "types" / "domain-aggregate.md",
        docs / "views" / "domain-aggregates.yml",
    ]
    write_file_if_missing(
        outputs[0],
        """---
type: Type
_icon: clipboard-list
_color: "#2563eb"
_order: 10
_list_properties_display:
  - status
  - project
  - created
_sort: "property:created:desc"
---

# Requirement

业务需求 README。由 Praxis 生成目录结构，由 Tolaria 提供关系、属性和视图聚合。
""",
    )
    write_file_if_missing(
        outputs[1],
        """---
type: Type
_icon: file-text
_color: "#7c3aed"
_order: 20
_list_properties_display:
  - requirement
  - created
_sort: "property:created:desc"
---

# Requirement Stage

需求分析、计划、进度和产出物阶段文档。
""",
    )
    write_file_if_missing(
        outputs[2],
        """---
type: Type
_icon: database
_color: "#059669"
_order: 30
_list_properties_display:
  - system
  - menu_path
  - status
_sort: "property:system:asc"
---

# ETL Asset

可复用 ETL、指标口径、SQL 和报表资产。
""",
    )
    write_file_if_missing(
        outputs[3],
        """name: Active Requirements
icon: clipboard-list
color: "#2563eb"
sort: "property:created:desc"
filters:
  all:
    - field: type
      op: equals
      value: requirement
    - field: status
      op: not_equals
      value: 已完成
""",
    )
    write_file_if_missing(
        outputs[4],
        """name: ETL Assets
icon: database
color: "#059669"
sort: "property:system:asc"
filters:
  any:
    - field: type
      op: equals
      value: etl-asset
    - field: tags
      op: contains
      value: ifc-mom/etl
""",
    )
    write_file_if_missing(
        outputs[5],
        """---
type: Type
_icon: boxes
_color: "#0f766e"
_order: 25
_list_properties_display:
  - bounded_context
  - aggregate
_sort: "property:bounded_context:asc"
---

# Domain Aggregate

业务聚合知识页。需求目录记录交付过程，业务聚合页沉淀长期口径、规则和历史坑点。
""",
    )
    write_file_if_missing(
        outputs[6],
        """name: Domain Aggregates
icon: boxes
color: "#0f766e"
sort: "property:bounded_context:asc"
filters:
  all:
    - field: type
      op: equals
      value: domain-aggregate
""",
    )
    return outputs


def publish_requirement_tolaria_index(config: dict[str, Any], requirement_name: str, req_dir: Path) -> Path:
    """发布单个需求的 Tolaria 知识索引，不改变标准需求目录结构。"""
    created_at = timestamp()
    index_path = req_dir / "04-产出物" / "Tolaria知识索引.md"
    stage_links: list[str] = []
    for relative_dir in ["00-原始需求", "01-需求分析拆解", "02-任务规划", "03-开发进度", "04-产出物"]:
        directory = req_dir / relative_dir
        if directory.is_dir():
            for file in sorted(directory.glob("*.md")):
                if file.name != "Tolaria知识索引.md":
                    stage_links.append(f"- [{file.stem}](../{file.relative_to(req_dir).as_posix()})")
    content = (
        tolaria_frontmatter(
            "tolaria-knowledge-index",
            f"{requirement_name} Tolaria 知识索引",
            created_at,
            ["ifc-mom/requirement", "ifc-mom/tolaria"],
            {"requirement": requirement_name, "related_to": f"[[{requirement_name}]]"},
        )
        + f"""# {requirement_name} Tolaria 知识索引

## 关系

- 需求：[[{requirement_name}]]
- 类型：[[Requirement]]

## 标准目录链接

- [需求 README](../README.md)

## 阶段文档

"""
        + "\n".join(stage_links)
        + "\n"
    )
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(content, encoding="utf-8")
    return index_path


def tolaria_publish(config: dict[str, Any], args: list[str]) -> Path:
    """发布 Tolaria 类型、视图和需求知识索引；不重写需求正文。"""
    target, roots = tolaria_scan_roots(config, args)
    outputs = publish_tolaria_types_and_views(config)
    index_paths: list[Path] = []
    if target == "--all":
        req_dirs = [path for path in requirement_root(config).glob("20??-??/20??-??-??-*") if path.is_dir()]
    else:
        req_dirs = [roots[0]]
    for req_dir in sorted(req_dirs):
        requirement_name = req_dir.name[11:] if re.match(r"^20\d{2}-\d{2}-\d{2}-", req_dir.name) else req_dir.name
        index_paths.append(publish_requirement_tolaria_index(config, requirement_name, req_dir))

    report = {
        "schemaVersion": 1,
        "target": target,
        "typesAndViews": [path.relative_to(docs_root(config)).as_posix() for path in outputs],
        "indexes": [path.relative_to(docs_root(config)).as_posix() for path in index_paths],
    }
    report_path = tolaria_report_dir(config) / "tolaria-publish.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Tolaria publish report: {report_path}")
    return index_paths[0] if len(index_paths) == 1 else report_path


def next_sequence(directory: Path) -> int:
    """读取目录内已有编号文件，返回下一个两位序号。"""
    max_seq = 0
    for path in directory.glob("*.md"):
        match = re.match(r"^(\d+)-", path.name)
        if match:
            max_seq = max(max_seq, int(match.group(1)))
    return max_seq + 1


def latest_file(req_dir: Path, relative_dir: str, suffix: str = "*.md") -> Path | None:
    """返回阶段目录内最新编号文件，忽略 README。"""
    directory = req_dir / relative_dir
    if not directory.is_dir():
        return None
    files = sorted(path for path in directory.glob(suffix) if path.name != "README.md")
    return files[-1] if files else None


def is_placeholder_raw_requirement(raw_requirement: str) -> bool:
    """识别明显不是用户原始需求正文的占位输入。"""
    normalized = re.sub(r"\s+", "", raw_requirement)
    return normalized in RAW_REQUIREMENT_PLACEHOLDERS


def validate_requirement_name(requirement_name: str) -> None:
    """阻止英文缩写、临时名和无业务含义名称进入 docs/worktree。"""
    normalized = safe_path_leaf(requirement_name)
    compact = re.sub(r"[\s\-_0-9]+", "", normalized).lower()
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    if compact in GENERIC_REQUIREMENT_NAMES or len(chinese_chars) < 2:
        fail("需求名必须使用与需求主题直接相关的中文名称，禁止 task/tmp/demo/fix 等临时名或英文缩写")


def extract_readme_field(text: str, label: str, default: str = "") -> str:
    """从 README 的 `- 字段：值` 行提取轻量元数据。"""
    match = re.search(rf"^-\s*{re.escape(label)}：\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else default


def extract_business_objects(text: str) -> list[str]:
    """按固定业务关键词从 README/阶段文件中提取需求索引用业务对象。"""
    normalized = text.replace(" ", "")
    return [keyword for keyword in BUSINESS_OBJECT_KEYWORDS if keyword.replace(" ", "") in normalized]


def classify_business_domain(text: str) -> dict[str, str]:
    """按轻量关键词推断业务域和聚合；人工 frontmatter 可覆盖。"""
    normalized = text.replace(" ", "").lower()
    for bounded_context, aggregate, capability, keywords in BUSINESS_DOMAIN_RULES:
        if any(keyword.replace(" ", "").lower() in normalized for keyword in keywords):
            return {
                "boundedContext": bounded_context,
                "aggregate": aggregate,
                "capability": capability,
            }
    return {
        "boundedContext": "uncategorized",
        "aggregate": "general",
        "capability": "待归类",
    }


def requirement_domain_fields(readme_text: str, combined_text: str) -> dict[str, str]:
    """读取 README frontmatter 中的业务聚合字段，缺失时用关键词推断。"""
    fields, _ = parse_frontmatter(readme_text)
    inferred = classify_business_domain(combined_text)
    return {
        "boundedContext": fields.get("bounded_context") or fields.get("boundedContext") or inferred["boundedContext"],
        "aggregate": fields.get("aggregate") or inferred["aggregate"],
        "capability": fields.get("capability") or inferred["capability"],
    }


def doc_init(config: dict[str, Any], requirement_name: str, raw_requirement: str = "") -> Path:
    """创建标准 docs/02-req/YYYY-MM/YYYY-MM-DD-需求名 v2 目录结构和初始文档。"""
    validate_requirement_name(requirement_name)
    raw_body = raw_requirement.strip()
    if not raw_body:
        fail("初始化需求文档必须传入用户原始需求；请使用 task req -- init <需求名> <用户原始需求原文>")
    if is_placeholder_raw_requirement(raw_body):
        fail("用户原始需求不能使用占位词或助手摘要；请完整粘贴用户原始描述、SQL、脚本、接口示例和附件留档状态")

    req_dir = requirement_dir(config, requirement_name)
    req_dir.mkdir(parents=True, exist_ok=True)
    created_at = timestamp()
    domain = classify_business_domain(f"{requirement_name}\n{raw_body}")

    for child in [
        "00-原始需求/附件",
        "01-需求分析拆解",
        "02-任务规划",
        "03-开发进度",
        "04-产出物/SQL",
        "04-产出物/MAGIC-API脚本草案",
        "04-产出物/前端需求说明",
        "04-产出物/关联信息调查",
        "04-产出物/附件",
    ]:
        (req_dir / child).mkdir(parents=True, exist_ok=True)

    write_file_once(
        req_dir / "README.md",
        tolaria_frontmatter(
            "requirement",
            requirement_name,
            created_at,
            ["ifc-mom/requirement", "ifc-mom/docs"],
            {
                "status": "初始化",
                "bounded_context": domain["boundedContext"],
                "aggregate": domain["aggregate"],
                "capability": domain["capability"],
            },
        )
        + f"""# {requirement_name}

## 基本信息

- 需求名称：{requirement_name}
- 目标项目：待确认
- 当前状态：初始化
- 验证方式：待确认

## 业务聚合

- 限界上下文：{domain["boundedContext"]}
- 聚合：{domain["aggregate"]}
- 能力：{domain["capability"]}
- 复用规则：同一业务目标的连续调整优先追加迭代文件；独立上线或独立验收时再新建需求目录。

## 原始需求入口

- [原始描述](00-原始需求/01-{created_at}-原始描述.md)
- [附件目录](00-原始需求/附件/)

## Tolaria 知识链接

- 当前需求：[[{requirement_name}]]
- 原始需求：[[01-{created_at}-原始描述]]

> [!note] 维护规则
> `task req` / `task project` 生成的 README、阶段文件和产出物目录仍是权威结构；Tolaria frontmatter、H1、wikilink 和 saved views 只作为知识网络补充。

## 最新结论

- 需求分析：待补充
- 任务规划：待补充
- 开发进度：待补充

## 产出物索引

- [SQL](04-产出物/SQL/)
- [MAGIC-API脚本草案](04-产出物/MAGIC-API脚本草案/)
- [前端需求说明](04-产出物/前端需求说明/)
- [关联信息调查](04-产出物/关联信息调查/)
- [附件](04-产出物/附件/)

## 关键规则与 Skill

"""
        + "".join(f"- `{path}`\n" for path in rule_skill_paths("docs"))
        + f"""

## 迭代记录

- {created_at} 初始化需求目录。
""",
    )
    write_file_once(
        req_dir / "00-原始需求" / f"01-{created_at}-原始描述.md",
        tolaria_frontmatter(
            "requirement-original",
            "原始描述",
            created_at,
            ["ifc-mom/requirement", "ifc-mom/original"],
            {"requirement": requirement_name},
        )
        + f"""# 原始描述

## 记录时间

{created_at}

## 用户原始描述

以下内容必须逐字保留用户在当前需求中提供的原始描述。不得缩写、改写为摘要或删除长 SQL、脚本、接口示例、验收要求、排除项和附件留档状态。

```text
{raw_body}
```

## 附件留档状态

- 若用户提供截图、录屏、表格或附件：必须保存到 `附件/` 并在此处建立相对链接。
- 若当前环境无法取得附件二进制或本地路径：必须在本节填写未落盘原因和需要用户补传的路径。
""",
    )
    write_file_once(
        req_dir / "00-原始需求" / "README.md",
        "# 原始需求\n\n保留用户原始描述、补充说明和附件引用。不要用助手总结替代用户原文。\n",
    )
    write_file_once(
        req_dir / "01-需求分析拆解" / "README.md",
        "# 需求分析拆解\n\n每轮分析新增文件，不覆盖历史分析。\n",
    )
    write_file_once(
        req_dir / "02-任务规划" / "README.md",
        "# 任务规划\n\n按时间段新增规划文件，不覆盖历史规划。\n",
    )
    write_file_once(
        req_dir / "03-开发进度" / "README.md",
        "# 开发进度\n\n每次迭代、联调、验证或收口新增进度文件。\n",
    )
    write_file_once(
        req_dir / "04-产出物" / "README.md",
        "# 产出物\n\n按需求选择 SQL、MAGIC-API 脚本草案、前端需求说明、关联信息调查和附件。\n",
    )

    print(f"Requirement docs: {req_dir}")
    return req_dir


def doc_iter(config: dict[str, Any], requirement_name: str, phase: str, subject: str, body: str | None = None) -> Path:
    """为需求新增一轮分析、规划或进度文件，避免覆盖历史迭代。"""
    if phase not in ITER_PHASES:
        fail(
            "usage: task req -- iter <简短中文需求名> "
            "analysis|plan|progress <主题>"
        )
    req_dir = find_requirement_dir(config, requirement_name)
    phase_dir, _phase_name = ITER_PHASES[phase]
    directory = req_dir / phase_dir
    directory.mkdir(parents=True, exist_ok=True)
    seq = next_sequence(directory)
    created_at = timestamp()
    safe_subject = safe_path_leaf(subject)
    path = directory / f"{seq:02d}-{created_at}-{safe_subject}.md"
    if body is not None:
        rendered = body.rstrip() + "\n"
    elif phase == "analysis":
        body = tolaria_frontmatter(
            "requirement-analysis",
            subject,
            created_at,
            ["ifc-mom/requirement", "ifc-mom/analysis"],
            {"requirement": requirement_name},
        ) + f"""# {subject}

## 记录时间

{created_at}

## 用户原始需求

待补充。

## 当前结论

待补充。

## 证据来源

- 来源证据：待补充。
- 源码路径：待补充。
- 表字段/接口/页面：待补充。
- 样例数据/日志/复现条件：待补充。

## 明确结论

待补充。

## 未决项

- 待补充。

## 下一步

- 待补充。

## 与上一轮关系

- 引用上一轮文件：待补充
- 继续有效内容：待补充
- 失效或调整内容：待补充
- 替代结论：待补充
"""
        rendered = body
    elif phase == "plan":
        body = tolaria_frontmatter(
            "requirement-plan",
            subject,
            created_at,
            ["ifc-mom/requirement", "ifc-mom/plan"],
            {"requirement": requirement_name},
        ) + f"""# {subject}

## 记录时间

{created_at}

## 用户原始需求

待补充。

## 当前结论

待补充。

## 决策

- 修改边界：待补充。
- 执行顺序：待补充。
- 写锁/所有权：待补充。

## 待验证项

- 待补充。

## 下一步

- 待补充。

## 与上一轮关系

- 引用上一轮文件：待补充
- 继续有效内容：待补充
- 失效或调整内容：待补充
- 替代结论：待补充
"""
        rendered = body
    else:
        body = tolaria_frontmatter(
            "requirement-progress",
            subject,
            created_at,
            ["ifc-mom/requirement", "ifc-mom/progress"],
            {"requirement": requirement_name},
        ) + f"""# {subject}

## 记录时间

{created_at}

## 用户原始需求

待补充。

## 当前结论

待补充。

## 已完成

- 待补充。

## 待验证项

- 待补充。

## 下一步

- 待补充。

## 与上一轮关系

- 引用上一轮文件：待补充
- 继续有效内容：待补充
- 失效或调整内容：待补充
- 替代结论：待补充
"""
        rendered = body
    write_file_once(
        path,
        rendered,
    )
    print(f"Iteration doc: {path}")
    return path


def update_context_index(req_dir: Path, project: str, worktree_path: Path | None = None) -> None:
    """更新 README 中的上下文索引信息。

    v2 文档结构不再单独创建 `上下文索引.md`，后续继续同一需求时优先读 README。
    """
    requirement_name = req_dir.name.split("-", 3)[-1]
    worktree_text = f"- Worktree：`{worktree_path}`\n" if worktree_path else ""
    readme = req_dir / "README.md"
    existing = readme.read_text(encoding="utf-8") if readme.exists() else ""
    if existing and "当前状态：初始化" not in existing and "目标项目：待确认" not in existing:
        return
    updated_at = timestamp()
    domain = classify_business_domain(requirement_name)
    readme.write_text(
        tolaria_frontmatter(
            "requirement",
            requirement_name,
            updated_at,
            ["ifc-mom/requirement", "ifc-mom/docs"],
            {
                "status": "已初始化",
                "project": project,
                "bounded_context": domain["boundedContext"],
                "aggregate": domain["aggregate"],
                "capability": domain["capability"],
            },
        )
        + f"""# {requirement_name}

## 基本信息

- 需求名称：{requirement_name}
- 目标项目：{project}
- 当前状态：已初始化
{worktree_text}- 验证方式：`{verify_command(project, requirement_name)}`

## 业务聚合

- 限界上下文：{domain["boundedContext"]}
- 聚合：{domain["aggregate"]}
- 能力：{domain["capability"]}
- 复用规则：同一业务目标的连续调整优先追加迭代文件；独立上线或独立验收时再新建需求目录。

## 原始需求入口

- [原始需求目录](00-原始需求/)
- [附件目录](00-原始需求/附件/)

## Tolaria 知识链接

- 当前需求：[[{requirement_name}]]
- 目标项目：[[{project}]]

> [!note] 维护规则
> `task req` / `task project` 生成的 README、阶段文件和产出物目录仍是权威结构；Tolaria frontmatter、H1、wikilink 和 saved views 只作为知识网络补充。

## 最新结论

- 需求分析：`01-需求分析拆解/README.md`
- 任务规划：`02-任务规划/README.md`
- 开发进度：`03-开发进度/README.md`

## 产出物索引

- [SQL](04-产出物/SQL/)
- [MAGIC-API脚本草案](04-产出物/MAGIC-API脚本草案/)
- [前端需求说明](04-产出物/前端需求说明/)
- [关联信息调查](04-产出物/关联信息调查/)
- [附件](04-产出物/附件/)

## 关键规则与 Skill

"""
        + "".join(f"- `{path}`\n" for path in rule_skill_paths(project))
        + f"""
## 迭代记录

- {updated_at} 初始化需求目录。
""",
        encoding="utf-8",
    )


def requirement_index_record(root: Path, req_dir: Path) -> dict[str, Any]:
    """读取单个需求目录，生成全局索引记录。"""
    readme = req_dir / "README.md"
    readme_text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
    stage_text_parts = [readme_text]
    for relative_dir in ["00-原始需求", "01-需求分析拆解", "02-任务规划", "03-开发进度"]:
        directory = req_dir / relative_dir
        if directory.is_dir():
            for file in sorted(directory.glob("*.md")):
                if file.name != "README.md":
                    stage_text_parts.append(file.read_text(encoding="utf-8"))
    combined_text = "\n".join(stage_text_parts)
    domain = requirement_domain_fields(readme_text, combined_text)
    relative = req_dir.relative_to(root).as_posix()
    date = req_dir.name[:10] if re.match(r"^20\d{2}-\d{2}-\d{2}-", req_dir.name) else ""
    title = req_dir.name[11:] if date else req_dir.name
    if readme_text.startswith("# "):
        title = readme_text.splitlines()[0].removeprefix("# ").strip() or title
    latest_analysis = latest_file(req_dir, "01-需求分析拆解")
    latest_plan = latest_file(req_dir, "02-任务规划")
    latest_progress = latest_file(req_dir, "03-开发进度")
    return {
        "title": title,
        "date": date,
        "project": extract_readme_field(readme_text, "目标项目", "待确认"),
        "status": extract_readme_field(readme_text, "当前状态", "未知"),
        **domain,
        "businessObjects": extract_business_objects(combined_text),
        "path": relative,
        "latestAnalysis": latest_analysis.relative_to(root).as_posix() if latest_analysis else "",
        "latestPlan": latest_plan.relative_to(root).as_posix() if latest_plan else "",
        "latestProgress": latest_progress.relative_to(root).as_posix() if latest_progress else "",
    }


def write_requirement_global_index(config: dict[str, Any]) -> tuple[Path, Path]:
    """生成 docs/02-req 全局 Markdown/JSON 索引，便于按业务对象恢复历史需求。"""
    root = requirement_root(config)
    records = [
        requirement_index_record(root, req_dir)
        for req_dir in sorted(root.glob("20??-??/20??-??-??-*"))
        if req_dir.is_dir() and (req_dir / "README.md").is_file()
    ]
    records.sort(key=lambda item: (item.get("date", ""), item.get("title", "")), reverse=True)

    md_lines = [
        "# 需求总索引",
        "",
        "本文件由 `task req -- index-all` 生成，用于按日期、项目、业务聚合和业务对象快速恢复历史需求。",
        "",
        "| 日期 | 需求 | 项目 | 状态 | 业务聚合 | 业务对象 | 路径 |",
        "|---|---|---|---|---|---|---|",
    ]
    for record in records:
        objects = "、".join(record["businessObjects"]) or "-"
        domain = f"{record['boundedContext']} / {record['aggregate']}"
        md_lines.append(
            f"| {record['date'] or '-'} | {record['title']} | {record['project']} | {record['status']} | {domain} | {objects} | `{record['path']}` |"
        )
    md_lines.append("")

    index_md = root / "INDEX.md"
    index_json = root / "index.json"
    index_md.write_text("\n".join(md_lines), encoding="utf-8")
    index_json.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Requirement global index updated: {index_md}")
    print(f"Requirement global index JSON updated: {index_json}")
    return index_md, index_json


def replace_generated_block(existing: str, generated: str) -> str:
    """更新生成区块，保留业务页面上人工维护的沉淀内容。"""
    block = f"{DOMAIN_GENERATED_START}\n{generated.rstrip()}\n{DOMAIN_GENERATED_END}\n"
    if DOMAIN_GENERATED_START in existing and DOMAIN_GENERATED_END in existing:
        before, rest = existing.split(DOMAIN_GENERATED_START, 1)
        _old, after = rest.split(DOMAIN_GENERATED_END, 1)
        return before.rstrip() + "\n\n" + block + after.lstrip()
    return existing.rstrip() + "\n\n" + block


def domain_page_template(context: str, aggregate: str) -> str:
    """生成业务聚合页面的人工沉淀骨架。"""
    title = f"{context} / {aggregate}"
    return (
        tolaria_frontmatter(
            "domain-aggregate",
            title,
            timestamp(),
            ["ifc-mom/domain", f"ifc-mom/domain/{context}"],
            {"bounded_context": context, "aggregate": aggregate},
        )
        + f"""# {title}

## 业务规则

- 待补充。

## 关键口径

- 待补充。

## 历史坑点

- 待补充。
"""
    )


def write_domain_page(root: Path, context: str, aggregate: str, records: list[dict[str, Any]]) -> Path:
    """写入单个业务聚合页面，只替换自动生成的需求清单。"""
    path = root / context / f"{aggregate}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else domain_page_template(context, aggregate)
    lines = ["## 关联需求", ""]
    for record in records:
        lines.append(
            f"- {record['date'] or '-'} [{record['title']}](../../02-req/{record['path']}/README.md) "
            f"`{record['status']}`"
        )
    path.write_text(replace_generated_block(existing, "\n".join(lines)), encoding="utf-8")
    return path


def write_domain_index(config: dict[str, Any]) -> tuple[Path, Path]:
    """生成 docs/01-domain 业务聚合索引，需求目录仍保留为交付流水。"""
    req_root = requirement_root(config)
    out_root = domain_root(config)
    records = [
        requirement_index_record(req_root, req_dir)
        for req_dir in sorted(req_root.glob("20??-??/20??-??-??-*"))
        if req_dir.is_dir() and (req_dir / "README.md").is_file()
    ]
    records.sort(key=lambda item: (item.get("boundedContext", ""), item.get("aggregate", ""), item.get("date", "")))

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault((record["boundedContext"], record["aggregate"]), []).append(record)

    index_records: list[dict[str, Any]] = []
    for (context, aggregate), group_records in sorted(grouped.items()):
        page = write_domain_page(out_root, context, aggregate, group_records)
        index_records.append(
            {
                "boundedContext": context,
                "aggregate": aggregate,
                "requirementCount": len(group_records),
                "path": page.relative_to(out_root).as_posix(),
                "requirements": group_records,
            }
        )

    md_lines = [
        "# 业务聚合索引",
        "",
        "本文件由 `task req -- domain-index` 生成；需求目录继续作为交付记录，业务页面用于长期知识沉淀。",
        "",
        "| 业务聚合 | 需求数 | 页面 |",
        "|---|---:|---|",
    ]
    for record in index_records:
        domain = f"{record['boundedContext']} / {record['aggregate']}"
        md_lines.append(f"| {domain} | {record['requirementCount']} | [{record['path']}]({record['path']}) |")
    md_lines.append("")

    index_md = out_root / "INDEX.md"
    index_json = out_root / "index.json"
    index_md.write_text("\n".join(md_lines), encoding="utf-8")
    index_json.write_text(json.dumps(index_records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Domain index updated: {index_md}")
    print(f"Domain index JSON updated: {index_json}")
    return index_md, index_json
