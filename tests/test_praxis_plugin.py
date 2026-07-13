from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_valid_workspace(root: Path) -> None:
    (root / ".praxis" / "contracts" / "agents").mkdir(parents=True)
    (root / ".praxis").mkdir(exist_ok=True)
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / "praxis.toml").write_text(
        'schema_version = 1\nproject_index = "praxis.projects.toml"\n',
        encoding="utf-8",
    )
    (root / "praxis.projects.toml").write_text(
        """
version = 1
worktreeRoot = ".worktrees"

[projects.web]
label = "Web"
path = "apps/web"
kind = "pnpm-web"
defaultBranch = "local"
upstreamBranch = "main"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / ".praxis" / "core.toml").write_text("schema_version = 1\n", encoding="utf-8")
    (root / ".praxis" / "project-adapter.toml").write_text(
        "schema_version = 1\n", encoding="utf-8"
    )
    (root / ".praxis" / "contracts" / "agents" / "turn.schema.json").write_text(
        '{"schemaVersion": 1}\n',
        encoding="utf-8",
    )
    (root / ".praxis" / "contracts" / "agents" / "delivery.schema.json").write_text(
        '{"schemaVersion": 1}\n',
        encoding="utf-8",
    )


def test_check_workspace_reads_project_branch_config_from_workspace(tmp_path: Path) -> None:
    write_valid_workspace(tmp_path)
    check_workspace = load_module(
        "praxis_check_workspace",
        PLUGIN_ROOT / "scripts" / "praxis_check_workspace.py",
    )

    report = check_workspace.analyze_workspace(tmp_path)

    assert report.ok is True
    assert report.projects == [
        {
            "name": "web",
            "path": "apps/web",
            "kind": "pnpm-web",
            "defaultBranch": "local",
            "upstreamBranch": "main",
        }
    ]


def test_check_workspace_reports_missing_required_files(tmp_path: Path) -> None:
    check_workspace = load_module(
        "praxis_check_workspace",
        PLUGIN_ROOT / "scripts" / "praxis_check_workspace.py",
    )

    report = check_workspace.analyze_workspace(tmp_path)

    assert report.ok is False
    assert "AGENTS.md" in report.missing_files
    assert "praxis.projects.toml" in report.missing_files


def test_check_workspace_requires_delivery_contract(tmp_path: Path) -> None:
    write_valid_workspace(tmp_path)
    (tmp_path / ".praxis" / "contracts" / "agents" / "delivery.schema.json").unlink()
    check_workspace = load_module(
        "praxis_check_workspace",
        PLUGIN_ROOT / "scripts" / "praxis_check_workspace.py",
    )

    report = check_workspace.analyze_workspace(tmp_path)

    assert report.ok is False
    assert ".praxis/contracts/agents/delivery.schema.json" in report.missing_files


def test_init_workspace_renders_thin_project_templates(tmp_path: Path) -> None:
    init_workspace = load_module(
        "praxis_init_workspace",
        PLUGIN_ROOT / "scripts" / "praxis_init_workspace.py",
    )

    written = init_workspace.initialize_workspace(tmp_path, name="Demo Workspace")

    assert "AGENTS.md" in written
    assert "praxis.toml" in written
    assert "praxis.projects.toml" in written
    assert ".praxis/contracts/agents/delivery.schema.json" in written
    projects_text = (tmp_path / "praxis.projects.toml").read_text(encoding="utf-8")
    assert 'description = "Workspace documentation and requirements."' in projects_text
    assert 'aliases = ["docs"]' in projects_text
    assert 'defaultBranch = "main"' in projects_text
    assert 'defaultBranch = "local"' not in projects_text
    turn_contract = (tmp_path / ".praxis" / "contracts" / "agents" / "turn.schema.json").read_text(
        encoding="utf-8"
    )
    delivery_contract = (
        tmp_path / ".praxis" / "contracts" / "agents" / "delivery.schema.json"
    ).read_text(encoding="utf-8")
    assert "enforce_business_startup_gate" in turn_contract
    assert "confirmedCommitAllowlist" in delivery_contract
    assert "implicit_non_test_commit_filtering" in delivery_contract


def test_skill_references_exist_and_are_linked() -> None:
    skill_text = (PLUGIN_ROOT / "skills" / "praxis-workflow" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    expected_references = {
        "startup-gate.md",
        "worktree.md",
        "command-contract.md",
        "project-config-boundary.md",
        "verification-closeout.md",
        "delivery-contract.md",
    }

    for reference in expected_references:
        assert reference in skill_text
        assert (PLUGIN_ROOT / "skills" / "praxis-workflow" / "references" / reference).is_file()


def test_codex_command_shortcuts_are_packaged() -> None:
    commands = {
        "praxis-help.toml": "显示 Praxis Workflow 快速参考",
        "praxis-check.toml": "检查当前 Praxis 工作区",
        "praxis-start.toml": "启动 Praxis 业务需求",
        "praxis-tolaria-check.toml": "检查 Tolaria 元数据缺口",
    }

    for filename, description in commands.items():
        text = (PLUGIN_ROOT / "commands" / filename).read_text(encoding="utf-8")
        assert f'description = "{description}"' in text
        assert "prompt = " in text
        assert "使用中文" in text


def test_step_handoff_guidance_is_packaged() -> None:
    paths = [
        PLUGIN_ROOT / "skills" / "praxis-workflow" / "SKILL.md",
        PLUGIN_ROOT / "templates" / "AGENTS.md.tpl",
        PLUGIN_ROOT
        / "profiles"
        / "ifc-mom"
        / ".praxis"
        / "extensions"
        / "ifc-mom"
        / "rules"
        / "global"
        / "00-工作流精简索引.md",
    ]

    for path in paths:
        assert "推荐下一步" in path.read_text(encoding="utf-8")



def test_oh_my_pi_codex_routing_guidance_is_packaged() -> None:
    skill_text = (PLUGIN_ROOT / "skills" / "praxis-workflow" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    agent_template = (PLUGIN_ROOT / "templates" / "AGENTS.md.tpl").read_text(encoding="utf-8")
    mom_skill = (
        PLUGIN_ROOT
        / "profiles"
        / "ifc-mom"
        / ".praxis"
        / "extensions"
        / "ifc-mom"
        / "skills"
        / "global"
        / "mom-agent-workflow"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    mom_rule = (
        PLUGIN_ROOT
        / "profiles"
        / "ifc-mom"
        / ".praxis"
        / "extensions"
        / "ifc-mom"
        / "rules"
        / "global"
        / "praxis-workflow"
        / "02-主对话与Subagent.md"
    ).read_text(encoding="utf-8")

    assert "Oh My Pi / Codex Runtime Routing" in skill_text
    assert "Tool-only" in skill_text
    assert "subagent: waived-small-change" in skill_text
    assert "Oh My Pi/Codex 默认按单一 Codex 订阅调度" in agent_template
    assert "Codex-Only Model Routing" in mom_skill
    assert "Codex 订阅下的模型/算力分配" in mom_rule


def test_agent_template_requires_chinese_conversation_and_requirement_docs() -> None:
    text = (PLUGIN_ROOT / "templates" / "AGENTS.md.tpl").read_text(encoding="utf-8")

    assert "默认使用中文与用户对话" in text
    assert "需求文档必须使用中文" in text


def test_agent_template_routes_codegraph_from_project_index() -> None:
    text = (PLUGIN_ROOT / "templates" / "AGENTS.md.tpl").read_text(encoding="utf-8")

    assert "praxis.projects.toml" in text
    assert "description" in text
    assert ".codegraph/" in text
    assert "current shell directory" in text


def test_ifc_mom_profile_packages_workflow_rules_and_skills() -> None:
    profile = PLUGIN_ROOT / "profiles" / "ifc-mom"
    profile_root = profile / ".praxis" / "extensions" / "ifc-mom"

    assert (profile / ".praxis" / "commands.toml").is_file()
    assert (profile / "workspaces.json").is_file()
    assert (profile_root / "extension.toml").is_file()
    assert (profile_root / "rules" / "global" / "praxis-workflow" / "06-交付收口.md").is_file()
    assert (profile_root / "skills" / "global" / "mom-agent-workflow" / "SKILL.md").is_file()
    assert (profile_root / "skills" / "global" / "mom-delivery-branch-hygiene" / "SKILL.md").is_file()
    assert (profile_root / "skills" / "global" / "mom-tolaria-vault" / "SKILL.md").is_file()
    assert (profile / "scripts" / "codex" / "task.py").is_file()
    assert (profile / "scripts" / "codex" / "momlib" / "finish.py").is_file()
    assert (profile / "scripts" / "codex" / "momlib" / "process.py").is_file()


def test_ifc_mom_profile_documents_engineering_control_layer() -> None:
    route_text = (
        PLUGIN_ROOT
        / "profiles"
        / "ifc-mom"
        / ".praxis"
        / "extensions"
        / "ifc-mom"
        / "rules"
        / "global"
        / "praxis-workflow"
        / "09-Praxis重型化路线.md"
    ).read_text(encoding="utf-8")

    assert "工程控制层" in route_text
    assert "工程控制论" in route_text
    assert "软件工程" in route_text
    assert "目标-观测-反馈" in route_text


def test_ifc_mom_profile_requires_chinese_conversation_and_requirement_docs() -> None:
    workflow_index = (
        PLUGIN_ROOT
        / "profiles"
        / "ifc-mom"
        / ".praxis"
        / "extensions"
        / "ifc-mom"
        / "rules"
        / "global"
        / "00-工作流精简索引.md"
    ).read_text(encoding="utf-8")

    assert "默认使用中文与用户对话" in workflow_index
    assert "需求文档、分析、规划、进度和交付说明必须使用中文" in workflow_index


def test_ifc_mom_profile_routes_codegraph_by_selected_project_root() -> None:
    workflow_index = (
        PLUGIN_ROOT
        / "profiles"
        / "ifc-mom"
        / ".praxis"
        / "extensions"
        / "ifc-mom"
        / "rules"
        / "global"
        / "00-工作流精简索引.md"
    ).read_text(encoding="utf-8")

    assert "description" in workflow_index
    assert "MOM/AOTU 聚合根不是单一 Git 仓库" in workflow_index
    assert ".codegraph/" in workflow_index


def test_sync_profile_copies_ifc_mom_assets_without_project_facts(tmp_path: Path) -> None:
    write_valid_workspace(tmp_path)
    original_projects = (tmp_path / "praxis.projects.toml").read_text(encoding="utf-8")
    sync_profile = load_module(
        "praxis_sync_profile",
        PLUGIN_ROOT / "scripts" / "praxis_sync_profile.py",
    )

    written = sync_profile.sync_profile(tmp_path, "ifc-mom")

    assert ".praxis/commands.toml" in written
    assert ".praxis/extensions/ifc-mom/extension.toml" in written
    assert ".praxis/extensions/ifc-mom/rules/global/praxis-workflow/06-交付收口.md" in written
    assert ".praxis/extensions/ifc-mom/skills/global/mom-agent-workflow/SKILL.md" in written
    assert "scripts/codex/task.py" in written
    assert "scripts/codex/momlib/finish.py" in written
    assert "workspaces.json" not in written
    assert not any("__pycache__" in path or path.endswith(".pyc") for path in written)
    assert not (tmp_path / "workspaces.json").exists()
    assert (tmp_path / "praxis.projects.toml").read_text(encoding="utf-8") == original_projects


def test_sync_workspaces_uses_profile_registry_without_overwriting_project_facts(tmp_path: Path) -> None:
    workspace_a = tmp_path / "mom"
    workspace_b = tmp_path / "aotu"
    write_valid_workspace(workspace_a)
    write_valid_workspace(workspace_b)
    original_projects = (workspace_a / "praxis.projects.toml").read_text(encoding="utf-8")
    registry = tmp_path / "workspaces.json"
    registry.write_text(
        json.dumps(
            {
                "profiles": {
                    "ifc-mom": {
                        "workspaces": [
                            {"name": "mom", "path": str(workspace_a)},
                            {"name": "aotu", "path": str(workspace_b)},
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    sync_workspaces = load_module(
        "praxis_sync_workspaces",
        PLUGIN_ROOT / "scripts" / "praxis_sync_workspaces.py",
    )

    dry_run = sync_workspaces.sync_workspaces("ifc-mom", registry_path=registry, force=True, dry_run=True)
    synced = sync_workspaces.sync_workspaces("ifc-mom", registry_path=registry, force=True)

    assert [entry["name"] for entry in dry_run] == ["mom", "aotu"]
    assert all(entry["status"] == "would-write" for entry in dry_run)
    assert all(".praxis/commands.toml" in entry["files"] for entry in synced)
    assert all("workspaces.json" not in entry["files"] for entry in synced)
    assert (workspace_a / "praxis.projects.toml").read_text(encoding="utf-8") == original_projects


def test_docs_workflow_uses_tolaria_vault_rules() -> None:
    profile_root = PLUGIN_ROOT / "profiles" / "ifc-mom" / ".praxis" / "extensions" / "ifc-mom"
    doc_skill = (profile_root / "skills" / "global" / "mom-doc-organization" / "SKILL.md").read_text(encoding="utf-8")
    tolaria_skill = (profile_root / "skills" / "global" / "mom-tolaria-vault" / "SKILL.md").read_text(encoding="utf-8")
    doc_rule = (profile_root / "rules" / "global" / "05-需求文档组织规范.md").read_text(encoding="utf-8")
    manifest = (profile_root / "manifest.toml").read_text(encoding="utf-8")

    assert "Tolaria" in doc_skill
    assert "Tolaria" in tolaria_skill
    assert "Tolaria" in doc_rule
    assert "mom-tolaria-vault/SKILL.md" in manifest


def test_docs_tolaria_helpers_are_split_from_large_docs_module() -> None:
    scripts_root = PLUGIN_ROOT / "profiles" / "ifc-mom" / "scripts" / "codex" / "momlib"
    docs_text = (scripts_root / "docs.py").read_text(encoding="utf-8")

    assert (scripts_root / "docs_tolaria.py").is_file()
    assert "def tolaria_check(" not in docs_text
    assert "def tolaria_publish(" not in docs_text
