from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import praxis.fastlane.small_fix as small_fix_module
from praxis.domain.requirement import RequirementStatus
from praxis.fastlane.service import FastLaneService
from praxis.fastlane.small_fix import SmallFixService
from praxis.guides.errors import lookup
from praxis.knowledge.requirements import RequirementService
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService

from tests.test_small_fix import FakeWorktrees, FakeRunner, _workspace


def _fake_route(*args, **kwargs):
    """测试用：绕开真实 skill 路由（环境缺 provider），返回最小成功路由。"""
    from praxis.result import Result

    return Result(
        True,
        data={
            "route_fingerprint": "test-fingerprint",
            "execution_principles": [],
            "decisions": [],
        },
    )


@pytest.fixture
def small_fix(tmp_path: Path, monkeypatch) -> tuple[SmallFixService, str, Path]:
    requirement_id, repository = _workspace(tmp_path)
    FakeWorktrees.calls = []
    FakeRunner.calls = []
    FakeRunner.results = []
    monkeypatch.setattr(small_fix_module, "WorktreeService", FakeWorktrees)
    monkeypatch.setattr(small_fix_module, "ProcessRunner", FakeRunner)
    monkeypatch.setattr(small_fix_module.shutil, "which", lambda name: "/usr/bin/rtk")
    monkeypatch.setattr(small_fix_module.NodeSkillRouter, "route", staticmethod(_fake_route))
    return SmallFixService(tmp_path), requirement_id, repository


def test_small_fix_start_reopens_completed_requirement(
    small_fix: tuple[SmallFixService, str, Path],
) -> None:
    """P0：completed 状态经 fix start 自动回退 in_progress（带原因审计）。"""
    service, requirement_id, _ = small_fix
    store = StateStore(service.root)
    for status in (
        RequirementStatus.IN_PROGRESS,
        RequirementStatus.IMPLEMENTED,
        RequirementStatus.VERIFYING,
        RequirementStatus.COMPLETED,
    ):
        store.transition_requirement(requirement_id, status)

    started = service.start(requirement_id, repository_id="web", small=True)

    assert started.ok
    requirement = store.requirement(requirement_id)
    assert requirement["status"] == "in_progress"
    reopened_events = [
        item for item in store.audit_events() if item["event"] == "requirement.reopened"
    ]
    assert reopened_events
    assert reopened_events[-1].get("details", {}).get("from") == "completed"


def test_small_fix_start_reuses_existing_worktree(
    small_fix: tuple[SmallFixService, str, Path],
) -> None:
    """P1：--worktree 复用既有绑定工作树，跳过新建。"""
    service, requirement_id, repository = small_fix
    store = StateStore(service.root)
    # 预置一个既有绑定
    store.set(
        "worktree",
        f"WT-{requirement_id}--web",
        {
            "binding_id": f"WT-{requirement_id}--web",
            "requirement_id": requirement_id,
            "repository_id": "web",
            "repository_path": str(repository),
            "path": str(repository),
            "branch": f"praxis/{requirement_id}",
            "status": "active",
        },
    )

    started = service.start(
        requirement_id,
        repository_id="web",
        small=True,
        worktree_binding=f"WT-{requirement_id}--web",
    )

    assert started.ok
    assert started.code == "SMALL_FIX_STARTED"
    assert started.data["worktree_path"] == str(repository.resolve())
    # 复用时不新建
    assert FakeWorktrees.calls == []


def test_small_fix_start_rejects_worktree_repository_mismatch(
    small_fix: tuple[SmallFixService, str, Path],
) -> None:
    """P1：--worktree 复用但 repository 不一致时报错。"""
    service, requirement_id, repository = small_fix
    store = StateStore(service.root)
    store.set(
        "worktree",
        f"WT-{requirement_id}--other",
        {
            "binding_id": f"WT-{requirement_id}--other",
            "requirement_id": requirement_id,
            "repository_id": "other",
            "repository_path": str(repository),
            "path": str(repository),
            "branch": f"praxis/{requirement_id}",
            "status": "active",
        },
    )

    result = service.start(
        requirement_id,
        repository_id="web",
        small=True,
        worktree_binding=f"WT-{requirement_id}--other",
    )

    assert not result.ok
    assert result.code == "SMALL_FIX_WORKTREE_REPOSITORY_MISMATCH"


