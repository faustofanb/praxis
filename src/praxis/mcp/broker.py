from __future__ import annotations

import json
import re
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Any

from praxis.documents.atomic_writer import atomic_write_text
from praxis.gates.policies import allowed_paths_gate
from praxis.gates.sql import inspect_sql
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService

_SERVER_ID = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


class CapabilityRisk(StrEnum):
    READ = "read"
    WORKSPACE_WRITE = "workspace_write"
    EXTERNAL_WRITE = "external_write"
    DESTRUCTIVE = "destructive"


_CAPABILITIES: dict[str, tuple[str, CapabilityRisk]] = {
    "workspace.read": ("workspace.inspect", CapabilityRisk.READ),
    "system.scan": ("portrait.scan", CapabilityRisk.WORKSPACE_WRITE),
    "requirement.create": ("requirement.new", CapabilityRisk.WORKSPACE_WRITE),
    "requirement.read": ("requirement.show", CapabilityRisk.READ),
    "requirement.transition": ("requirement.transition", CapabilityRisk.WORKSPACE_WRITE),
    "requirement.update_progress": ("task.progress", CapabilityRisk.WORKSPACE_WRITE),
    "code.search": ("codegraph.query", CapabilityRisk.READ),
    "code.explore": ("codegraph.explore", CapabilityRisk.READ),
    "code.impact": ("codegraph.affected", CapabilityRisk.READ),
    "code.affected_tests": ("codegraph.affected", CapabilityRisk.READ),
    "database.connections": ("database.connections", CapabilityRisk.READ),
    "database.schema": ("database.query", CapabilityRisk.READ),
    "database.query": ("database.query", CapabilityRisk.READ),
    "database.write": ("database.query", CapabilityRisk.EXTERNAL_WRITE),
    "runtime.process": ("runtime.diagnose", CapabilityRisk.READ),
    "runtime.port": ("runtime.diagnose", CapabilityRisk.READ),
    "runtime.container": ("runtime.diagnose", CapabilityRisk.READ),
    "worktree.create": ("worktree.create", CapabilityRisk.WORKSPACE_WRITE),
    "worktree.status": ("worktree.list", CapabilityRisk.READ),
    "gate.run": ("gate.run", CapabilityRisk.WORKSPACE_WRITE),
    "gate.explain": ("gate.explain", CapabilityRisk.READ),
    "artifact.register": ("artifact.add", CapabilityRisk.WORKSPACE_WRITE),
    "artifact.read": ("artifact.list", CapabilityRisk.READ),
    "context.build": ("context.build", CapabilityRisk.WORKSPACE_WRITE),
    "context.read": ("context.show", CapabilityRisk.READ),
    "context.diff": ("context.diff", CapabilityRisk.READ),
    "skill.search": ("skill.search", CapabilityRisk.READ),
    "skill.route": ("skill.route", CapabilityRisk.READ),
    "skill.plan": ("skill.route-node", CapabilityRisk.WORKSPACE_WRITE),
    "skill.invoke": ("skill.invoke", CapabilityRisk.WORKSPACE_WRITE),
    "skill.complete": ("skill.complete", CapabilityRisk.WORKSPACE_WRITE),
    "skill.gate": ("skill.gate", CapabilityRisk.READ),
    "deployment.execute": ("deployment.execute", CapabilityRisk.DESTRUCTIVE),
}

