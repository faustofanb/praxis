from __future__ import annotations

import sqlite3
import tomllib
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from praxis.domain.requirement import Requirement, RequirementStatus
from praxis.gates.commit_message import validate_commit_message
from praxis.knowledge.requirements import RequirementService
from praxis.naming.requirement import RequirementPathPolicy
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService


def test_workspace_init_writes_schema_v3_facts(tmp_path: Path) -> None:
    result = WorkspaceService(tmp_path).init("aotu", "IFC制造开发工作空间")

    assert result.ok
    payload = tomllib.loads((tmp_path / "praxis.toml").read_text())
    assert payload == {
        "schema_version": 3,
        "workspace": {
            "id": "aotu",
            "name": "IFC制造开发工作空间",
            "language": "zh-CN",
            "knowledge_root": "知识库",
            "artifact_root": "产出物",
            "generated_root": "生成内容",
            "state_root": ".praxis",
            "worktree_root": ".worktrees",
        },
    }
    assert not (tmp_path / ".praxis" / "workspace.db").exists()


def test_workspace_add_registers_repository_in_existing_system(tmp_path: Path) -> None:
    workspace = WorkspaceService(tmp_path)
    workspace.init("demo", "演示开发工作空间")
    workspace.add_system("orders", "订单系统")

    result = workspace.add_project(
        "orders",
        Project(
            id="backend",
            name="后端服务",
            kind="backend",
            path="services/backend",
            default_branch="main",
            test_commands=("pytest -q",),
        ),
    )

    assert result.ok
    assert workspace.project("backend").test_commands == ("pytest -q",)


def test_requirement_create_persists_state_and_projects_chinese_documents(tmp_path: Path) -> None:
    WorkspaceService(tmp_path).init("aotu", "IFC制造开发工作空间")
    WorkspaceService(tmp_path).add_system("ifc-mom", "IFC-MOM制造运营系统", ["metal-balance"])
    result = RequirementService(tmp_path).create(
        short_name="金属平衡块复制",
        request="用户原始要求：支持二维区域复制。",
        systems=["ifc-mom"],
        domains=["metal-balance"],
        now=datetime(2026, 7, 20, 2, 30, tzinfo=UTC),
    )

    assert result.ok and result.data["requirement_id"] == "REQ-20260720-001"
    root = tmp_path / "知识库" / "需求" / "2026" / "07" / "REQ-20260720-001__金属平衡块复制"
    assert "用户原始要求：支持二维区域复制。" in (root / "01-原始需求.md").read_text()
    assert "需求状态: 已捕获" in (root / "00-需求总览.md").read_text()
    assert {path.name for path in root.iterdir()} == {
        "00-需求总览.md",
        "01-原始需求.md",
        "02-调查分析.md",
        "03-实施计划.md",
        "04-执行进度.md",
        "05-决策记录.md",
        "06-验收结论.md",
        "07-变更记录.md",
        "08-关联关系.yaml",
        "09-产出物清单.yaml",
        "10-事件记录.jsonl",
        "产出物",
    }
    with closing(sqlite3.connect(tmp_path / ".praxis" / "workspace.db")) as database:
        assert database.execute("select status from requirements").fetchone()[0] == "captured"
        assert database.execute("select processed_at from outbox").fetchone()[0] is not None
    assert StateStore(tmp_path).verify_audit_chain()


def test_requirement_layout_repair_migrates_legacy_names_idempotently(
    tmp_path: Path,
) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    requirements = RequirementService(tmp_path)
    created = requirements.create("历史布局迁移", "迁移后保持人工内容", [], [])
    requirement_id = created.data["requirement_id"]
    current = Path(created.data["path"])
    legacy = current.with_name(f"历史布局迁移__{requirement_id}")
    current.rename(legacy)
    for path in list(legacy.iterdir()):
        if path.name == "产出物":
            continue
        prefix, separator, suffix = path.name.partition("-")
        if separator and prefix.isdigit():
            path.rename(legacy / suffix)
    (legacy / "调查分析.md").write_text("# 调查分析\n\n保留人工证据。\n")

    first = requirements.repair_layout()
    snapshot = {
        path.relative_to(current): path.read_bytes()
        for path in current.rglob("*")
        if path.is_file()
    }
    second = requirements.repair_layout()

    assert first.ok and first.data["migrated_requirements"] == [requirement_id]
    assert second.ok and second.data["migrated_requirements"] == []
    assert not legacy.exists()
    assert "保留人工证据" in (current / "02-调查分析.md").read_text()
    assert snapshot == {
        path.relative_to(current): path.read_bytes()
        for path in current.rglob("*")
        if path.is_file()
    }


