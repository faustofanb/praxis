from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .paths import ROOT_DIR


TEMPLATE_DIR = ".praxis/templates"
REPORT_FILE = ".praxis/out/template-report.json"
TEMPLATE_FILES = {
    "rule": "rule.md.tpl",
    "skill": "skill.md.tpl",
}
SCHEMA_FILE = ".praxis/templates/schema.json"
REQUIRED_SECTIONS = [
    "## Metadata",
    "## Scope",
    "## Triggers",
    "## Inputs",
    "## Outputs",
    "## Workflow",
    "## Validation",
    "## Evidence",
    "## Failure Modes",
    "## Examples",
    "## References",
    "## Compatibility",
    "## Version",
]
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        return {}
    data: dict[str, str] = {}
    for line in lines[1:end_index]:
        key, separator, value = line.partition(":")
        if separator:
            data[key.strip()] = value.strip().strip("'\"")
    return data


def _body_after_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[index + 1 :])
    return text


def _template_path(root: Path, kind: str) -> Path:
    filename = TEMPLATE_FILES.get(kind)
    if not filename:
        raise ValueError(f"unknown Praxis template kind: {kind}")
    return root / TEMPLATE_DIR / filename


def render_template(
    *,
    root: Path = ROOT_DIR,
    kind: str,
    slug: str,
    title: str,
    description: str,
    output: Path,
) -> Path:
    """Render a Praxis rule or skill template to a concrete file."""
    if kind == "skill" and not SKILL_NAME_PATTERN.match(slug):
        raise ValueError("skill slug must use lowercase letters, digits and hyphens")
    template_path = _template_path(root, kind)
    if not template_path.is_file():
        raise FileNotFoundError(f"missing template: {_relative(root, template_path)}")
    values = {
        "slug": slug,
        "name": slug,
        "title": title,
        "description": description,
        "date": time.strftime("%Y-%m-%d"),
    }
    text = template_path.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    if re.search(r"{{[^}]+}}", text):
        raise ValueError(f"rendered template still contains unresolved placeholders: {kind}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return output


def _template_issues(root: Path) -> tuple[list[str], list[str]]:
    templates: list[str] = []
    issues: list[str] = []
    schema_path = root / SCHEMA_FILE
    if not schema_path.is_file():
        issues.append(f"missing Praxis template schema: {SCHEMA_FILE}")
    for kind, filename in TEMPLATE_FILES.items():
        path = root / TEMPLATE_DIR / filename
        templates.append(_relative(root, path))
        if not path.is_file():
            issues.append(f"missing Praxis {kind} template: {_relative(root, path)}")
            continue
        text = path.read_text(encoding="utf-8")
        for placeholder in ("{{title}}", "{{description}}"):
            if placeholder not in text:
                issues.append(f"{_relative(root, path)} missing placeholder {placeholder}")
        for section in REQUIRED_SECTIONS:
            if section not in text:
                issues.append(f"{_relative(root, path)} missing structured section {section}")
        if kind == "skill":
            for placeholder in ("{{slug}}", "name:", "description:"):
                if placeholder not in text:
                    issues.append(f"{_relative(root, path)} missing skill contract token {placeholder}")
    return templates, issues


def _rule_issues(root: Path) -> tuple[int, list[str]]:
    rule_roots = [root / ".praxis" / "rules", root / ".rule"]
    extension_root = root / ".praxis" / "extensions"
    if extension_root.is_dir():
        rule_roots.extend(sorted(path for path in extension_root.glob("*/rules") if path.is_dir()))
    if not any(path.is_dir() for path in rule_roots):
        return 0, ["missing Praxis rule roots: .praxis/rules or .praxis/extensions/*/rules"]
    issues: list[str] = []
    files = sorted(path for rule_root in rule_roots if rule_root.is_dir() for path in rule_root.rglob("*.md"))
    for path in files:
        body = _body_after_frontmatter(path.read_text(encoding="utf-8"))
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if not lines or not lines[0].startswith("# "):
            issues.append(f"{_relative(root, path)} must start with a level-1 title")
    return len(files), issues


def _skill_issues(root: Path) -> tuple[int, list[str]]:
    skill_roots = [root / ".praxis" / "skills", root / ".skill"]
    extension_root = root / ".praxis" / "extensions"
    if extension_root.is_dir():
        skill_roots.extend(sorted(path for path in extension_root.glob("*/skills") if path.is_dir()))
    if not any(path.is_dir() for path in skill_roots):
        return 0, ["missing Praxis skill roots: .praxis/skills or .praxis/extensions/*/skills"]
    issues: list[str] = []
    files = sorted(path for skill_root in skill_roots if skill_root.is_dir() for path in skill_root.rglob("SKILL.md"))
    for path in files:
        text = path.read_text(encoding="utf-8")
        meta = _frontmatter(text)
        name = meta.get("name", "")
        description = meta.get("description", "")
        if not name:
            issues.append(f"{_relative(root, path)} missing frontmatter name")
        elif not SKILL_NAME_PATTERN.match(name):
            issues.append(f"{_relative(root, path)} has invalid skill name: {name}")
        if not description:
            issues.append(f"{_relative(root, path)} missing frontmatter description")
    return len(files), issues


def template_report(root: Path = ROOT_DIR) -> dict[str, Any]:
    """Validate Praxis rule/skill templates and existing project rule/skill files."""
    templates, template_errors = _template_issues(root)
    rule_count, rule_errors = _rule_issues(root)
    skill_count, skill_errors = _skill_issues(root)
    issues = [*template_errors, *rule_errors, *skill_errors]
    return {
        "schemaVersion": 1,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "PASS" if not issues else "FAIL",
        "templates": templates,
        "schema": SCHEMA_FILE if (root / SCHEMA_FILE).is_file() else "",
        "requiredSections": REQUIRED_SECTIONS,
        "counts": {
            "rules": rule_count,
            "skills": skill_count,
        },
        "issues": issues,
    }


def write_template_report(root: Path = ROOT_DIR) -> Path:
    """Write the Praxis rule/skill template validation report."""
    report = template_report(root)
    report_path = root / REPORT_FILE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Praxis template check: {report['status']}")
    print(f"  report: {report_path}")
    print(f"  rules: {report['counts']['rules']}")
    print(f"  skills: {report['counts']['skills']}")
    if report["issues"]:
        print("Issues:")
        for issue in report["issues"]:
            print(f"  - {issue}")
    return report_path
