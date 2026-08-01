from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from praxis.agents.guidance import AgentGuidanceService
from praxis.application import PraxisApplication
from praxis.artifacts.service import ArtifactService
from praxis.cli import _operation, _parser
from praxis.context.service import ContextBuildRequest, ContextCompiler
from praxis.knowledge.requirements import RequirementService
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService
from praxis.worktree.lifecycle import WorktreeLifecycle


def _workspace_with_requirement(root: Path) -> str:
    repository = root / "backend"
    repository.mkdir()
    WorkspaceService(root).init(
        "demo",
        "演示工作空间",
        projects=[Project("backend", "python", "backend", "main")],
    )
    return RequirementService(root).create(
        "流程摩擦优化",
        "优化工作流入口与隔离门禁",
        ["demo"],
        [],
    ).data["requirement_id"]


def test_context_injects_cli_fallback_and_root_edit_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requirement_id = _workspace_with_requirement(tmp_path)
    monkeypatch.setattr(
        "praxis.entrypoints.shutil.which",
        lambda command: "/usr/local/bin/praxis" if command == "praxis" else None,
    )

    result = ContextCompiler(tmp_path).build(
        ContextBuildRequest(
            requirement_id=requirement_id,
            project_id="backend",
            stage="development",
            agent_role="coder",
            entrypoint="cli",
        )
    )

    assert result.ok
    assert any(item["fragment_id"] == "praxis-entrypoint" for item in result.data["sources"])
    facts = result.data["critical_facts"]
    assert facts["entrypoints"]["current"]["kind"] == "CLI"
    assert facts["entrypoints"]["current"]["path"] == "/usr/local/bin/praxis"
    assert facts["edit_boundary"] == {
        "binding_required": True,
        "root_worktree_edits_blocked": True,
        "pre_commit_guard": "lifecycle pre-commit",
    }
    assert "当前 Praxis 入口：CLI（/usr/local/bin/praxis）" in Path(
        result.data["path"]
    ).read_text()


def test_doctor_reports_cli_and_mcp_entrypoint_diagnostics(tmp_path: Path) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")

    cli = PraxisApplication(tmp_path).execute("doctor", {"entrypoint": "cli"})

    assert cli.ok
    assert cli.data["entrypoints"]["current"]["kind"] == "CLI"
    assert "cli" in cli.data["entrypoints"]
    assert "mcp" in cli.data["entrypoints"]


def test_mcp_doctor_is_available_as_an_unscoped_read(tmp_path: Path) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")

    from praxis.mcp.server import execute

    result = execute(tmp_path, "doctor", {})

    assert result["ok"] is True
    assert result["data"]["entrypoints"]["current"]["kind"] == "MCP"


def test_cli_exposes_binding_and_complete_node_syntax(capsys: pytest.CaptureFixture[str]) -> None:
    args = _parser().parse_args(
        [
            "artifact",
            "add",
            "--requirement",
            "REQ-1",
            "--type",
            "test-report",
            "--source",
            "report.txt",
            "--stage",
            "verify",
            "--binding",
            "WT-REQ-1--backend",
        ]
    )
    operation, values = _operation(args)
    assert operation == "artifact.add"
    assert values["binding_id"] == "WT-REQ-1--backend"

    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["lifecycle", "complete-node", "--help"])
    assert "--used-skill 'skill-id=passed:结果说明'" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        parser.parse_args(["skill", "complete-node", "--help"])
    assert "--used-skill 'skill-id=passed:结果说明'" in capsys.readouterr().out


def test_guidance_documents_cli_fallback_guard_and_skill_value_syntax(
    tmp_path: Path,
) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")

    result = AgentGuidanceService(tmp_path).render()

    assert result.ok
    guidance = (tmp_path / "AGENTS.md").read_text()
    assert "praxis doctor --json" in guidance
    assert "请走 praxis 工作树" in guidance
    assert "--used-skill 'skill-id=passed:结果说明'" in guidance


def test_root_business_changes_require_a_worktree_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "backend"
    repository.mkdir()
    WorkspaceService(
        tmp_path
    ).init(
        "demo",
        "演示工作空间",
        projects=[Project("backend", "python", "backend", "main")],
    )
    lifecycle_module = __import__("praxis.worktree.lifecycle", fromlist=["ProcessRunner"])

    class ChangedFilesRunner:
        def __init__(self, cwd: Path, **kwargs: object):
            assert cwd == repository

        def run(self, command: list[str], *, machine_output: bool) -> Result:
            if command[1] == "diff":
                return Result(True, data={"stdout": "src/service.py\n"})
            return Result(True, data={"stdout": ""})

    monkeypatch.setattr(lifecycle_module, "ProcessRunner", ChangedFilesRunner)
    result = WorktreeLifecycle(tmp_path).run(
        "pre-commit",
        {
            "branch": "main",
            "repo_path": str(repository),
            "worktree_path": str(repository),
        },
    )

    assert result.code == "WORKTREE_BINDING_REQUIRED"
    assert result.data["blocked_paths"] == ["src/service.py"]
    assert "请走 praxis 工作树" in result.data["message"]


def test_artifact_add_accepts_a_new_file_inside_bound_worktree(tmp_path: Path) -> None:
    requirement_id = _workspace_with_requirement(tmp_path)
    repository = tmp_path.parent / f"{tmp_path.name}-bound-worktree"
    repository.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repository, check=True, capture_output=True)
    source = repository / "new-service.py"
    source.write_text("value = 1\n")
    binding_id = "WT-REQ-BOUND--backend"
    StateStore(tmp_path).set(
        "worktree",
        binding_id,
        {
            "binding_id": binding_id,
            "requirement_id": requirement_id,
            "repository_id": "backend",
            "repository_path": str(repository),
            "path": str(repository.parent),
            "status": "active",
        },
    )

    added = ArtifactService(tmp_path).add(
        requirement_id,
        "test-report",
        source,
        stage="verify",
        binding_id=binding_id,
    )

    assert added.ok
    assert added.data["source_path"] == str(source.resolve())
    assert added.data["binding_id"] == binding_id
    assert Path(added.data["archived_path"]).is_file()


def test_requirement_plan_contains_a_verification_matrix_template(tmp_path: Path) -> None:
    _workspace_with_requirement(tmp_path)
    plan = next(tmp_path.rglob("03-实施计划.md")).read_text()

    assert "验证矩阵（计划阶段确认）" in plan
    assert "可自动化" in plan
    assert "需环境" in plan
    assert "授权状态" in plan


def test_short_name_length_error_reports_actual_count(tmp_path: Path) -> None:
    policy = __import__(
        "praxis.naming.requirement", fromlist=["RequirementPathPolicy"]
    ).RequirementPathPolicy(tmp_path)

    with pytest.raises(ValueError, match=r"当前为27个字符"):
        policy.validate_short_name("流程工作流优化建议" * 3)
