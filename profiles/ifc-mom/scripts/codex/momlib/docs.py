from __future__ import annotations

import datetime as dt
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import project_config
from .context import rule_skill_paths, verify_command
from .docs_tolaria import parse_frontmatter, tolaria_check, tolaria_frontmatter, tolaria_publish
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
BUSINESS_DOMAIN_RULES_FILE = Path(__file__).with_name("business-domain-rules.json")
DOMAIN_GENERATED_START = "<!-- praxis:domain-index:start -->"
DOMAIN_GENERATED_END = "<!-- praxis:domain-index:end -->"
COMPLETED_STATUSES = {"已完成", "完成", "已关闭", "已取消", "取消"}
DOMAIN_CANDIDATE_STOPWORDS = {
    "用户要求",
    "原始需求",
    "需求分析",
    "关联信息",
    "调查",
    "涉及",
    "需要",
    "优化",
    "调整",
    "当前",
    "页面",
    "接口",
    "字段",
    "表字段",
}
DOMAIN_CANDIDATE_SUFFIXES = [
    "清单",
    "规则",
    "页面",
    "接口",
    "字段",
    "报表",
    "流程",
    "申请",
    "任务",
    "计划",
    "单据",
    "看板",
    "驾驶舱",
    "口径",
]


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


def recommended_next_steps(requirement_name: str, phase: str) -> str:
    """生成阶段文件中的推荐下一步。"""
    recommended = {
        "analysis": f"task req -- iter {requirement_name} plan <实施规划主题>",
        "plan": f"task req -- iter {requirement_name} progress <进展主题>",
        "progress": f"task req -- index {requirement_name}",
    }.get(phase, f"task req -- check {requirement_name}")
    actions = [
        (recommended, "推荐继续推进当前需求流。"),
        (f"task req -- check {requirement_name}", "检查需求文档占位和证据完整性。"),
        (f"task req -- index {requirement_name}", "回写 README 最新结论和索引。"),
    ]
    lines = ["## 推荐下一步", ""]
    for index, (command, description) in enumerate(actions):
        marker = "[推荐] " if index == 0 else ""
        lines.append(f"- {marker}`{command}`：{description}")
    return "\n".join(lines) + "\n"


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


@lru_cache(maxsize=1)
def business_domain_rules() -> list[dict[str, Any]]:
    """读取业务域字典，避免改代码才能调整聚合归属。"""
    if not BUSINESS_DOMAIN_RULES_FILE.is_file():
        return []
    return json.loads(BUSINESS_DOMAIN_RULES_FILE.read_text(encoding="utf-8"))


def classify_business_domain(text: str) -> dict[str, str]:
    """按轻量关键词推断业务域和聚合；人工 frontmatter 可覆盖。"""
    normalized = text.replace(" ", "").lower()
    for rule in business_domain_rules():
        bounded_context = str(rule.get("boundedContext", "")).strip()
        aggregate = str(rule.get("aggregate", "")).strip()
        capability = str(rule.get("capability", "")).strip()
        keywords = [str(keyword) for keyword in rule.get("keywords", [])]
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


def tag_value(value: str) -> str:
    """把业务词转成可用于 Tolaria tag 的短值。"""
    return re.sub(r"[\s/]+", "-", value.strip()).strip("-")


def business_domain_tags(domain: dict[str, str]) -> list[str]:
    """按主业务域生成可检索标签，主归属仍由 frontmatter 字段决定。"""
    tags = []
    if domain["boundedContext"] != "uncategorized":
        tags.append(f"domain/{tag_value(domain['boundedContext'])}")
    if domain["aggregate"] != "general":
        tags.append(f"aggregate/{tag_value(domain['aggregate'])}")
    if domain["capability"] != "待归类":
        tags.append(f"capability/{tag_value(domain['capability'])}")
    return tags


def suggested_business_tags(text: str, terms: list[str]) -> list[str]:
    """从调查词生成多标签候选，不直接修改主业务域。"""
    domain = classify_business_domain(text)
    tags = business_domain_tags(domain)
    tags.extend(f"object/{tag_value(term)}" for term in terms if tag_value(term))
    return list(dict.fromkeys(tags))