def test_requirement_layout_conflict_does_not_partially_rename_directory(
    tmp_path: Path,
) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    requirements = RequirementService(tmp_path)
    created = requirements.create("冲突布局迁移", "冲突时保持原目录", [], [])
    requirement_id = created.data["requirement_id"]
    current = Path(created.data["path"])
    legacy = current.with_name(f"冲突布局迁移__{requirement_id}")
    current.rename(legacy)
    (legacy / "调查分析.md").write_text("# 旧调查\n")
    (legacy / "02-调查分析.md").write_text("# 新调查\n")

    repaired = requirements.repair_layout()

    assert not repaired.ok
    assert repaired.code == "REQUIREMENT_LAYOUT_CONFLICT"
    assert legacy.is_dir()
    assert not current.exists()


def test_requirement_state_machine_rejects_skipped_transition() -> None:
    requirement = Requirement("REQ-20260720-001", "金属平衡块复制")

    assert requirement.transition(RequirementStatus.INVESTIGATING).status == "investigating"
    with pytest.raises(ValueError, match="非法需求状态转换"):
        requirement.transition(RequirementStatus.READY)


def test_implemented_is_required_before_verifying() -> None:
    requirement = Requirement(
        "REQ-20260720-001",
        "金属平衡块复制",
        RequirementStatus.IN_PROGRESS,
    )

    with pytest.raises(ValueError, match="非法需求状态转换"):
        requirement.transition(RequirementStatus.VERIFYING)

    implemented = requirement.transition(RequirementStatus.IMPLEMENTED)

    assert implemented.status == "implemented"
    assert implemented.transition(RequirementStatus.VERIFYING).status == "verifying"


def test_requirement_projection_managed_state_is_idempotent(tmp_path: Path) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    requirements = RequirementService(tmp_path)
    created = requirements.create("投影幂等", "重复刷新受管状态", [], [])
    requirement_id = created.data["requirement_id"]

    for _ in range(5):
        requirements.project_current(requirement_id)

    overview = (Path(created.data["path"]) / "00-需求总览.md").read_text()
    assert overview.count("<!-- PRAXIS:MANAGED:STATE:START -->") == 1
    assert overview.count("<!-- PRAXIS:MANAGED:STATE:END -->") == 1


def test_requirement_advance_moves_one_legal_state_and_reports_gate(
    tmp_path: Path,
) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    requirements = RequirementService(tmp_path)
    created = requirements.create("单步推进", "一次只推进一个状态", [], [])
    requirement_id = created.data["requirement_id"]

    first = requirements.advance(requirement_id)

    assert first.ok
    assert first.data["source_status"] == "captured"
    assert first.data["target_status"] == "investigating"
    assert first.data["missing_gates"] == []

    store = StateStore(tmp_path)
    for status in (
        RequirementStatus.ANALYZED,
        RequirementStatus.PLANNED,
        RequirementStatus.READY,
        RequirementStatus.IN_PROGRESS,
    ):
        store.transition_requirement(requirement_id, status)

    blocked = requirements.advance(requirement_id)

    assert not blocked.ok
    assert blocked.code == "REQUIREMENT_ADVANCE_BLOCKED"
    assert blocked.data["source_status"] == "in_progress"
    assert blocked.data["target_status"] == "implemented"
    assert blocked.data["missing_gates"] == ["implementation"]

    requirements.record_implementation(requirement_id, "backend")
    implemented = requirements.advance(requirement_id)
    assert implemented.ok
    assert implemented.data["target_status"] == "implemented"


