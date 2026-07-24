from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import praxis.fastlane.small_fix as small_fix_module
from praxis.domain.requirement import RequirementStatus
from praxis.fastlane.small_fix import SmallFixService
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService


def _workspace(
    root: Path,
    *,
    typecheck_command: str = "pnpm run type-check {files}",
) -> tuple[str, Path]:
    repository = root / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
    (repository / "src").mkdir()
    (repository / "src" / "mapping.ts").write_text("export const value = 1;\n")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repository, check=True)
    WorkspaceService(root).init(
        "demo",
        "演示",
        projects=[
            Project(
                "web",
                "frontend",
                "repo",
                "main",
                system_id="demo",
                template_branches=("main",),
                typecheck_commands=(typecheck_command,),
            )
        ],
    )
    store = StateStore(root)
    requirement = store.create_requirement("已有小修复", "修复字段映射", ["demo"], [])
    for status in (
        RequirementStatus.INVESTIGATING,
        RequirementStatus.ANALYZED,
        RequirementStatus.PLANNED,
        RequirementStatus.READY,
    ):
        store.transition_requirement(requirement["requirement_id"], status)
    return str(requirement["requirement_id"]), repository


class FakeWorktrees:
    calls: list[dict[str, object]] = []

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def resolve_template_revision(self, repository_id: str) -> Result:
        return Result(
            True,
            "WORKTREE_TEMPLATE_REVISION_RESOLVED",
            data={"repository_id": repository_id, "revision": "abc123"},
        )

    def create_for_requirement(
        self,
        requirement_id: str,
        repository_id: str,
        stage: str | None = None,
        *,
        base_revision: str | None = None,
    ) -> Result:
        type(self).calls.append(
            {
                "requirement_id": requirement_id,
                "repository_id": repository_id,
                "base_revision": base_revision,
            }
        )
        repository = self.root / "repo"
        binding = {
            "binding_id": f"WT-{requirement_id}--{repository_id}",
            "requirement_id": requirement_id,
            "repository_id": repository_id,
            "repository_path": str(repository),
            "path": str(repository),
            "branch": f"praxis/{requirement_id}",
            "base_revision": base_revision,
            "status": "active",
        }
        StateStore(self.root).set("worktree", binding["binding_id"], binding)
        return Result(True, data=binding)


class FakeRunner:
    calls: list[list[str]] = []
    results: list[Result] = []

    def __init__(self, cwd: Path | str, **kwargs):
        self.cwd = Path(cwd)

    def run(self, command: list[str], *, machine_output: bool) -> Result:
        type(self).calls.append(command)
        return type(self).results.pop(0)


@pytest.fixture
def small_fix(tmp_path: Path, monkeypatch) -> tuple[SmallFixService, str, Path]:
    requirement_id, repository = _workspace(tmp_path)
    FakeWorktrees.calls = []
    FakeRunner.calls = []
    FakeRunner.results = []
    monkeypatch.setattr(small_fix_module, "WorktreeService", FakeWorktrees)
    monkeypatch.setattr(small_fix_module, "ProcessRunner", FakeRunner)
    monkeypatch.setattr(small_fix_module.shutil, "which", lambda name: "/usr/bin/rtk")
    return SmallFixService(tmp_path), requirement_id, repository


def test_small_fix_start_reuses_requirement_and_fixed_template_revision(
    small_fix: tuple[SmallFixService, str, Path],
) -> None:
    service, requirement_id, repository = small_fix

    started = service.start(requirement_id, repository_id="web", small=True)

    assert started.ok
    assert started.code == "SMALL_FIX_STARTED"
    assert started.data["requirement_id"] == requirement_id
    assert started.data["profile"] == "small-fix-v2"
    assert started.data["template_sha"] == "abc123"
    assert started.data["typecheck_mode"] == "scoped"
    assert StateStore(service.root).requirement(requirement_id)["status"] == "in_progress"
    assert FakeWorktrees.calls == [
        {
            "requirement_id": requirement_id,
            "repository_id": "web",
            "base_revision": "abc123",
        }
    ]
    assert subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout == ""


def test_small_fix_start_reopens_verifying_requirement(
    small_fix: tuple[SmallFixService, str, Path],
) -> None:
    service, requirement_id, _ = small_fix
    store = StateStore(service.root)
    for status in (
        RequirementStatus.IN_PROGRESS,
        RequirementStatus.IMPLEMENTED,
        RequirementStatus.VERIFYING,
    ):
        store.transition_requirement(requirement_id, status)

    started = service.start(requirement_id, repository_id="web", small=True)

    assert started.ok
    requirement = store.requirement(requirement_id)
    assert requirement["status"] == "in_progress"
    assert any(
        item["event"] == "requirement.reopened"
        for item in store.audit_events()
    )


