from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from time import monotonic_ns
from typing import Any

from praxis import __version__
from praxis.agents.guidance import AgentGuidanceService
from praxis.agents.lifecycle import AgentLifecycle
from praxis.agents.service import AgentSessionService
from praxis.artifacts.service import ArtifactService
from praxis.codegraph.hooks import CodeGraphHooks
from praxis.codegraph.service import CodeGraphService
from praxis.context.service import ContextBuildRequest, ContextCompiler
from praxis.database.service import DatabaseService
from praxis.domain.requirement import RequirementStatus
from praxis.domains.service import DomainService
from praxis.gates.commit_message import validate_commit_message
from praxis.gates.engine import GateEngine, GateEvent
from praxis.governance.service import ApprovalService, ExecutionBudgetService, VerificationService
from praxis.integrations.ponytail import diff_warning
from praxis.integrations.witr import WitrService
from praxis.knowledge.requirements import RequirementService
from praxis.mcp.broker import McpBrokerService
from praxis.portraits.service import PortraitService
from praxis.result import Result
from praxis.skills.candidates import SkillCandidateService
from praxis.skills.importer import SkillImportService
from praxis.skills.registry import Skill, SkillRegistry
from praxis.skills.routing import (
    NodeSkillRouter,
    NodeSkillRoutingRequest,
    SkillInvocationService,
)
from praxis.storage.sqlite import StateStore
from praxis.tasks.service import TaskService
from praxis.workspace.service import Project, WorkspaceService
from praxis.worktree.lifecycle import WorktreeLifecycle
from praxis.worktree.service import WorktreeService, resolve_worktree_binding


def _skill_data(skill: Skill) -> dict[str, Any]:
    data = asdict(skill)
    data["path"] = str(skill.path)
    for key, value in tuple(data.items()):
        if isinstance(value, tuple):
            data[key] = list(value)
    return data


