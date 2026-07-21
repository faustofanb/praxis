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
            "lint_commands": [],
            "typecheck_commands": [],
            "test_commands": ["pytest -q"],
        },
    )


def test_agent_install_and_launch_cli_preserve_explicit_execution() -> None:
    install = _parser().parse_args(["agent", "install", "--agent", "codex"])
    launch = _parser().parse_args(["agent", "launch", "SES-TEST", "--execute"])

    assert _operation(install) == ("agent.install", {"agent_type": "codex"})
    assert _operation(launch) == (
        "agent.launch",
        {"session_id": "SES-TEST", "execute": True},
    )
