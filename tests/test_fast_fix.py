from __future__ import annotations

import subprocess
from pathlib import Path

from praxis.application import PraxisApplication
from praxis.fastlane.fast_fix import FastFixService
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService


def _workspace(
    tmp_path: Path,
    *,
    target_relative: str = "src/WmsStocktakingDiffRecordMapper.java",
) -> tuple[FastFixService, str, Path]:
    repository = tmp_path / "repo"
    target = repository / target_relative
    target.parent.mkdir(parents=True)
    target.write_text(
        "package demo;\n\npublic interface WmsStocktakingDiffRecordMapper {}\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repository,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repository, check=True)
    WorkspaceService(tmp_path).init(
        "demo",
        "演示",
        projects=[
            Project(
                "backend",
                "java-maven",
                "repo",
                "main",
                system_id="demo",
                template_branches=("main",),
            )
        ],
    )
    store = StateStore(tmp_path)
    requirement = store.create_requirement(
        "库存盘点租户修复",
        "快速修复，只加租户忽略注解，不要走标准流程，不要跑测试",
        ["demo"],
        [],
    )
    requirement_id = str(requirement["requirement_id"])
    binding_id = f"WT-{requirement_id}--backend"
    store.set(
        "worktree",
        binding_id,
        {
            "binding_id": binding_id,
            "requirement_id": requirement_id,
            "repository_id": "backend",
            "repository_path": str(repository),
            "path": str(repository),
            "branch": f"praxis/{requirement_id}",
            "status": "active",
        },
    )
    target.write_text(
        "package demo;\n\n"
        "@InterceptorIgnore(tenantLine = \"true\")\n"
        "public interface WmsStocktakingDiffRecordMapper {}\n",
        encoding="utf-8",
    )
    return FastFixService(tmp_path), requirement_id, repository


def test_fast_fix_record_declined_completes_governance_without_skill_invocations(
    tmp_path: Path,
) -> None:
    service, requirement_id, _ = _workspace(tmp_path)

    recorded = PraxisApplication(service.root).execute(
        "fix.record",
        {
            "requirement_id": requirement_id,
            "file": "WmsStocktakingDiffRecordMapper.java",
            "verification": "declined",
            "reason": "用户要求单注解快速修复，不要走标准流程，不要跑测试",
            "command_count": 2,
            "elapsed_seconds": 90,
        },
    )

    assert recorded.ok
    assert recorded.code == "FAST_FIX_RECORDED"
    assert recorded.data["mode"] == "fast_fix"
    assert recorded.data["tests"] == "declined_by_user"
    assert recorded.data["compile"] == "not_requested"
    assert recorded.data["scope"] == "target_file_only"
    assert recorded.data["change_kind"] == "annotation"
    assert recorded.data["verification"]["status"] == "declined"
    assert recorded.data["omitted_verification"] == [
        "tests",
        "compile",
        "full_typecheck",
        "quality_review",
        "integration_verification",
    ]
    store = StateStore(service.root)
    assert store.requirement(requirement_id)["status"] == "implemented"
    assert len(store.list_scope("artifact")) == 1
    assert len(store.list_scope("verification_decline")) == 1
    assert not [
        item
        for item in store.list_scope("skill_invocation")
        if item.get("requirement_id") == requirement_id
    ]


def test_fast_fix_record_reuses_same_worktree_head_and_file_evidence(
    tmp_path: Path,
) -> None:
    service, requirement_id, _ = _workspace(tmp_path)
    arguments = {
        "file": "WmsStocktakingDiffRecordMapper.java",
        "verification": "declined",
        "reason": "用户要求单注解快速修复",
        "command_count": 1,
        "elapsed_seconds": 60,
    }

    first = service.record(requirement_id, **arguments)
    second = service.record(requirement_id, **arguments)

    assert first.ok and second.ok
    assert first.data["evidence_key"] == second.data["evidence_key"]
    assert second.data["reused_evidence"] is True
    store = StateStore(service.root)
    assert len(store.list_scope("artifact")) == 1
    assert len(store.list_scope("verification_decline")) == 1


def test_fast_fix_record_accepts_three_bounded_files_with_generic_change_kind(
    tmp_path: Path,
) -> None:
    service, requirement_id, repository = _workspace(tmp_path)
    other = repository / "src" / "Other.java"
    migration = repository / "db" / "migration" / "V1__seed.sql"
    migration.parent.mkdir(parents=True)
    other.write_text("class Other {}\n")
    migration.write_text("insert into config(name) values ('old');\n")
    subprocess.run(["git", "add", str(other), str(migration)], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "add bounded files"], cwd=repository, check=True)
    other.write_text("class Other { static final int LIMIT = 2; }\n")
    migration.write_text("insert into config(name) values ('new');\n")

    recorded = service.record(
        requirement_id,
        file=[
            "WmsStocktakingDiffRecordMapper.java",
            "Other.java",
            "V1__seed.sql",
        ],
        verification="direct",
        reason="根因已明确的三文件小改动",
        change_kind="bounded_update",
        risk="变更是否仅限于指定文件",
        evidence="Git diff 显示仅三个指定文件变更",
    )

    assert recorded.ok
    assert recorded.data["scope"] == "bounded_files_only"
    assert recorded.data["target_files"] == [
        "db/migration/V1__seed.sql",
        "src/Other.java",
        "src/WmsStocktakingDiffRecordMapper.java",
    ]
    assert recorded.data["change_kind"] == "bounded_update"
    assert len(StateStore(service.root).list_scope("artifact")) == 1


