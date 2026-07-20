from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from praxis.application import PraxisApplication
from praxis.skills.registry import SkillRegistry


def execute(
    root: Path | str, operation: str, arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    return PraxisApplication(root).execute(operation, arguments).to_dict()


def create_server(root: Path | str) -> FastMCP:
    workspace = Path(root)
    server = FastMCP("Praxis V2", json_response=True)

    @server.tool()
    def praxis_execute(operation: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a Praxis service operation and return the canonical result envelope."""
        return execute(workspace, operation, arguments)

    @server.tool()
    def codegraph_status(project_id: str) -> dict[str, Any]:
        """Return current CodeGraph freshness without querying a stale graph."""
        return execute(workspace, "codegraph.status", {"project_id": project_id})

    @server.tool()
    def codegraph_query(project_id: str, expression: str) -> dict[str, Any]:
        """Query CodeGraph after enforcing freshness."""
        return execute(
            workspace,
            "codegraph.query",
            {"project_id": project_id, "target": expression},
        )

    @server.tool()
    def codegraph_explore(project_id: str, target: str) -> dict[str, Any]:
        """Explore a fresh CodeGraph target."""
        return execute(workspace, "codegraph.explore", {"project_id": project_id, "target": target})

    @server.tool()
    def codegraph_node(project_id: str, node_id: str) -> dict[str, Any]:
        """Read a node only after enforcing CodeGraph freshness."""
        return execute(workspace, "codegraph.node", {"project_id": project_id, "target": node_id})

    @server.tool()
    def codegraph_affected(project_id: str) -> dict[str, Any]:
        """Return affected nodes after enforcing freshness."""
        return execute(workspace, "codegraph.affected", {"project_id": project_id})

    @server.tool()
    def skill_route(intent: str) -> dict[str, Any]:
        """Route an intent to the smallest matching Skill set."""
        return execute(workspace, "skill.route", {"intent": intent})

    @server.tool()
    def skill_inspect(skill_id: str) -> dict[str, Any]:
        """Inspect version, origin, risk, tools, hash, and context budget for a Skill."""
        return execute(workspace, "skill.inspect", {"id": skill_id})

    @server.resource("praxis://skills/{skill_type}/{skill_id}")
    def skill_resource(skill_type: str, skill_id: str) -> str:
        """Read a versioned Praxis Skill content asset."""
        return SkillRegistry.bundled().resource(f"praxis://skills/{skill_type}/{skill_id}")

    return server


def serve(root: Path | str) -> None:
    create_server(root).run(transport="stdio")
