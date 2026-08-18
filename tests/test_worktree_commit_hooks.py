from __future__ import annotations

from pathlib import Path

from praxis.knowledge.requirements import RequirementService
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService
from praxis.worktree.service import WorktreeService, detect_commit_hooks


def test_detect_husky_pre_commit(tmp_path: Path) -> None:
    hooks = tmp_path / ".husky"
    hooks.mkdir()
    (hooks / "pre-commit").write_text("lint-staged\n", encoding="utf-8")

    detected = detect_commit_hooks(tmp_path)

    assert "husky-pre-commit" in detected["detected"]
    assert "提交" in detected["note"]


def test_detect_pre_commit_framework_config(tmp_path: Path) -> None:
    (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")

    detected = detect_commit_hooks(tmp_path)

    assert "pre-commit-framework" in detected["detected"]


def test_detect_git_hook_and_lint_staged(tmp_path: Path) -> None:
    git_hooks = tmp_path / ".git" / "hooks"
    git_hooks.mkdir(parents=True)
    (git_hooks / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"lint-staged": {"*": "eslint"}}', encoding="utf-8"
    )

    detected = detect_commit_hooks(tmp_path)

    assert "git-pre-commit" in detected["detected"]
    assert "lint-staged" in detected["detected"]


def test_detect_returns_empty_when_no_hooks(tmp_path: Path) -> None:
    detected = detect_commit_hooks(tmp_path)

    assert detected["detected"] == []
    assert detected["note"]


def test_ensure_output_includes_commit_hooks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "backend"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[Project("backend", "python", "backend", "main")],
    )
    requirement = RequirementService(tmp_path).create(
        "钩子登记", "ensure 输出提交触发项", ["demo"], []
    )
    requirement_id = requirement.data["requirement_id"]

    workspace_repo = tmp_path / ".worktrees" / f"{requirement_id}__钩子登记" / "backend"
    (workspace_repo / ".husky").mkdir(parents=True)
    (workspace_repo / ".husky" / "pre-commit").write_text(
        "lint-staged\n", encoding="utf-8"
    )
    StateStore(tmp_path).set(
        "worktree",
        f"WT-{requirement_id}--backend",
        {
            "binding_id": f"WT-{requirement_id}--backend",
            "requirement_id": requirement_id,
            "repository_id": "backend",
            "branch": f"praxis/{requirement_id}",
            "path": str(workspace_repo.parent),
            "repository_path": str(workspace_repo),
            "status": "active",
        },
    )

    service = WorktreeService(tmp_path)
    preview = service.preview_for_requirement(requirement_id, ["backend"])
    assert preview.ok

    def fake_create(self, req_id, repository_id, stage):
        return Result(True, data={"binding_id": f"WT-{req_id}--{repository_id}"})

    from praxis.result import Result

    monkeypatch.setattr(WorktreeService, "create_for_requirement", fake_create)

    ensured = service.ensure_for_requirement(
        requirement_id, ["backend"], preview_id=preview.data["preview_id"]
    )

    assert ensured.ok
    item = ensured.data["items"][0]
    assert item["ok"]
    assert "husky-pre-commit" in item["commit_hooks"]["detected"]
