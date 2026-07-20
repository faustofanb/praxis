from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextResourceContents
from pydantic import AnyUrl

from praxis.artifacts.service import ArtifactService
from praxis.knowledge.requirements import RequirementService
from praxis.mcp.broker import McpBrokerService
from praxis.portraits.service import PortraitService
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService


def test_mcp_stdio_exposes_tools_resources_and_shared_results(tmp_path: Path) -> None:
    repo = tmp_path / "backend"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='demo'\n")
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[Project("backend", "python", "backend", "main")],
    )
    requirement_id = RequirementService(tmp_path).create(
        "报表查询优化", "核对数据库表结构", ["demo"], []
    ).data["requirement_id"]
    PortraitService(tmp_path).scan("backend")
    store = StateStore(tmp_path)
    context_path = tmp_path / "context.md"
    context_path.write_text("# 最小上下文\n")
    store.set("context", "CTX-TEST", {"context_id": "CTX-TEST", "path": str(context_path)})
    store.set(
        "worktree",
        "req/example",
        {
            "requirement_id": requirement_id,
            "stage": "backend",
            "branch": "req/example",
            "path": str(tmp_path / "worktree"),
            "allowed_paths": ["**"],
            "forbidden_paths": [".env"],
        },
    )
    report = tmp_path / "report.txt"
    report.write_text("passed")
    artifact_id = ArtifactService(tmp_path).add(
        requirement_id, "test-report", report, stage="verify"
    ).data["artifact_id"]
    McpBrokerService(tmp_path).grant(
        "SES-ARCH",
        "architect",
        [
            "workspace.read",
            "system.scan",
            "requirement.read",
            "requirement.transition",
        ],
        requirement_id=requirement_id,
        worktree="req/example",
    )
    McpBrokerService(tmp_path).grant(
        "SES-CODER",
        "coder",
        [
            "context.read",
            "skill.search",
            "skill.route",
            "worktree.status",
            "gate.explain",
            "artifact.read",
        ],
        requirement_id=requirement_id,
        worktree="req/example",
    )

    async def exercise() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "praxis", "--root", str(tmp_path), "mcp", "serve"],
        )
        async with (
            stdio_client(parameters) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert {
                "praxis_execute",
                "praxis_broker_invoke",
                "praxis_workspace_get",
                "praxis_system_get",
                "praxis_system_scan",
                "praxis_requirement_create",
                "praxis_requirement_get",
                "praxis_requirement_transition",
                "praxis_context_build",
                "praxis_context_get",
                "praxis_context_diff",
                "praxis_worktree_create",
                "praxis_worktree_list",
                "praxis_skill_search",
                "praxis_skill_route",
                "praxis_gate_run",
                "praxis_artifact_register",
                "praxis_artifact_list",
                "praxis_session_start",
                "praxis_session_finish",
                "codegraph_status",
                "skill_route",
                "skill_inspect",
            } <= names
            templates = await session.list_resource_templates()
            assert any(
                str(template.uriTemplate).startswith("praxis://skills/")
                for template in templates.resourceTemplates
            )
            resource = await session.read_resource(
                AnyUrl("praxis://skills/system/dbx-database-investigation")
            )
            content = resource.contents[0]
            assert isinstance(content, TextResourceContents)
            assert "DBX 数据库调查" in content.text
            result = await session.call_tool("skill_route", {"intent": "核对数据库表结构"})
            assert result.structuredContent is not None
            assert result.structuredContent["ok"] is True
            workspace_result = await session.call_tool(
                "praxis_workspace_get", {"session_id": "SES-ARCH"}
            )
            assert workspace_result.structuredContent is not None
            assert workspace_result.structuredContent["ok"] is True
            system_result = await session.call_tool(
                "praxis_system_get", {"session_id": "SES-ARCH", "system_id": "demo"}
            )
            assert system_result.structuredContent is not None
            assert system_result.structuredContent["data"]["id"] == "demo"
            requirement_result = await session.call_tool(
                "praxis_requirement_get",
                {"session_id": "SES-ARCH", "requirement_id": requirement_id},
            )
            assert requirement_result.structuredContent is not None
            assert requirement_result.structuredContent["ok"] is True
            context_result = await session.call_tool(
                "praxis_context_get",
                {"session_id": "SES-CODER", "context_id": "CTX-TEST"},
            )
            assert context_result.structuredContent is not None
            assert context_result.structuredContent["ok"] is True
            skill_result = await session.call_tool(
                "praxis_skill_search", {"session_id": "SES-CODER", "query": "DBX"}
            )
            assert skill_result.structuredContent is not None
            assert skill_result.structuredContent["ok"] is True
            artifact_result = await session.call_tool(
                "praxis_artifact_list",
                {"session_id": "SES-CODER", "requirement_id": requirement_id},
            )
            assert artifact_result.structuredContent is not None
            assert artifact_result.structuredContent["ok"] is True
            denied = await session.call_tool(
                "praxis_execute", {"operation": "requirement.complete", "arguments": {}}
            )
            assert denied.structuredContent is not None
            assert denied.structuredContent["code"] == "MCP_SESSION_REQUIRED"

            for uri in (
                "praxis://contexts/CTX-TEST",
                f"praxis://artifacts/{artifact_id}",
                f"praxis://requirements/{requirement_id}/overview",
                "praxis://systems/demo/portrait",
            ):
                loaded = await session.read_resource(AnyUrl(uri))
                assert loaded.contents

    asyncio.run(exercise())