def test_requirement_transition_preserves_existing_progress_content(tmp_path: Path) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    requirements = RequirementService(tmp_path)
    created = requirements.create("进度保留", "保留已有执行记录", [], [])
    progress = Path(created.data["path"]) / "04-执行进度.md"
    progress.write_text(progress.read_text() + "\n- 已完成调查证据。\n")

    assert requirements.transition(
        created.data["requirement_id"], RequirementStatus.INVESTIGATING
    ).ok

    assert "已完成调查证据。" in progress.read_text()


def test_requirement_reopen_returns_verification_to_development_with_reason(
    tmp_path: Path,
) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    requirements = RequirementService(tmp_path)
    created = requirements.create("重新开发", "验证阶段发现需调整", [], [])
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
    ):
        store.transition_requirement(requirement_id, status)

    reopened = requirements.reopen(requirement_id, "验证发现兼容性问题")

    assert reopened.ok and reopened.code == "REQUIREMENT_REOPENED"
    assert reopened.data["status"] == "in_progress"
    assert reopened.data["reason"] == "验证发现兼容性问题"


def test_record_implementation_empty_list_requires_explicit_reset(
    tmp_path: Path,
) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    requirements = RequirementService(tmp_path)
    created = requirements.create("空列表保护", "空列表不得覆盖已有产出物", [], [])
    requirement_id = created.data["requirement_id"]
    requirements.record_implementation(requirement_id, "backend", artifact_ids=["ART-1"])

    blocked = requirements.record_implementation(
        requirement_id, projects={"backend": []}
    )

    assert not blocked.ok
    assert blocked.code == "REQUIREMENT_IMPLEMENTATION_RESET_REQUIRED"
    assert blocked.data["project_id"] == "backend"
    assert blocked.data["existing_artifact_ids"] == ["ART-1"]

    reset = requirements.record_implementation(
        requirement_id, projects={"backend": []}, reset=True
    )
    assert reset.ok
    delivery = requirements.delivery(requirement_id).data
    assert delivery["implementation"]["backend"]["artifact_ids"] == []


def test_record_implementation_preserves_unmentioned_project_recorded_at(
    tmp_path: Path,
) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    requirements = RequirementService(tmp_path)
    created = requirements.create("时间戳保留", "未提及项目 recorded_at 不变", [], [])
    requirement_id = created.data["requirement_id"]

    requirements.record_implementation(
        requirement_id, projects={"backend": ["ART-B"]}
    )
    backend_recorded_at = (
        requirements.delivery(requirement_id).data["implementation"]["backend"][
            "recorded_at"
        ]
    )
    requirements.record_implementation(
        requirement_id, projects={"mes-pda": ["ART-P"]}
    )

    implementation = requirements.delivery(requirement_id).data["implementation"]
    assert implementation["backend"]["recorded_at"] == backend_recorded_at
    assert implementation["backend"]["artifact_ids"] == ["ART-B"]


def test_requirement_reopen_from_implemented_returns_to_in_progress(
    tmp_path: Path,
) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    requirements = RequirementService(tmp_path)
    created = requirements.create("实施回退", "implemented 单步回开发", [], [])
    requirement_id = created.data["requirement_id"]
    store = StateStore(tmp_path)
    for status in (
        RequirementStatus.INVESTIGATING,
        RequirementStatus.ANALYZED,
        RequirementStatus.PLANNED,
        RequirementStatus.READY,
        RequirementStatus.IN_PROGRESS,
        RequirementStatus.IMPLEMENTED,
    ):
        store.transition_requirement(requirement_id, status)

    blocked = requirements.reopen(requirement_id, "实施遗漏边界处理")

    assert not blocked.ok
    assert blocked.code == "REQUIREMENT_REOPEN_STATUS_INVALID"
    assert "--from implemented" in blocked.data["hint"]

    reopened = requirements.reopen(
        requirement_id, "实施遗漏边界处理", from_status="implemented"
    )

    assert reopened.ok and reopened.code == "REQUIREMENT_REOPENED"
    assert reopened.data["status"] == "in_progress"
    assert reopened.data["from_status"] == "implemented"


