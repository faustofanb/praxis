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
    root = tmp_path / "知识库" / "需求" / "2026" / "07" / "金属平衡块复制__REQ-20260720-001"
    assert "用户原始要求：支持二维区域复制。" in (root / "原始需求.md").read_text()
    assert "需求状态: 已捕获" in (root / "需求总览.md").read_text()
    assert {path.name for path in root.iterdir()} == {
        "需求总览.md",
        "原始需求.md",
        "调查分析.md",
        "实施计划.md",
        "执行进度.md",
        "验收结论.md",
        "变更记录.md",
        "关联关系.yaml",
        "产出物清单.yaml",
        "事件记录.jsonl",
        "产出物",
    }
    with closing(sqlite3.connect(tmp_path / ".praxis" / "workspace.db")) as database:
        assert database.execute("select status from requirements").fetchone()[0] == "captured"
        assert database.execute("select processed_at from outbox").fetchone()[0] is not None
    assert StateStore(tmp_path).verify_audit_chain()


def test_requirement_state_machine_rejects_skipped_transition() -> None:
    requirement = Requirement("REQ-20260720-001", "金属平衡块复制")

    assert requirement.transition(RequirementStatus.INVESTIGATING).status == "investigating"
    with pytest.raises(ValueError, match="非法需求状态转换"):
        requirement.transition(RequirementStatus.READY)


def test_requirement_transition_preserves_existing_progress_content(tmp_path: Path) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    requirements = RequirementService(tmp_path)
    created = requirements.create("进度保留", "保留已有执行记录", [], [])
    progress = Path(created.data["path"]) / "执行进度.md"
    progress.write_text(progress.read_text() + "\n- 已完成调查证据。\n")

    assert requirements.transition(
        created.data["requirement_id"], RequirementStatus.INVESTIGATING
    ).ok

    assert "已完成调查证据。" in progress.read_text()


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
    (requirement_path / "调查分析.md").write_text("# 调查分析\n\n已确认影响范围。\n")
    (requirement_path / "实施计划.md").write_text("# 实施计划\n\n按后端阶段实现并验证。\n")

    assert blocked.code == "REQUIREMENT_NOT_READY"
    assert blocked.data["missing_documents"] == ["调查分析.md", "实施计划.md"]
    assert requirements.transition(requirement_id, RequirementStatus.READY).ok
    assert requirements.progress(requirement_id, "已完成调查与计划").ok
    renamed = requirements.rename(requirement_id, "生产报表性能优化")
    assert renamed.ok
    assert Path(renamed.data["path"]).is_dir()
    assert not requirement_path.exists()
