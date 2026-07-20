from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

from praxis.knowledge.requirements import RequirementService
from praxis.mcp.broker import McpBrokerService
from praxis.mcp.server import create_server
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService


def test_canonical_mcp_tools_delegate_to_application_and_broker(tmp_path: Path) -> None:
    repo = tmp_path / "backend"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='demo'\n")
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[Project("backend", "python", "backend", "main")],
    )
    requirement_id = RequirementService(tmp_path).create(
        "报表查询优化", "核对报表查询", ["demo"], []
    ).data["requirement_id"]
    store = StateStore(tmp_path)
    context_path = tmp_path / "context.md"
    context_path.write_text("# 上下文\n")
    store.set(
        "context",
        "CTX-OLD",
        {"context_id": "CTX-OLD", "path": str(context_path), "sources": []},
    )
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
    broker = McpBrokerService(tmp_path)
    broker.grant("SES-BOOT", "architect", ["requirement.create"])
    broker.grant(
        "SES-ARCH",
        "architect",
        [
            "workspace.read",
            "system.scan",
            "requirement.read",
            "requirement.transition",
            "context.build",
            "context.read",
            "context.diff",
        ],
        requirement_id=requirement_id,
        worktree="req/example",
    )
    broker.grant(
        "SES-CODER",
        "coder",
        [
            "requirement.update_progress",
            "worktree.status",
            "skill.search",
            "skill.route",
            "gate.run",
            "gate.explain",
            "artifact.register",
            "artifact.read",
        ],
        requirement_id=requirement_id,
        worktree="req/example",
    )
    artifact = tmp_path / "report.txt"
    artifact.write_text("passed")
    server = create_server(tmp_path)

    async def exercise() -> None:
        async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            _, structured = await server.call_tool(name, arguments)
            assert structured is not None
            return cast(dict[str, Any], structured)

        assert (await call("praxis_execute", {"operation": "version"}))["ok"]
        assert not (
            await call("praxis_execute", {"operation": "requirement.complete"})
        )["ok"]
        assert (
            await call(
                "praxis_broker_invoke",
                {
                    "session_id": "SES-ARCH",
                    "capability": "requirement.read",
                    "arguments": {"requirement_id": requirement_id},
                },
            )
        )["ok"]
        assert (await call("praxis_workspace_get", {"session_id": "SES-ARCH"}))["ok"]
        assert (
            await call(
                "praxis_system_get", {"session_id": "SES-ARCH", "system_id": "demo"}
            )
        )["ok"]
        assert (
            await call(
                "praxis_system_scan",
                {"session_id": "SES-ARCH", "project_id": "backend"},
            )
        )["ok"]
        created = await call(
            "praxis_requirement_create",
            {
                "session_id": "SES-BOOT",
                "short_name": "库存数量校验",
                "request": "核对库存数量",
                "systems": ["demo"],
                "domains": [],
            },
        )
        assert created["ok"]
        assert (
            await call(
                "praxis_requirement_get",
                {"session_id": "SES-ARCH", "requirement_id": requirement_id},
            )
        )["ok"]
        assert (
            await call(
                "praxis_requirement_transition",
                {
                    "session_id": "SES-ARCH",
                    "requirement_id": requirement_id,
                    "status": "investigating",
                },
            )
        )["ok"]
        context = await call(
            "praxis_context_build",
            {
                "session_id": "SES-ARCH",
                "arguments": {
                    "requirement_id": requirement_id,
                    "project_id": "backend",
                    "stage": "backend",
                    "agent_role": "coder",
                    "token_budget": 8_000,
                },
            },
        )
        context_id = context["data"]["context_id"]
        assert (
            await call(
                "praxis_context_get",
                {"session_id": "SES-ARCH", "context_id": context_id},
            )
        )["ok"]
        assert (
            await call(
                "praxis_context_diff",
                {
                    "session_id": "SES-ARCH",
                    "context_id": context_id,
                    "previous_context_id": "CTX-OLD",
                },
            )
        )["ok"]
        assert not (
            await call(
                "praxis_requirement_update_progress",
                {"session_id": "SES-CODER", "task_id": "missing", "message": "done"},
            )
        )["ok"]
        assert not (
            await call("praxis_worktree_list", {"session_id": "SES-CODER"})
        )["ok"]
        assert not (
            await call("praxis_worktree_status", {"session_id": "SES-CODER"})
        )["ok"]
        assert (
            await call(
                "praxis_skill_search", {"session_id": "SES-CODER", "query": "DBX"}
            )
        )["ok"]
        assert (
            await call(
                "praxis_skill_route", {"session_id": "SES-CODER", "intent": "数据库"}
            )
        )["ok"]
        assert (
            await call(
                "praxis_gate_explain", {"session_id": "SES-CODER", "event": "pre_commit"}
            )
        )["ok"]
        registered = await call(
            "praxis_artifact_register",
            {
                "session_id": "SES-CODER",
                "arguments": {
                    "requirement_id": requirement_id,
                    "artifact_type": "test-report",
                    "source_path": str(artifact),
                    "stage": "verify",
                },
            },
        )
        assert registered["ok"]
        assert (
            await call(
                "praxis_artifact_list",
                {"session_id": "SES-CODER", "requirement_id": requirement_id},
            )
        )["ok"]
        started = await call(
            "praxis_session_start",
            {
                "arguments": {
                    "agent_type": "codex",
                    "role": "coder",
                    "requirement_id": requirement_id,
                    "context_id": context_id,
                    "worktree": "req/example",
                    "requested_capabilities": ["requirement.read"],
                }
            },
        )
        assert (
            await call(
                "praxis_session_finish",
                {"session_id": started["data"]["session_id"], "status": "completed"},
            )
        )["ok"]
        assert (await call("codegraph_status", {"project_id": "backend"}))["code"] == (
            "MCP_SESSION_REQUIRED"
        )
        assert (await call("skill_route", {"intent": "数据库"}))["ok"]
        assert (
            await call("skill_inspect", {"skill_id": "dbx-database-investigation"})
        )["ok"]

    asyncio.run(exercise())