def test_fast_fix_record_requires_new_risk_reason_when_soft_budget_is_exceeded(
    tmp_path: Path,
) -> None:
    service, requirement_id, _ = _workspace(tmp_path)

    recorded = service.record(
        requirement_id,
        file="WmsStocktakingDiffRecordMapper.java",
        verification="declined",
        reason="用户要求单注解快速修复",
        command_count=3,
        elapsed_seconds=90,
    )

    assert not recorded.ok
    assert recorded.code == "FAST_FIX_COMMAND_BUDGET_EXCEEDED"
    assert recorded.data["budget"]["max_commands"] == 2
    assert recorded.data["requires"] == "new_risk_justification"


def test_fast_fix_record_allows_simple_api_path_but_rejects_transaction_changes(
    tmp_path: Path,
) -> None:
    api_service, api_requirement, _ = _workspace(
        tmp_path / "api-case",
        target_relative="src/api/PublicApi.java",
    )

    api_result = api_service.record(
        api_requirement,
        file="PublicApi.java",
        verification="declined",
        reason="用户要求单注解快速修复",
    )

    assert api_result.ok

    transaction_service, transaction_requirement, transaction_repository = _workspace(
        tmp_path / "transaction-case"
    )
    target = (
        transaction_repository / "src" / "WmsStocktakingDiffRecordMapper.java"
    )
    target.write_text(
        "package demo;\n\n"
        "@Transactional\n"
        "public interface WmsStocktakingDiffRecordMapper {}\n",
        encoding="utf-8",
    )

    transaction_result = transaction_service.record(
        transaction_requirement,
        file="WmsStocktakingDiffRecordMapper.java",
        verification="declined",
        reason="用户要求单注解快速修复",
    )

    assert not transaction_result.ok
    assert transaction_result.code == "FAST_FIX_HIGH_RISK_CONTENT"


def test_fast_fix_record_allows_simple_test_file_change(tmp_path: Path) -> None:
    service, requirement_id, _ = _workspace(
        tmp_path,
        target_relative="src/mapping.test.ts",
    )

    recorded = service.record(
        requirement_id,
        file="mapping.test.ts",
        verification="declined",
        reason="用户要求单注解快速修复",
    )

    assert recorded.ok


def test_fast_fix_record_auto_selects_bounded_change_without_magic_phrase(
    tmp_path: Path,
) -> None:
    service, requirement_id, _ = _workspace(tmp_path)

    recorded = service.record(
        requirement_id,
        file="WmsStocktakingDiffRecordMapper.java",
        verification="direct",
        reason="修正已明确的小问题",
        risk="diff 是否超出单文件",
        evidence="仅目标文件变更",
    )

    assert recorded.ok
    assert recorded.data["change_kind"] == "bounded_change"


def test_fast_fix_record_hard_stops_after_five_commands_or_three_minutes(
    tmp_path: Path,
) -> None:
    service, requirement_id, _ = _workspace(tmp_path)

    recorded = service.record(
        requirement_id,
        file="WmsStocktakingDiffRecordMapper.java",
        verification="declined",
        reason="用户要求单注解快速修复",
        command_count=6,
        elapsed_seconds=181,
        new_risk_justification="新增风险是租户 SQL 行为",
    )

    assert not recorded.ok
    assert recorded.code == "FAST_FIX_HARD_BUDGET_EXCEEDED"
    assert recorded.data["budget"]["hard_max_commands"] == 5
    assert recorded.data["budget"]["hard_max_seconds"] == 180


def test_fast_fix_direct_check_records_evidence_without_claiming_tests_passed(
    tmp_path: Path,
) -> None:
    service, requirement_id, _ = _workspace(tmp_path)

    recorded = service.record(
        requirement_id,
        file="WmsStocktakingDiffRecordMapper.java",
        verification="direct",
        reason="用户要求单注解快速修复",
        risk="重启后租户插件生成的 SQL 是否正确",
        evidence="已确认错误 SQL；修改后需要重启并复测真实查询",
        command_count=2,
        elapsed_seconds=100,
    )

    assert recorded.ok
    assert recorded.data["tests"] == "not_run"
    assert recorded.data["verification"]["status"] == "evidence_recorded"
    assert recorded.data["verification"]["risk"].startswith("重启后")
    assert "integration_verification" in recorded.data["omitted_verification"]
