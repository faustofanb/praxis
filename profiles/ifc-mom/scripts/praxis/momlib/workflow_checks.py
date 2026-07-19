from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import local_database_config, project_dir
from .context import verify_command
from .delivery_policy import commit_changed_files, delivery_policy_issues, is_official_migration
from .docs import find_requirement_dir, is_placeholder_raw_requirement
from .finish import delivery_commits
from .git_worktree import action_repo_dir, project_worktree_dirs
from .names import safe_path_leaf
from .paths import ROOT_DIR
from .praxis import PRAXIS_DIR, relative
from .process import capture


TEMPLATE_MARKERS = ["待补充", "后续确认", "需进一步调查"]
EVIDENCE_MARKERS = ["来源证据", "源码路径", "表字段", "样例数据", "明确结论", "未决项", "查询环境", "关键 SQL"]
ATTACHMENT_KEYWORDS = ["截图", "图片", "附件", "录屏", "表格", "Excel", "文件"]
NO_PUSH_MARKERS = ["不推送", "仅本地验证", "local only", "no push", "not push"]
DB_REQUIRED_KEYWORDS = ["SQL", "迁移", "报表口径", "数据修复", "字段映射", "字段来源", "表关系", "真实数据"]
DB_OPTIONAL_KEYWORDS = ["字典", "主数据", "样例数据", "数据口径", "统计", "报表", "菜单授权", "低代码"]
SQL_KEYWORDS = ["SQL", "DDL", "Flyway", "迁移", "MagicAPI", "magic-api", "菜单授权", "低代码模型", "应用设计"]
DATA_SCOPE_TERMS = [
    "数据库",
    "数据表",
    "表结构",
    "表字段",
    "字段",
    "字段映射",
    "字段来源",
    "表关系",
    "真实数据",
    "数据口径",
    "报表口径",
]
SQL_SCOPE_TERMS = ["SQL", "DDL", "Flyway", "迁移", "MagicAPI", "magic-api", "菜单授权", "低代码模型", "应用设计"]
NEGATION_PREFIXES = ["不涉及", "无需", "不需要", "不改", "不会修改", "不会涉及", "不包含", "不用", "没有", "无"]
FRONTEND_COMMON_PATH_MARKERS = [
    "/src/hooks/",
    "/src/utils/",
    "/src/composables/",
    "/src/components/",
    "/src/store/",
    "/src/api/request",
    "/src/plugins/",
    "apps/web-antd/src/hooks/",
    "apps/web-antd/src/utils/",
    "apps/web-antd/src/components/",
    "apps/web-antd/src/store/",
]
COMMON_CHANGE_APPROVAL_KEYWORDS = [
    "公共影响范围",
    "跨页面影响",
    "跨模块影响",
    "已确认影响范围",
    "必须修改公共",
    "允许修改公共",
    "公共能力变更",
    "通用能力变更",
]
CONFIG_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    "application.yml",
    "application.yaml",
    "application-dev.yml",
    "application-dev.yaml",
    "application-prod.yml",
    "application-prod.yaml",
}


def changed_files(repo_dir: Path) -> list[str]:
    """返回仓库当前已跟踪和未跟踪变更，用于工作流门禁检查。"""
    tracked = capture(["git", "-C", str(repo_dir), "diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD"], ROOT_DIR)
    untracked = capture(["git", "-C", str(repo_dir), "ls-files", "--others", "--exclude-standard"], ROOT_DIR)
    return sorted({line for line in [*tracked.splitlines(), *untracked.splitlines()] if line})


def print_issues(title: str, issues: list[str]) -> int:
    """统一打印检查结果并返回可组合的退出码。"""
    if not issues:
        print(f"{title} passed.")
        return 0
    print(f"{title} found issues:")
    for issue in issues:
        print(f"  - {issue}")
    return 1


def negates_any(text: str, terms: list[str]) -> bool:
    """Return whether a short natural-language clause explicitly excludes terms."""
    prefix_pattern = "|".join(re.escape(prefix) for prefix in NEGATION_PREFIXES)
    term_pattern = "|".join(re.escape(term) for term in terms)
    return bool(re.search(rf"(?:{prefix_pattern})[^。\n；;，,但]*?(?:{term_pattern})", text, re.IGNORECASE))