def requirement_domain_fields(readme_text: str, combined_text: str) -> dict[str, str]:
    """读取 README frontmatter 中的业务聚合字段，缺失时用关键词推断。"""
    fields, _ = parse_frontmatter(readme_text)
    inferred = classify_business_domain(combined_text)
    bounded_context = fields.get("bounded_context") or fields.get("boundedContext") or ""
    aggregate = fields.get("aggregate") or ""
    capability = fields.get("capability") or ""
    return {
        "boundedContext": bounded_context if bounded_context and bounded_context != "uncategorized" else inferred["boundedContext"],
        "aggregate": aggregate if aggregate and aggregate != "general" else inferred["aggregate"],
        "capability": capability if capability and capability != "待归类" else inferred["capability"],
    }


def active_domain_requirements(config: dict[str, Any], domain: dict[str, str], current_dir: Path) -> list[dict[str, Any]]:
    """查找同业务聚合下未完成需求，用于提示复用目录。"""
    if domain["boundedContext"] == "uncategorized":
        return []
    root = requirement_root(config)
    matches = []
    for req_dir in sorted(root.glob("20??-??/20??-??-??-*"), reverse=True):
        if req_dir == current_dir or not (req_dir / "README.md").is_file():
            continue
        record = requirement_index_record(root, req_dir)
        if record["status"] in COMPLETED_STATUSES:
            continue
        if record["boundedContext"] == domain["boundedContext"] and record["aggregate"] == domain["aggregate"]:
            matches.append(record)
    return matches


def print_reuse_suggestion(config: dict[str, Any], domain: dict[str, str], current_dir: Path) -> None:
    """提示同聚合未完成需求，仍允许显式创建新需求目录。"""
    matches = active_domain_requirements(config, domain, current_dir)
    if not matches:
        return
    root = requirement_root(config)
    print("建议复用已有需求目录：")
    for record in matches[:3]:
        print(f"- {record['title']}：`{root / record['path']}`")
    print("如属同一业务目标，优先使用 `task req -- iter <需求名> analysis|plan|progress <主题>` 追加迭代。")


def doc_init(config: dict[str, Any], requirement_name: str, raw_requirement: str = "") -> Path:
    """创建标准 docs/02-req/YYYY-MM/YYYY-MM-DD-需求名 v2 目录结构和初始文档。"""
    validate_requirement_name(requirement_name)
    raw_body = raw_requirement.strip()
    if not raw_body:
        fail("初始化需求文档必须传入用户原始需求；请使用 task req -- init <需求名> <用户原始需求原文>")
    if is_placeholder_raw_requirement(raw_body):
        fail("用户原始需求不能使用占位词或助手摘要；请完整粘贴用户原始描述、SQL、脚本、接口示例和附件留档状态")

    req_dir = requirement_dir(config, requirement_name)
    created_at = timestamp()
    domain = classify_business_domain(f"{requirement_name}\n{raw_body}")
    tag_text = f"{requirement_name}\n{raw_body}"
    requirement_tags = [
        "ifc-mom/requirement",
        "ifc-mom/docs",
        *suggested_business_tags(tag_text, extract_domain_candidate_terms(tag_text)),
    ]
    print_reuse_suggestion(config, domain, req_dir)
    req_dir.mkdir(parents=True, exist_ok=True)

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
            requirement_tags,
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

    write_domain_index(config)
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

{recommended_next_steps(requirement_name, phase)}

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

{recommended_next_steps(requirement_name, phase)}

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

{recommended_next_steps(requirement_name, phase)}

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
    write_domain_index(config)
    write_domain_candidates(config)
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


def requirement_has_default_domain_metadata(readme_text: str) -> bool:
    """判断需求 README 是否仍使用默认业务聚合元数据。"""
    fields, _ = parse_frontmatter(readme_text)
    if not any(key in fields for key in ["bounded_context", "boundedContext", "aggregate", "capability"]):
        return False
    return (
        fields.get("bounded_context", fields.get("boundedContext", "uncategorized")) == "uncategorized"
        or fields.get("aggregate", "general") == "general"
        or fields.get("capability", "待归类") == "待归类"
    )


