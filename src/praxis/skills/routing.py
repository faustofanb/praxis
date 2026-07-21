from __future__ import annotations

import hashlib
import tomllib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from praxis.result import Result
from praxis.skills.registry import SkillRegistry, SkillRoutingContext
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService

_MODES = {"required", "conditional", "approval_required"}


@dataclass(frozen=True, slots=True)
class SkillProviderPolicy:
    id: str
    source: str
    source_version: str
    license: str
    nodes: tuple[str, ...]
    mode: str
    availability: str
    priority: int
    context_budget: int
    intent_triggers: tuple[str, ...] = ()
    repository_kinds: tuple[str, ...] = ()
    agent_roles: tuple[str, ...] = ()
    artifact_types: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NodeSkillRoutingRequest:
    node: str
    intent: str = ""
    requirement_id: str = ""
    project_id: str = ""
    system_id: str = ""
    business_domains: tuple[str, ...] = ()
    repository_kind: str = ""
    agent_role: str = ""
    artifact_types: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    available_skills: tuple[str, ...] = ()
    approved_skills: tuple[str, ...] = ()
    token_budget: int = 2_000


class NodeSkillRouter:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.store = StateStore(self.root)

    @classmethod
    def policies(cls) -> tuple[SkillProviderPolicy, ...]:
        path = cls.policy_path()
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError("Unsupported node routing schema")
        policies = []
        for raw in payload.get("providers", []):
            if raw["mode"] not in _MODES:
                raise ValueError(f"Unknown Skill routing mode: {raw['mode']}")
            policies.append(
                SkillProviderPolicy(
                    id=raw["id"],
                    source=raw["source"],
                    source_version=raw["source_version"],
                    license=raw["license"],
                    nodes=tuple(raw["nodes"]),
                    mode=raw["mode"],
                    availability=raw["availability"],
                    priority=int(raw.get("priority", 0)),
                    context_budget=int(raw.get("context_budget", 0)),
                    intent_triggers=tuple(raw.get("intent_triggers", [])),
                    repository_kinds=tuple(raw.get("repository_kinds", [])),
                    agent_roles=tuple(raw.get("agent_roles", [])),
                    artifact_types=tuple(raw.get("artifact_types", [])),
                    risks=tuple(raw.get("risks", [])),
                )
            )
        return tuple(policies)

    @staticmethod
    def policy_path() -> Path:
        source = (
            Path(__file__).resolve().parents[3]
            / "skills"
            / "praxis-system-development"
            / "references"
            / "node-routing.toml"
        )
        packaged = (
            Path(__file__).resolve().parents[1]
            / "bundled_skills"
            / "praxis-system-development"
            / "references"
            / "node-routing.toml"
        )
        return source if source.is_file() else packaged

    def route(self, request: NodeSkillRoutingRequest) -> Result:
        registry = SkillRegistry.workspace(self.root)
        registered = {skill.id: skill for skill in registry.all()}
        bundled = set(registered)
        installed = self._installed_skills()
        available = bundled | set(installed) | set(request.available_skills)
        approved = set(request.approved_skills)
        decisions: list[dict[str, Any]] = []
        used = 0
        for policy in sorted(self.policies(), key=lambda item: (-item.priority, item.id)):
            reasons = self._matches(policy, request)
            if reasons is None:
                continue
            status = "planned"
            if policy.id not in available:
                status = "unavailable"
            elif policy.mode == "approval_required" and policy.id not in approved:
                status = "blocked_pending_approval"
            elif used + policy.context_budget > request.token_budget:
                status = "omitted_budget"
            else:
                status = "available"
                used += policy.context_budget
            decisions.append(
                {
                    **asdict(policy),
                    "content_hash": registered.get(policy.id).content_hash
                    if policy.id in registered
                    else installed.get(policy.id, {}).get("content_hash", ""),
                    "installed_path": str(registered[policy.id].path)
                    if policy.id in registered
                    else installed.get(policy.id, {}).get("path", ""),
                    "status": status,
                    "provider_available": policy.id in available,
                    "reasons": reasons,
                }
            )

        business = registry.route_context(
            SkillRoutingContext(
                system_id=request.system_id,
                business_domains=request.business_domains,
                repository_role=request.repository_kind,
                stage=request.node,
                agent_role=request.agent_role,
                risks=request.risks,
                artifact_types=request.artifact_types,
                token_budget=max(0, request.token_budget - used),
            )
        )
        known = {item["id"] for item in decisions}
        for skill in business:
            if skill.id in known:
                continue
            decisions.append(
                {
                    "id": skill.id,
                    "source": skill.source,
                    "source_version": skill.source_version,
                    "license": skill.license,
                    "nodes": list(skill.stages),
                    "mode": "conditional",
                    "availability": "workspace",
                    "priority": 50,
                    "context_budget": skill.context_budget,
                    "intent_triggers": [],
                    "repository_kinds": list(skill.repository_roles),
                    "agent_roles": [],
                    "artifact_types": list(skill.artifact_types),
                    "risks": [],
                    "status": "available",
                    "provider_available": True,
                    "content_hash": skill.content_hash,
                    "reasons": ["business-context"],
                }
            )
            used += skill.context_budget

        blocked = [
            item["id"]
            for item in decisions
            if item["mode"] == "required" and item["status"] != "available"
        ]
        data = {
            "requirement_id": request.requirement_id,
            "project_id": request.project_id,
            "node": request.node,
            "intent": request.intent,
            "decisions": decisions,
            "context_budget": request.token_budget,
            "used_budget": used,
            "blocked_required_skills": blocked,
        }
        if request.requirement_id:
            key = f"{request.requirement_id}:{request.node}"
            self.store.set("skill_route", key, data)
            data["audit_id"] = self.store.audit(
                "skill.route_planned",
                "SKILL_REQUIRED_UNAVAILABLE" if blocked else "OK",
                data,
            )
        return Result(not blocked, "OK" if not blocked else "SKILL_REQUIRED_UNAVAILABLE", data)

    @staticmethod
    def _installed_skills() -> dict[str, dict[str, str]]:
        roots = (
            Path.home() / ".codex" / "skills",
            Path.home() / ".agents" / "skills",
            Path.home() / ".claude" / "skills",
        )
        installed: dict[str, dict[str, str]] = {}
        for root in roots:
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("SKILL.md")):
                try:
                    content = path.read_bytes()
                except OSError:
                    continue
                skill_id = NodeSkillRouter._skill_name(content) or path.parent.name
                installed.setdefault(
                    skill_id,
                    {
                        "path": str(path),
                        "content_hash": hashlib.sha256(content).hexdigest(),
                    },
                )
        return installed

    @staticmethod
    def _skill_name(content: bytes) -> str:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return ""
        if not text.startswith("---\n"):
            return ""
        for line in text.split("---", 2)[1].splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip() == "name":
                return value.strip().strip("\"'")
        return ""

    @staticmethod
    def _matches(
        policy: SkillProviderPolicy, request: NodeSkillRoutingRequest
    ) -> list[str] | None:
        if request.node not in policy.nodes:
            return None
        reasons = [f"node:{request.node}"]
        normalized = request.intent.casefold()
        conditions = []
        if policy.intent_triggers:
            match = any(item.casefold() in normalized for item in policy.intent_triggers)
            conditions.append(match)
            if match:
                reasons.append("intent")
        if policy.repository_kinds:
            match = request.repository_kind in policy.repository_kinds
            conditions.append(match)
            if match:
                reasons.append(f"repository:{request.repository_kind}")
        if policy.agent_roles:
            match = request.agent_role in policy.agent_roles
            conditions.append(match)
            if match:
                reasons.append(f"role:{request.agent_role}")
        if policy.artifact_types:
            match = bool(set(request.artifact_types) & set(policy.artifact_types))
            conditions.append(match)
            if match:
                reasons.append("artifact")
        if policy.risks:
            match = bool(set(request.risks) & set(policy.risks))
            conditions.append(match)
            if match:
                reasons.append("risk")
        if policy.mode != "required" and conditions and not any(conditions):
            return None
        return reasons


