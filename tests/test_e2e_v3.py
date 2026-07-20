from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from praxis.agents.service import AgentSessionService
from praxis.artifacts.service import ArtifactService
from praxis.context.service import ContextBuildRequest, ContextCompiler
from praxis.domain.requirement import RequirementStatus
from praxis.gates.commit_message import validate_commit_message
from praxis.knowledge.requirements import RequirementService
from praxis.portraits.service import PortraitService
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService
from praxis.worktree.lifecycle import WorktreeLifecycle
from praxis.worktree.service import WorktreeService


@pytest.mark.skipif(
    shutil.which("wt") is None or shutil.which("codegraph") is None,
    reason="真实闭环需要 Worktrunk 与 CodeGraph",
)
def test_real_requirement_to_agent_artifact_loop(tmp_path: Path) -> None:
    repo = tmp_path / "backend"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "praxis@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Praxis Test"], cwd=repo, check=True)
    (repo / "app.py").write_text("def total(values):\n    return sum(values)\n")
    subprocess.run(["git", "add", "app.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "chore: initialize fixture"], cwd=repo, check=True)

    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[
            Project(
                "backend",
                "python",
                "backend",
                "main",
                lint_commands=("python -m py_compile app.py",),
                test_commands=("python -c 'assert True'",),
            )
        ],
    )
    requirements = RequirementService(tmp_path)
    requirement_id = requirements.create(
        "合计逻辑优化", "优化合计逻辑并完成验证", ["demo"], []
    ).data["requirement_id"]
    requirement_path = next((tmp_path / "知识库" / "需求").rglob(f"*{requirement_id}"))
    (requirement_path / "调查分析.md").write_text("# 调查分析\n\n已确认合计逻辑影响范围。\n")
    (requirement_path / "实施计划.md").write_text("# 实施计划\n\n修改函数并运行质量与测试门禁。\n")
    for status in (
        RequirementStatus.INVESTIGATING,
        RequirementStatus.ANALYZED,
        RequirementStatus.PLANNED,
        RequirementStatus.READY,
    ):
        assert requirements.transition(requirement_id, status).ok

    hooks = WorktreeService(tmp_path).install_hooks("backend")
    assert hooks.ok
    subprocess.run(["git", "add", ".config/wt.toml"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: install Praxis lifecycle hooks"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    PortraitService(tmp_path).scan("backend")
    created = WorktreeService(tmp_path).create_for_requirement(
        requirement_id, "backend", "backend"
    )
    assert created.ok, created.to_dict()
    worktree = Path(created.data["path"])
    assert worktree.is_dir()
    hook_context = {
        "branch": created.data["branch"],
        "repo_path": str(repo),
        "worktree_path": str(worktree),
    }
    lifecycle = WorktreeLifecycle(tmp_path)
    assert lifecycle.run("worktree-pre-start", hook_context).ok
    initialized = lifecycle.run("worktree-post-start", hook_context)
    assert initialized.ok, initialized.to_dict()

    (worktree / "app.py").write_text(
        "def total(values):\n    return sum(value for value in values if value is not None)\n"
    )
    pre_commit = lifecycle.run("pre-commit", hook_context)
    assert pre_commit.ok, pre_commit.to_dict()
    pre_merge = lifecycle.run("pre-merge", hook_context)
    assert pre_merge.ok, pre_merge.to_dict()

    context = ContextCompiler(tmp_path).build(
        ContextBuildRequest(
            requirement_id,
            "backend",
            "backend",
            "coder",
            allowed_paths=("app.py",),
        )
    )
    session = AgentSessionService(tmp_path).start(
        "codex",
        "coder",
        requirement_id,
        context.data["context_id"],
        created.data["branch"],
        ["requirement.read", "artifact.register"],
    )
    assert session.ok
    assert AgentSessionService(tmp_path).render(session.data["session_id"]).ok
    report = tmp_path / "verification.txt"
    report.write_text("代码质量与测试门禁通过\n")
    artifact = ArtifactService(tmp_path).add(
        requirement_id, "test-report", report, stage="verify"
    )

    assert artifact.ok
    (requirement_path / "验收结论.md").write_text(
        "# 验收结论\n\n功能、质量、测试和影响范围复核均通过。\n"
    )
    message = (
        f"feat(praxis): [{requirement_id}] 优化合计逻辑\n\n"
        f"Praxis-Requirement: {requirement_id}\n"
        "Praxis-Stage: backend\n"
    )
    assert validate_commit_message(message=message).ok
    subprocess.run(["git", "add", "app.py"], cwd=worktree, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=worktree, check=True)
    assert AgentSessionService(tmp_path).finish(session.data["session_id"]).ok
    merged = WorktreeService(tmp_path).merge("main", branch=created.data["branch"])
    assert merged.ok, merged.to_dict()
    assert "value is not None" in (repo / "app.py").read_text()
    for status in (
        RequirementStatus.IN_PROGRESS,
        RequirementStatus.VERIFYING,
        RequirementStatus.COMPLETED,
    ):
        assert requirements.transition(requirement_id, status).ok
    assert StateStore(tmp_path).verify_audit_chain()