def preflight_risk_flags(text: str, req_dir: Path) -> tuple[bool, bool, bool]:
    """Classify database and SQL risk while respecting explicit out-of-scope wording."""
    data_out_of_scope = negates_any(text, DATA_SCOPE_TERMS)
    sql_out_of_scope = negates_any(text, SQL_SCOPE_TERMS)
    db_required = contains_any(text, DB_REQUIRED_KEYWORDS) and not data_out_of_scope
    db_optional = contains_any(text, DB_OPTIONAL_KEYWORDS) and not data_out_of_scope
    sql_related = (contains_any(text, SQL_KEYWORDS) and not sql_out_of_scope) or has_intermediate_sql(req_dir)
    return db_required, db_optional, sql_related


def analysis_files(req_dir: Path) -> list[Path]:
    """返回需求分析目录下真实分析文件，排除 README。"""
    directory = req_dir / "01-需求分析拆解"
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.md") if path.name != "README.md")


def latest_file(req_dir: Path, relative_dir: str, suffix: str = "*.md") -> Path | None:
    """返回指定目录下按文件名排序的最新业务文件，排除 README。"""
    directory = req_dir / relative_dir
    if not directory.is_dir():
        return None
    files = sorted(path for path in directory.glob(suffix) if path.name != "README.md")
    return files[-1] if files else None


def artifact_files(req_dir: Path) -> list[Path]:
    """列出 04-产出物 下可索引的产出文件。"""
    root = req_dir / "04-产出物"
    if not root.is_dir():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and path.name != "README.md")


def raw_requirement_files(req_dir: Path) -> list[Path]:
    """返回原始需求目录下真实原文文件，排除 README 和附件说明。"""
    directory = req_dir / "00-原始需求"
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.md") if path.name != "README.md")


def attachment_files(req_dir: Path) -> list[Path]:
    """返回原始需求附件目录下的已落盘附件或说明文件。"""
    directory = req_dir / "00-原始需求" / "附件"
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.rglob("*") if path.is_file())


def raw_user_text(text: str) -> str:
    """提取原始描述中的用户正文，避免模板说明触发门禁。"""
    match = re.search(r"```text\n(?P<body>.*?)\n```", text, re.DOTALL)
    if match:
        return match.group("body")
    marker = "## 用户原始描述"
    if marker in text:
        return text.split(marker, 1)[1].split("## 附件留档状态", 1)[0]
    return text


def relative_link(req_dir: Path, path: Path | None) -> str:
    """把路径转成 README 中使用的相对链接文本。"""
    if not path:
        return "待补充"
    return f"`{path.relative_to(req_dir).as_posix()}`"


def recommended_next_steps(requirement_name: str, plan: Path | None, progress: Path | None) -> str:
    """生成 README 索引中的推荐下一步。"""
    if plan is None:
        recommended = f"task req -- iter {requirement_name} plan <实施规划主题>"
    elif progress is None:
        recommended = f"task req -- iter {requirement_name} progress <进展主题>"
    else:
        recommended = f"task req -- check {requirement_name}"
    actions = [
        (recommended, "推荐继续推进当前需求流。"),
        (f"task req -- check {requirement_name}", "检查需求文档占位和证据完整性。"),
        (f"task req -- index {requirement_name}", "回写 README 最新结论和索引。"),
    ]
    lines = ["## 推荐下一步", ""]
    for index, (command, description) in enumerate(actions):
        marker = "[推荐] " if index == 0 else ""
        lines.append(f"- {marker}`{command}`：{description}")
    return "\n".join(lines)


def relative_path_text(req_dir: Path, path: Path | None) -> str:
    """返回适合终端报告的相对路径。"""
    return path.relative_to(req_dir).as_posix() if path else "missing"


def requirement_text(req_dir: Path) -> str:
    """读取需求目录中的轻量文本，用于 preflight 风险提示。"""
    parts: list[str] = []
    readme = req_dir / "README.md"
    if readme.is_file():
        parts.append(readme.read_text(encoding="utf-8"))
    raw_dir = req_dir / "00-原始需求"
    if raw_dir.is_dir():
        for file in sorted(path for path in raw_dir.glob("*.md") if path.name != "README.md"):
            parts.append(raw_user_text(file.read_text(encoding="utf-8")))
    return "\n".join(parts)


