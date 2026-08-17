from __future__ import annotations

from pathlib import Path

from praxis.agents.guidance import AgentGuidanceService
from praxis.workspace.service import Project, WorkspaceService

SKILL_MD = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "praxis-requirement-workflow"
    / "SKILL.md"
)


def _read_workflow_skill() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def test_agent_guidance_preserves_custom_content_and_refreshes_managed_block(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "backend"
    (repository / ".cursor" / "rules").mkdir(parents=True)
    (repository / "skills").mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[
            Project(
                "backend",
                "java-maven",
                "backend",
                "local",
                template_branches=("develop",),
            )
        ],
    )
    (tmp_path / "AGENTS.md").write_text("# 团队自定义规则\n\n保留此内容。\n")

    first = AgentGuidanceService(tmp_path).render()
    second = AgentGuidanceService(tmp_path).render()

    assert first.ok and second.ok
    agents = (tmp_path / "AGENTS.md").read_text()
    claude = (tmp_path / "CLAUDE.md").read_text()
    # 自定义内容与 marker 保护
    assert "保留此内容。" in agents
    assert agents.count("<!-- praxis:managed:start -->") == 1
    assert agents.count("<!-- praxis:managed:end -->") == 1
    # 动态数据表（由 guidance 生成，保留）
    assert "`local` | `develop`" in agents
    assert "`backend/.cursor/rules`" in agents
    assert "`backend/skills`" in agents
    assert "`brainstorming`（必需）" in agents
    assert "`grilling`（必需）" in agents
    # 工作空间身份
    assert "演示工作空间" in agents
    # 指针/不变式（保留在 AGENTS）
    assert "praxis-requirement-workflow" in agents
    assert ".worktrees/<需求ID>__<简称>" in agents
    assert "praxis skill route-node" in agents
    assert "praxis skill invoke" in agents
    assert "praxis skill complete" in agents
    assert "lifecycle complete-node" in agents
    assert "select current_database()" in agents
    assert "默认执行 TDD" in agents
    assert "fast_fix" in agents
    assert "完整回归" in agents
    assert "独立验证授权" in agents
    assert "rtk" in agents
    assert "codegraph-impact-analysis" in agents
    assert claude.startswith("# Claude Code 项目规则")
    # 迁出细则改断言 SKILL.md 含该内容（AGENTS 不再重复正文）
    skill = _read_workflow_skill()
    assert "mode=fast_fix" in skill
    assert "tests=declined_by_user" in skill
    assert "compile=not_requested" in skill
    assert "scope=target_file_only" in skill
    assert "RTK 自身执行失败" in skill
    assert "正则匹配" in skill
    assert "目标文件指纹" in skill
    assert "禁止扩大为全仓构建" in skill


def test_agent_guidance_stops_on_broken_managed_markers(tmp_path: Path) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    (tmp_path / "AGENTS.md").write_text("<!-- praxis:managed:start -->\n")

    result = AgentGuidanceService(tmp_path).render()

    assert result.code == "AGENT_GUIDANCE_MARKERS_INVALID"
    assert not (tmp_path / "CLAUDE.md").exists()


def test_agent_guidance_requires_canonical_praxis_entry_resolution(
    tmp_path: Path,
) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")

    result = AgentGuidanceService(tmp_path).render()

    assert result.ok
    agents = (tmp_path / "AGENTS.md").read_text()
    assert "Praxis MCP" in agents
    assert "`praxis` CLI" in agents
    assert "MCP 不可用时" in agents
    assert "DBX 调查" in agents