def domain_candidate_text(req_dir: Path) -> str:
    """收集最能反推业务词的需求调查和分析文档。"""
    parts = []
    for relative_dir in ["", "00-原始需求", "01-需求分析拆解", "04-产出物/关联信息调查"]:
        directory = req_dir / relative_dir if relative_dir else req_dir
        if not directory.is_dir():
            continue
        for file in sorted(directory.glob("*.md")):
            if file.name == "README.md" and relative_dir:
                continue
            parts.append(file.read_text(encoding="utf-8"))
    return "\n".join(parts)


def extract_domain_candidate_terms(text: str) -> list[str]:
    """从调查文本提取用于补业务字典的候选词。"""
    counter: dict[str, int] = {}
    for match in re.finditer(r"[A-Za-z][A-Za-z0-9_/-]{1,}", text):
        term = match.group(0).strip("_-/")
        if len(term) >= 2:
            counter[term] = counter.get(term, 0) + 1
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if chunk not in DOMAIN_CANDIDATE_STOPWORDS and len(chunk) <= 8:
            counter[chunk] = counter.get(chunk, 0) + 1
        for suffix in DOMAIN_CANDIDATE_SUFFIXES:
            end = chunk.find(suffix)
            if end < 0:
                continue
            end += len(suffix)
            term = chunk[max(0, end - 4) : end]
            if len(term) >= 2 and term not in DOMAIN_CANDIDATE_STOPWORDS:
                counter[term] = counter.get(term, 0) + 1
    return [
        term
        for term, _count in sorted(counter.items(), key=lambda item: (-item[1], len(item[0]), item[0]))[:12]
    ]


def write_domain_candidates(config: dict[str, Any]) -> tuple[Path, Path]:
    """生成待补业务域字典候选报告，不自动修改字典。"""
    req_root = requirement_root(config)
    out_dir = docs_root(config) / ".praxis" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[dict[str, Any]] = []
    for req_dir in sorted(req_root.glob("20??-??/20??-??-??-*")):
        readme = req_dir / "README.md"
        if not req_dir.is_dir() or not readme.is_file():
            continue
        readme_text = readme.read_text(encoding="utf-8")
        record = requirement_index_record(req_root, req_dir)
        if record["boundedContext"] != "uncategorized" and not requirement_has_default_domain_metadata(readme_text):
            continue
        text = domain_candidate_text(req_dir)
        terms = extract_domain_candidate_terms(text)
        if not terms:
            continue
        suggested_tags = suggested_business_tags(f"{record['title']}\n{text}\n" + "\n".join(terms), terms)
        candidates.append(
            {
                "title": record["title"],
                "path": record["path"],
                "currentDomain": {
                    "boundedContext": record["boundedContext"],
                    "aggregate": record["aggregate"],
                    "capability": record["capability"],
                },
                "terms": terms,
                "suggestedTags": suggested_tags,
            }
        )

    markdown_path = out_dir / "domain-candidates.md"
    json_path = out_dir / "domain-candidates.json"
    lines = [
        "# 业务域候选词报告",
        "",
        "本文件由 `task docs -- domain-candidates` 生成，用于从需求调查和分析文档反推待补业务字典；不会自动修改字典。",
        "",
        "| 需求 | 当前聚合 | 候选词 | 建议标签 | 路径 |",
        "|---|---|---|---|---|",
    ]
    for item in candidates:
        domain = f"{item['currentDomain']['boundedContext']} / {item['currentDomain']['aggregate']}"
        lines.append(
            f"| {item['title']} | {domain} | {'、'.join(item['terms'])} | {'、'.join(item['suggestedTags'])} | `{item['path']}` |"
        )
    lines.append("")
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "generatedAt": timestamp(),
                "candidateCount": len(candidates),
                "candidates": candidates,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Domain candidate report updated: {markdown_path}")
    print(f"Domain candidate report JSON updated: {json_path}")
    return markdown_path, json_path