def contains_any(text: str, keywords: list[str]) -> bool:
    """判断文本是否命中任意关键词。"""
    return any(keyword.lower() in text.lower() for keyword in keywords)


def is_frontend_common_path(path: str) -> bool:
    """识别 Web/PDA 公共 hook、工具、组件、store 等高影响路径。"""
    normalized = path.replace("\\", "/")
    prefixed = f"/{normalized}"
    return any(marker in prefixed or normalized.startswith(marker) for marker in FRONTEND_COMMON_PATH_MARKERS)


def common_change_issues(req_dir: Path, files: list[str]) -> list[str]:
    """页面局部需求默认禁止改公共 hook/tool；有明确影响范围说明才放行。"""
    common_files = [file for file in files if is_frontend_common_path(file)]
    if not common_files:
        return []
    text = requirement_text(req_dir)
    if contains_any(text, COMMON_CHANGE_APPROVAL_KEYWORDS):
        return []
    issues = ["common frontend hook/tool changed by a page-local requirement; document cross-page impact or move fix into page scope"]
    issues.extend(f"common frontend file: {file}" for file in common_files)
    return issues


def docs_issues(req_dir: Path) -> list[str]:
    """收集需求文档索引和证据化分析问题，供 req check/preflight 复用。"""
    issues: list[str] = []

    readme = req_dir / "README.md"
    readme_text = ""
    if not readme.is_file():
        issues.append("README.md is missing")
    else:
        readme_text = readme.read_text(encoding="utf-8")
        if "需求分析：待补充" in readme_text or "当前状态：初始化" in readme_text:
            issues.append("README latest conclusion is still placeholder")

    latest_stage_files = [
        latest_file(req_dir, "01-需求分析拆解"),
        latest_file(req_dir, "02-任务规划"),
        latest_file(req_dir, "03-开发进度"),
    ]
    if readme_text:
        for path in latest_stage_files:
            if path and path.relative_to(req_dir).as_posix() not in readme_text:
                issues.append(f"README does not reference latest stage file: {path.relative_to(req_dir)}")

    raw_files = raw_requirement_files(req_dir)
    raw_text = "\n".join(path.read_text(encoding="utf-8") for path in raw_files)
    raw_body_text = raw_user_text(raw_text)
    if not raw_files:
        issues.append("raw requirement document is missing")
    elif not raw_body_text.strip():
        issues.append("raw requirement document is empty")
    elif is_placeholder_raw_requirement(raw_body_text):
        issues.append("raw requirement document still contains placeholder instead of original user text")
    if contains_any(raw_body_text, ATTACHMENT_KEYWORDS) and not attachment_files(req_dir) and "附件未落盘原因" not in raw_body_text:
        issues.append("raw requirement mentions attachments/screenshots but has no saved attachment or explicit missing-attachment reason")

    files = analysis_files(req_dir)
    if not files:
        issues.append("analysis document still contains template placeholder: no analysis iteration file")
    for path in files:
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in TEMPLATE_MARKERS):
            issues.append(f"analysis document still contains template placeholder: {path.relative_to(req_dir)}")
        if not any(marker in text for marker in EVIDENCE_MARKERS):
            issues.append(f"analysis document lacks evidence markers: {path.relative_to(req_dir)}")

    return issues


def has_intermediate_sql(req_dir: Path) -> bool:
    """判断需求目录是否已有迁移正式确认前的 SQL 中间产物。"""
    v2_sql = req_dir / "04-产出物" / "SQL"
    if any(v2_sql.glob("*.sql")):
        return True
    legacy = req_dir / "中间文档"
    return legacy.is_dir() and any(legacy.rglob("*.sql"))


def classify_changed_file(path: str) -> str:
    """把变更文件归类为收尾检查可读的风险类别。"""
    normalized = path.replace("\\", "/")
    lower = normalized.lower()
    name = Path(normalized).name
    if is_official_migration(normalized):
        return "migration"
    if "/src/test/" in lower or lower.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
        return "test"
    if normalized.startswith("docs/"):
        return "docs"
    if name in CONFIG_FILE_NAMES or lower.endswith((".properties", ".toml")) and "config" in lower:
        return "config"
    if "/src/main/" in lower or lower.endswith((".java", ".ts", ".tsx", ".vue", ".py", ".sql")):
        return "source"
    return "other"


