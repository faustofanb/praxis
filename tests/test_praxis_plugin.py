from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tomllib
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
    for filename in (
        "praxis-help.toml",
        "praxis-check.toml",
        "praxis-start.toml",
        "praxis-tolaria-check.toml",
    ):
        assert (PLUGIN_ROOT / "commands" / filename).is_file()


def test_backend_verification_does_not_infer_or_override_java_runtime() -> None:
    verification_rule = (
        PLUGIN_ROOT
        / "profiles"
        / "ifc-mom"
        / ".praxis"
        / "extensions"
        / "ifc-mom"
        / "rules"
        / "global"
        / "praxis-workflow"
        / "05-大任务拆分与验证.md"
    ).read_text(encoding="utf-8")

    assert "直接继承调用进程的全局 `PATH` / `JAVA_HOME`" in verification_rule
    assert "只以 `Java version:` 和 `runtime:` 字段为准" in verification_rule
    assert "`OS name` / `version` 是操作系统版本" in verification_rule



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
    assert not any("__pycache__" in path or path.endswith((".pyc", ".DS_Store")) for path in written)
    assert not (tmp_path / "workspaces.json").exists()
    assert (tmp_path / "praxis.projects.toml").read_text(encoding="utf-8") == original_projects


def test_initialized_ifc_mom_workspace_passes_system_check(tmp_path: Path) -> None:
    init_workspace = load_module(
        "praxis_init_workspace_for_check",
        PLUGIN_ROOT / "scripts" / "praxis_init_workspace.py",
    )
    init_workspace.initialize_workspace_with_profiles(tmp_path, name="Demo", profiles=["ifc-mom"])

    completed = subprocess.run(
        [sys.executable, "-B", str(tmp_path / "scripts" / "codex" / "task.py"), "system", "check"],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    assert completed.returncode == 0, completed.stdout


def test_profile_keeps_lightweight_execution_and_backend_commands() -> None:
    profile = PLUGIN_ROOT / "profiles" / "ifc-mom"
    commands = (profile / ".praxis/commands.toml").read_text(encoding="utf-8")
    task = (profile / "scripts/codex/task.py").read_text(encoding="utf-8")
    praxis = (profile / "scripts/codex/momlib/praxis.py").read_text(encoding="utf-8")
    subagent_rule = (
        profile
        / ".praxis/extensions/ifc-mom/rules/global/praxis-workflow/02-主对话与Subagent.md"
    ).read_text(encoding="utf-8")
    process_rule = (
        profile
        / ".praxis/extensions/ifc-mom/rules/global/praxis-workflow/07-过程改进与维护.md"
    ).read_text(encoding="utf-8")
    backend_run = (profile / "scripts/codex/backend_run.py").read_text(encoding="utf-8")

    assert "代码类任务必须在完成必要规划后自动派发 subagent" not in subagent_rule
    assert "每个业务需求进入最终收口时，必须新增一份" not in process_rule
    assert "Full clean install" not in backend_run
    assert "validate-verdict" not in task
    assert "import-verdict" not in task
    assert "task role" not in task
    assert "precheck-all" not in task
    assert "praxis_require_verdict" not in praxis
    assert "project.import-verdict" not in commands
    assert "project.delivery-precheck-all" not in commands


def test_report_task_loads_one_etl_router_and_keeps_split_rules_on_demand() -> None:
    extension = PLUGIN_ROOT / "profiles/ifc-mom/.praxis/extensions/ifc-mom"
    manifest = tomllib.loads((extension / "manifest.toml").read_text(encoding="utf-8"))
    report_rules = manifest["task"]["report"]["rules"]
    router = extension / "rules/global/praxis-workflow/08-轻量ETL报表工作流.md"
    router_text = router.read_text(encoding="utf-8")

    assert report_rules == [
        "AGENTS.md",
        ".praxis/extensions/ifc-mom/rules/global/00-工作流精简索引.md",
        ".praxis/extensions/ifc-mom/rules/global/praxis-workflow/08-轻量ETL报表工作流.md",
    ]
    for split_rule in (
        "08a-轻量ETL资产与分层.md",
        "08b-轻量ETL调查与口径治理.md",
        "08c-轻量ETLMagicAPI与积木报表.md",
        "08d-轻量ETL产出物与验收.md",
    ):
        assert split_rule in router_text
    assert len(router_text.splitlines()) < 100


def test_verify_and_backend_run_reuse_shared_config_and_process_helpers() -> None:
    scripts = PLUGIN_ROOT / "profiles/ifc-mom/scripts/codex"
    for script_name in ("verify.py", "backend_run.py"):
        text = (scripts / script_name).read_text(encoding="utf-8")
        assert "from momlib.config import" in text
        assert "from momlib.process import" in text
        assert "def fail(" not in text
        assert "def load_config(" not in text
        assert "def capture(" not in text


def test_workflow_checks_reuses_delivery_commit_and_migration_helpers() -> None:
    workflow_checks = (
        PLUGIN_ROOT / "profiles/ifc-mom/scripts/codex/momlib/workflow_checks.py"
    ).read_text(encoding="utf-8")

    assert "commit_changed_files" in workflow_checks.split("from .delivery_policy import", 1)[1].split("\n", 1)[0]
    assert "is_official_migration" in workflow_checks.split("from .delivery_policy import", 1)[1].split("\n", 1)[0]
    assert "def commit_changed_files(" not in workflow_checks
    assert "def is_official_migration(" not in workflow_checks


def test_task_routes_do_not_preload_optional_agent_coordination_skill() -> None:
    manifest_path = PLUGIN_ROOT / "profiles/ifc-mom/.praxis/extensions/ifc-mom/manifest.toml"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))

    for task_name, task_config in manifest["task"].items():
        assert not any("mom-agent-workflow" in skill for skill in task_config.get("skills", [])), task_name


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


def test_docs_tolaria_helpers_are_split_from_large_docs_module() -> None:
    scripts_root = PLUGIN_ROOT / "profiles" / "ifc-mom" / "scripts" / "codex" / "momlib"
    docs_text = (scripts_root / "docs.py").read_text(encoding="utf-8")

    assert (scripts_root / "docs_tolaria.py").is_file()
    assert "def tolaria_check(" not in docs_text
    assert "def tolaria_publish(" not in docs_text
