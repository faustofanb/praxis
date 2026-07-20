from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from praxis import __version__
from praxis.codegraph.hooks import CodeGraphHooks
from praxis.codegraph.service import CodeGraphService
from praxis.gates.engine import GateEngine, GateEvent
from praxis.integrations.ponytail import diff_warning
from praxis.integrations.witr import WitrService
from praxis.knowledge.requirements import RequirementService
from praxis.portraits.service import PortraitService
from praxis.result import Result
from praxis.skills.candidates import SkillCandidateService
from praxis.skills.registry import Skill, SkillRegistry
from praxis.tasks.service import TaskService
from praxis.workspace.service import Project, WorkspaceService
from praxis.worktree.service import WorktreeService


def _skill_data(skill: Skill) -> dict[str, Any]:
    data = asdict(skill)
    data["path"] = str(skill.path)
    data["required_tools"] = list(skill.required_tools)
    data["triggers"] = list(skill.triggers)
    return data


class PraxisApplication:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def execute(self, operation: str, arguments: dict[str, Any] | None = None) -> Result:
        values = arguments or {}
        try:
            return self._execute(operation, values)
        except (KeyError, TypeError, ValueError) as error:
            return Result(False, "INVALID_REQUEST", data={"message": str(error)})

    def _execute(self, operation: str, values: dict[str, Any]) -> Result:
        if operation == "version":
            return Result(True, data={"version": __version__})
        if operation == "workspace.init":
            projects = [Project(**item) for item in values.get("projects", [])]
            return WorkspaceService(self.root).init(
                values["workspace_id"],
                values["product_family"],
                values.get("vault", "knowledge"),
                projects,
            )
        if operation == "workspace.inspect":
            return WorkspaceService(self.root).inspect()
        if operation == "workspace.bootstrap":
            workspace = WorkspaceService(self.root).load()
            initialized = []
            for project in workspace.get("projects", []):
                result = CodeGraphService(self.root, project["id"]).ensure_fresh(initialize=True)
                if not result.ok:
                    return result
                initialized.append(project["id"])
            return Result(True, data={"projects": initialized})
        if operation == "requirement.create":
            return RequirementService(self.root).create(
                values["requirement_id"],
                values["title"],
                values["request"],
                values.get("domain_tags", []),
            )
        if operation == "skill.inspect":
            return Result(True, data=_skill_data(SkillRegistry.bundled().inspect(values["id"])))
        if operation == "skill.route":
            skills = SkillRegistry.bundled().route(
                values["intent"], budget=values.get("budget", 2000)
            )
            return Result(
                True,
                data={
                    "skills": [_skill_data(skill) for skill in skills],
                    "context_budget": sum(skill.context_budget for skill in skills),
                },
            )
        if operation == "skill.resource":
            content = SkillRegistry.bundled().resource(values["uri"])
            return Result(True, data={"uri": values["uri"], "content": content})
        if operation == "skill.candidate":
            return SkillCandidateService(self.root).generate(values["project_id"])
        if operation == "skill.approve":
            return SkillCandidateService(self.root).promote(
                values["id"], values["catalog_root"], approved=values.get("approved", False)
            )
        if operation.startswith("codegraph."):
            return self._codegraph(operation.removeprefix("codegraph."), values)
        if operation.startswith("worktree."):
            return self._worktree(operation.removeprefix("worktree."), values)
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
        if operation == "portrait.scan":
            return PortraitService(self.root).scan(values["project_id"])
        if operation == "gate.run":
            return self._gate(values)
        if operation == "runtime.diagnose":
            return WitrService(self.root).diagnose(values.get("arguments", []), explicit=True)
        return Result(False, "OPERATION_NOT_FOUND", data={"operation": operation})

    def _codegraph(self, action: str, values: dict[str, Any]) -> Result:
        graph = CodeGraphService(self.root, values["project_id"])
        if action == "status":
            return graph.status()
        if action == "build":
            return graph.build()
        if action == "sync":
            return graph.sync()
        if action == "ensure-fresh":
            return graph.ensure_fresh(initialize=values.get("initialize", False))
        if action in {"query", "explore", "node"}:
            return getattr(graph, action)(values["target"])
        if action == "affected":
            return graph.affected()
        return Result(False, "OPERATION_NOT_FOUND", data={"operation": f"codegraph.{action}"})

    def _worktree(self, action: str, values: dict[str, Any]) -> Result:
        worktree = WorktreeService(self.root)
        if action == "create":
            return worktree.create(values["branch"], values.get("base", "main"))
        if action == "list":
            return worktree.list()
        if action == "remove":
            return worktree.remove(values["branch"])
        if action == "merge":
            return worktree.merge(values.get("target", "main"))
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
        return engine.run(event, values)