def commit_subject(line: str) -> str:
    """从 `git log --oneline` 行中提取提交标题。"""
    parts = line.split(maxsplit=1)
    return parts[1] if len(parts) > 1 else ""


def commit_hash(line: str) -> str:
    """从 `git log --oneline` 行中提取提交哈希。"""
    return line.split(maxsplit=1)[0]


def delivery_commit_lines(config: dict[str, Any], project: str, repo_dir: Path) -> list[str]:
    """返回需求分支相对本地基座新增的提交。"""
    default_branch = config["projects"].get(project, {}).get("defaultBranch") or "local"
    output = capture(["git", "-C", str(repo_dir), "log", "--oneline", f"{default_branch}..HEAD"], ROOT_DIR)
    return [line for line in output.splitlines() if line]


def change_check(config: dict[str, Any], project: str, requirement_name: str) -> int:
    """检查收尾前的代码变更范围、测试提交隔离和基础文档门禁。"""
    req_dir = find_requirement_dir(config, requirement_name)
    repo_dir = action_repo_dir(config, project, [requirement_name]) if project != "docs" else project_dir(config, project)
    issues: list[str] = []
    status = capture(["git", "-C", str(repo_dir), "status", "--short"], ROOT_DIR)
    if status:
        issues.append("working tree is not clean; commit production and test changes separately before delivery")

    commits = delivery_commit_lines(config, project, repo_dir)
    included_commits, excluded_commits = delivery_commits(commits)
    category_counts: dict[str, int] = {}
    official_migrations: list[str] = []

    for line in included_commits:
        current_hash = commit_hash(line)
        for path in commit_changed_files(repo_dir, current_hash):
            category = classify_changed_file(path)
            category_counts[category] = category_counts.get(category, 0) + 1
            if category == "test":
                issues.append(f"delivery commit contains test file: {current_hash} {path}")
            if category == "migration":
                official_migrations.append(path)

    for line in excluded_commits:
        subject = commit_subject(line)
        current_hash = commit_hash(line)
        if not any(marker in subject for marker in NO_PUSH_MARKERS):
            issues.append(f"test commit must state not pushed/local-only intent: {current_hash} {subject}")
        for path in commit_changed_files(repo_dir, current_hash):
            category = classify_changed_file(path)
            category_counts[category] = category_counts.get(category, 0) + 1
            if category != "test":
                issues.append(f"test commit contains non-test file: {current_hash} {path}")

    issues.extend(delivery_policy_issues(repo_dir, [commit_hash(line) for line in included_commits]))

    if official_migrations and not has_intermediate_sql(req_dir):
        issues.append("delivery includes official Flyway migration but requirement SQL intermediate artifact is missing")
        for path in official_migrations:
            issues.append(f"official migration file: {path}")
    if has_intermediate_sql(req_dir) and included_commits and project != "docs" and not official_migrations:
        issues.append("requirement SQL intermediate artifact exists but delivery has no official Flyway migration")

    if category_counts:
        print("Changed file categories:")
        for category in sorted(category_counts):
            print(f"  {category}: {category_counts[category]}")
    else:
        print("Changed file categories: no delivery commits detected")

    exit_code = 0
    if docs_check(config, requirement_name):
        exit_code = 1
    if print_issues("Change check", issues):
        exit_code = 1
    if exit_code == 0:
        print("Change check passed.")
    return exit_code


def docs_check(config: dict[str, Any], requirement_name: str) -> int:
    """检查需求文档是否满足证据化分析和 README 索引门禁。"""
    req_dir = find_requirement_dir(config, requirement_name)
    return print_issues("Docs check", docs_issues(req_dir))


