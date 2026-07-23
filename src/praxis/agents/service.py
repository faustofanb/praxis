from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from praxis.context.service import ContextBuildRequest, ContextCompiler
from praxis.documents.atomic_writer import atomic_write_text
from praxis.mcp.broker import McpBrokerService
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService, _array, _quote
from praxis.worktree.service import resolve_worktree_binding

_AGENT_TYPES = {"codex", "claude-code", "oh-my-pi"}
_AGENT_COMMANDS = {"codex": "codex", "claude-code": "claude", "oh-my-pi": "pi"}


class AgentSessionService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.store = StateStore(self.root)

    def install(self, agent_type: str) -> Result:
        if agent_type not in _AGENT_TYPES:
            return Result(False, "AGENT_TYPE_INVALID")
        workspace = WorkspaceService(self.root).load()["workspace"]
        path = (
            self.root
            / workspace["generated_root"]
            / "Agent适配器"
            / agent_type
            / "adapter.json"
        )
        command = _AGENT_COMMANDS[agent_type]
        payload = {
            "agent_type": agent_type,
            "command": [command],
            "thin_adapter": True,
            "mcp": {
                "command": "praxis",
                "args": ["--root", str(self.root.resolve()), "mcp", "serve"],
            },
        }
        atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        audit_id = self.store.audit(
            "agent.adapter_installed", "OK", {"agent_type": agent_type, "path": str(path)}
        )
        return Result(
            True,
            data={
                **payload,
                "path": str(path),
                "executable_available": shutil.which(command) is not None,
                "audit_id": audit_id,
            },
        )

    def start(
        self,
        agent_type: str,
        role: str,
        requirement_id: str,
        context_id: str,
        worktree: str,
        requested_capabilities: list[str],
        *,
        skills: list[str] | None = None,
        approved_external: bool = False,
        parent_session_id: str = "",
        intent: str = "",
    ) -> Result:
        if agent_type not in _AGENT_TYPES:
            return Result(False, "AGENT_TYPE_INVALID")
        if not self.store.requirement(requirement_id):
            return Result(False, "REQUIREMENT_NOT_FOUND")
        if parent_session_id and not self.store.get("agent_session", parent_session_id):
            return Result(False, "AGENT_PARENT_SESSION_NOT_FOUND")
        child_denied = {
            "requirement.transition",
            "requirement.reopen",
            "skill.gate",
            "worktree.create",
            "worktree.ensure",
        }
        denied_requests = sorted(set(requested_capabilities) & child_denied)
        if parent_session_id and denied_requests:
            return Result(
                False,
                "AGENT_CHILD_STATE_WRITE_DENIED",
                data={"capabilities": denied_requests},
            )
        resolved = resolve_worktree_binding(self.store, worktree)
        binding = resolved[1] if resolved else None
        if not binding or binding.get("requirement_id") != requirement_id:
            return Result(False, "WORKTREE_BINDING_INVALID")
        assert resolved is not None
        if context_id:
            if not self.store.get("context", context_id):
                return Result(False, "CONTEXT_NOT_FOUND")
        else:
            project_id = str(binding.get("repository_id", ""))
            if not project_id:
                return Result(False, "WORKTREE_PROJECT_UNRESOLVED")
            built = ContextCompiler(self.root).build(
                ContextBuildRequest(
                    requirement_id=requirement_id,
                    project_id=project_id,
                    stage=str(binding.get("stage", "development")),
                    agent_role=role,
                    intent=intent,
                    allowed_paths=tuple(binding.get("allowed_paths", [])),
                    forbidden_paths=tuple(binding.get("forbidden_paths", [])),
                    workflow_node="in_progress",
                )
            )
            if not built.ok:
                return built
            context_id = str(built.data["context_id"])
        timestamp = datetime.now(UTC)
        session_id = f"SES-{timestamp:%Y%m%dT%H%M%S}-{uuid4().hex[:8].upper()}"
        grant = McpBrokerService(self.root).grant(
            session_id,
            role,
            requested_capabilities,
            requirement_id=requirement_id,
            worktree=resolved[0],
            approved_external=approved_external,
        )
        if not grant.ok:
            return grant
        data = {
            "session_id": session_id,
            "agent_type": agent_type,
            "role": role,
            "requirement_id": requirement_id,
            "context_id": context_id,
            "worktree": resolved[0],
            "worktree_path": binding["path"],
            "skills": skills or [],
            "grant_id": grant.data["grant_id"],
            "allowed_capabilities": grant.data["allowed_capabilities"],
            "status": "ready",
            "started_at": timestamp.isoformat(),
            "coordination": {
                "fork_turns": "none",
                "context_mode": "compact_handoff",
                "requirement_state_owner": parent_session_id or session_id,
                "child_may_transition_requirement": False,
                "child_may_close_skill_gate": False,
            },
            "parent_session_id": parent_session_id,
        }
        self.store.set("agent_session", session_id, data)
        audit_id = self.store.audit("agent.session_started", "OK", data)
        return Result(True, data={**data, "audit_id": audit_id})

    def render(self, session_id: str) -> Result:
        session = self.store.get("agent_session", session_id)
        if not session:
            return Result(False, "AGENT_SESSION_NOT_FOUND")
        target = self._target(session_id)
        agent_type = session["agent_type"]
        if agent_type == "codex":
            path = target / "codex.toml"
            content = self._codex(session)
        elif agent_type == "claude-code":
            path = target / "claude-code.json"
            content = self._json_config(session)
        else:
            path = target / "oh-my-pi.json"
            content = self._json_config(session)
        atomic_write_text(path, content)
        handoff_path = target / "handoff.json"
        atomic_write_text(
            handoff_path,
            json.dumps(self._handoff(session), ensure_ascii=False, indent=2) + "\n",
        )
        self.store.audit("agent.config_rendered", "OK", {"session_id": session_id})
        return Result(
            True,
            data={"session_id": session_id, "files": [str(path), str(handoff_path)]},
        )

    def launch(self, session_id: str, *, execute: bool = False) -> Result:
        session = self.store.get("agent_session", session_id)
        if not session:
            return Result(False, "AGENT_SESSION_NOT_FOUND")
        if session.get("status") not in {"ready", "launched"}:
            return Result(False, "AGENT_SESSION_NOT_LAUNCHABLE")
        rendered = self.render(session_id)
        if not rendered.ok:
            return rendered
        context = self.store.get("context", str(session["context_id"])) or {}
        handoff_path = rendered.data["files"][1]
        prompt = (
            f"Read the Praxis handoff at {handoff_path} and context at "
            f"{context.get('path', '')} before doing any work."
        )
        command = [_AGENT_COMMANDS[session["agent_type"]], prompt]
        data: dict[str, Any] = {
            "session_id": session_id,
            "command": command,
            "cwd": session["worktree_path"],
            "config_files": rendered.data["files"],
            "executed": False,
        }
        if not execute:
            data["audit_id"] = self.store.audit("agent.launch_prepared", "OK", data)
            return Result(True, data=data)
        executable = shutil.which(command[0])
        if not executable:
            return Result(False, "AGENT_EXECUTABLE_NOT_FOUND", data={"command": command[0]})
        log_path = self.root / ".praxis" / "raw-logs" / f"agent-{session_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment.update(
            {
                "PRAXIS_SESSION_ID": session_id,
                "PRAXIS_AGENT_CONFIG": rendered.data["files"][0],
            }
        )
        with log_path.open("ab") as stream:
            process = subprocess.Popen(
                [executable, *command[1:]],
                cwd=session["worktree_path"],
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        session.update(
            {
                "status": "launched",
                "pid": process.pid,
                "launched_at": datetime.now(UTC).isoformat(),
                "log_path": str(log_path),
            }
        )
        self.store.set("agent_session", session_id, session)
        data.update({"executed": True, "pid": process.pid, "log_path": str(log_path)})
        data["audit_id"] = self.store.audit("agent.launched", "OK", data)
        return Result(True, data=data)

    def finish(self, session_id: str, status: str = "completed") -> Result:
        session = self.store.get("agent_session", session_id)
        if not session:
            return Result(False, "AGENT_SESSION_NOT_FOUND")
        session["status"] = status
        session["finished_at"] = datetime.now(UTC).isoformat()
        self.store.set("agent_session", session_id, session)
        self.store.audit("agent.session_finished", "OK", {"session_id": session_id})
        return Result(True, data=session)

    def sessions(self) -> Result:
        return Result(True, data={"sessions": self.store.list_scope("agent_session")})

    def receipt(
        self,
        session_id: str,
        *,
        changed_paths: list[str],
        decisions: list[str],
        blockers: list[str],
        follow_up: str = "",
    ) -> Result:
        session = self.store.get("agent_session", session_id)
        if not session:
            return Result(False, "AGENT_SESSION_NOT_FOUND")
        payload = {
            "session_id": session_id,
            "requirement_id": session["requirement_id"],
            "changed_paths": list(dict.fromkeys(changed_paths)),
            "decisions": list(dict.fromkeys(decisions)),
            "blockers": list(dict.fromkeys(blockers)),
            "follow_up": follow_up.strip(),
            "created_at": datetime.now(UTC).isoformat(),
        }
        serialized = json.dumps(payload, ensure_ascii=False)
        if len(serialized.encode("utf-8")) > 16_384:
            return Result(False, "AGENT_RECEIPT_TOO_LARGE", data={"limit_bytes": 16_384})
        self.store.set("agent_receipt", session_id, payload)
        audit_id = self.store.audit("agent.parent_receipt", "OK", payload)
        return Result(True, "AGENT_RECEIPT_RECORDED", data={**payload, "audit_id": audit_id})

    def _target(self, session_id: str) -> Path:
        workspace = WorkspaceService(self.root).load()["workspace"]
        return self.root / workspace["generated_root"] / "Agent配置" / session_id

    def _codex(self, session: dict[str, Any]) -> str:
        return "\n".join(
            (
                f"session_id = {_quote(str(session['session_id']))}",
                f"context_id = {_quote(str(session['context_id']))}",
                f"worktree = {_quote(str(session['worktree_path']))}",
                f"capabilities = {_array(session['allowed_capabilities'])}",
                'fork_turns = "none"',
                'requirement_state_owner = "parent"',
                "",
                "[mcp_servers.praxis]",
                'command = "praxis"',
                f"args = {_array(['--root', str(self.root.resolve()), 'mcp', 'serve'])}",
                "",
            )
        )

    def _json_config(self, session: dict[str, Any]) -> str:
        payload = {
            "praxis": {
                "session_id": session["session_id"],
                "context_id": session["context_id"],
                "worktree": session["worktree_path"],
                "allowed_capabilities": session["allowed_capabilities"],
                "coordination": session.get("coordination", {}),
                "mcp": {
                    "command": "praxis",
                    "args": ["--root", str(self.root.resolve()), "mcp", "serve"],
                },
            }
        }
        if session["agent_type"] == "claude-code":
            base = [
                "praxis",
                "--root",
                str(self.root.resolve()),
                "lifecycle",
            ]

            def hook(event: str) -> dict[str, str]:
                command = [
                    *base,
                    event,
                    "--stdin-json",
                    "--session",
                    session["session_id"],
                ]
                return {"command": " ".join(command)}

            payload["hooks"] = {
                "PreToolUse": [hook("before-tool")],
                "PostToolUse": [hook("after-tool")],
                "Stop": [hook("session-stop")],
            }
        return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    def _handoff(self, session: dict[str, Any]) -> dict[str, Any]:
        context = self.store.get("context", str(session["context_id"])) or {}
        requirement = self.store.requirement(str(session["requirement_id"])) or {}
        return {
            "session_id": session["session_id"],
            "parent_session_id": session.get("parent_session_id", ""),
            "requirement": {
                "id": requirement.get("requirement_id", ""),
                "short_name": requirement.get("short_name", ""),
                "status": requirement.get("status", ""),
            },
            "context": {
                "id": context.get("context_id", ""),
                "path": context.get("path", ""),
                "fingerprint": context.get("fingerprint", ""),
                "estimated_tokens": context.get("estimated_tokens", 0),
                "critical_facts": context.get("critical_facts", {}),
            },
            "worktree": {
                "binding_id": session.get("worktree", ""),
                "path": session.get("worktree_path", ""),
            },
            "skills": session.get("skills", []),
            "allowed_capabilities": session.get("allowed_capabilities", []),
            "coordination": session.get("coordination", {}),
        }