def test_small_fix_finish_runs_scoped_verification_and_registers_one_diff_artifact(
    small_fix: tuple[SmallFixService, str, Path],
) -> None:
    service, requirement_id, repository = small_fix
    assert service.start(requirement_id, repository_id="web", small=True).ok
    (repository / "src" / "mapping.ts").write_text("export const value = 2;\n")
    (repository / "src" / "mapping.test.ts").write_text("test('mapping', () => {});\n")
    FakeRunner.results = [
        Result(True, data={"raw_log": "green.log"}),
        Result(True, data={"raw_log": "diff.log"}),
        Result(True, data={"raw_log": "type.log"}),
    ]

    finished = service.finish(
        requirement_id,
        test_command="pnpm vitest run src/mapping.test.ts",
    )

    assert finished.ok
    assert finished.code == "SMALL_FIX_IMPLEMENTED"
    assert finished.data["business_files"] == ["src/mapping.ts"]
    assert finished.data["changed_lines"] == 2
    assert FakeRunner.calls == [
        ["rtk", "test", "pnpm", "vitest", "run", "src/mapping.test.ts"],
        ["rtk", "git", "diff", "--check"],
        ["rtk", "proxy", "pnpm", "run", "type-check", "src/mapping.ts"],
    ]
    artifacts = StateStore(service.root).list_scope("artifact")
    assert len(artifacts) == 1
    assert artifacts[0]["metadata"]["business_files"] == ["src/mapping.ts"]
    assert artifacts[0]["metadata"]["code_change"]["diff"]
    assert {
        item["path"] for item in artifacts[0]["metadata"]["code_change"]["files"]
    } == {"src/mapping.test.ts", "src/mapping.ts"}


def test_small_fix_finish_downgrades_before_commands_when_diff_exceeds_80_lines(
    small_fix: tuple[SmallFixService, str, Path],
) -> None:
    service, requirement_id, repository = small_fix
    assert service.start(requirement_id, repository_id="web", small=True).ok
    (repository / "src" / "mapping.ts").write_text(
        "".join(f"export const value{index} = {index};\n" for index in range(81))
    )

    finished = service.finish(
        requirement_id,
        test_command="pnpm vitest run mapping.test.ts",
    )

    assert not finished.ok
    assert finished.code == "SMALL_FIX_DOWNGRADED"
    assert "80" in finished.data["downgrade_reason"]
    assert not FakeRunner.calls


def test_small_fix_baseline_mode_ignores_existing_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    requirement_id, repository = _workspace(
        tmp_path,
        typecheck_command="pnpm run type-check",
    )
    FakeWorktrees.calls = []
    FakeRunner.calls = []
    FakeRunner.results = [
        Result(
            False,
            data={
                "stdout": "src/legacy.ts(1,1): error TS1001: existing\n",
                "stderr": "",
                "raw_log": "baseline.log",
            },
        )
    ]
    monkeypatch.setattr(small_fix_module, "WorktreeService", FakeWorktrees)
    monkeypatch.setattr(small_fix_module, "ProcessRunner", FakeRunner)
    monkeypatch.setattr(small_fix_module.shutil, "which", lambda name: "/usr/bin/rtk")
    service = SmallFixService(tmp_path)

    started = service.start(requirement_id, repository_id="web", small=True)
    assert started.ok
    assert started.data["typecheck_mode"] == "baseline"
    (repository / "src" / "mapping.ts").write_text("export const value = 2;\n")
    FakeRunner.results = [
        Result(True, data={"raw_log": "green.log"}),
        Result(True, data={"raw_log": "diff.log"}),
        Result(
            False,
            data={
                "stdout": "src/legacy.ts(99,3): error TS1001: existing\n",
                "stderr": "",
                "raw_log": "type.log",
            },
        ),
    ]

    finished = service.finish(
        requirement_id,
        test_command="pnpm vitest run mapping.test.ts",
    )

    assert finished.ok
    assert finished.data["verification"]["typecheck"]["status"] == (
        "incremental_passed_baseline_failed"
    )


def test_small_fix_time_gate_warns_for_budget_and_ratio(
    small_fix: tuple[SmallFixService, str, Path],
) -> None:
    service, _, _ = small_fix

    warnings = service._time_warnings(121.0, 10.0)

    assert {item["code"] for item in warnings} == {
        "SMALL_FIX_GOVERNANCE_BUDGET_EXCEEDED",
        "SMALL_FIX_GOVERNANCE_RATIO_EXCEEDED",
    }


def test_small_fix_finish_retry_reuses_exact_approval_receipt(
    small_fix: tuple[SmallFixService, str, Path],
) -> None:
    service, requirement_id, repository = small_fix
    assert service.start(requirement_id, repository_id="web", small=True).ok
    (repository / "src" / "mapping.ts").write_text("export const value = 2;\n")
    FakeRunner.results = [Result(False, data={"raw_log": "red-green.log"})]

    failed = service.finish(
        requirement_id,
        test_command="pnpm vitest run mapping.test.ts",
    )

    assert not failed.ok
    assert failed.code == "SMALL_FIX_GREEN_FAILED"
    assert len(StateStore(service.root).list_scope("approval_receipt")) == 1
    FakeRunner.results = [
        Result(True, data={"raw_log": "green.log"}),
        Result(True, data={"raw_log": "diff.log"}),
        Result(True, data={"raw_log": "type.log"}),
    ]

    retried = service.finish(
        requirement_id,
        test_command="pnpm vitest run mapping.test.ts",
    )

    assert retried.ok
    assert len(StateStore(service.root).list_scope("approval_receipt")) == 1


def test_small_fix_scoped_typecheck_failure_has_specific_result_code(
    small_fix: tuple[SmallFixService, str, Path],
) -> None:
    service, requirement_id, repository = small_fix
    assert service.start(requirement_id, repository_id="web", small=True).ok
    (repository / "src" / "mapping.ts").write_text("export const value = 2;\n")
    FakeRunner.results = [
        Result(True, data={"raw_log": "green.log"}),
        Result(True, data={"raw_log": "diff.log"}),
        Result(False, data={"raw_log": "type.log"}),
    ]

    finished = service.finish(
        requirement_id,
        test_command="pnpm vitest run mapping.test.ts",
    )

    assert not finished.ok
    assert finished.code == "SMALL_FIX_SCOPED_TYPECHECK_FAILED"