def write_execution_compliance_evidence(
    config: dict[str, Any],
    project: str,
    requirement_name: str,
    output_dir: Path | None = None,
) -> Path:
    """Write closeout evidence so Quality does not infer execution state from template docs."""
    req_dir = find_requirement_dir(config, requirement_name)
    issues = docs_issues(req_dir) if req_dir.is_dir() else ["requirement directory is missing"]
    data = {
        "schemaVersion": 1,
        "role": "Execution",
        "project": project,
        "requirementName": requirement_name,
        "status": "FAIL" if issues else "PASS",
        "requirementDir": relative(req_dir),
        "verificationCommand": verify_command(project, requirement_name),
        "docsIssues": issues,
        "closeoutCommands": [
            f"task gate -- ready {project} {requirement_name}",
            f"task delivery -- commit-split {project} {requirement_name} <production-message>",
            f"task delivery -- deliver {project} {requirement_name}",
            f"task delivery -- cleanup {project} {requirement_name}",
        ],
    }
    target_dir = output_dir or PRAXIS_DIR / "evidence"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{safe_path_leaf(project)}-{safe_path_leaf(requirement_name)}-execution-compliance.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Execution compliance evidence: {path}")
    return path


def preflight(config: dict[str, Any], project: str, requirement_name: str) -> int:
    """输出需求恢复/启动前的只读检查报告。"""
    req_dir = find_requirement_dir(config, requirement_name)
    text = requirement_text(req_dir) if req_dir.is_dir() else requirement_name
    doc_issues = docs_issues(req_dir) if req_dir.is_dir() else ["requirement directory is missing"]
    analysis = latest_file(req_dir, "01-需求分析拆解") if req_dir.is_dir() else None
    plan = latest_file(req_dir, "02-任务规划") if req_dir.is_dir() else None
    progress = latest_file(req_dir, "03-开发进度") if req_dir.is_dir() else None
    artifacts = artifact_files(req_dir) if req_dir.is_dir() else []

    print("Preflight")
    print(f"  target project: {project}")
    print(f"  requirement: {requirement_name}")
    print(f"  requirement docs: {req_dir} ({'exists' if req_dir.is_dir() else 'missing'})")
    print(f"  latest analysis: {relative_path_text(req_dir, analysis)}")
    print(f"  latest plan: {relative_path_text(req_dir, plan)}")
    print(f"  latest progress: {relative_path_text(req_dir, progress)}")
    print(f"  artifacts: {len(artifacts)}")

    if project == "docs":
        print("  worktree: not required for docs-only task")
    else:
        matches = project_worktree_dirs(config, project, requirement_name, include_feature=True)
        if matches:
            print("  worktree:")
            for path in matches:
                print(f"    - {path}")
        else:
            print("  worktree: missing")

    db_required, db_optional, sql_related = preflight_risk_flags(text, req_dir)
    print("  database investigation:", "required" if db_required else "optional-risk" if db_optional else "not indicated")
    print("  SQL/migration intermediate artifact:", "required" if sql_related else "not indicated")
    print(f"  verification: {verify_command(project, requirement_name)}")
    print()

    exit_code = print_issues("Preflight docs index", doc_issues)
    if not req_dir.is_dir() or (project != "docs" and not project_worktree_dirs(config, project, requirement_name, include_feature=True)):
        exit_code = 1
    return exit_code


def docs_index(config: dict[str, Any], requirement_name: str) -> int:
    """按最新阶段文件和产出物重写 README 索引区。"""
    req_dir = find_requirement_dir(config, requirement_name)
    readme = req_dir / "README.md"
    existing = readme.read_text(encoding="utf-8") if readme.is_file() else f"# {requirement_name}\n"
    title = existing.splitlines()[0] if existing.startswith("# ") else f"# {requirement_name}"
    analysis = latest_file(req_dir, "01-需求分析拆解")
    plan = latest_file(req_dir, "02-任务规划")
    progress = latest_file(req_dir, "03-开发进度")
    artifacts = artifact_files(req_dir)
    artifact_lines = "\n".join(f"- `{path.relative_to(req_dir).as_posix()}`" for path in artifacts) or "- 待补充"

    readme.write_text(
        f"""{title}

## 最新结论

- 需求分析：{relative_link(req_dir, analysis)}
- 任务规划：{relative_link(req_dir, plan)}
- 开发进度：{relative_link(req_dir, progress)}

## 产出物索引

{artifact_lines}

{recommended_next_steps(requirement_name, plan, progress)}

## 迭代记录

- README 索引已由 `task req -- index` 自动更新（建议每次阶段文件新增后执行）。
""",
        encoding="utf-8",
    )
    print(f"Docs index updated: {readme}")
    return 0


