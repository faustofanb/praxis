from __future__ import annotations

import json
from pathlib import Path

from praxis.application import PraxisApplication
from praxis.cli import _operation, _parser, main
from praxis.mcp.server import execute as mcp_execute


def test_cli_and_mcp_use_identical_application_results(tmp_path: Path, capsys) -> None:
    application = PraxisApplication(tmp_path)
    expected = application.execute("skill.route", {"intent": "核对数据库表结构"}).to_dict()

    assert mcp_execute(tmp_path, "skill.route", {"intent": "核对数据库表结构"}) == expected
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "skill",
                "route",
                "核对数据库表结构",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == expected


def test_workspace_cli_initializes_v3_facts(tmp_path: Path, capsys) -> None:
    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "init",
            "--workspace-id",
            "demo",
            "--name",
            "演示开发工作空间",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert (tmp_path / "praxis.toml").exists()


def test_doctor_reports_skill_provider_registration_status(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    unmanaged = home / ".codex" / "skills" / "unmanaged-helper" / "SKILL.md"
    unmanaged.parent.mkdir(parents=True)
    unmanaged.write_text("---\nname: unmanaged-helper\n---\n\n# Helper\n")
    monkeypatch.setattr(Path, "home", lambda: home)
    PraxisApplication(tmp_path).execute(
        "init", {"workspace_id": "demo", "name": "演示工作空间"}
    )

    result = PraxisApplication(tmp_path).execute("doctor")

    assert result.ok
    assert result.data["skill_providers"]["installed_without_policy"] == [
        "unmanaged-helper"
    ]
    assert "code-quality-review" in result.data["skill_providers"][
        "policy_without_provider"
    ]


def test_mcp_server_registers_praxis_tools_and_skill_resource(tmp_path: Path) -> None:
    from praxis.mcp.server import create_server

    server = create_server(tmp_path)
    assert server.name == "Praxis V3"


def test_portrait_and_database_cli_preserve_requested_action() -> None:
    portrait = _parser().parse_args(["portrait", "diff", "--project", "backend"])
    database = _parser().parse_args(
        [
            "database",
            "query",
            "--project",
            "backend",
            "--connection",
            "dbx://dev",
            "--sql",
            "select 1",
        ]
    )
    investigation = _parser().parse_args(
        [
            "database",
            "investigate",
            "--project",
            "backend",
            "--connection",
            "dbx://BL_DMS_DB/app",
            "--purpose",
            "追溯一期",
            "--sql",
            "select 1",
        ]
    )

    assert _operation(portrait) == ("portrait.diff", {"project_id": "backend"})
    assert _operation(database) == (
        "database.query",
        {
            "project_id": "backend",
            "connection_ref": "dbx://dev",
            "sql": "select 1",
            "approved": False,
        },
    )
    assert _operation(investigation) == (
        "database.investigate",
        {
            "project_id": "backend",
            "connection_ref": "dbx://BL_DMS_DB/app",
            "purpose": "追溯一期",
            "sql": "select 1",
        },
    )


def test_codegraph_cli_maps_worktree_scoped_selectors() -> None:
    binding = "WT-REQ-20260722-001--backend"
    ensure = _parser().parse_args(
        ["codegraph", "ensure-fresh", "--binding", binding, "--initialize"]
    )
    affected = _parser().parse_args(
        ["codegraph", "affected", "--worktree", "/tmp/backend"]
    )
    explore = _parser().parse_args(
        ["codegraph", "explore", "OrderService", "--binding", binding]
    )

    assert _operation(ensure) == (
        "codegraph.ensure-fresh",
        {"binding_id": binding, "initialize": True},
    )
    assert _operation(affected) == (
        "codegraph.affected",
        {"worktree": Path("/tmp/backend")},
    )
    assert _operation(explore) == (
        "codegraph.explore",
        {"binding_id": binding, "target": "OrderService"},
    )


def test_context_cli_build_maps_traceability_inputs() -> None:
    args = _parser().parse_args(
        [
            "context",
            "build",
            "--requirement",
            "REQ-20260720-001",
            "--project",
            "backend",
            "--stage",
            "backend",
            "--agent-role",
            "coder",
            "--allow-path",
            "src/**",
        ]
    )

    assert _operation(args) == (
        "context.build",
        {
            "requirement_id": "REQ-20260720-001",
            "project_id": "backend",
            "stage": "backend",
            "agent_role": "coder",
            "intent": "",
            "token_budget": 24_000,
            "allowed_paths": ["src/**"],
            "forbidden_paths": [],
            "workflow_node": "in_progress",
            "artifact_types": [],
            "risks": [],
            "available_skills": [],
            "approved_skills": [],
        },
    )


def test_requirement_constraint_delivery_and_verification_decline_cli_mapping() -> None:
    constraint = _parser().parse_args(
        [
            "requirement",
            "constraint",
            "add",
            "--requirement",
            "REQ-1",
            "--statement",
            "新增独立记录表",
            "--supersedes",
            "CON-OLD",
            "--source",
            "用户纠正",
        ]
    )
    implementation = _parser().parse_args(
        [
            "requirement",
            "record-implementation",
            "--requirement",
            "REQ-1",
            "--project",
            "backend",
            "--artifact",
            "ART-1",
        ]
    )
    decline = _parser().parse_args(
        [
            "verification",
            "decline",
            "--requirement",
            "REQ-1",
            "--entry",
            "pytest",
            "--user-evidence",
            "用户拒绝",
            "--authorized-by-user",
        ]
    )

    assert _operation(constraint) == (
        "requirement.constraint.add",
        {
            "requirement_id": "REQ-1",
            "statement": "新增独立记录表",
            "supersedes": ["CON-OLD"],
            "source": "用户纠正",
        },
    )
    assert _operation(implementation) == (
        "requirement.record-implementation",
        {
            "requirement_id": "REQ-1",
            "project_id": "backend",
            "artifact_ids": ["ART-1"],
        },
    )
    assert _operation(decline) == (
        "verification.decline",
        {
            "requirement_id": "REQ-1",
            "entry": "pytest",
            "user_evidence": "用户拒绝",
            "authorized_by_user": True,
        },
    )


def test_workspace_add_cli_maps_repository_facts() -> None:
    args = _parser().parse_args(
        [
            "workspace",
            "add",
            "--system",
            "demo",
            "--id",
            "backend",
            "--name",
            "后端服务",
            "--kind",
            "backend",
            "--path",
            "services/backend",
            "--default-branch",
            "main",
            "--test-command",
            "pytest -q",
        ]
    )

    assert _operation(args) == (
        "workspace.add",
        {
            "system_id": "demo",
            "project_id": "backend",
            "name": "后端服务",
            "kind": "backend",
            "path": "services/backend",
            "default_branch": "main",
            "database_connections": [],
            "production_database_connections": [],
            "deployment_commands": [],
            "release_branches": [],
            "template_branches": [],
            "local_files": [],
            "worktree_setup_commands": [],
            "lint_commands": [],
            "typecheck_commands": [],
            "test_commands": ["pytest -q"],
        },
    )


def test_fast_path_cli_commands_map_to_application_operations() -> None:
    commands = [
        ["requirement", "reopen", "REQ-1", "--reason", "继续开发"],
        [
            "skill",
            "complete-node",
            "--requirement",
            "REQ-1",
            "--node",
            "in_progress",
            "--used-skill",
            "ponytail=完成最小实现",
        ],
        ["codegraph", "wait", "--binding", "WT-1", "--timeout", "5"],
        ["worktree", "preview", "REQ-1", "--repository", "backend"],
        [
            "worktree",
            "ensure",
            "REQ-1",
            "--repository",
            "backend",
            "--confirm",
            "WTP-1",
        ],
        ["worktree", "prepare", "REQ-1", "--repository", "backend"],
        ["worktree", "migrate-name", "REQ-1", "--repository", "backend"],
        [
            "agent",
            "receipt",
            "SES-1",
            "--changed-path",
            "src/app.py",
            "--decision",
            "复用现有服务",
        ],
        [
            "approval",
            "grant",
            "--requirement",
            "REQ-1",
            "--scope",
            "verification",
            "--entry",
            "pytest",
            "--user-evidence",
            "用户批准",
            "--authorized-by-user",
        ],
        [
            "approval",
            "check",
            "--requirement",
            "REQ-1",
            "--scope",
            "verification",
            "--entry",
            "pytest",
        ],
        ["approval", "list", "--requirement", "REQ-1"],
        [
            "budget",
            "consume",
            "--requirement",
            "REQ-1",
            "--node",
            "in_progress",
            "--kind",
            "retry",
            "--operation-key",
            "setup:backend",
        ],
        ["budget", "status", "--requirement", "REQ-1"],
    ]

    operations = [_operation(_parser().parse_args(command))[0] for command in commands]

    assert operations == [
        "requirement.reopen",
        "skill.complete-node",
        "codegraph.wait",
        "worktree.preview",
        "worktree.ensure",
        "worktree.prepare",
        "worktree.migrate-name",
        "agent.receipt",
        "approval.grant",
        "approval.check",
        "approval.list",
        "budget.consume",
        "budget.status",
    ]


def test_agent_install_and_launch_cli_preserve_explicit_execution() -> None:
    install = _parser().parse_args(["agent", "install", "--agent", "codex"])
    launch = _parser().parse_args(["agent", "launch", "SES-TEST", "--execute"])

    assert _operation(install) == ("agent.install", {"agent_type": "codex"})
    assert _operation(launch) == (
        "agent.launch",
        {"session_id": "SES-TEST", "execute": True},
    )


def test_agent_start_cli_allows_automatic_context() -> None:
    args = _parser().parse_args(
        [
            "agent",
            "start",
            "--type",
            "codex",
            "--role",
            "coder",
            "--requirement",
            "REQ-1",
            "--worktree",
            "WT-REQ-1--backend",
            "--capability",
            "requirement.read",
            "--intent",
            "修复上下文",
        ]
    )

    operation, values = _operation(args)
    assert operation == "agent.start"
    assert values["context_id"] == ""
    assert values["intent"] == "修复上下文"


def test_worktree_create_cli_allows_omitted_stage() -> None:
    args = _parser().parse_args(
        ["worktree", "create", "REQ-20260721-001", "--repository", "backend"]
    )

    assert _operation(args) == (
        "worktree.create",
        {
            "requirement_id": "REQ-20260721-001",
            "repository_id": "backend",
            "stage": None,
        },
    )


def test_codegraph_status_cli_accepts_binding_without_project() -> None:
    args = _parser().parse_args(
        ["codegraph", "status", "--binding", "WT-REQ-20260721-001--backend"]
    )

    assert _operation(args) == (
        "codegraph.status",
        {"binding_id": "WT-REQ-20260721-001--backend"},
    )
