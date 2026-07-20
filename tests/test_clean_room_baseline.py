from __future__ import annotations

import json
from pathlib import Path

from praxis import __version__
from praxis.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_version_is_3() -> None:
    assert __version__ == "3.0.0"


def test_cli_version_is_machine_readable(capsys) -> None:
    assert main(["version", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "code": "OK",
        "data": {"version": "3.0.0"},
        "diagnostics": [],
    }


def test_cli_version_is_human_readable(capsys) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out == "3.0.0\n"


def test_v3_tree_contains_foundational_architecture() -> None:
    for package in (
        "cli",
        "mcp",
        "workspace",
        "worktree",
        "tasks",
        "knowledge",
        "skills",
        "gates",
        "portraits",
        "codegraph",
        "integrations",
        "storage",
        "domain",
        "naming",
        "documents",
    ):
        assert (ROOT / "src" / "praxis" / package).is_dir()