class SkillInvocationService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.store = StateStore(self.root)

    def start(
        self,
        requirement_id: str,
        node: str,
        skill_id: str,
        *,
        session_id: str = "",
        approved: bool = False,
    ) -> Result:
        route = self.store.get("skill_route", f"{requirement_id}:{node}")
        if not route:
            return Result(False, "SKILL_ROUTE_NOT_FOUND")
        decision = next(
            (item for item in route["decisions"] if item["id"] == skill_id), None
        )
        if not decision:
            return Result(False, "SKILL_NOT_ROUTED", data={"skill_id": skill_id})
        if decision["status"] == "blocked_pending_approval" and not approved:
            return Result(False, "USER_APPROVAL_REQUIRED", data={"skill_id": skill_id})
        if decision["status"] in {"unavailable", "omitted_budget"}:
            return Result(False, "SKILL_NOT_AVAILABLE", data={"skill_id": skill_id})
        invocation_id = f"SKI-{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid4().hex[:8].upper()}"
        data = {
            "invocation_id": invocation_id,
            "requirement_id": requirement_id,
            "node": node,
            "skill_id": skill_id,
            "session_id": session_id,
            "source": decision["source"],
            "source_version": decision["source_version"],
            "content_hash": decision.get("content_hash", ""),
            "status": "invoked",
            "approved": approved,
            "started_at": datetime.now(UTC).isoformat(),
        }
        self.store.set("skill_invocation", invocation_id, data)
        data["audit_id"] = self.store.audit("skill.invoked", "OK", data)
        return Result(True, data=data)

    def complete(self, invocation_id: str, *, outcome: str = "completed") -> Result:
        invocation = self.store.get("skill_invocation", invocation_id)
        if not invocation:
            return Result(False, "SKILL_INVOCATION_NOT_FOUND")
        invocation.update(
            status="completed",
            outcome=outcome,
            completed_at=datetime.now(UTC).isoformat(),
        )
        self.store.set("skill_invocation", invocation_id, invocation)
        audit_id = self.store.audit("skill.completed", "OK", invocation)
        return Result(True, data={**invocation, "audit_id": audit_id})

    def gate(self, requirement_id: str, node: str) -> Result:
        route = self.store.get("skill_route", f"{requirement_id}:{node}")
        if not route:
            return Result(False, "SKILL_ROUTE_NOT_FOUND")
        required = {
            item["id"]
            for item in route["decisions"]
            if item["mode"] == "required"
            or (item["mode"] == "approval_required" and item["status"] == "available")
        }
        completed = {
            item["skill_id"]
            for item in self.store.list_scope("skill_invocation")
            if item["requirement_id"] == requirement_id
            and item["node"] == node
            and (item.get("status") == "completed" or bool(item.get("completed_at")))
        }
        missing = sorted(required - completed)
        return Result(
            not missing,
            "OK" if not missing else "SKILL_NODE_GATE_BLOCKED",
            data={"required": sorted(required), "completed": sorted(completed), "missing": missing},
        )