_ROLE_CAPABILITIES = {
    "architect": {
        "workspace.read",
        "system.scan",
        "requirement.create",
        "requirement.read",
        "requirement.transition",
        "context.build",
        "context.read",
        "context.diff",
        "skill.search",
        "skill.route",
        "skill.plan",
        "skill.invoke",
        "skill.complete",
        "skill.gate",
        "code.search",
        "code.explore",
        "code.impact",
        "worktree.status",
    },
    "investigator": {
        "workspace.read",
        "system.scan",
        "requirement.read",
        "requirement.transition",
        "context.build",
        "context.read",
        "context.diff",
        "skill.search",
        "skill.route",
        "skill.plan",
        "skill.invoke",
        "skill.complete",
        "skill.gate",
        "code.search",
        "code.explore",
        "code.impact",
        "database.connections",
        "database.schema",
        "database.query",
        "runtime.process",
        "runtime.port",
        "runtime.container",
    },
    "coder": {
        "workspace.read",
        "requirement.read",
        "requirement.update_progress",
        "code.search",
        "code.explore",
        "code.impact",
        "code.affected_tests",
        "worktree.status",
        "gate.run",
        "gate.explain",
        "artifact.register",
        "artifact.read",
        "context.read",
        "skill.search",
        "skill.route",
        "skill.plan",
        "skill.invoke",
        "skill.complete",
        "skill.gate",
    },
    "reviewer": {
        "workspace.read",
        "requirement.read",
        "code.search",
        "code.explore",
        "code.impact",
        "gate.run",
        "gate.explain",
        "worktree.status",
        "artifact.read",
        "context.read",
        "skill.plan",
        "skill.invoke",
        "skill.complete",
        "skill.gate",
    },
    "tester": {
        "workspace.read",
        "requirement.read",
        "code.affected_tests",
        "gate.run",
        "artifact.register",
        "artifact.read",
        "context.read",
        "skill.plan",
        "skill.invoke",
        "skill.complete",
        "skill.gate",
    },
    "database": {
        "workspace.read",
        "requirement.read",
        "database.connections",
        "database.schema",
        "database.query",
        "database.write",
        "artifact.register",
        "artifact.read",
        "context.read",
        "skill.plan",
        "skill.invoke",
        "skill.complete",
        "skill.gate",
    },
    "release": {
        "workspace.read",
        "requirement.read",
        "worktree.status",
        "gate.run",
        "artifact.register",
        "artifact.read",
        "context.read",
        "skill.plan",
        "skill.invoke",
        "skill.complete",
        "skill.gate",
        "deployment.execute",
    },
}

Executor = Callable[[str, dict[str, Any]], Result]


