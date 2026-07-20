from __future__ import annotations

import json
from pathlib import Path

from praxis.application import PraxisApplication
from praxis.cli import main
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


def test_workspace_cli_initializes_v2_facts(tmp_path: Path, capsys) -> None:
    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "workspace",
            "init",
            "--workspace-id",
            "demo",
            "--product-family",
            "ifc-manufacturing",
            "--project",
            "backend:java-maven:backend:main",
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
    assert server.name == "Praxis V2"
