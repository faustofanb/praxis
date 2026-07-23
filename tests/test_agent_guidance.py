from __future__ import annotations

from pathlib import Path

from praxis.agents.guidance import AgentGuidanceService
from praxis.workspace.service import Project, WorkspaceService


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
    assert "保留此内容。" in agents
    assert agents.count("<!-- praxis:managed:start -->") == 1
    assert agents.count("<!-- praxis:managed:end -->") == 1
    assert "`local` | `develop`" in agents
    assert "`backend/.cursor/rules`" in agents
    assert "`backend/skills`" in agents
    assert "`brainstorming`（必需）" in agents
    assert "`grilling`（必需）" in agents
    assert ".worktrees/<需求ID>__<简称>" in agents
    assert "praxis/<需求ID>" in agents
    assert "praxis skill route-node" in agents
    assert "praxis skill invoke" in agents
    assert "praxis skill complete" in agents
    assert "lifecycle complete-node" in agents
    assert "自动生成当前项目的 coder context" in agents
    assert "select current_database()" in agents
    assert "database investigate" in agents
    assert "规划模式" in agents
    assert "默认执行 TDD" in agents
    assert "RED" in agents
    assert "GREEN" in agents
    assert "完整回归" in agents
    assert "独立验证授权" in agents
    assert "最小受影响模块" in agents
    assert "minimum-module-compile" in agents
    assert "禁止扩大为全仓构建" in agents
    assert "所有外部命令" in agents
    assert "rtk proxy" in agents
    assert "RTK 自身执行失败" in agents
    assert "降级命令" in agents
    assert "高风险改动必须在编辑前" in agents
    assert "codegraph-impact-analysis" in agents
    assert "调用路径和 Blast Radius" in agents
    assert "连续错误后才刷新" in agents
    assert "实施完成不等于验证通过" in agents
    assert claude.startswith("# Claude Code 项目规则")


def test_agent_guidance_stops_on_broken_managed_markers(tmp_path: Path) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    (tmp_path / "AGENTS.md").write_text("<!-- praxis:managed:start -->\n")

    result = AgentGuidanceService(tmp_path).render()

    assert result.code == "AGENT_GUIDANCE_MARKERS_INVALID"
    assert not (tmp_path / "CLAUDE.md").exists()
