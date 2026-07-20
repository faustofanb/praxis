from __future__ import annotations

import json
from pathlib import Path

from praxis import __version__
from praxis.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_version_is_2() -> None:
    assert __version__ == "2.0.0"


def test_cli_version_is_machine_readable(capsys) -> None:
    assert main(["version", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "code": "OK",
        "data": {"version": "2.0.0"},
        "diagnostics": [],
    }


def test_cli_version_is_human_readable(capsys) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out == "2.0.0\n"


def test_clean_room_tree_contains_only_v2_architecture() -> None:
    for path in (
        ROOT / "profiles",
        ROOT / "capabilities",
        ROOT / "extensions",
        ROOT / "rules",
        ROOT / "runtime",
        ROOT / "src" / "praxis" / "profiles",
        ROOT / "src" / "praxis" / "capabilities",
        ROOT / "src" / "praxis" / "legacy",
    ):
        assert not path.exists()
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
    ):
        assert (ROOT / "src" / "praxis" / package).is_dir()
