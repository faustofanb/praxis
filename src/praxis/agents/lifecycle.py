from __future__ import annotations

from pathlib import Path
from typing import Any

from praxis.agents.service import AgentSessionService
from praxis.mcp.broker import McpBrokerService
from praxis.result import Result
from praxis.storage.sqlite import StateStore


class AgentLifecycle:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.store = StateStore(self.root)

    def run(self, event: str, context: dict[str, Any]) -> Result:
        session_id = str(context.get("session_id", ""))
        if not session_id:
            return Result(False, "AGENT_SESSION_REQUIRED")
        if event == "before-tool":
            return McpBrokerService(self.root).authorize(
                session_id, str(context.get("capability", "")), context.get("arguments", {})
            )
        if event == "after-tool":
            audit_id = self.store.audit(
                "agent.tool_completed",
                str(context.get("code", "OK")),
                {
                    "session_id": session_id,
                    "capability": context.get("capability"),
                },
            )
            return Result(True, data={"audit_id": audit_id})
        if event == "session-stop":
            return AgentSessionService(self.root).finish(
                session_id, str(context.get("status", "completed"))
            )
        return Result(False, "AGENT_LIFECYCLE_EVENT_INVALID", data={"event": event})