def test_advance_to_implemented_emits_artifact_hint_for_unregistered_changes(
    tmp_path: Path,
) -> None:
    import subprocess
    import time

    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[Project("backend", "python", "backend-repo", "main")],
    )
    repo = tmp_path / "backend-repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "service.py").write_text("print('v1')\n", encoding="utf-8")

    def git(*arguments: str) -> None:
        subprocess.run(
            ["git", *arguments], cwd=repo, check=True, capture_output=True, text=True
        )

    git("init", "-b", "main")
    git("config", "user.email", "test@praxis.local")
    git("config", "user.name", "praxis-test")
    git("add", "-A")
    git("commit", "-m", "init")
    (repo / "src" / "service.py").write_text("print('v2')\n", encoding="utf-8")
    (repo / "src" / "new_module.py").write_text("print('new')\n", encoding="utf-8")

    requirements = RequirementService(tmp_path)
    created = requirements.create("产出物提示", "advance 提示未登记改动", ["demo"], [])
    requirement_id = created.data["requirement_id"]
    StateStore(tmp_path).set(
        "worktree",
        f"WT-{requirement_id}--backend",
        {
            "binding_id": f"WT-{requirement_id}--backend",
            "requirement_id": requirement_id,
            "repository_id": "backend",
            "branch": f"praxis/{requirement_id}",
            "path": str(repo.parent),
            "repository_path": str(repo),
            "status": "active",
        },
    )

    requirements.record_implementation(requirement_id, "backend", artifact_ids=[])
    time.sleep(0.01)
    store = StateStore(tmp_path)
    for status in (
        RequirementStatus.INVESTIGATING,
        RequirementStatus.ANALYZED,
        RequirementStatus.PLANNED,
        RequirementStatus.READY,
        RequirementStatus.IN_PROGRESS,
    ):
        store.transition_requirement(requirement_id, status)

    advanced = requirements.advance(requirement_id)

    assert advanced.ok
    assert advanced.data["target_status"] == "implemented"
    hint = advanced.data["artifact_hint"]
    assert hint["binding_id"] == f"WT-{requirement_id}--backend"
    assert hint["command"].startswith(
        f"praxis artifact add --requirement {requirement_id} "
        "--type code-change --source"
    )
    assert "src/service.py" in hint["unregistered_files"]
    assert "src/new_module.py" in hint["unregistered_files"]


def test_requirement_constraints_supersede_atomically_and_project_active_state(
    tmp_path: Path,
) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    requirements = RequirementService(tmp_path)
    created = requirements.create("约束治理", "沉淀当前有效约束", [], [])
    other = requirements.create("其他需求", "验证跨需求拒绝", [], [])
    requirement_id = created.data["requirement_id"]

    original = requirements.add_constraint(
        requirement_id,
        "不新增业务表",
        source="首次计划",
    )
    foreign = requirements.add_constraint(
        other.data["requirement_id"],
        "其他需求约束",
    )
    rejected = requirements.add_constraint(
        requirement_id,
        "新增独立时效记录表",
        supersedes=[foreign.data["constraint_id"]],
        source="用户后续纠正",
    )
    replacement = requirements.add_constraint(
        requirement_id,
        "新增独立时效记录表",
        supersedes=[original.data["constraint_id"]],
        source="用户后续纠正",
    )

    assert rejected.code == "REQUIREMENT_CONSTRAINT_SUPERSEDES_INVALID"
    assert replacement.ok
    listed = requirements.list_constraints(requirement_id).data
    assert [item["statement"] for item in listed["active"]] == [
        "新增独立时效记录表"
    ]
    historical = {item["constraint_id"]: item for item in listed["historical"]}
    assert historical[original.data["constraint_id"]]["status"] == "superseded"
    assert historical[original.data["constraint_id"]]["superseded_by"] == (
        replacement.data["constraint_id"]
    )
    overview = Path(created.data["path"]) / "00-需求总览.md"
    decisions = Path(created.data["path"]) / "05-决策记录.md"
    assert "新增独立时效记录表" in overview.read_text()
    assert "不新增业务表" not in overview.read_text()
    assert "不新增业务表" in decisions.read_text()
    assert replacement.data["constraint_id"] in decisions.read_text()


