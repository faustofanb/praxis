from __future__ import annotations

from pathlib import Path

from praxis.context.service import ContextBuildRequest, ContextCompiler, ContextFragment
from praxis.knowledge.requirements import RequirementService
from praxis.portraits.service import PortraitService
from praxis.workspace.service import Project, WorkspaceService


def _workspace_with_requirement(root: Path) -> str:
    repo = root / "backend"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='demo'\n")
    WorkspaceService(root).init(
        "demo",
        "演示工作空间",
        projects=[Project("backend", "python", "backend", "main")],
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
