from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from praxis.domain.requirement import RequirementStatus
from praxis.result import Result
from praxis.skills.registry import SkillRegistry, SkillRoutingContext
from praxis.storage.sqlite import StateStore

_MODES = {"required", "conditional_required", "conditional", "approval_required"}
_GATED_MODES = {"required", "conditional_required"}
_EXCLUDED_PROVIDER_IDS = {
    "obsidian-markdown",
    "orca-cli",
    "orca-per-workspace-env",
}
_NODE_ALIASES = {
    "investigation": "investigating",
    "analysis": "analyzed",
    "planning": "planned",
    "development": "in_progress",
    "verification": "verifying",
}


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
    condition_match: str = "any"
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
    token_budget: int = 4_000
    profile: str = "standard"


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
            if raw.get("condition_match", "any") not in {"any", "all"}:
                raise ValueError("Unknown Skill condition match mode")
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
                    condition_match=raw.get("condition_match", "any"),
                    intent_triggers=tuple(raw.get("intent_triggers", [])),
                    repository_kinds=tuple(raw.get("repository_kinds", [])),
                    agent_roles=tuple(raw.get("agent_roles", [])),
                    artifact_types=tuple(raw.get("artifact_types", [])),
                    risks=tuple(raw.get("risks", [])),
                )
            )
        return tuple(policies)

    @staticmethod
    def canonical_node(node: str) -> str:
        return _NODE_ALIASES.get(node, node)

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
        if request.profile not in {"standard", "fast-defect-v1"}:
            return Result(
                False,
                "SKILL_PROFILE_INVALID",
                data={"profile": request.profile},
            )
        canonical_node = self.canonical_node(request.node)
        known_nodes = {node for policy in self.policies() for node in policy.nodes}
        if canonical_node not in known_nodes:
            return Result(
                False,
                "SKILL_NODE_INVALID",
                data={"node": request.node, "allowed_nodes": sorted(known_nodes)},
            )
        if canonical_node != request.node:
            request = replace(request, node=canonical_node)
        registry = SkillRegistry.workspace(self.root)
        registered = {skill.id: skill for skill in registry.all()}
        bundled = set(registered)
        installed = self._installed_skills()
        request_payload = asdict(request)
        if request.profile == "standard":
            request_payload.pop("profile")
        fingerprint = hashlib.sha256(
            json_bytes(
                {
                    "request": request_payload,
                    "policy_hash": hashlib.sha256(
                        self.policy_path().read_bytes()
                    ).hexdigest(),
                    "registered": {
                        key: skill.content_hash for key, skill in sorted(registered.items())
                    },
                    "installed": {
                        key: value.get("content_hash", "")
                        for key, value in sorted(installed.items())
                    },
                }
            )
        ).hexdigest()
        key = f"{request.requirement_id}:{request.node}"
        if request.profile != "standard":
            key = f"{key}:{request.profile}"
        if request.requirement_id:
            cached = self.store.get("skill_route", key)
            if cached and cached.get("route_fingerprint") == fingerprint:
                data = {**cached, "cached": True}
                blocked_value = data.get("blocked_required_skills", [])
                blocked = blocked_value if isinstance(blocked_value, list) else []
                data["audit_id"] = self.store.audit(
                    "skill.route_reused",
                    "SKILL_REQUIRED_UNAVAILABLE" if blocked else "OK",
                    {
                        "requirement_id": request.requirement_id,
                        "node": request.node,
                        "route_fingerprint": fingerprint,
                    },
                )
                return Result(
                    not blocked,
                    "OK" if not blocked else "SKILL_REQUIRED_UNAVAILABLE",
                    data,
                )
        available = bundled | set(installed) | set(request.available_skills)
        approved = set(request.approved_skills)
        matched_policies = [
            (policy, reasons)
            for policy in sorted(self.policies(), key=lambda item: (-item.priority, item.id))
            if (reasons := self._matches(policy, request)) is not None
        ]
        if request.profile == "fast-defect-v1":
            core = {
                "praxis-requirement-workflow",
                "systematic-debugging",
                "test-driven-development",
            }
            already_matched = {policy.id for policy, _ in matched_policies}
            matched_policies = [
                (policy, reasons)
                for policy, reasons in matched_policies
                if policy.id in core or policy.mode == "approval_required"
            ]
            for policy in sorted(
                self.policies(), key=lambda item: (-item.priority, item.id)
            ):
                if (
                    policy.id in core
                    and policy.id not in already_matched
                    and request.node in policy.nodes
                ):
                    matched_policies.append(
                        (replace(policy, mode="required"), ["profile:fast-defect-v1"])
                    )
        protected_ids = {
            policy.id
            for policy, _ in matched_policies
            if policy.mode in _GATED_MODES
            or (policy.mode == "approval_required" and policy.id in approved)
        }
        protected_budget = sum(
            policy.context_budget
            for policy, _ in matched_policies
            if policy.id in protected_ids and policy.id in available
        )
        business = registry.route_context(
            SkillRoutingContext(
                intent=request.intent,
                system_id=request.system_id,
                project_id=request.project_id,
                business_domains=request.business_domains,
                repository_role=request.repository_kind,
                stage=request.node,
                agent_role=request.agent_role,
                risks=request.risks,
                artifact_types=request.artifact_types,
                token_budget=max(0, request.token_budget - protected_budget),
            )
        )
        matched_policy_ids = {policy.id for policy, _ in matched_policies}
        business = tuple(
            skill for skill in business if skill.id not in matched_policy_ids
        )
        if request.profile == "fast-defect-v1":
            business = ()
        business_budget = sum(skill.context_budget for skill in business)
        optional_budget = max(
            0,
            request.token_budget - protected_budget - business_budget,
        )
        decisions: list[dict[str, Any]] = []
        optional_used = 0
        for policy, reasons in matched_policies:
            status = "planned"
            if policy.id not in available:
                status = "unavailable"
            elif policy.mode == "approval_required" and policy.id not in approved:
                status = "blocked_pending_approval"
            elif policy.id in protected_ids:
                status = "available"
            elif optional_used + policy.context_budget > optional_budget:
                status = "omitted_budget"
            else:
                status = "available"
                optional_used += policy.context_budget
            decisions.append(
                {
                    **asdict(policy),
                    "recommended_agent_roles": list(policy.agent_roles),
                    "content_hash": registered[policy.id].content_hash
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

        known = {item["id"] for item in decisions}
        for skill in business:
            if skill.id in known:
                continue
            intent_matched = bool(
                skill.triggers
                and not skill.id.endswith(".development")
                and any(
                    trigger.casefold() in request.intent.casefold()
                    for trigger in skill.triggers
                )
            )
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
                    "intent_triggers": list(skill.triggers),
                    "repository_kinds": list(skill.repository_roles),
                    "agent_roles": [],
                    "recommended_agent_roles": [],
                    "artifact_types": list(skill.artifact_types),
                    "risks": [],
                    "status": "available",
                    "provider_available": True,
                    "content_hash": skill.content_hash,
                    "reasons": [
                        "business-context",
                        *(["intent"] if intent_matched else []),
                    ],
                }
            )
        used = protected_budget + business_budget + optional_used
        budget_shortfall = max(0, protected_budget - request.token_budget)

        blocked = [
            item["id"]
            for item in decisions
            if item["mode"] in _GATED_MODES and item["status"] != "available"
        ]
        data = {
            "requirement_id": request.requirement_id,
            "project_id": request.project_id,
            "node": request.node,
            "profile": request.profile,
            "intent": request.intent,
            "decisions": decisions,
            "context_budget": request.token_budget,
            "used_budget": used,
            "protected_budget": protected_budget,
            "budget_shortfall": budget_shortfall,
            "blocked_required_skills": blocked,
            "route_fingerprint": fingerprint,
            "cached": False,
        }
        if request.profile == "fast-defect-v1":
            data["execution_principles"] = [
                "file-search",
                "karpathy-guidelines",
                "ponytail",
            ]
        if request.requirement_id:
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
            Path.home() / ".skilldock" / "skills",
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
                if skill_id in _EXCLUDED_PROVIDER_IDS:
                    continue
                installed.setdefault(
                    skill_id,
                    {
                        "path": str(path),
                        "content_hash": hashlib.sha256(content).hexdigest(),
                    },
                )
        return installed

    def provider_diagnostics(self) -> dict[str, Any]:
        policies = {policy.id for policy in self.policies()}
        installed = self._installed_skills()
        registered = {
            skill.id: {
                "path": str(skill.path),
                "content_hash": skill.content_hash,
            }
            for skill in SkillRegistry.workspace(self.root).all()
        }
        providers = {**registered, **installed}
        delegates = self._delegates()
        normalized_policies = {self._normalized_id(skill_id) for skill_id in policies}
        delegate_without_policy = sorted(
            skill_id
            for skill_id in delegates
            if self._normalized_id(skill_id) not in normalized_policies
        )
        installed_details = {
            skill_id: {
                **details,
                "registered": skill_id in policies,
            }
            for skill_id, details in sorted(installed.items())
        }
        return {
            "policy_count": len(policies),
            "provider_count": len(providers),
            "installed": installed_details,
            "policy_without_provider": sorted(policies - providers.keys()),
            "installed_without_policy": sorted(installed.keys() - policies),
            "delegate_without_policy": delegate_without_policy,
            "excluded_provider_ids": sorted(_EXCLUDED_PROVIDER_IDS),
        }

    @classmethod
    def _delegates(cls) -> tuple[str, ...]:
        path = cls.policy_path().parent.parent / "skill.toml"
        if not path.is_file():
            return ()
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        return tuple(payload.get("delegates", []))

    @staticmethod
    def _normalized_id(value: str) -> str:
        return "-".join(value.casefold().replace("_", "-").split())

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
        if policy.mode != "required" and conditions:
            matched = all(conditions) if policy.condition_match == "all" else any(conditions)
            if not matched:
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
        node = NodeSkillRouter.canonical_node(node)
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

    def complete_node(
        self,
        requirement_id: str,
        node: str,
        outcomes: dict[str, Any],
        *,
        session_id: str = "",
        approved_skills: tuple[str, ...] = (),
        structured: bool = False,
        advance: bool = False,
    ) -> Result:
        if structured:
            return self._complete_node_structured(
                requirement_id,
                node,
                outcomes,
                session_id=session_id,
                approved_skills=approved_skills,
                advance=advance,
            )
        node = NodeSkillRouter.canonical_node(node)
        if not outcomes or any(
            not isinstance(value, str) or not value.strip()
            for value in outcomes.values()
        ):
            return Result(False, "SKILL_NODE_OUTCOME_REQUIRED")
        route = self.store.get("skill_route", f"{requirement_id}:{node}")
        if not route:
            return Result(False, "SKILL_ROUTE_NOT_FOUND")
        decisions = {item["id"]: item for item in route["decisions"]}
        required = {
            item["id"]
            for item in route["decisions"]
            if item["mode"] in _GATED_MODES
            or (item["mode"] == "approval_required" and item["status"] == "available")
        }
        missing_outcomes = sorted(required - outcomes.keys())
        if missing_outcomes:
            return Result(
                False,
                "SKILL_NODE_OUTCOME_MISSING",
                data={"missing": missing_outcomes},
            )
        unknown = sorted(outcomes.keys() - decisions.keys())
        if unknown:
            return Result(False, "SKILL_NOT_ROUTED", data={"skills": unknown})
        completed: list[dict[str, Any]] = []
        approved = set(approved_skills)
        for skill_id, outcome in outcomes.items():
            existing = next(
                (
                    item
                    for item in self.store.list_scope("skill_invocation")
                    if item.get("requirement_id") == requirement_id
                    and item.get("node") == node
                    and item.get("skill_id") == skill_id
                    and item.get("status") == "completed"
                ),
                None,
            )
            if existing:
                completed.append(existing)
                continue
            invoked = self.start(
                requirement_id,
                node,
                skill_id,
                session_id=session_id,
                approved=skill_id in approved,
            )
            if not invoked.ok:
                return invoked
            finished = self.complete(
                str(invoked.data["invocation_id"]), outcome=outcome.strip()
            )
            if not finished.ok:
                return finished
            completed.append(finished.data)
        gate = self.gate(requirement_id, node)
        return Result(
            gate.ok,
            gate.code,
            data={
                "requirement_id": requirement_id,
                "node": node,
                "completed": completed,
                "gate": gate.data,
            },
        )

    def _complete_node_structured(
        self,
        requirement_id: str,
        node: str,
        results: dict[str, Any],
        *,
        session_id: str,
        approved_skills: tuple[str, ...],
        advance: bool,
    ) -> Result:
        from praxis.knowledge.requirements import RequirementService

        node = NodeSkillRouter.canonical_node(node)
        if not results:
            return Result(False, "SKILL_NODE_OUTCOME_REQUIRED")
        route = self.store.get("skill_route", f"{requirement_id}:{node}")
        if not route:
            return Result(False, "SKILL_ROUTE_NOT_FOUND")
        decisions = {item["id"]: item for item in route["decisions"]}
        required = {
            item["id"]
            for item in route["decisions"]
            if item["mode"] in _GATED_MODES
            or (item["mode"] == "approval_required" and item["status"] == "available")
        }
        missing = sorted(required - results.keys())
        if missing:
            return Result(False, "SKILL_NODE_OUTCOME_MISSING", data={"missing": missing})
        unknown = sorted(results.keys() - decisions.keys())
        if unknown:
            return Result(False, "SKILL_NOT_ROUTED", data={"skills": unknown})

        normalized = {}
        allowed_results = {"passed", "not_applicable", "approval_missing", "failed"}
        approved = set(approved_skills)
        for skill_id, raw in results.items():
            if not isinstance(raw, dict):
                return Result(False, "SKILL_NODE_RESULT_INVALID", data={"skill_id": skill_id})
            result = str(raw.get("result", "")).strip()
            details = str(raw.get("details", "")).strip()
            if result not in allowed_results:
                return Result(
                    False,
                    "SKILL_NODE_RESULT_INVALID",
                    data={"skill_id": skill_id, "result": result},
                )
            decision = decisions[skill_id]
            if decision["status"] in {"unavailable", "omitted_budget"}:
                return Result(False, "SKILL_NOT_AVAILABLE", data={"skill_id": skill_id})
            if (
                decision["status"] == "blocked_pending_approval"
                and skill_id not in approved
                and result != "approval_missing"
            ):
                return Result(False, "USER_APPROVAL_REQUIRED", data={"skill_id": skill_id})
            normalized[skill_id] = {"result": result, "details": details}

        failed = sorted(
            skill_id
            for skill_id, item in normalized.items()
            if item["result"] == "failed"
        )
        approval_missing = sorted(
            skill_id
            for skill_id, item in normalized.items()
            if item["result"] == "approval_missing"
        )
        completed = sorted(
            skill_id
            for skill_id, item in normalized.items()
            if item["result"] in {"passed", "not_applicable"}
        )
        if failed:
            gate_code = "SKILL_NODE_FAILED"
        elif approval_missing:
            gate_code = "SKILL_NODE_APPROVAL_MISSING"
        else:
            gate_code = "OK"
        gate = {
            "code": gate_code,
            "required": sorted(required),
            "completed": completed,
            "missing": [],
            "approval_missing": approval_missing,
            "failed": failed,
        }

        requirements = RequirementService(self.root)
        preview = None
        may_advance = advance and not failed and (
            not approval_missing or node == "in_progress"
        )
        if may_advance:
            preview = requirements.preview_advance(requirement_id)
            if not preview.ok:
                return preview

        timestamp = datetime.now(UTC).isoformat()
        invocations = []
        for skill_id, item in normalized.items():
            invocation_id = (
                f"SKI-{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid4().hex[:8].upper()}"
            )
            status = (
                "completed"
                if item["result"] in {"passed", "not_applicable"}
                else item["result"]
            )
            invocation = {
                "invocation_id": invocation_id,
                "requirement_id": requirement_id,
                "node": node,
                "skill_id": skill_id,
                "session_id": session_id,
                "source": decisions[skill_id]["source"],
                "source_version": decisions[skill_id]["source_version"],
                "content_hash": decisions[skill_id].get("content_hash", ""),
                "status": status,
                "result": item["result"],
                "details": item["details"],
                "approved": skill_id in approved,
                "started_at": timestamp,
            }
            if status == "completed":
                invocation["completed_at"] = timestamp
            else:
                invocation["recorded_at"] = timestamp
            invocations.append(invocation)

        target = RequirementStatus(preview.data["target_status"]) if preview else None
        stored = self.store.complete_skill_node(
            requirement_id,
            node,
            invocations,
            gate,
            target=target,
            recorded_at=timestamp,
        )
        if target is not None:
            requirements.repair_projections()
        delivery = requirements.delivery(requirement_id)
        if delivery.ok:
            gate["implementation_status"] = delivery.data["implementation_status"]
            gate["verification_status"] = (
                "approval_missing" if approval_missing else delivery.data["verification_status"]
            )
        code = (
            "IMPLEMENTATION_COMPLETE_VERIFICATION_PENDING_APPROVAL"
            if approval_missing and target is not None
            else gate_code
        )
        ok = not failed and (not approval_missing or target is not None)
        return Result(
            ok,
            code,
            data={
                "requirement_id": requirement_id,
                "node": node,
                "source_status": preview.data["source_status"] if preview else node,
                "target_status": preview.data["target_status"] if preview else "",
                "results": invocations,
                "gate": {**gate, "audit_id": stored["gate_audit_id"]},
                "transition_audit_id": stored["transition_audit_id"],
            },
        )

    def gate(self, requirement_id: str, node: str) -> Result:
        node = NodeSkillRouter.canonical_node(node)
        route = self.store.get("skill_route", f"{requirement_id}:{node}")
        if not route:
            data = {
                "required": [],
                "completed": [],
                "missing": [],
                "reason": "route_not_found",
            }
            data["audit_id"] = self.store.audit(
                "skill.gate",
                "SKILL_ROUTE_NOT_FOUND",
                {"requirement_id": requirement_id, "node": node, **data},
            )
            return Result(False, "SKILL_ROUTE_NOT_FOUND", data=data)
        required = {
            item["id"]
            for item in route["decisions"]
            if item["mode"] in _GATED_MODES
            or (item["mode"] == "approval_required" and item["status"] == "available")
        }
        invocations = [
            item
            for item in self.store.list_scope("skill_invocation")
            if item["requirement_id"] == requirement_id and item["node"] == node
        ]
        completed = {
            item["skill_id"]
            for item in invocations
            if item.get("result") in {"passed", "not_applicable"}
            or (
                "result" not in item
                and (item.get("status") == "completed" or bool(item.get("completed_at")))
            )
        }
        approval_missing = sorted(
            item["skill_id"]
            for item in invocations
            if item.get("result") == "approval_missing"
        )
        failed = sorted(
            item["skill_id"] for item in invocations if item.get("result") == "failed"
        )
        missing = sorted(required - completed)
        if failed:
            code = "SKILL_NODE_FAILED"
        elif approval_missing:
            code = "SKILL_NODE_APPROVAL_MISSING"
        else:
            code = "OK" if not missing else "SKILL_NODE_GATE_BLOCKED"
        data = {
            "required": sorted(required),
            "completed": sorted(completed),
            "missing": missing,
            "approval_missing": approval_missing,
            "failed": failed,
        }
        data["audit_id"] = self.store.audit(
            "skill.gate",
            code,
            {"requirement_id": requirement_id, "node": node, **data},
        )
        return Result(
            not missing and not approval_missing and not failed,
            code,
            data=data,
        )


def json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
