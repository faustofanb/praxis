from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from praxis.agents.service import AgentSessionService
from praxis.application import PraxisApplication
from praxis.mcp.broker import McpBrokerService
from praxis.naming.requirement import RequirementPathPolicy, requirement_document
from praxis.portraits.service import PortraitService
from praxis.skills.registry import SkillRegistry
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService

_UNSCOPED_READS = {
    "version",
    "workspace.inspect",
    "skill.inspect",
    "skill.list",
    "skill.search",
    "skill.route",
    "portrait.show",
    "portrait.diff",
    "context.show",
    "context.diff",
    "artifact.list",
    "artifact.verify",
    "audit.list",
    "audit.show",
    "audit.verify",
}


def execute(
    root: Path | str, operation: str, arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    if operation not in _UNSCOPED_READS:
        return {
            "ok": False,
            "code": "MCP_SESSION_REQUIRED",
            "data": {"operation": operation},
            "diagnostics": [],
        }
    return PraxisApplication(root).execute(operation, arguments).to_dict()


def create_server(root: Path | str) -> FastMCP:
    workspace = Path(root)
    server = FastMCP("Praxis V3", json_response=True)

    def invoke(session_id: str, capability: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return McpBrokerService(workspace).invoke(session_id, capability, arguments).to_dict()

    @server.tool()
    def praxis_execute(operation: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute an unscoped read-only Praxis operation; writes require the Broker tool."""
        return execute(workspace, operation, arguments)

    @server.tool()
    def praxis_broker_invoke(
        session_id: str, capability: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Invoke one capability through a session-scoped Praxis grant."""
        return invoke(session_id, capability, arguments or {})

    @server.tool()
    def praxis_workspace_get(session_id: str) -> dict[str, Any]:
        return invoke(session_id, "workspace.read", {})

    @server.tool()
    def praxis_system_get(session_id: str, system_id: str) -> dict[str, Any]:
        result = McpBrokerService(workspace).invoke(session_id, "workspace.read", {})
        if result.ok:
            system = next(
                (item for item in result.data.get("systems", []) if item["id"] == system_id),
                None,
            )
            return {
                "ok": bool(system),
                "code": "OK" if system else "SYSTEM_NOT_FOUND",
                "data": system or {},
                "diagnostics": [],
            }
        return result.to_dict()

    @server.tool()
    def praxis_system_scan(session_id: str, project_id: str) -> dict[str, Any]:
        return invoke(session_id, "system.scan", {"project_id": project_id})

    @server.tool()
    def praxis_requirement_create(
        session_id: str,
        short_name: str,
        request: str,
        systems: list[str],
        domains: list[str],
    ) -> dict[str, Any]:
        return invoke(
            session_id,
            "requirement.create",
            {"short_name": short_name, "request": request, "systems": systems, "domains": domains},
        )

    @server.tool()
    def praxis_requirement_get(session_id: str, requirement_id: str) -> dict[str, Any]:
        return invoke(
            session_id, "requirement.read", {"requirement_id": requirement_id}
        )

    @server.tool()
    def praxis_requirement_transition(
        session_id: str, requirement_id: str, status: str
    ) -> dict[str, Any]:
        return invoke(
            session_id,
            "requirement.transition",
            {"requirement_id": requirement_id, "status": status},
        )

    @server.tool()
    def praxis_requirement_reopen(
        session_id: str, requirement_id: str, reason: str
    ) -> dict[str, Any]:
        return invoke(
            session_id,
            "requirement.reopen",
            {"requirement_id": requirement_id, "reason": reason},
        )

    @server.tool()
    def praxis_requirement_update_progress(
        session_id: str, task_id: str, message: str
    ) -> dict[str, Any]:
        return invoke(
            session_id,
            "requirement.update_progress",
            {"task_id": task_id, "message": message},
        )

    @server.tool()
    def praxis_context_build(session_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return invoke(session_id, "context.build", arguments)

    @server.tool()
    def praxis_context_get(session_id: str, context_id: str) -> dict[str, Any]:
        return invoke(session_id, "context.read", {"context_id": context_id})

    @server.tool()
    def praxis_context_diff(
        session_id: str, context_id: str, previous_context_id: str
    ) -> dict[str, Any]:
        return invoke(
            session_id,
            "context.diff",
            {"context_id": context_id, "previous_context_id": previous_context_id},
        )

    @server.tool()
    def praxis_worktree_create(session_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return invoke(session_id, "worktree.create", arguments)

    @server.tool()
    def praxis_worktree_preview(session_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return invoke(session_id, "worktree.preview", arguments)

    @server.tool()
    def praxis_worktree_ensure(session_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return invoke(session_id, "worktree.ensure", arguments)

    @server.tool()
    def praxis_worktree_prepare(session_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return invoke(session_id, "worktree.prepare", arguments)

    @server.tool()
    def praxis_worktree_list(session_id: str) -> dict[str, Any]:
        return invoke(session_id, "worktree.status", {})

    @server.tool()
    def praxis_worktree_status(session_id: str) -> dict[str, Any]:
        return invoke(session_id, "worktree.status", {})

    @server.tool()
    def praxis_skill_search(session_id: str, query: str) -> dict[str, Any]:
        return invoke(session_id, "skill.search", {"query": query})

    @server.tool()
    def praxis_skill_route(session_id: str, intent: str, budget: int = 2000) -> dict[str, Any]:
        return invoke(session_id, "skill.route", {"intent": intent, "budget": budget})

    @server.tool()
    def praxis_skill_route_node(
        session_id: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        return invoke(session_id, "skill.plan", arguments)

    @server.tool()
    def praxis_skill_invoke(
        session_id: str,
        requirement_id: str,
        node: str,
        skill_id: str,
        approved: bool = False,
    ) -> dict[str, Any]:
        return invoke(
            session_id,
            "skill.invoke",
            {
                "requirement_id": requirement_id,
                "node": node,
                "skill_id": skill_id,
                "session_id": session_id,
                "approved": approved,
            },
        )

    @server.tool()
    def praxis_skill_complete(
        session_id: str, invocation_id: str, outcome: str = "completed"
    ) -> dict[str, Any]:
        return invoke(
            session_id,
            "skill.complete",
            {"invocation_id": invocation_id, "outcome": outcome},
        )

    @server.tool()
    def praxis_skill_complete_node(
        session_id: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        arguments = {**arguments, "session_id": session_id}
        return invoke(session_id, "skill.complete_node", arguments)

    @server.tool()
    def praxis_skill_gate(
        session_id: str, requirement_id: str, node: str
    ) -> dict[str, Any]:
        return invoke(
            session_id,
            "skill.gate",
            {"requirement_id": requirement_id, "node": node},
        )

    @server.tool()
    def praxis_gate_run(session_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return invoke(session_id, "gate.run", arguments)

    @server.tool()
    def praxis_gate_explain(session_id: str, event: str) -> dict[str, Any]:
        return invoke(session_id, "gate.explain", {"event": event})

    @server.tool()
    def praxis_artifact_register(session_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return invoke(session_id, "artifact.register", arguments)

    @server.tool()
    def praxis_artifact_list(
        session_id: str, requirement_id: str | None = None
    ) -> dict[str, Any]:
        return invoke(session_id, "artifact.read", {"requirement_id": requirement_id})

    @server.tool()
    def praxis_session_start(arguments: dict[str, Any]) -> dict[str, Any]:
        return AgentSessionService(workspace).start(**arguments).to_dict()

    @server.tool()
    def praxis_session_finish(session_id: str, status: str = "completed") -> dict[str, Any]:
        return AgentSessionService(workspace).finish(session_id, status).to_dict()

    @server.tool()
    def praxis_session_receipt(session_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return AgentSessionService(workspace).receipt(session_id, **arguments).to_dict()

    @server.tool()
    def codegraph_status(
        project_id: str = "",
        binding_id: str = "",
        worktree: str = "",
    ) -> dict[str, Any]:
        arguments = {}
        if project_id:
            arguments["project_id"] = project_id
        if binding_id:
            arguments["binding_id"] = binding_id
        if worktree:
            arguments["worktree"] = worktree
        return execute(workspace, "codegraph.status", arguments)

    @server.tool()
    def skill_route(intent: str) -> dict[str, Any]:
        return execute(workspace, "skill.route", {"intent": intent})

    @server.tool()
    def skill_inspect(skill_id: str) -> dict[str, Any]:
        return execute(workspace, "skill.inspect", {"id": skill_id})

    @server.resource("praxis://skills/{skill_type}/{skill_id}")
    def skill_resource(skill_type: str, skill_id: str) -> str:
        return SkillRegistry.workspace(workspace).resource(
            f"praxis://skills/{skill_type}/{skill_id}"
        )

    @server.resource("praxis://contexts/{context_id}")
    def context_resource(context_id: str) -> str:
        context = StateStore(workspace).get("context", context_id)
        if not context:
            raise KeyError(context_id)
        return Path(context["path"]).read_text(encoding="utf-8")

    @server.resource("praxis://artifacts/{artifact_id}")
    def artifact_resource(artifact_id: str) -> str:
        artifact = StateStore(workspace).get("artifact", artifact_id)
        if not artifact:
            raise KeyError(artifact_id)
        return json.dumps(artifact, ensure_ascii=False, indent=2)

    @server.resource("praxis://requirements/{requirement_id}/overview")
    def requirement_resource(requirement_id: str) -> str:
        store = StateStore(workspace)
        requirement = store.requirement(requirement_id)
        if not requirement:
            raise KeyError(requirement_id)
        facts = WorkspaceService(workspace).load()
        path = RequirementPathPolicy(
            workspace / facts["knowledge_root"]
        ).locate_requirement_path(requirement_id, requirement["short_name"])
        return (path / requirement_document("overview")).read_text(encoding="utf-8")

    @server.resource("praxis://systems/{system_id}/portrait")
    def system_portrait_resource(system_id: str) -> str:
        facts = WorkspaceService(workspace).load()
        projects = [item for item in facts["projects"] if item["system_id"] == system_id]
        if not projects:
            raise KeyError(system_id)
        contents = []
        for project in projects:
            path = PortraitService(workspace).path(project["id"])
            if path.is_file():
                contents.append(path.read_text(encoding="utf-8"))
        return "\n\n".join(contents)

    return server


def serve(root: Path | str) -> None:
    create_server(root).run(transport="stdio")