def db_plan(config: dict[str, Any], requirement_name: str) -> int:
    """输出数据库 MCP 真实库调查清单和只读 SQL 模板。"""
    req_dir = find_requirement_dir(config, requirement_name)
    investigation_dir = req_dir / "04-产出物" / "关联信息调查"
    analysis_dir = req_dir / "01-需求分析拆解"
    local_db = local_database_config(config)
    database = local_db["database"] or "<当前 workspace 的本地数据库名>"
    schema = local_db["schema"]
    print(f"需求目录: {req_dir}")
    print(f"调查沉淀目录: {investigation_dir}")
    print(f"分析回写目录: {analysis_dir}")
    if local_db["database"]:
        print(
            "本地数据库配置: "
            f"connection={local_db['connection']}, database={local_db['database']}, schema={local_db['schema']}"
        )
    else:
        print("本地数据库配置: 未配置 [database.local].database，查库前必须确认目标库名")
    print()
    print("数据库 MCP 调查清单:")
    print("  1. 表结构与字段注释：确认主表、明细表、字典表、主数据表和关键字段。")
    print("  2. 约束与索引：确认主键、唯一约束、业务编码索引、时间字段索引。")
    print("  3. 字典与主数据：确认枚举值、字典中文名、产线/设备/组织等主数据关联。")
    print("  4. 样例数据：按业务条件取 5-20 条正例、反例、边界样本。")
    print("  5. 数据分布：统计状态、类型、产线、时间范围、空值和异常值分布。")
    print("  6. 结论回写：把查询环境、SQL、表关系、字段口径、样例特征和未决项写入分析或关联信息调查。")
    print()
    print("只读 SQL 模板:")
    print("  -- 查询会话确认")
    print("  select current_database(), current_schema();")
    print()
    print("  -- 表结构")
    print("  select table_schema, table_name, column_name, data_type, is_nullable")
    print("  from information_schema.columns")
    print(f"  where table_catalog = '{database}'")
    print(f"    and table_schema = '{schema}'")
    print("    and table_name in ('<候选表名>')")
    print("  order by table_schema, table_name, ordinal_position;")
    print()
    print("  -- 样例数据")
    print("  select * from <候选表名> where <业务条件> order by <时间或主键字段> desc limit 20;")
    print()
    print("  -- 数据分布")
    print("  select <状态或类型字段>, count(*) from <候选表名> group by <状态或类型字段> order by count(*) desc;")
    return 0


def migration_check(config: dict[str, Any], project: str, requirement_name: str) -> int:
    """检查正式 Flyway 迁移变更是否已有需求目录中间 SQL 作为来源。"""
    req_dir = find_requirement_dir(config, requirement_name)
    repo_dir = action_repo_dir(config, project, [requirement_name]) if project != "docs" else project_dir(config, project)
    files = changed_files(repo_dir)
    official = [file for file in files if is_official_migration(file)]
    issues: list[str] = []

    if official and not has_intermediate_sql(req_dir):
        issues.append("official Flyway migration changed before intermediate SQL is present")
        for file in official:
            issues.append(f"official migration file: {file}")

    return print_issues("Migration check", issues)


def guard_check(config: dict[str, Any], project: str, requirement_name: str) -> int:
    """组合执行需求文档、迁移和高风险路径门禁检查。"""
    req_dir = find_requirement_dir(config, requirement_name)
    repo_dir = action_repo_dir(config, project, [requirement_name]) if project != "docs" else project_dir(config, project)
    files = changed_files(repo_dir)
    issues: list[str] = []
    issues.extend(common_change_issues(req_dir, files))

    exit_code = 0
    if docs_check(config, requirement_name):
        exit_code = 1
    if change_check(config, project, requirement_name):
        exit_code = 1
    if migration_check(config, project, requirement_name):
        exit_code = 1
    if print_issues("Guard path check", issues):
        exit_code = 1
    if exit_code == 0:
        print("Guard check passed.")
    return exit_code
