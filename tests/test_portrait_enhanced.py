from __future__ import annotations

import json
import subprocess
from pathlib import Path

from praxis.portraits.service import PortraitService
from praxis.skills.registry import SkillRegistry
from praxis.workspace.service import Project, WorkspaceService


def _init_workspace(tmp_path: Path, project: Project) -> str:
    repo = tmp_path / project.path
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[project],
    )
    return repo


def test_commands_detect_pnpm_scripts_from_package_json(tmp_path: Path) -> None:
    repo = _init_workspace(
        tmp_path,
        Project("web", "pnpm-web", "web", "main"),
    )
    (repo / "package.json").write_text(
        json.dumps(
            {
                "name": "web",
                "packageManager": "pnpm@10.22.0",
                "scripts": {
                    "build": "vite build",
                    "build:antd": "vite build antd",
                    "test": "vitest run",
                    "check:type": "vue-tsc --noEmit",
                    "lint": "eslint .",
                },
            }
        ),
        encoding="utf-8",
    )
    (repo / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'", encoding="utf-8")

    result = PortraitService(tmp_path).scan("web")

    assert result.ok
    # pnpm 前缀 + 语义脚本
    assert "pnpm build" in result.data["build_commands"]
    assert "pnpm test" in result.data["test_commands"]
    assert "pnpm check:type" in result.data["typecheck_commands"]
    assert "pnpm lint" in result.data["lint_commands"]


def test_commands_detect_maven_modules_from_pom(tmp_path: Path) -> None:
    repo = _init_workspace(
        tmp_path,
        Project("backend", "java-maven", "backend", "main"),
    )
    (repo / "pom.xml").write_text(
        "<project><modules>"
        "<module>lamp-public</module>"
        "<module>lamp-mes</module>"
        "</modules></project>",
        encoding="utf-8",
    )

    result = PortraitService(tmp_path).scan("backend")

    assert result.ok
    assert "lamp-public" in result.data["module_structure"]
    assert "lamp-mes" in result.data["module_structure"]


def test_rule_summary_extracted_from_claude_md(tmp_path: Path) -> None:
    repo = _init_workspace(
        tmp_path,
        Project("web", "pnpm-web", "web", "main"),
    )
    (repo / "CLAUDE.md").write_text(
        "# 项目规则\n\n"
        "这是管理端仓库，基于 Vue3 + Antd。\n\n"
        "## 常用命令\n\n"
        "```bash\n"
        "pnpm build:antd\n"
        "pnpm check:type\n"
        "```\n",
        encoding="utf-8",
    )

    result = PortraitService(tmp_path).scan("web")

    assert result.ok
    summary = result.data["rule_summary"]
    assert "管理端仓库" in summary
    assert "pnpm build:antd" in summary


def test_subrepo_skills_discovered_and_registered(tmp_path: Path) -> None:
    repo = _init_workspace(
        tmp_path,
        Project("web", "pnpm-web", "web", "main"),
    )
    skill_dir = repo / "docs" / "skills" / "gen-api"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: gen-api\ndescription: 生成 API 客户端。\n---\n\n# Gen API\n",
        encoding="utf-8",
    )
    (skill_dir / "skill.toml").write_text(
        'id = "demo-web-gen-api"\ntype = "business"\nversion = "1.0.0"\n'
        'license = "Proprietary"\nsource = "test"\nsource_version = "1"\n'
        'risk = "none"\ncontext_budget = 500\nrequired_tools = []\ntriggers = []\n'
        "systems = []\nprojects = []\nrepository_roles = []\n",
        encoding="utf-8",
    )

    registered = PortraitService(tmp_path)._discover_subrepo_skills("web", repo)

    assert "demo-web-gen-api" in registered
    # 已登记到 knowledge/skills/business/
    registered_skill = tmp_path / "知识库" / "skills" / "business" / "demo-web-gen-api"
    assert (registered_skill / "SKILL.md").is_file()
    # 可被 SkillRegistry.workspace 发现
    skills = SkillRegistry.workspace(tmp_path).all()
    assert any(s.id == "demo-web-gen-api" for s in skills)
