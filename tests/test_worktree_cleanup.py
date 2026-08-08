from __future__ import annotations

import subprocess
from pathlib import Path

from praxis.context.service import ContextBuildRequest, ContextCompiler
from praxis.knowledge.requirements import RequirementService
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService
from praxis.worktree.service import WorktreeService


def _init_workspace(root: Path) -> str:
    repo = root / "backend"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    WorkspaceService(root).init(
        "demo",
        "演示工作空间",
        projects=[Project("backend", "python", "backend", "main")],
    )
    requirement = RequirementService(root).create(
        "清理验证",
        "验证需求派生资源清理",
        ["demo"],
        [],
    )
    return requirement.data["requirement_id"]


def _bind_worktree(
    root: Path,
    requirement_id: str,
    *,
    branch: str | None = None,
    status: str = "active",
) -> tuple[Path, Path]:
    workspace_path = root / ".worktrees" / f"{requirement_id}__清理验证"
    repository_path = workspace_path / "backend"
    repository_path.mkdir(parents=True)
    branch = branch or f"praxis/{requirement_id}"
    store = StateStore(root)
    store.set(
        "worktree",
        f"WT-{requirement_id}--backend",
        {
            "binding_id": f"WT-{requirement_id}--backend",
            "requirement_id": requirement_id,
            "repository_id": "backend",
            "branch": branch,
            "path": str(workspace_path),
            "repository_path": str(repository_path),
            "status": status,
        },
    )
    return workspace_path, repository_path


def _build_context(root: Path, requirement_id: str) -> str:
    compiler = ContextCompiler(root)
    result = compiler.build(
        ContextBuildRequest(
            requirement_id=requirement_id,
            project_id="backend",
            stage="backend",
            agent_role="coder",
            token_budget=8_000,
            allowed_paths=("src/**",),
            forbidden_paths=(".env",),
        )
    )
    assert result.ok
    return result.data["context_id"]


def _cleanup_result(root: Path, requirement_id: str, *, dry_run: bool) -> dict:
    return WorktreeService(root).cleanup_for_requirement(
        requirement_id, dry_run=dry_run
    ).data


def test_cleanup_dry_run_previews_without_deleting(tmp_path: Path) -> None:
    requirement_id = _init_workspace(tmp_path)
    workspace_path, _ = _bind_worktree(tmp_path, requirement_id)
    context_id = _build_context(tmp_path, requirement_id)

    def run(command, cwd, environment):
        if command[:3] == ["git", "branch", "--merged"]:
            return subprocess.CompletedProcess(
                command, 0, f"  praxis/{requirement_id}\n", ""
            )
        raise AssertionError(command)

    result = WorktreeService(tmp_path, run=run).cleanup_for_requirement(
        requirement_id, dry_run=True
    )

    assert result.ok
    assert result.data["dry_run"] is True
    assert len(result.data["worktrees"]) == 1
    assert result.data["worktrees"][0]["action"] == "remove"
    assert len(result.data["contexts"]) == 1
    assert result.data["contexts"][0]["context_id"] == context_id
    # Nothing deleted in dry-run
    assert workspace_path.exists()
    assert StateStore(tmp_path).get("worktree", f"WT-{requirement_id}--backend")
    assert (tmp_path / "生成内容" / "上下文包" / f"{context_id}.md").exists()


def test_cleanup_removes_worktree_branch_binding_and_contexts(tmp_path: Path) -> None:
    requirement_id = _init_workspace(tmp_path)
    workspace_path, repository_path = _bind_worktree(tmp_path, requirement_id)
    context_id = _build_context(tmp_path, requirement_id)

    calls: list[list[str]] = []

    def run(command, cwd, environment):
        calls.append(command)
        if command[0] == "wt":
            repository_path.rmdir()
            return subprocess.CompletedProcess(
                command, 0, '{"items": [{"branch_deleted": true}]}', ""
            )
        if command[:3] == ["git", "branch", "--merged"]:
            return subprocess.CompletedProcess(
                command, 0, f"  praxis/{requirement_id}\n", ""
            )
        if command[:3] == ["git", "branch", "--list"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    result = WorktreeService(tmp_path, run=run).cleanup_for_requirement(
        requirement_id, dry_run=False
    )

    assert result.ok
    assert not workspace_path.exists()
    assert StateStore(tmp_path).get("worktree", f"WT-{requirement_id}--backend") is None
    assert not (tmp_path / "生成内容" / "上下文包" / f"{context_id}.md").exists()
    assert StateStore(tmp_path).get("context", context_id) is None
    events = [e["event"] for e in StateStore(tmp_path).audit_events()]
    assert "worktree.cleaned" in events
    assert "context.cleaned" in events


def test_cleanup_only_touches_matching_requirement(tmp_path: Path) -> None:
    requirement_id = _init_workspace(tmp_path)
    other_id = RequirementService(tmp_path).create(
        "其他需求",
        "不应被清理",
        ["demo"],
        [],
    ).data["requirement_id"]
    _, repo_a = _bind_worktree(tmp_path, requirement_id)
    workspace_b, _ = _bind_worktree(tmp_path, other_id)
    context_id = _build_context(tmp_path, requirement_id)
    _build_context(tmp_path, other_id)

    def run(command, cwd, environment):
        if command[0] == "wt":
            repo_a.rmdir()
            return subprocess.CompletedProcess(
                command, 0, '{"items": [{"branch_deleted": true}]}', ""
            )
        if command[:3] == ["git", "branch", "--merged"]:
            return subprocess.CompletedProcess(
                command, 0, f"  praxis/{requirement_id}\n", ""
            )
        if command[:3] == ["git", "branch", "--list"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    result = WorktreeService(tmp_path, run=run).cleanup_for_requirement(
        requirement_id, dry_run=False
    )

    assert result.ok
    assert workspace_b.exists(), "other requirement worktree must be untouched"
    assert StateStore(tmp_path).get("worktree", f"WT-{other_id}--backend")
    assert (tmp_path / "生成内容" / "上下文包" / f"{context_id}.md")  # only for REQ-A cleaned
    other_contexts = [
        item
        for item in StateStore(tmp_path).list_scope("context")
        if item["requirement_id"] == other_id
    ]
    assert other_contexts, "other requirement contexts must remain"


def test_cleanup_skips_binding_with_unmerged_branch(tmp_path: Path) -> None:
    requirement_id = _init_workspace(tmp_path)
    _, repository_path = _bind_worktree(tmp_path, requirement_id)

    def run(command, cwd, environment):
        if command[0] == "wt":
            return subprocess.CompletedProcess(
                command, 0, '{"items": [{"branch": "praxis/' + requirement_id + '"}]}', ""
            )
        if command[:3] == ["git", "branch", "--merged"]:
            return subprocess.CompletedProcess(command, 0, "  main\n", "")
        if command[:3] == ["git", "branch", "--list"]:
            return subprocess.CompletedProcess(command, 0, f"  praxis/{requirement_id}\n", "")
        raise AssertionError(command)

    result = WorktreeService(tmp_path, run=run).cleanup_for_requirement(
        requirement_id, dry_run=False
    )

    assert result.ok
    assert len(result.data["worktrees"]) == 1
    assert result.data["worktrees"][0]["action"] == "blocked"
    assert "unmerged" in result.data["worktrees"][0]["reason"]
    assert repository_path.exists()
    assert StateStore(tmp_path).get("worktree", f"WT-{requirement_id}--backend")
