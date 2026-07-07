from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .process import fail


TOLARIA_SKIP_DIRS = {".git", ".obsidian", ".tolaria", ".tolaria-rename-txn", ".vscode", "attachments", "附件"}
TOLARIA_REQUIRED_FIELDS = {"type", "title", "created", "tags"}


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


def workspace_root_for_docs(config: dict[str, Any]) -> Path:
    """按 docs 项目路径推导工作区根目录，用于写 `.praxis/out` 报告。"""
    from .docs import docs_root

    root = docs_root(config)
    if root.name == "docs":
        return root.parent
    return root


def tolaria_report_dir(config: dict[str, Any]) -> Path:
    """返回 Tolaria 检查报告目录。"""
    path = workspace_root_for_docs(config) / ".praxis" / "out" / "tolaria"
    path.mkdir(parents=True, exist_ok=True)
    return path


def tolaria_scan_roots(config: dict[str, Any], args: list[str]) -> tuple[str, list[Path]]:
    """解析 Tolaria check/publish 目标。"""
    from .docs import docs_root, find_requirement_dir

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
    from .docs import docs_root

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
    from .docs import docs_root

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
    from .docs import timestamp

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
    from .docs import docs_root, requirement_root

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