class McpBrokerService:
    def __init__(self, root: Path | str, *, execute: Executor | None = None):
        self.root = Path(root)
        self.store = StateStore(self.root)
        self.execute = execute or self._execute

    def grant(
        self,
        session_id: str,
        role: str,
        requested_capabilities: list[str],
        *,
        requirement_id: str | None = None,
        worktree: str | None = None,
        approved_external: bool = False,
    ) -> Result:
        if role not in _ROLE_CAPABILITIES:
            return Result(False, "AGENT_ROLE_INVALID")
        allowed = []
        denied = []
        role_capabilities = _ROLE_CAPABILITIES[role]
        for capability in sorted(set(requested_capabilities)):
            definition = _CAPABILITIES.get(capability)
            permitted = bool(definition and capability in role_capabilities)
            if permitted:
                risk = definition[1]
                if risk == CapabilityRisk.WORKSPACE_WRITE:
                    if capability == "requirement.create":
                        permitted = True
                    elif capability in {"skill.plan", "skill.invoke", "skill.complete"}:
                        permitted = bool(requirement_id)
                    else:
                        permitted = bool(requirement_id and worktree)
                elif risk == CapabilityRisk.EXTERNAL_WRITE:
                    permitted = approved_external
                elif risk == CapabilityRisk.DESTRUCTIVE:
                    permitted = False
            (allowed if permitted else denied).append(capability)
        data = {
            "grant_id": f"GRANT-{session_id}",
            "session_id": session_id,
            "role": role,
            "requirement_id": requirement_id,
            "worktree": worktree,
            "allowed_capabilities": allowed,
            "denied_capabilities": denied,
            "approved_external": approved_external,
        }
        self.store.set("mcp_grant", session_id, data)
        audit_id = self.store.audit("mcp.grant", "OK", data)
        return Result(True, data={**data, "audit_id": audit_id})

    def invoke(self, session_id: str, capability: str, arguments: dict[str, Any]) -> Result:
        authorization = self.authorize(session_id, capability, arguments)
        if not authorization.ok:
            return authorization
        grant = self.store.get("mcp_grant", session_id)
        assert grant is not None
        operation, _ = _CAPABILITIES[capability]
        values = dict(arguments)
        if capability == "database.write":
            values["approved"] = True
            binding = self.store.get("worktree", grant["worktree"])
            write_context = dict(values.get("write_context", {}))
            write_context.update(
                {
                    "requirement_id": grant["requirement_id"],
                    "stage": binding.get("stage") if binding else None,
                    "approval": f"MCP Grant {grant['grant_id']}",
                }
            )
            values["write_context"] = write_context
        result = self.execute(operation, values)
        self.store.audit(
            "mcp.invoke",
            result.code,
            {"session_id": session_id, "capability": capability, "operation": operation},
        )
        return result

    def authorize(
        self, session_id: str, capability: str, arguments: dict[str, Any] | None = None
    ) -> Result:
        grant = self.store.get("mcp_grant", session_id)
        if not grant:
            return Result(False, "MCP_SESSION_NOT_FOUND")
        if capability not in grant["allowed_capabilities"]:
            return Result(False, "MCP_CAPABILITY_DENIED", data={"capability": capability})
        values = arguments or {}
        scoped_capabilities = {
            "requirement.read",
            "requirement.transition",
            "skill.plan",
            "skill.invoke",
            "skill.gate",
        }
        if capability in scoped_capabilities and values.get("requirement_id") != grant.get(
            "requirement_id"
        ):
            return Result(False, "MCP_REQUIREMENT_SCOPE_MISMATCH")
        if capability == "skill.complete":
            invocation = self.store.get(
                "skill_invocation", str(values.get("invocation_id", ""))
            )
            if not invocation or invocation.get("requirement_id") != grant.get(
                "requirement_id"
            ):
                return Result(False, "MCP_REQUIREMENT_SCOPE_MISMATCH")
        if capability == "database.write":
            sql = inspect_sql(str(values.get("sql", "")))
            if not sql.ok or sql.data.get("kind") != "write":
                return Result(False, sql.code, data=sql.data)
        paths = values.get("paths", [])
        if paths and grant.get("worktree"):
            binding = self.store.get("worktree", grant["worktree"])
            if not binding:
                return Result(False, "WORKTREE_BINDING_INVALID")
            path_gate = allowed_paths_gate(
                paths, binding.get("allowed_paths", ["**"]), binding.get("forbidden_paths", [])
            )
            if not path_gate.ok:
                return path_gate
        return Result(True, data={"session_id": session_id, "capability": capability})

    def capabilities(self) -> Result:
        return Result(
            True,
            data={
                "capabilities": [
                    {"id": capability, "operation": operation, "risk": risk.value}
                    for capability, (operation, risk) in sorted(_CAPABILITIES.items())
                ]
            },
        )

    def register_server(
        self,
        server_id: str,
        command: list[str],
        capabilities: list[str],
        risk: str,
        *,
        approved: bool = False,
    ) -> Result:
        if not _SERVER_ID.fullmatch(server_id) or not command:
            return Result(False, "MCP_SERVER_INVALID")
        if risk not in CapabilityRisk:
            return Result(False, "MCP_RISK_INVALID")
        unknown = sorted(set(capabilities) - _CAPABILITIES.keys())
        if unknown:
            return Result(False, "MCP_CAPABILITY_UNKNOWN", data={"capabilities": unknown})
        if any(re.search(r"(?i)(password|secret|token|api[_-]?key)", item) for item in command):
            return Result(False, "MCP_SERVER_SECRET_FORBIDDEN")
        data = {
            "server_id": server_id,
            "transport": "stdio",
            "command": command,
            "capabilities": sorted(set(capabilities)),
            "risk": risk,
            "status": "approved" if approved else "pending-review",
        }
        self.store.set("mcp_server", server_id, data)
        self.store.audit("mcp.server_registered", "OK", data)
        return Result(True, data=data)

    def render(self, session_id: str) -> Result:
        grant = self.store.get("mcp_grant", session_id)
        if not grant:
            return Result(False, "MCP_SESSION_NOT_FOUND")
        allowed = set(grant["allowed_capabilities"])
        servers = [
            server
            for server in self.store.list_scope("mcp_server")
            if server["status"] == "approved" and allowed & set(server["capabilities"])
        ]
        workspace = WorkspaceService(self.root).load()["workspace"]
        path = self.root / workspace["generated_root"] / "MCP配置" / f"{session_id}.json"
        payload = {
            "session_id": session_id,
            "servers": {
                server["server_id"]: {
                    "command": server["command"][0],
                    "args": server["command"][1:],
                    "capabilities": sorted(allowed & set(server["capabilities"])),
                }
                for server in servers
            },
        }
        atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return Result(True, data={**payload, "path": str(path)})

    def _execute(self, operation: str, arguments: dict[str, Any]) -> Result:
        from praxis.application import PraxisApplication

        return PraxisApplication(self.root).execute(operation, arguments)
