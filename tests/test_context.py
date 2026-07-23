from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from praxis.context.service import ContextBuildRequest, ContextCompiler, ContextFragment
from praxis.governance.service import ApprovalService
from praxis.knowledge.requirements import RequirementService
from praxis.portraits.service import PortraitService
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService


def _workspace_with_requirement(root: Path) -> str:
    repo = root / "backend"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='demo'\n")
    WorkspaceService(root).init(
        "demo",
        "演示工作空间",
        projects=[
            Project(
                "backend",
                "python",
                "backend",
                "main",
                database_connections=("dbx://LOCAL/demo", "dbx://PROD/demo"),
                production_database_connections=("dbx://PROD/demo",),
            )
        ],
    )
    requirement = RequirementService(root).create(
        "报表查询优化",
        "调查报表 SQL 慢查询并优化接口",
        ["demo"],
        [],
    )
    PortraitService(root).scan("backend")
    return requirement.data["requirement_id"]


def test_context_build_keeps_required_facts_and_persists_manifest(tmp_path: Path) -> None:
    requirement_id = _workspace_with_requirement(tmp_path)
    compiler = ContextCompiler(tmp_path)

    result = compiler.build(
        ContextBuildRequest(
            requirement_id=requirement_id,
            project_id="backend",
            stage="backend",
            agent_role="coder",
            token_budget=8_000,
            allowed_paths=("src/**", "tests/**"),
            forbidden_paths=(".env",),
        )
    )

    assert result.ok
    assert result.data["estimated_tokens"] <= 8_000
    assert {item["source_type"] for item in result.data["sources"]} >= {
        "original_request",
        "task_stage",
        "gate",
        "system_portrait",
    }
    assert all(item["content_hash"].startswith("blake2b:") for item in result.data["sources"])
    assert Path(result.data["path"]).is_file()
    assert compiler.show(result.data["context_id"]).data == result.data
    routed = next(
        event for event in StateStore(tmp_path).audit_events() if event["event"] == "skill.routed"
    )
    assert routed["details"]["skills"] == [
        "dbx-database-investigation",
        "ponytail",
        "praxis-requirement-workflow",
    ]


def test_context_build_fails_instead_of_dropping_required_fragments(tmp_path: Path) -> None:
    requirement_id = _workspace_with_requirement(tmp_path)

    result = ContextCompiler(tmp_path).build(
        ContextBuildRequest(
            requirement_id=requirement_id,
            project_id="backend",
            stage="backend",
            agent_role="coder",
            token_budget=10,
        )
    )

    assert result.code == "CONTEXT_BUDGET_TOO_SMALL"
    assert result.data["required_tokens"] > 10


def test_context_fragment_deduplication_and_secret_redaction(tmp_path: Path) -> None:
    compiler = ContextCompiler(tmp_path)
    fragments = [
        ContextFragment.create("one", "reference", "参考", "password='secret'", 2),
        ContextFragment.create("two", "reference", "重复", "password='secret'", 3),
    ]

    selected, omitted = compiler.select(fragments, token_budget=100)

    assert len(selected) == 1
    assert selected[0].sensitive is True
    assert selected[0].content == "password='[已脱敏]'"
    assert omitted == [{"fragment_id": "two", "reason": "内容重复"}]


def test_context_diff_reports_changed_source(tmp_path: Path) -> None:
    requirement_id = _workspace_with_requirement(tmp_path)
    compiler = ContextCompiler(tmp_path)
    request = ContextBuildRequest(requirement_id, "backend", "backend", "coder")
    first = compiler.build(request)
    analysis = next((tmp_path / "知识库" / "需求").rglob("调查分析.md"))
    analysis.write_text("# 调查分析\n\n已确认慢查询来源。\n")
    second = compiler.build(request)

    result = compiler.diff(second.data["context_id"], first.data["context_id"])

    assert result.data["changed"] == ["requirement-analysis"]


def test_context_p0_contains_project_database_constraints_and_approvals_without_portrait(
    tmp_path: Path,
) -> None:
    requirement_id = _workspace_with_requirement(tmp_path)
    RequirementService(tmp_path).add_constraint(
        requirement_id,
        "查询数据库前必须确认目标连接",
        source="用户约束",
    )
    ApprovalService(tmp_path).grant(
        requirement_id,
        "verification",
        ["pytest tests/test_context.py"],
        user_evidence="用户批准",
        authorized_by_user=True,
    )
    ApprovalService(tmp_path).grant(
        requirement_id,
        "verification",
        ["pytest tests/expired.py"],
        user_evidence="过期批准",
        authorized_by_user=True,
        expires_at="2020-01-01T00:00:00+00:00",
    )
    PortraitService(tmp_path).path("backend").unlink()

    result = ContextCompiler(tmp_path).build(
        ContextBuildRequest(
            requirement_id,
            "backend",
            "development",
            "coder",
            token_budget=5_000,
            intent="修复数据库上下文注入",
        )
    )

    assert result.ok
    project_source = next(
        item for item in result.data["sources"] if item["fragment_id"] == "project-facts"
    )
    assert project_source["priority"] == 0
    facts = result.data["critical_facts"]
    assert facts["project"] == {
        "id": "backend",
        "system_id": "demo",
        "kind": "python",
        "path": str((tmp_path / "backend").resolve()),
    }
    assert facts["database"]["registered"] == ["dbx://LOCAL/demo", "dbx://PROD/demo"]
    assert facts["database"]["production"] == ["dbx://PROD/demo"]
    assert facts["database"]["precheck_sql"] == "select current_database()"
    assert facts["constraints"][0]["statement"] == "查询数据库前必须确认目标连接"
    assert facts["verification"]["approvals"][0]["entries"] == [
        "pytest tests/test_context.py"
    ]
    assert len(facts["verification"]["approvals"]) == 1
    rendered = Path(result.data["path"]).read_text()
    assert "禁止依赖默认数据库连接" in rendered
    assert "select current_database()" in rendered


def test_context_identity_isolated_by_project_node_role_and_intent(tmp_path: Path) -> None:
    requirement_id = _workspace_with_requirement(tmp_path)
    compiler = ContextCompiler(tmp_path)
    request = ContextBuildRequest(
        requirement_id,
        "backend",
        "development",
        "coder",
        intent="生成后端上下文",
    )

    first = compiler.build(request)
    unchanged = compiler.build(request)
    changed_intent = compiler.build(replace(request, intent="生成数据库调查上下文"))
    changed_node = compiler.build(replace(request, workflow_node="verifying"))

    assert unchanged.code == "CONTEXT_UNCHANGED"
    assert unchanged.data["context_id"] == first.data["context_id"]
    assert changed_intent.data["context_id"] != first.data["context_id"]
    assert changed_node.data["context_id"] != first.data["context_id"]
    assert len(StateStore(tmp_path).list_scope("context_current")) == 3
