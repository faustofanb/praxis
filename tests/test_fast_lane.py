from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

import praxis.fastlane.service as fastlane_module
from praxis.fastlane.service import FastLaneService
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService


def _workspace(root: Path) -> Path:
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
                typecheck_commands=("pnpm run type-check",),
            )
        ],
    )
    return repository


class FakeWorktrees:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def preview_for_requirement(self, requirement_id: str, repository_ids) -> Result:
        preview = {
            "preview_id": "WTP-FAST",
            "requirement_id": requirement_id,
            "repositories": list(repository_ids),
            "items": [{"repository_id": repository_ids[0]}],
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
        StateStore(self.root).set("worktree_preview", "WTP-FAST", preview)
        return Result(True, "WORKTREE_PREVIEWED", data=preview)

    def ensure_for_requirement(self, requirement_id: str, repository_ids, *, preview_id) -> Result:
        repository = self.root / "repo"
        return Result(
            True,
            "WORKTREE_ENSURED",
            data={
                "preview_id": preview_id,
                "items": [
                    {
                        "repository_id": repository_ids[0],
                        "ok": True,
                        "code": "OK",
                        "data": {
                            "binding_id": f"WT-{requirement_id}--web",
                            "repository_id": "web",
                            "repository_path": str(repository),
                            "path": str(repository),
                            "stage": "development",
                            "allowed_paths": ["**"],
                            "forbidden_paths": [".git", ".praxis"],
                        },
                    }
                ],
            },
        )


class FakeRunner:
    calls: list[list[str]] = []
    results: list[Result] = []

    def __init__(self, cwd: Path | str, **kwargs):
        self.cwd = Path(cwd)

    def run(self, command: list[str], *, machine_output: bool) -> Result:
        type(self).calls.append(command)
        return type(self).results.pop(0)


@pytest.fixture
def fastlane(tmp_path: Path, monkeypatch) -> FastLaneService:
    _workspace(tmp_path)
    FakeRunner.calls = []
    FakeRunner.results = []
    monkeypatch.setattr(fastlane_module, "WorktreeService", FakeWorktrees)
    monkeypatch.setattr(fastlane_module, "ProcessRunner", FakeRunner)
    monkeypatch.setattr(fastlane_module.shutil, "which", lambda name: "/usr/bin/rtk")
    return FastLaneService(tmp_path)


def test_fast_start_registers_candidate_and_returns_preview(
    fastlane: FastLaneService,
) -> None:
    started = fastlane.start(
        short_name="字段映射修复",
        request="修复页面字段映射",
        systems=["demo"],
        domains=[],
        project_id="web",
        reproduction="打开列表即可复现",
        now=datetime(2026, 7, 24, tzinfo=UTC),
    )

    assert started.ok
    assert started.code == "FAST_LANE_CANDIDATE"
    assert started.data["preview_id"] == "WTP-FAST"
    assert started.data["status"] == "candidate"
    assert started.data["deadlines"]["locate"] == "2026-07-24T00:05:00+00:00"
    assert "一次性限定授权" in started.data["pending_confirmation"]


def test_fast_confirm_creates_exact_receipts_and_lazy_baseline(
    fastlane: FastLaneService,
) -> None:
    started = fastlane.start(
        short_name="字段映射修复",
        request="修复页面字段映射",
        systems=["demo"],
        domains=[],
        project_id="web",
        reproduction="打开列表即可复现",
    )
    FakeRunner.results = [
        Result(True, data={"stdout": "src/mapping.ts\n", "stderr": "", "raw_log": "tracked"}),
        Result(
            False,
            "COMMAND_FAILED",
            data={
                "stdout": "src/old.ts(1,1): error TS1001: existing\n",
                "stderr": "",
                "raw_log": "baseline.json",
            },
        ),
    ]

    confirmed = fastlane.confirm(
        started.data["requirement_id"],
        preview_id="WTP-FAST",
        business_files=["src/mapping.ts"],
        root_cause="字段映射使用了旧属性",
        evidence="src/mapping.ts 中读取 oldField",
        test_command="pnpm vitest run src/mapping.test.ts",
        expected_red="expected newField",
        risks=[],
        user_evidence="用户确认一次授权",
        authorized_by_user=True,
    )

    assert confirmed.ok
    assert confirmed.code == "FAST_LANE_CONFIRMED"
    assert confirmed.data["status"] == "confirmed"
    receipts = StateStore(fastlane.root).list_scope("approval_receipt")
    assert {item["scope"] for item in receipts} == {"development_tdd", "verification"}
    assert ["rtk", "proxy", "pnpm", "run", "type-check"] in FakeRunner.calls
    assert confirmed.data["baseline"]["status"] == "captured"
    calls = list(FakeRunner.calls)
    repeated = fastlane.confirm(
        started.data["requirement_id"],
        preview_id="WTP-FAST",
        business_files=["src/mapping.ts"],
        root_cause="字段映射使用了旧属性",
        evidence="src/mapping.ts 中读取 oldField",
        test_command="pnpm vitest run src/mapping.test.ts",
        expected_red="expected newField",
        risks=[],
        user_evidence="用户确认一次授权",
        authorized_by_user=True,
    )
    assert repeated.ok
    assert FakeRunner.calls == calls
    assert len(StateStore(fastlane.root).list_scope("approval_receipt")) == 2


def test_fast_confirm_downgrades_for_forbidden_risk_without_worktree(
    fastlane: FastLaneService,
) -> None:
    started = fastlane.start(
        short_name="字段映射修复",
        request="修复页面字段映射",
        systems=["demo"],
        domains=[],
        project_id="web",
        reproduction="打开列表即可复现",
    )

    result = fastlane.confirm(
        started.data["requirement_id"],
        preview_id="WTP-FAST",
        business_files=["src/mapping.ts"],
        root_cause="接口契约变化",
        evidence="OpenAPI 字段已改变",
        test_command="pnpm vitest run src/mapping.test.ts",
        expected_red="expected newField",
        risks=["api-contract"],
        user_evidence="用户确认一次授权",
        authorized_by_user=True,
    )

    assert not result.ok
    assert result.code == "FAST_LANE_DOWNGRADED"
    assert result.data["status"] == "downgraded"
    assert not FakeRunner.calls


def _confirmed(fastlane: FastLaneService) -> str:
    started = fastlane.start(
        short_name="字段映射修复",
        request="修复页面字段映射",
        systems=["demo"],
        domains=[],
        project_id="web",
        reproduction="打开列表即可复现",
    )
    FakeRunner.results = [
        Result(True, data={"stdout": "src/mapping.ts\n", "stderr": ""}),
        Result(
            False,
            "COMMAND_FAILED",
            data={
                "stdout": "src/old.ts(1,1): error TS1001: existing\n",
                "stderr": "",
                "raw_log": "baseline.json",
            },
        ),
    ]
    confirmed = fastlane.confirm(
        started.data["requirement_id"],
        preview_id="WTP-FAST",
        business_files=["src/mapping.ts"],
        root_cause="字段映射使用了旧属性",
        evidence="src/mapping.ts 中读取 oldField",
        test_command="pnpm vitest run src/mapping.test.ts",
        expected_red="expected newField",
        risks=[],
        user_evidence="用户确认一次授权",
        authorized_by_user=True,
    )
    assert confirmed.ok
    return str(started.data["requirement_id"])


def _record_red(fastlane: FastLaneService, requirement_id: str) -> None:
    FakeRunner.results = [
        Result(
            False,
            "COMMAND_FAILED",
            data={"stdout": "expected newField", "stderr": "", "raw_log": "red.json"},
        )
    ]
    assert fastlane.red(requirement_id).ok


def test_fast_red_rejects_business_changes_before_test(
    fastlane: FastLaneService,
) -> None:
    requirement_id = _confirmed(fastlane)
    (fastlane.root / "repo" / "src" / "mapping.ts").write_text(
        "export const value = 2;\n"
    )

    result = fastlane.red(requirement_id)

    assert not result.ok
    assert result.code == "FAST_LANE_RED_AFTER_IMPLEMENTATION"


def test_fast_finish_runs_green_diff_and_incremental_typecheck(
    fastlane: FastLaneService,
) -> None:
    requirement_id = _confirmed(fastlane)
    _record_red(fastlane, requirement_id)
    (fastlane.root / "repo" / "src" / "mapping.ts").write_text(
        "export const value = 2;\n"
    )
    FakeRunner.results = [
        Result(True, data={"stdout": "passed", "stderr": "", "raw_log": "green.json"}),
        Result(True, data={"stdout": "", "stderr": "", "raw_log": "diff.json"}),
        Result(
            False,
            "COMMAND_FAILED",
            data={
                "stdout": "src/old.ts(20,4): error TS1001: existing\n",
                "stderr": "",
                "raw_log": "type.json",
            },
        ),
    ]

    result = fastlane.finish(requirement_id)

    assert result.ok
    assert result.code == "FAST_LANE_IMPLEMENTED"
    assert result.data["verification"]["typecheck"]["status"] == (
        "incremental_passed_baseline_failed"
    )
    assert ["rtk", "git", "diff", "--check"] in FakeRunner.calls


def test_fast_finish_keeps_red_state_when_green_fails(
    fastlane: FastLaneService,
) -> None:
    requirement_id = _confirmed(fastlane)
    _record_red(fastlane, requirement_id)
    (fastlane.root / "repo" / "src" / "mapping.ts").write_text(
        "export const value = 2;\n"
    )
    FakeRunner.results = [
        Result(
            False,
            "COMMAND_FAILED",
            data={"stdout": "still failing", "stderr": "", "raw_log": "green.json"},
        )
    ]

    result = fastlane.finish(requirement_id)

    assert not result.ok
    assert result.code == "FAST_LANE_GREEN_FAILED"
    assert fastlane.status(requirement_id).data["status"] == "red_recorded"


def test_fast_finish_downgrades_and_preserves_worktree_for_extra_business_file(
    fastlane: FastLaneService,
) -> None:
    requirement_id = _confirmed(fastlane)
    _record_red(fastlane, requirement_id)
    repository = fastlane.root / "repo"
    (repository / "src" / "mapping.ts").write_text("export const value = 2;\n")
    (repository / "src" / "extra.ts").write_text("export const extra = true;\n")

    result = fastlane.finish(requirement_id)

    assert not result.ok
    assert result.code == "FAST_LANE_DOWNGRADED"
    assert result.data["extra_files"] == ["src/extra.ts"]
    assert repository.is_dir()


def test_fast_finish_records_inconclusive_when_baseline_is_unavailable(
    fastlane: FastLaneService,
) -> None:
    requirement_id = _confirmed(fastlane)
    record = StateStore(fastlane.root).get("fast_lane", requirement_id)
    assert record is not None
    StateStore(fastlane.root).delete(
        "fast_lane_baseline", record["baseline_fingerprint"]
    )
    _record_red(fastlane, requirement_id)
    (fastlane.root / "repo" / "src" / "mapping.ts").write_text(
        "export const value = 2;\n"
    )
    FakeRunner.results = [
        Result(True, data={"stdout": "passed", "stderr": "", "raw_log": "green.json"}),
        Result(True, data={"stdout": "", "stderr": "", "raw_log": "diff.json"}),
        Result(True, data={"stdout": "", "stderr": "", "raw_log": "type.json"}),
    ]

    result = fastlane.finish(requirement_id)

    assert result.ok
    assert result.code == "FAST_LANE_IMPLEMENTED_VERIFICATION_INCONCLUSIVE"
    assert result.data["verification"]["typecheck"]["status"] == "baseline_unavailable"
