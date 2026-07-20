from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextResourceContents
from pydantic import AnyUrl


def test_mcp_stdio_exposes_tools_resources_and_shared_results(tmp_path: Path) -> None:
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
                "codegraph_status",
                "codegraph_query",
                "codegraph_explore",
                "codegraph_node",
                "codegraph_affected",
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
            assert "DBX database investigation" in content.text
            result = await session.call_tool("skill_route", {"intent": "核对数据库表结构"})
            assert result.structuredContent is not None
            assert result.structuredContent["ok"] is True

    asyncio.run(exercise())