def test_record_implementation_is_independent_from_lifecycle_and_projects_delivery(
    tmp_path: Path,
) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    requirements = RequirementService(tmp_path)
    created = requirements.create("交付状态", "拆分实施与验证", [], [])
    requirement_id = created.data["requirement_id"]

    result = requirements.record_implementation(
        requirement_id,
        "backend",
        artifact_ids=["ART-1"],
    )

    assert result.ok
    assert requirements.show(requirement_id).data["status"] == "captured"
    delivery = requirements.delivery(requirement_id).data
    assert delivery["implementation_status"] == "implemented"
    assert delivery["verification_status"] == "not_recorded"
    assert delivery["manual_acceptance_status"] == "awaiting_manual_acceptance"
    overview = Path(created.data["path"]) / "00-需求总览.md"
    assert "实施状态：implemented" in overview.read_text()
    assert "验证状态：not_recorded" in overview.read_text()


def test_record_implementation_merges_multiple_projects_atomically(
    tmp_path: Path,
) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    requirements = RequirementService(tmp_path)
    created = requirements.create("多项目实施", "原子登记后端与 PDA", [], [])
    requirement_id = created.data["requirement_id"]

    recorded = requirements.record_implementation(
        requirement_id,
        projects={
            "backend": ["ART-BACKEND"],
            "mes-pda": ["ART-PDA"],
        },
    )
    rerecorded = requirements.record_implementation(
        requirement_id,
        projects={"backend": ["ART-BACKEND-2"]},
    )

    assert recorded.ok and rerecorded.ok
    implementation = requirements.delivery(requirement_id).data["implementation"]
    assert implementation["backend"]["artifact_ids"] == ["ART-BACKEND-2"]
    assert implementation["mes-pda"]["artifact_ids"] == ["ART-PDA"]
    events = [
        item
        for item in StateStore(tmp_path).audit_events()
        if item["event"] == "requirement.implementation_recorded"
    ]
    assert any(
        event["details"]["projects"] == ["backend", "mes-pda"]
        for event in events
    )


def test_requirement_path_and_commit_message_apply_shared_naming_rules(tmp_path: Path) -> None:
    policy = RequirementPathPolicy(tmp_path)
    assert policy.requirement_path("REQ-20260720-001", "金属平衡块复制").is_relative_to(tmp_path)
    with pytest.raises(ValueError, match="非法路径字符"):
        policy.validate_short_name("金属/平衡")

    message_file = tmp_path / "COMMIT_EDITMSG"
    message_file.write_text(
        "feat(report): [REQ-20260720-001] 支持金属平衡块复制\n\n"
        "Praxis-Requirement: REQ-20260720-001\n"
        "Praxis-Stage: backend\n"
    )
    result = validate_commit_message(message_file=message_file)
    assert result.ok and result.data["requirement_id"] == "REQ-20260720-001"


def test_ready_gate_requires_registered_domains_and_meaningful_documents(tmp_path: Path) -> None:
    workspace = WorkspaceService(tmp_path)
    workspace.init("demo", "演示工作空间")
    workspace.add_system("demo-system", "演示系统", ["production"])
    requirements = RequirementService(tmp_path)
    created = requirements.create(
        "生产报表优化", "优化生产报表", ["demo-system"], ["production"]
    )
    requirement_id = created.data["requirement_id"]
    for status in (
        RequirementStatus.INVESTIGATING,
        RequirementStatus.ANALYZED,
        RequirementStatus.PLANNED,
    ):
        assert requirements.transition(requirement_id, status).ok

    blocked = requirements.transition(requirement_id, RequirementStatus.READY)
    requirement_path = Path(created.data["path"])
    (requirement_path / "02-调查分析.md").write_text("# 调查分析\n\n已确认影响范围。\n")
    (requirement_path / "03-实施计划.md").write_text("# 实施计划\n\n按后端阶段实现并验证。\n")

    assert blocked.code == "REQUIREMENT_NOT_READY"
    assert blocked.data["missing_documents"] == ["02-调查分析.md", "03-实施计划.md"]
    assert requirements.transition(requirement_id, RequirementStatus.READY).ok
    assert requirements.progress(requirement_id, "已完成调查与计划").ok
    renamed = requirements.rename(requirement_id, "生产报表性能优化")
    assert renamed.ok
    assert Path(renamed.data["path"]).is_dir()
    assert not requirement_path.exists()
