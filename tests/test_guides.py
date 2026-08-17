from __future__ import annotations

import json
from pathlib import Path

import pytest

from praxis.cli import main
from praxis.workspace.service import WorkspaceService


def _init_workspace(tmp_path: Path) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")


def test_guide_without_scenario_reports_current_step(tmp_path: Path, capsys) -> None:
    _init_workspace(tmp_path)

    assert main(["--root", str(tmp_path), "guide"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["workspace_id"] == "demo"
    assert "尚未登记需求" in out["current_step"]


def test_guide_scenario_returns_steps(tmp_path: Path, capsys) -> None:
    _init_workspace(tmp_path)

    assert main(["--root", str(tmp_path), "guide", "--scenario", "new-requirement"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scenario"] == "new-requirement"
    steps = out["steps"]
    assert any("requirement new" in command for _, command in steps)


def test_guide_invalid_scenario_is_rejected_by_parser(tmp_path: Path) -> None:
    _init_workspace(tmp_path)

    with pytest.raises(SystemExit) as exc:
        main(["--root", str(tmp_path), "guide", "--scenario", "nope"])
    assert exc.value.code == 2


def test_errors_without_code_lists_catalog(tmp_path: Path, capsys) -> None:
    _init_workspace(tmp_path)

    assert main(["--root", str(tmp_path), "errors"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["count"] > 0
    assert "REQUIREMENT_NOT_FOUND" in out["entries"]


def test_errors_lookup_known_code_returns_hint_and_next_step(
    tmp_path: Path, capsys
) -> None:
    _init_workspace(tmp_path)

    assert main(["--root", str(tmp_path), "errors", "REQUIREMENT_NOT_FOUND"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["code"] == "REQUIREMENT_NOT_FOUND"
    assert "hint" in out
    assert "next_step" in out


def test_error_output_includes_hint_and_next_step(tmp_path: Path, capsys) -> None:
    _init_workspace(tmp_path)

    assert main(["--root", str(tmp_path), "requirement", "advance", "NOPE"]) == 2
    err = capsys.readouterr().out
    assert "REQUIREMENT_NOT_FOUND" in err
    assert "提示" in err
    assert "下一步" in err