def test_typecheck_not_configured_has_recovery_hint(
    tmp_path: Path,
) -> None:
    """P1：FAST_LANE_TYPECHECK_NOT_CONFIGURED 的 data 携带恢复动作。"""
    from praxis.fastlane.small_fix import SmallFixService

    # 无 typecheck_commands 的 workspace
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repository, check=True)
    (repository / "src").mkdir()
    (repository / "src" / "mapping.ts").write_text("export const value = 1;\n")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repository, check=True)
    WorkspaceService(tmp_path).init(
        "demo",
        "演示",
        projects=[Project("web", "frontend", "repo", "main", system_id="demo")],
    )
    store = StateStore(tmp_path)
    requirement = store.create_requirement("小修复", "修复字段映射", ["demo"], [])
    for status in (
        RequirementStatus.INVESTIGATING,
        RequirementStatus.ANALYZED,
        RequirementStatus.PLANNED,
        RequirementStatus.READY,
    ):
        store.transition_requirement(requirement["requirement_id"], status)

    service = SmallFixService(tmp_path)
    result = service.start(
        requirement["requirement_id"], repository_id="web", small=True
    )

    assert not result.ok
    assert result.code == "FAST_LANE_TYPECHECK_NOT_CONFIGURED"
    assert "typecheck_commands" in result.data.get("hint", "")


def test_errors_catalog_covers_fastlane_codes() -> None:
    """P2：全部 FAST_LANE_* / SMALL_FIX_* 错误码在 errors 目录可查。"""
    used: set[str] = set()
    for path in Path("src/praxis").rglob("*.py"):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in __import__("re").finditer(
            r'"(FAST_LANE_[A-Z_]+|SMALL_FIX_[A-Z_]+)"', content
        ):
            used.add(match.group(1))
    for code in sorted(used):
        result = lookup(code)
        assert result.ok, f"{code} 不在 errors 目录"
        assert result.data.get("next_step"), f"{code} 缺 next_step"


def test_errors_catalog_reopen_completed_has_recovery() -> None:
    """P2：REQUIREMENT_REOPEN_STATUS_INVALID 指引含 completed 回退动作。"""
    result = lookup("REQUIREMENT_REOPEN_STATUS_INVALID")
    assert result.ok
    assert "--from" in result.data.get("next_step", "")


def test_doctor_warns_missing_typecheck_for_typed_repository(
    tmp_path: Path,
) -> None:
    """P1：doctor 对强类型仓库缺 typecheck_commands 输出 warning。"""
    from praxis.application import PraxisApplication

    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repository, check=True)
    (repository / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repository, check=True)
    WorkspaceService(tmp_path).init(
        "demo",
        "演示",
        projects=[Project("backend", "java-maven", "repo", "main", system_id="demo")],
    )

    result = PraxisApplication(tmp_path).execute("doctor", {})

    assert result.ok
    warnings = result.data.get("warnings", [])
    assert any("typecheck_commands" in w for w in warnings)


def test_cli_reopen_accepts_completed_from_choice(tmp_path: Path) -> None:
    """P0：CLI `requirement reopen --from completed` 是合法选择。"""
    from praxis.cli import main

    WorkspaceService(tmp_path).init("demo", "演示")
    requirements = RequirementService(tmp_path)
    created = requirements.create("完工回退", "completed 回开发", [], [])
    requirement_id = created.data["requirement_id"]
    store = StateStore(tmp_path)
    for status in (
        RequirementStatus.INVESTIGATING,
        RequirementStatus.ANALYZED,
        RequirementStatus.PLANNED,
        RequirementStatus.READY,
        RequirementStatus.IN_PROGRESS,
        RequirementStatus.IMPLEMENTED,
        RequirementStatus.VERIFYING,
        RequirementStatus.COMPLETED,
    ):
        store.transition_requirement(requirement_id, status)

    # --from completed 是合法选择：不应被 argparse 拒绝（应用层已支持回退）
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "requirement",
                "reopen",
                requirement_id,
                "--reason",
                "完工后缺陷",
                "--from",
                "completed",
            ]
        )
        == 0
    )