class PraxisApplication:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def _skills(self) -> SkillRegistry:
        return SkillRegistry.workspace(self.root)

    def execute(self, operation: str, arguments: dict[str, Any] | None = None) -> Result:
        values = arguments or {}
        started = monotonic_ns()
        try:
            result = self._execute(operation, values)
        except (KeyError, OSError, TypeError, ValueError) as error:
            result = Result(False, "INVALID_REQUEST", data={"message": str(error)})
        duration_ms = round((monotonic_ns() - started) / 1_000_000, 3)
        timed_operations = {
            "requirement.reopen",
            "requirement.advance",
            "artifact.add",
            "skill.complete-node",
            "lifecycle.complete-node",
            "agent.start",
            "agent.receipt",
        }
        is_timed_operation = operation in timed_operations or operation.startswith(
            ("worktree.", "codegraph.", "approval.", "budget.")
        )
        if not is_timed_operation:
            return result
        identifiers = {
            key: str(values[key])
            for key in (
                "requirement_id",
                "project_id",
                "repository_id",
                "binding_id",
                "session_id",
            )
            if values.get(key)
        }
        timing = {
            "operation": operation,
            "code": result.code,
            "ok": result.ok,
            "duration_ms": duration_ms,
            **identifiers,
        }
        timing_audit_id = StateStore(self.root).audit(
            "operation.timed", result.code, timing
        )
        return Result(
            result.ok,
            result.code,
            data={
                **result.data,
                "duration_ms": duration_ms,
                **({"timing_audit_id": timing_audit_id} if timing_audit_id else {}),
            },
            diagnostics=result.diagnostics,
        )

    def _execute(self, operation: str, values: dict[str, Any]) -> Result:
        if operation == "version":
            return Result(True, data={"version": __version__})
        if operation in {"init", "workspace.init"}:
            return WorkspaceService(self.root).init(
                values["workspace_id"],
                values["name"],
                values.get("knowledge_root", "知识库"),
            )
        if operation == "doctor":
            workspace = WorkspaceService(self.root).load()
            audit_valid = StateStore(self.root).verify_audit_chain()
            skill_providers = NodeSkillRouter(self.root).provider_diagnostics()
            return Result(
                audit_valid,
                "OK" if audit_valid else "AUDIT_CHAIN_INVALID",
                data={
                    "schema_version": workspace["schema_version"],
                    "audit_chain": audit_valid,
                    "skill_providers": skill_providers,
                },
            )
        if operation in {"workspace.inspect", "workspace.show"}:
            return WorkspaceService(self.root).inspect()
        if operation == "workspace.validate":
            workspace = WorkspaceService(self.root).load()
            return Result(True, data={"schema_version": workspace["schema_version"]})
        if operation == "workspace.guidance":
            return AgentGuidanceService(self.root).render()
        if operation == "workspace.add":
            return WorkspaceService(self.root).add_project(
                values["system_id"],
                Project(
                    id=values["project_id"],
                    name=values["name"],
                    kind=values["kind"],
                    path=values["path"],
                    default_branch=values["default_branch"],
                    database_connections=tuple(values.get("database_connections", [])),
                    production_database_connections=tuple(
                        values.get("production_database_connections", [])
                    ),
                    deployment_commands=tuple(values.get("deployment_commands", [])),
                    release_branches=tuple(values.get("release_branches", [])),
                    template_branches=tuple(values.get("template_branches", [])),
                    local_files=tuple(values.get("local_files", [])),
                    worktree_setup_commands=tuple(
                        values.get("worktree_setup_commands", [])
                    ),
                    lint_commands=tuple(values.get("lint_commands", [])),
                    typecheck_commands=tuple(values.get("typecheck_commands", [])),
                    test_commands=tuple(values.get("test_commands", [])),
                ),
            )
        if operation == "system.add":
            return WorkspaceService(self.root).add_system(
                values["system_id"], values["name"], values.get("domains", [])
            )
        if operation == "domain.add":
            return DomainService(self.root).add(
                values["system_id"], values["domain_id"], values["name_zh"]
            )
        if operation == "domain.upsert":
            return DomainService(self.root).upsert(
                values["system_id"],
                values["domain_id"],
                values["name_zh"],
                **{
                    key: values.get(key, [])
                    for key in (
                        "objectives",
                        "responsibilities",
                        "entities",
                        "processes",
                        "rules",
                        "interfaces",
                        "owners",
                    )
                },
            )
        if operation == "domain.list":
            return DomainService(self.root).list()
        if operation == "domain.merge":
            return DomainService(self.root).merge(values["source"], values["target"])
        if operation == "workspace.bootstrap":
            workspace = WorkspaceService(self.root).load()
            guidance = AgentGuidanceService(self.root).render()
            if not guidance.ok:
                return guidance
            initialized = []
            candidates = []
            promoted = []
            catalog = self.root / workspace["knowledge_root"] / "skills"
            for project in workspace.get("projects", []):
                result = CodeGraphService(self.root, project["id"]).ensure_fresh(initialize=True)
                if not result.ok:
                    return result
                initialized.append(project["id"])
                candidate = SkillCandidateService(self.root).generate(project["id"])
                if not candidate.ok:
                    return candidate
                candidates.append(candidate.data["id"])
                if values.get("approve_skills") and candidate.data.get("source_files"):
                    approved = SkillCandidateService(self.root).promote(
                        candidate.data["id"], catalog, approved=True
                    )
                    if not approved.ok:
                        return approved
                    promoted.append(approved.data["id"])
            database = DatabaseService(self.root).discover()
            return Result(
                True,
                data={
                    "projects": initialized,
                    "skill_candidates": candidates,
                    "business_skills": promoted,
                    "database_discovery": database.to_dict(),
                    "agent_guidance": guidance.data,
                },
            )
        if operation in {"requirement.create", "requirement.new"}:
            return RequirementService(self.root).create(
                values["short_name"],
                values["request"],
                values.get("systems", []),
                values.get("domains", []),
            )
        if operation == "requirement.show":
            return RequirementService(self.root).show(values["requirement_id"])
        if operation == "requirement.progress":
            return RequirementService(self.root).progress(
                values["requirement_id"], values["message"]
            )
        if operation == "requirement.constraint.add":
            return RequirementService(self.root).add_constraint(
                values["requirement_id"],
                values["statement"],
                supersedes=values.get("supersedes", []),
                source=values.get("source", ""),
            )
        if operation == "requirement.constraint.list":
            return RequirementService(self.root).list_constraints(values["requirement_id"])
        if operation == "requirement.record-implementation":
            return RequirementService(self.root).record_implementation(
                values["requirement_id"],
                values.get("project_id", ""),
                artifact_ids=values.get("artifact_ids", []),
                projects=values.get("projects", {}),
            )
        if operation == "verification.decline":
            return VerificationService(self.root).decline(
                values["requirement_id"],
                values["entry"],
                user_evidence=values.get("user_evidence", ""),
                authorized_by_user=values.get("authorized_by_user", False),
            )
        if operation == "requirement.rename":
            return RequirementService(self.root).rename(
                values["requirement_id"], values["short_name"]
            )
        if operation == "requirement.reopen":
            return RequirementService(self.root).reopen(
                values["requirement_id"], values["reason"]
            )
        if operation == "requirement.advance":
            requirement_id = values["requirement_id"]
            skill_gate = self._gate_current_skill_route(requirement_id)
            if not skill_gate.ok:
                return skill_gate
            return RequirementService(self.root).advance(requirement_id)
        if operation == "requirement.transition":
            target = RequirementStatus(values["status"])
            if target not in {RequirementStatus.BLOCKED, RequirementStatus.CANCELLED}:
                skill_gate = self._gate_current_skill_route(values["requirement_id"])
                if not skill_gate.ok:
                    return skill_gate
            return RequirementService(self.root).transition(
                values["requirement_id"], target
            )
        if operation == "requirement.analyze":
            requirements = RequirementService(self.root)
            current = requirements.show(values["requirement_id"])
            if not current.ok:
                return current
            if current.data["status"] == RequirementStatus.CAPTURED:
                skill_gate = self._gate_current_skill_route(values["requirement_id"])
                if not skill_gate.ok:
                    return skill_gate
                return requirements.transition(
                    values["requirement_id"], RequirementStatus.INVESTIGATING
                )
            skill_gate = self._gate_current_skill_route(values["requirement_id"])
            if not skill_gate.ok:
                return skill_gate
            return requirements.transition(values["requirement_id"], RequirementStatus.ANALYZED)
        requirement_targets = {
            "requirement.plan": RequirementStatus.PLANNED,
            "requirement.ready": RequirementStatus.READY,
            "requirement.start": RequirementStatus.IN_PROGRESS,
            "requirement.verify": RequirementStatus.VERIFYING,
            "requirement.complete": RequirementStatus.COMPLETED,
            "requirement.archive": RequirementStatus.ARCHIVED,
            "requirement.cancel": RequirementStatus.CANCELLED,
        }
        if operation in requirement_targets:
            requirement_id = values["requirement_id"]
            if operation != "requirement.cancel":
                skill_gate = self._gate_current_skill_route(requirement_id)
                if not skill_gate.ok:
                    return skill_gate
            return RequirementService(self.root).transition(
                requirement_id, requirement_targets[operation]
            )
        if operation == "repair.projections":
            return RequirementService(self.root).repair_projections()
        if operation == "repair.requirement-layout":
            return RequirementService(self.root).repair_layout()
        if operation == "skill.inspect":
            return Result(True, data=_skill_data(self._skills().inspect(values["id"])))
        if operation == "skill.list":
            return Result(
                True,
                data={"skills": [_skill_data(skill) for skill in self._skills().all()]},
            )
        if operation == "skill.search":
            return Result(
                True,
                data={
                    "skills": [
                        _skill_data(skill)
                        for skill in self._skills().search(values["query"])
                    ]
                },
            )
        if operation == "skill.verify":
            return self._skills().verify()
        if operation == "skill.dedupe":
            return self._skills().duplicates()
        if operation == "skill.import":
            return SkillImportService(self.root).import_legacy(
                values["source_root"], values["system_id"]
            )
        if operation == "skill.route":
            skills = self._skills().route(
                values["intent"], budget=values.get("budget", 2000)
            )
            return Result(
                True,
                data={
                    "skills": [_skill_data(skill) for skill in skills],
                    "context_budget": sum(skill.context_budget for skill in skills),
                },
            )
        if operation == "skill.route-node":
            project_id = values.get("project_id", "")
            project = WorkspaceService(self.root).project(project_id) if project_id else None
            return NodeSkillRouter(self.root).route(
                NodeSkillRoutingRequest(
                    node=values["node"],
                    intent=values.get("intent", ""),
                    requirement_id=values.get("requirement_id", ""),
                    project_id=project_id,
                    system_id=values.get(
                        "system_id", project.system_id if project else ""
                    ),
                    business_domains=tuple(values.get("business_domains", [])),
                    repository_kind=values.get(
                        "repository_kind", project.kind if project else ""
                    ),
                    agent_role=values.get("agent_role", ""),
                    artifact_types=tuple(values.get("artifact_types", [])),
                    risks=tuple(values.get("risks", [])),
                    available_skills=tuple(values.get("available_skills", [])),
                    approved_skills=tuple(values.get("approved_skills", [])),
                    token_budget=values.get("budget", 4_000),
                )
            )
        if operation == "skill.invoke":
            return SkillInvocationService(self.root).start(
                values["requirement_id"],
                values["node"],
                values["skill_id"],
                session_id=values.get("session_id", ""),
                approved=values.get("approved", False),
            )
        if operation == "skill.complete":
            return SkillInvocationService(self.root).complete(
                values["invocation_id"], outcome=values.get("outcome", "completed")
            )
        if operation == "skill.complete-node":
            project_id = values.get("project_id", "")
            project = WorkspaceService(self.root).project(project_id) if project_id else None
            routed = NodeSkillRouter(self.root).route(
                NodeSkillRoutingRequest(
                    node=values["node"],
                    intent=values.get("intent", ""),
                    requirement_id=values["requirement_id"],
                    project_id=project_id,
                    system_id=values.get(
                        "system_id", project.system_id if project else ""
                    ),
                    business_domains=tuple(values.get("business_domains", [])),
                    repository_kind=values.get(
                        "repository_kind", project.kind if project else ""
                    ),
                    agent_role=values.get("agent_role", ""),
                    artifact_types=tuple(values.get("artifact_types", [])),
                    risks=tuple(values.get("risks", [])),
                    available_skills=tuple(values.get("available_skills", [])),
                    approved_skills=tuple(values.get("approved_skills", [])),
                    token_budget=values.get("budget", 4_000),
                )
            )
            if not routed.ok:
                return routed
            return SkillInvocationService(self.root).complete_node(
                values["requirement_id"],
                values["node"],
                values["outcomes"],
                session_id=values.get("session_id", ""),
                approved_skills=tuple(values.get("approved_skills", [])),
            )
        if operation == "skill.gate":
            return SkillInvocationService(self.root).gate(
                values["requirement_id"], values["node"]
            )
        if operation == "lifecycle.complete-node":
            return SkillInvocationService(self.root).complete_node(
                values["requirement_id"],
                values["node"],
                values["results"],
                session_id=values.get("session_id", ""),
                approved_skills=tuple(values.get("approved_skills", [])),
                structured=True,
                advance=True,
            )
        if operation == "skill.resource":
            content = self._skills().resource(values["uri"])
            return Result(True, data={"uri": values["uri"], "content": content})
        if operation in {"skill.candidate", "skill.generate"}:
            return SkillCandidateService(self.root).generate(values["project_id"])
        if operation == "skill.approve":
            return SkillCandidateService(self.root).promote(
                values["id"], values["catalog_root"], approved=values.get("approved", False)
            )
        if operation.startswith("codegraph."):
            return self._codegraph(operation.removeprefix("codegraph."), values)
        if operation.startswith("worktree."):
            return self._worktree(operation.removeprefix("worktree."), values)
        if operation.startswith("lifecycle."):
            action = operation.removeprefix("lifecycle.")
            if action in {"before-tool", "after-tool", "session-stop"}:
                return AgentLifecycle(self.root).run(action, values["context"])
            return WorktreeLifecycle(self.root).run(
                action, values["context"]
            )
        if operation.startswith("hook."):
            return CodeGraphHooks(self.root).run(
                operation.removeprefix("hook."),
                values["project_id"],
                worktree=values.get("worktree"),
                initialize=values.get("initialize", False),
                graph_required=values.get("graph_required", True),
            )
        if operation.startswith("task."):
            return self._task(operation.removeprefix("task."), values)
        if operation.startswith("portrait."):
            portraits = PortraitService(self.root)
            action = operation.removeprefix("portrait.")
            if action == "scan":
                return portraits.scan(values["project_id"], values.get("runtime_arguments"))
            if action in {"show", "diff", "verify"}:
                return getattr(portraits, action)(values["project_id"])
        if operation.startswith("system.") and operation != "system.add":
            action = operation.removeprefix("system.")
            if action in {"scan", "show", "diff"}:
                return getattr(PortraitService(self.root), action)(values["project_id"])
        if operation == "database.connections":
            return DatabaseService(self.root).connections(values["project_id"])
        if operation == "database.discover":
            return DatabaseService(self.root).discover()
        if operation == "database.configure":
            return WorkspaceService(self.root).set_database_connections(
                values["project_id"],
                values.get("connection_refs", []),
                values.get("production_connection_refs", []),
            )
        if operation == "database.query":
            return DatabaseService(self.root).query(
                values["project_id"],
                values["connection_ref"],
                values["sql"],
                approved=values.get("approved", False),
                read_allowed=values.get("read_allowed", True),
                write_context=values.get("write_context"),
            )
        if operation == "database.investigate":
            return DatabaseService(self.root).investigate(
                values["project_id"],
                values["connection_ref"],
                values["sql"],
                purpose=values["purpose"],
            )
        if operation == "context.build":
            return ContextCompiler(self.root).build(
                ContextBuildRequest(
                    requirement_id=values["requirement_id"],
                    project_id=values["project_id"],
                    stage=values["stage"],
                    agent_role=values["agent_role"],
                    intent=values.get("intent", ""),
                    token_budget=values.get("token_budget", 24_000),
                    allowed_paths=tuple(values.get("allowed_paths", [])),
                    forbidden_paths=tuple(values.get("forbidden_paths", [])),
                    workflow_node=values.get("workflow_node", "in_progress"),
                    artifact_types=tuple(values.get("artifact_types", [])),
                    risks=tuple(values.get("risks", [])),
                    available_skills=tuple(values.get("available_skills", [])),
                    approved_skills=tuple(values.get("approved_skills", [])),
                )
            )
        if operation == "context.show":
            return ContextCompiler(self.root).show(values["context_id"])
        if operation == "context.diff":
            return ContextCompiler(self.root).diff(
                values["context_id"], values["previous_context_id"]
            )
        if operation == "mcp.list":
            return McpBrokerService(self.root).capabilities()
        if operation == "mcp.grant":
            return McpBrokerService(self.root).grant(
                values["session_id"],
                values["role"],
                values["capabilities"],
                requirement_id=values.get("requirement_id"),
                worktree=values.get("worktree"),
                approved_external=values.get("approved_external", False),
            )
        if operation == "mcp.invoke":
            return McpBrokerService(self.root).invoke(
                values["session_id"], values["capability"], values.get("arguments", {})
            )
        if operation == "mcp.add":
            return McpBrokerService(self.root).register_server(
                values["server_id"],
                values["command"],
                values["capabilities"],
                values["risk"],
                approved=values.get("approved", False),
            )
        if operation == "mcp.render":
            return McpBrokerService(self.root).render(values["session_id"])
        if operation == "agent.start":
            return AgentSessionService(self.root).start(
                values["agent_type"],
                values["role"],
                values["requirement_id"],
                values["context_id"],
                values["worktree"],
                values["capabilities"],
                skills=values.get("skills", []),
                approved_external=values.get("approved_external", False),
                parent_session_id=values.get("parent_session_id", ""),
                intent=values.get("intent", ""),
            )
        if operation == "agent.install":
            return AgentSessionService(self.root).install(values["agent_type"])
        if operation == "agent.render":
            return AgentSessionService(self.root).render(values["session_id"])
        if operation == "agent.launch":
            return AgentSessionService(self.root).launch(
                values["session_id"], execute=values.get("execute", False)
            )
        if operation == "agent.finish":
            return AgentSessionService(self.root).finish(
                values["session_id"], values.get("status", "completed")
            )
        if operation == "agent.receipt":
            return AgentSessionService(self.root).receipt(
                values["session_id"],
                changed_paths=values.get("changed_paths", []),
                decisions=values.get("decisions", []),
                blockers=values.get("blockers", []),
                follow_up=values.get("follow_up", ""),
            )
        if operation == "agent.sessions":
            return AgentSessionService(self.root).sessions()
        if operation == "artifact.add":
            return ArtifactService(self.root).add(
                values["requirement_id"],
                values["artifact_type"],
                values["source_path"],
                stage=values["stage"],
                metadata=values.get("metadata", {}),
            )
        if operation == "artifact.list":
            return ArtifactService(self.root).list(values.get("requirement_id"))
        if operation == "artifact.verify":
            return ArtifactService(self.root).verify(values["artifact_id"])
        if operation == "approval.grant":
            return ApprovalService(self.root).grant(
                values["requirement_id"],
                values["scope"],
                values["entries"],
                user_evidence=values["user_evidence"],
                authorized_by_user=values.get("authorized_by_user", False),
                expires_at=values.get("expires_at", ""),
            )
        if operation == "approval.check":
            return ApprovalService(self.root).check(
                values["requirement_id"], values["scope"], values["entry"]
            )
        if operation == "approval.list":
            return ApprovalService(self.root).list(values.get("requirement_id", ""))
        if operation == "budget.consume":
            return ExecutionBudgetService(self.root).consume(
                values["requirement_id"],
                values["node"],
                values["kind"],
                values["operation_key"],
            )
        if operation == "budget.status":
            return ExecutionBudgetService(self.root).status(
                values["requirement_id"], values.get("node", "")
            )
        if operation == "audit.list":
            events = StateStore(self.root).audit_events(values.get("limit", 100))
            return Result(True, data={"events": events})
        if operation == "audit.show":
            event = StateStore(self.root).audit_event(values["audit_id"])
            return Result(bool(event), "OK" if event else "AUDIT_NOT_FOUND", data=event or {})
        if operation == "audit.verify":
            valid = StateStore(self.root).verify_audit_chain()
            return Result(valid, "OK" if valid else "AUDIT_CHAIN_INVALID")
        if operation == "repair.indexes":
            projections = RequirementService(self.root).repair_projections()
            skills = SkillRegistry.bundled().verify()
            return Result(
                projections.ok and skills.ok,
                data={"projections": projections.data, "skills": skills.data},
            )
        if operation == "gate.list":
            return Result(True, data={"events": [event.value for event in GateEvent]})
        if operation == "gate.explain":
            try:
                event = GateEvent(values["event"])
            except ValueError:
                return Result(False, "GATE_NOT_FOUND", data={"event": values["event"]})
            return Result(
                True,
                data={
                    "event": event.value,
                    "blocking": True,
                    "rule_source": "Python",
                    "message_zh": "门禁由 Praxis 领域策略执行，Agent 配置不包含规则副本。",
                },
            )
        if operation == "gate.history":
            events = [
                item
                for item in StateStore(self.root).audit_events(values.get("limit", 100))
                if item["event"] == "gate.run"
            ]
            return Result(True, data={"runs": events})
        if operation == "gate.run":
            return self._gate(values)
        if operation == "gate.commit-message":
            return validate_commit_message(
                message=values.get("message"), message_file=values.get("message_file")
            )
        if operation == "runtime.diagnose":
            return WitrService(self.root).diagnose(values.get("arguments", []), explicit=True)
        return Result(False, "OPERATION_NOT_FOUND", data={"operation": operation})

    def _gate_current_skill_route(self, requirement_id: str) -> Result:
        store = StateStore(self.root)
        requirement = store.requirement(requirement_id)
        if not requirement:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        node = requirement["status"]
        return SkillInvocationService(self.root).gate(requirement_id, node)

    def _codegraph(self, action: str, values: dict[str, Any]) -> Result:
        project_id = str(values.get("project_id") or "")
        repository_path = values.get("worktree")
        binding_id = str(values.get("binding_id") or "")
        binding = None
        if binding_id:
            resolved = resolve_worktree_binding(StateStore(self.root), binding_id)
            if not resolved:
                return Result(False, "WORKTREE_BINDING_INVALID")
            binding_id, binding = resolved
            project_id = str(binding["repository_id"])
            repository_path = binding.get("repository_path", binding["path"])
        elif repository_path and not project_id:
            resolved = resolve_worktree_binding(
                StateStore(self.root),
                "",
                worktree_path=repository_path,
            )
            if not resolved:
                return Result(False, "WORKTREE_BINDING_INVALID")
            binding_id, binding = resolved
            project_id = str(binding["repository_id"])
            repository_path = binding.get("repository_path", binding["path"])
        if not project_id:
            return Result(False, "CODEGRAPH_PROJECT_REQUIRED")
        graph = CodeGraphService(
            self.root,
            project_id,
            repo=repository_path,
        )
        if action == "status":
            result = graph.status()
            if binding:
                return Result(
                    result.ok,
                    result.code,
                    data={
                        **result.data,
                        "binding_id": binding_id,
                        "workspace_path": binding["path"],
                    },
                    diagnostics=result.diagnostics,
                )
            return result
        if action == "build":
            return graph.build()
        if action == "sync":
            return graph.sync()
        if action == "ensure-fresh":
            return graph.ensure_fresh(initialize=values.get("initialize", False))
        if action == "run-pending":
            return graph.run_pending(binding_id=binding_id)
        if action == "wait":
            return graph.wait(timeout=float(values.get("timeout", 0)))
        if action in {"query", "explore", "node"}:
            return getattr(graph, action)(values["target"])
        if action == "affected":
            return graph.affected()
        return Result(False, "OPERATION_NOT_FOUND", data={"operation": f"codegraph.{action}"})

    def _worktree(self, action: str, values: dict[str, Any]) -> Result:
        worktree = WorktreeService(self.root)
        if action == "create":
            skill_gate = self._gate_current_skill_route(values["requirement_id"])
            if not skill_gate.ok:
                return skill_gate
            return worktree.create_for_requirement(
                values["requirement_id"], values["repository_id"], values.get("stage")
            )
        if action == "preview":
            return worktree.preview_for_requirement(
                values["requirement_id"], values["repository_ids"]
            )
        if action == "ensure":
            skill_gate = self._gate_current_skill_route(values["requirement_id"])
            if not skill_gate.ok:
                return skill_gate
            ensured = worktree.ensure_for_requirement(
                values["requirement_id"],
                values["repository_ids"],
                preview_id=values["preview_id"],
            )
            requirement = StateStore(self.root).requirement(values["requirement_id"]) or {}
            bundles = []
            errors = []
            for item in ensured.data.get("items", []):
                if not item.get("ok"):
                    continue
                worktree_data = item.get("data", {})
                repository_id = str(
                    worktree_data.get("repository_id") or item.get("repository_id", "")
                )
                try:
                    built = ContextCompiler(self.root).build(
                        ContextBuildRequest(
                            requirement_id=values["requirement_id"],
                            project_id=repository_id,
                            stage=str(worktree_data.get("stage", "development")),
                            agent_role="coder",
                            intent=str(requirement.get("original_request", "")),
                            allowed_paths=tuple(worktree_data.get("allowed_paths", [])),
                            forbidden_paths=tuple(worktree_data.get("forbidden_paths", [])),
                            workflow_node="in_progress",
                        )
                    )
                except (KeyError, FileNotFoundError, ValueError) as error:
                    errors.append(
                        {
                            "repository_id": repository_id,
                            "code": "CONTEXT_AUTO_BUILD_FAILED",
                            "data": {"error": str(error)},
                        }
                    )
                    continue
                if built.ok:
                    bundles.append(built.data)
                else:
                    errors.append(
                        {
                            "repository_id": repository_id,
                            "code": built.code,
                            "data": built.data,
                        }
                    )
            return Result(
                ensured.ok,
                ensured.code,
                data={
                    **ensured.data,
                    "context_bundles": bundles,
                    "context_errors": errors,
                },
                diagnostics=ensured.diagnostics,
            )
        if action == "prepare":
            return worktree.prepare_for_requirement(
                values["requirement_id"], values["repository_id"]
            )
        if action == "migrate-name":
            skill_gate = self._gate_current_skill_route(values["requirement_id"])
            if not skill_gate.ok:
                return skill_gate
            return worktree.migrate_name(
                values["requirement_id"], values["repository_id"]
            )
        if action == "list":
            return worktree.list()
        if action == "status":
            return worktree.status(
                binding_id=values.get("binding_id", ""),
                worktree_path=values.get("worktree", ""),
            )
        if action == "remove":
            return worktree.remove(values["branch"])
        if action == "merge":
            return worktree.merge(values.get("target", "main"), branch=values.get("branch"))
        if action == "install-hooks":
            return worktree.install_hooks(values["project_id"])
        return Result(False, "OPERATION_NOT_FOUND", data={"operation": f"worktree.{action}"})

    def _task(self, action: str, values: dict[str, Any]) -> Result:
        tasks = TaskService(self.root)
        if action == "start":
            return tasks.start(
                values["task_id"],
                values["title"],
                values["project_id"],
                requirement_id=values.get("requirement_id"),
                graph_required=values.get("graph_required", False),
            )
        if action == "resume":
            return tasks.resume(values["task_id"])
        if action == "progress":
            return tasks.progress(values["task_id"], values["message"])
        if action == "inspect":
            task = tasks.inspect(values["task_id"])
            return Result(task is not None, "OK" if task else "TASK_NOT_FOUND", data=task or {})
        return Result(False, "OPERATION_NOT_FOUND", data={"operation": f"task.{action}"})

    def _gate(self, values: dict[str, Any]) -> Result:
        try:
            event = GateEvent(values["event"])
        except ValueError:
            return Result(False, "GATE_NOT_FOUND", data={"event": values["event"]})
        project_id = values["project_id"]
        mapped = {
            GateEvent.TASK_START: "task-context",
            GateEvent.CHANGE_PREFLIGHT: "change-preflight",
            GateEvent.VERIFY: "verify",
            GateEvent.WORKTREE_PRE_MERGE: "pre-merge",
            GateEvent.DELIVERY: "verify",
        }
        engine = GateEngine()
        if event == GateEvent.VERIFY:
            requirement_id = str(values.get("requirement_id", ""))
            entries = list(values.get("verification_entries", []))
            if not requirement_id or not entries:
                return Result(
                    False,
                    "VERIFICATION_SCOPE_REQUIRED",
                    data={"requirement_id": requirement_id, "entries": entries},
                )
            for entry in entries:
                engine.register(
                    event,
                    lambda context, entry=entry: ApprovalService(self.root).check(
                        requirement_id, "verification", entry
                    ),
                )
        if event == GateEvent.WORKSPACE_SCAN:
            engine.register(event, lambda context: PortraitService(self.root).scan(project_id))
        else:
            engine.register(
                event,
                lambda context: CodeGraphHooks(self.root).run(
                    mapped[event],
                    project_id,
                    worktree=values.get("worktree"),
                    graph_required=values.get("graph_required", True),
                ),
            )
        if event == GateEvent.DELIVERY:
            engine.register(
                event,
                lambda context: diff_warning(
                    values.get("added_lines", 0), values.get("deleted_lines", 0)
                ),
            )
        result = engine.run(event, values)
        audit_id = StateStore(self.root).audit(
            "gate.run", result.code, {"event": event.value, "project_id": project_id}
        )
        return Result(
            result.ok,
            result.code,
            data={**result.data, "audit_id": audit_id},
            diagnostics=result.diagnostics,
        )
