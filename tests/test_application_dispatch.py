from __future__ import annotations

from pathlib import Path

import pytest

import praxis.application as application_module
from praxis.application import PraxisApplication
from praxis.domain.requirement import RequirementStatus
from praxis.result import Result
from praxis.skills.routing import (
    NodeSkillRouter,
    NodeSkillRoutingRequest,
    SkillInvocationService,
)
from praxis.storage.sqlite import StateStore


class FakeGraph:
    last_repo = None

    def __init__(self, *args, **kwargs):
        type(self).last_repo = kwargs.get("repo")

    def status(self) -> Result:
        return Result(True, data={"action": "status"})

    def build(self) -> Result:
        return Result(True, data={"action": "build"})

    def sync(self) -> Result:
        return Result(True, data={"action": "sync"})

    def ensure_fresh(self, *, initialize: bool = False) -> Result:
        return Result(True, data={"action": "ensure", "initialize": initialize})

    def query(self, target: str) -> Result:
        return Result(True, data={"action": "query", "target": target})

    def explore(self, target: str) -> Result:
        return Result(True, data={"action": "explore", "target": target})

    def node(self, target: str) -> Result:
        return Result(True, data={"action": "node", "target": target})

    def affected(self) -> Result:
        return Result(True, data={"action": "affected"})


class FakeWorktree:
    def __init__(self, root):
        pass

    def create_for_requirement(self, requirement_id: str, repository_id: str, stage=None) -> Result:
        return Result(True, data={"requirement_id": requirement_id, "stage": stage})

    def list(self) -> Result:
        return Result(True, data={"items": []})

    def status(self, *, binding_id: str = "", worktree_path: str = "") -> Result:
        return Result(
            True,
            data={"items": [], "binding_id": binding_id, "worktree": worktree_path},
        )

    def remove(self, branch: str) -> Result:
        return Result(True, data={"removed": branch})

    def merge(self, target: str, **kwargs) -> Result:
        return Result(True, data={"target": target})

    def install_hooks(self, project_id: str) -> Result:
        return Result(True, data={"project_id": project_id})

    def preview_for_requirement(self, requirement_id: str, repository_ids) -> Result:
        return Result(True, "WORKTREE_PREVIEWED", data={"repositories": repository_ids})

    def ensure_for_requirement(self, requirement_id: str, repository_ids, *, preview_id) -> Result:
        return Result(
            True,
            "WORKTREE_ENSURED",
            data={
                "preview_id": preview_id,
                "items": [
                    {
                        "repository_id": repository_id,
                        "ok": True,
                        "code": "OK",
                        "data": {
                            "binding_id": f"WT-{requirement_id}--{repository_id}",
                            "repository_id": repository_id,
                            "stage": "development",
                            "allowed_paths": ["**"],
                            "forbidden_paths": [".git", ".praxis", ".env"],
                            "path": str(Path("worktrees") / requirement_id),
                        },
                    }
                    for repository_id in repository_ids
                ],
            },
        )

    def prepare_for_requirement(self, requirement_id: str, repository_id: str) -> Result:
        return Result(True, "WORKTREE_SETUP_COMPLETED", data={"repository_id": repository_id})

    def migrate_name(self, requirement_id: str, repository_id: str) -> Result:
        return Result(True, "WORKTREE_NAME_MIGRATED", data={"repository_id": repository_id})


class FakeTask:
    def __init__(self, root):
        pass

    def start(self, task_id, title, project_id, **kwargs) -> Result:
        return Result(True, data={"id": task_id})

    def resume(self, task_id: str) -> Result:
        return Result(True, data={"id": task_id})

    def progress(self, task_id: str, message: str) -> Result:
        return Result(True, data={"message": message})

    def inspect(self, task_id: str):
        return {"id": task_id} if task_id != "missing" else None


class FakeDatabase:
    def __init__(self, root):
        pass

    def connections(self, project_id: str) -> Result:
        return Result(True, data={"project_id": project_id})

    def discover(self) -> Result:
        return Result(True, data={"connections": []})

    def query(self, project_id: str, connection_ref: str, sql: str, **kwargs) -> Result:
        return Result(
            True,
            data={
                "project_id": project_id,
                "connection_ref": connection_ref,
                "sql": sql,
                **kwargs,
            },
        )


@pytest.fixture
def application(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PraxisApplication:
    monkeypatch.setattr(application_module, "CodeGraphService", FakeGraph)
    monkeypatch.setattr(application_module, "WorktreeService", FakeWorktree)
    monkeypatch.setattr(application_module, "TaskService", FakeTask)
    monkeypatch.setattr(application_module, "DatabaseService", FakeDatabase)
    return PraxisApplication(tmp_path)


def test_workspace_requirement_and_skill_dispatch(application: PraxisApplication) -> None:
    root = application.root
    initialized = application.execute(
        "workspace.init",
        {
            "workspace_id": "demo",
            "name": "演示开发工作空间",
        },
    )
    assert initialized.ok
    assert application.execute("workspace.inspect").data["schema_version"] == 3
    assert application.execute(
        "system.add",
        {"system_id": "demo-system", "name": "演示系统", "domains": ["demo"]},
    ).ok
    bootstrap = application.execute("workspace.bootstrap")
    assert bootstrap.ok
    assert {Path(path).name for path in bootstrap.data["agent_guidance"]["files"]} == {
        "AGENTS.md",
        "CLAUDE.md",
    }
    assert application.execute(
        "requirement.new",
        {
            "short_name": "演示需求实现",
            "request": "原始需求",
            "systems": ["demo-system"],
            "domains": ["demo"],
        },
    ).ok
    assert list((root / "知识库" / "需求").rglob("原始需求.md"))
    assert application.execute("skill.inspect", {"id": "dbx-database-investigation"}).ok
    uri = "praxis://skills/system/dbx-database-investigation"
    assert application.execute("skill.resource", {"uri": uri}).ok


def test_requirement_analyze_does_not_skip_investigating_node(
    application: PraxisApplication,
) -> None:
    assert application.execute(
        "workspace.init", {"workspace_id": "demo", "name": "演示开发工作空间"}
    ).ok
    created = application.execute(
        "requirement.new",
        {
            "short_name": "调查节点保留",
            "request": "调查后再分析",
            "systems": [],
            "domains": [],
        },
    )
    requirement_id = created.data["requirement_id"]

    blocked = application.execute("requirement.analyze", {"requirement_id": requirement_id})

    assert not blocked.ok
    assert blocked.code == "SKILL_ROUTE_NOT_FOUND"
    assert application.execute("requirement.show", {"requirement_id": requirement_id}).data[
        "status"
    ] == RequirementStatus.CAPTURED

    assert NodeSkillRouter(application.root).route(
        NodeSkillRoutingRequest(
            node="captured",
            requirement_id=requirement_id,
            token_budget=5_000,
        )
    ).ok
    invocations = SkillInvocationService(application.root)
    started = invocations.start(
        requirement_id, "captured", "praxis-requirement-workflow"
    )
    assert started.ok
    assert invocations.complete(started.data["invocation_id"]).ok

    result = application.execute("requirement.analyze", {"requirement_id": requirement_id})

    assert result.ok
    assert result.data["status"] == "investigating"


def test_worktree_create_requires_current_ready_skill_gate(
    application: PraxisApplication,
) -> None:
    assert application.execute(
        "workspace.init", {"workspace_id": "demo", "name": "演示开发工作空间"}
    ).ok
    created = application.execute(
        "requirement.new",
        {
            "short_name": "工作树门禁",
            "request": "完成 ready 门禁后创建工作树",
            "systems": [],
            "domains": [],
        },
    )
    requirement_id = created.data["requirement_id"]
    store = StateStore(application.root)
    for status in (
        RequirementStatus.INVESTIGATING,
        RequirementStatus.ANALYZED,
        RequirementStatus.PLANNED,
        RequirementStatus.READY,
    ):
        store.transition_requirement(requirement_id, status)

    blocked = application.execute(
        "worktree.create",
        {"requirement_id": requirement_id, "repository_id": "app"},
    )

    assert not blocked.ok
    assert blocked.code == "SKILL_ROUTE_NOT_FOUND"

    assert NodeSkillRouter(application.root).route(
        NodeSkillRoutingRequest(
            node="ready",
            requirement_id=requirement_id,
            token_budget=5_000,
        )
    ).ok
    invocations = SkillInvocationService(application.root)
    started = invocations.start(
        requirement_id, "ready", "praxis-requirement-workflow"
    )
    assert started.ok
    assert invocations.complete(started.data["invocation_id"]).ok

    created_worktree = application.execute(
        "worktree.create",
        {"requirement_id": requirement_id, "repository_id": "app"},
    )
    assert created_worktree.ok


@pytest.mark.parametrize(
    ("operation", "arguments", "key"),
    [
        ("codegraph.status", {"project_id": "app"}, "status"),
        ("codegraph.build", {"project_id": "app"}, "build"),
        ("codegraph.sync", {"project_id": "app"}, "sync"),
        ("codegraph.ensure-fresh", {"project_id": "app", "initialize": True}, "ensure"),
        ("codegraph.query", {"project_id": "app", "target": "A"}, "query"),
        ("codegraph.explore", {"project_id": "app", "target": "A"}, "explore"),
        ("codegraph.node", {"project_id": "app", "target": "A"}, "node"),
        ("codegraph.affected", {"project_id": "app"}, "affected"),
    ],
)
def test_codegraph_dispatch(application, operation, arguments, key) -> None:
    assert application.execute(operation, arguments).data["action"] == key


def test_codegraph_status_resolves_bound_repository_worktree(
    application: PraxisApplication,
) -> None:
    from praxis.storage.sqlite import StateStore

    repository_path = application.root / ".worktrees" / "REQ-TEST" / "backend"
    StateStore(application.root).set(
        "worktree",
        "WT-REQ-TEST--backend",
        {
            "binding_id": "WT-REQ-TEST--backend",
            "requirement_id": "REQ-TEST",
            "repository_id": "backend",
            "repository_path": str(repository_path),
            "path": str(repository_path.parent),
            "branch": "praxis/REQ-TEST",
            "status": "active",
        },
    )

    result = application.execute(
        "codegraph.status", {"binding_id": "WT-REQ-TEST--backend"}
    )

    assert result.ok
    assert result.data["binding_id"] == "WT-REQ-TEST--backend"
    assert FakeGraph.last_repo is not None
    assert Path(FakeGraph.last_repo) == repository_path

    by_path = application.execute(
        "codegraph.status", {"worktree": repository_path}
    )
    assert by_path.ok
    assert by_path.data["binding_id"] == "WT-REQ-TEST--backend"


def test_governance_operations_dispatch_with_timing_metadata(tmp_path: Path) -> None:
    application = PraxisApplication(tmp_path)
    assert application.execute(
        "init", {"workspace_id": "demo", "name": "演示工作空间"}
    ).ok
    requirement = StateStore(tmp_path).create_requirement("验证批准", "运行验证", [], [])
    requirement_id = requirement["requirement_id"]

    granted = application.execute(
        "approval.grant",
        {
            "requirement_id": requirement_id,
            "scope": "verification",
            "entries": ["pytest"],
            "user_evidence": "用户批准",
            "authorized_by_user": True,
        },
    )
    checked = application.execute(
        "approval.check",
        {
            "requirement_id": requirement_id,
            "scope": "verification",
            "entry": "pytest",
        },
    )
    consumed = application.execute(
        "budget.consume",
        {
            "requirement_id": requirement_id,
            "node": "in_progress",
            "kind": "retry",
            "operation_key": "setup:backend",
        },
    )
    status = application.execute(
        "budget.status", {"requirement_id": requirement_id, "node": "in_progress"}
    )

    assert granted.ok and checked.ok and consumed.ok and status.ok
    assert all(
        "duration_ms" in result.data
        for result in (granted, checked, consumed, status)
    )
    assert all(
        "timing_audit_id" in result.data
        for result in (granted, checked, consumed, status)
    )


def test_fast_path_operations_dispatch_through_public_application(
    application: PraxisApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert application.execute(
        "init", {"workspace_id": "demo", "name": "演示工作空间"}
    ).ok
    store = StateStore(application.root)
    requirement = store.create_requirement("快速路径", "验证公共入口", [], [])
    requirement_id = requirement["requirement_id"]
    route = application.execute(
        "skill.route-node",
        {
            "node": "in_progress",
            "requirement_id": requirement_id,
            "intent": "实现最小正确修改",
            "budget": 5_000,
        },
    )
    required = {
        item["id"]
        for item in route.data["decisions"]
        if item["mode"] == "required"
    }
    completed = application.execute(
        "skill.complete-node",
        {
            "node": "in_progress",
            "requirement_id": requirement_id,
            "intent": "实现最小正确修改",
            "outcomes": {skill_id: "已完成" for skill_id in required},
            "budget": 5_000,
        },
    )
    assert completed.ok

    report = application.root / "report.txt"
    report.write_text("passed")
    artifact = application.execute(
        "artifact.add",
        {
            "requirement_id": requirement_id,
            "artifact_type": "test-report",
            "source_path": report,
            "stage": "verify",
        },
    )
    assert application.execute(
        "artifact.verify", {"artifact_id": artifact.data["artifact_id"]}
    ).ok
    assert application.execute(
        "artifact.list", {"requirement_id": requirement_id}
    ).ok

    store.set(
        "agent_session",
        "SES-FAST",
        {"session_id": "SES-FAST", "requirement_id": requirement_id},
    )
    assert application.execute(
        "agent.receipt",
        {"session_id": "SES-FAST", "changed_paths": ["src/app.py"]},
    ).ok
    assert application.execute("agent.sessions").ok

    monkeypatch.setattr(
        application,
        "_gate_current_skill_route",
        lambda requirement_id: Result(True),
    )
    assert application.execute(
        "worktree.preview",
        {"requirement_id": requirement_id, "repository_ids": ["backend"]},
    ).ok
    assert application.execute(
        "worktree.ensure",
        {
            "requirement_id": requirement_id,
            "repository_ids": ["backend"],
            "preview_id": "WTP-FAST",
        },
    ).ok
    assert application.execute(
        "worktree.prepare",
        {"requirement_id": requirement_id, "repository_id": "backend"},
    ).ok
    assert application.execute(
        "worktree.migrate-name",
        {"requirement_id": requirement_id, "repository_id": "backend"},
    ).ok

    for status in (
        RequirementStatus.INVESTIGATING,
        RequirementStatus.ANALYZED,
        RequirementStatus.PLANNED,
        RequirementStatus.READY,
        RequirementStatus.IN_PROGRESS,
        RequirementStatus.VERIFYING,
    ):
        store.transition_requirement(requirement_id, status)
    assert application.execute(
        "requirement.reopen",
        {"requirement_id": requirement_id, "reason": "验证后继续开发"},
    ).ok


def test_worktree_ensure_builds_coder_context_bundle_without_portrait(
    application: PraxisApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = application.root / "backend"
    repository.mkdir()
    from praxis.workspace.service import Project, WorkspaceService

    WorkspaceService(application.root).init(
        "demo",
        "演示工作空间",
        projects=[
            Project(
                "backend",
                "python",
                "backend",
                "main",
                database_connections=("dbx://LOCAL/demo",),
            )
        ],
    )
    requirement = application.execute(
        "requirement.new",
        {
            "short_name": "自动上下文",
            "request": "创建工作树后自动生成上下文",
            "systems": ["demo"],
            "domains": [],
        },
    )
    monkeypatch.setattr(application, "_gate_current_skill_route", lambda _: Result(True))

    result = application.execute(
        "worktree.ensure",
        {
            "requirement_id": requirement.data["requirement_id"],
            "repository_ids": ["backend"],
            "preview_id": "WTP-CONTEXT",
        },
    )

    assert result.ok
    assert result.data["context_errors"] == []
    assert result.data["context_bundles"][0]["project_id"] == "backend"
    assert result.data["context_bundles"][0]["critical_facts"]["database"][
        "registered"
    ] == ["dbx://LOCAL/demo"]


def test_worktree_partial_ensure_keeps_context_for_successful_repository(
    application: PraxisApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = application.root / "backend"
    repository.mkdir()
    from praxis.workspace.service import Project, WorkspaceService

    WorkspaceService(application.root).init(
        "demo",
        "演示工作空间",
        projects=[Project("backend", "python", "backend", "main")],
    )
    requirement = application.execute(
        "requirement.new",
        {
            "short_name": "部分工作树",
            "request": "成功仓库仍需生成上下文",
            "systems": ["demo"],
            "domains": [],
        },
    )
    monkeypatch.setattr(application, "_gate_current_skill_route", lambda _: Result(True))

    def partial_ensure(*args, **kwargs) -> Result:
        return Result(
            False,
            "WORKTREE_ENSURE_PARTIAL",
            data={
                "items": [
                    {
                        "repository_id": "backend",
                        "ok": True,
                        "code": "OK",
                        "data": {
                            "repository_id": "backend",
                            "stage": "development",
                            "allowed_paths": ["**"],
                            "forbidden_paths": [".env"],
                        },
                    },
                    {
                        "repository_id": "missing",
                        "ok": False,
                        "code": "WORKTREE_ENSURE_REPOSITORY_FAILED",
                        "data": {},
                    },
                ]
            },
        )

    monkeypatch.setattr(FakeWorktree, "ensure_for_requirement", partial_ensure)
    result = application.execute(
        "worktree.ensure",
        {
            "requirement_id": requirement.data["requirement_id"],
            "repository_ids": ["backend", "missing"],
            "preview_id": "WTP-PARTIAL",
        },
    )

    assert not result.ok
    assert result.code == "WORKTREE_ENSURE_PARTIAL"
    assert [item["project_id"] for item in result.data["context_bundles"]] == [
        "backend"
    ]


@pytest.mark.parametrize(
    ("operation", "arguments"),
    [
        ("worktree.list", {}),
        ("worktree.remove", {"branch": "feature"}),
        ("worktree.merge", {"target": "main"}),
        ("worktree.install-hooks", {"project_id": "app"}),
        ("task.start", {"task_id": "T", "title": "T", "project_id": "app"}),
        ("task.resume", {"task_id": "T"}),
        ("task.progress", {"task_id": "T", "message": "done"}),
        ("task.inspect", {"task_id": "T"}),
        ("database.connections", {"project_id": "app"}),
        (
            "database.query",
            {
                "project_id": "app",
                "connection_ref": "dbx://dev",
                "sql": "select 1",
            },
        ),
    ],
)
def test_worktree_and_task_dispatch(application, operation, arguments) -> None:
    assert application.execute(operation, arguments).ok


def test_dispatch_returns_stable_errors(application: PraxisApplication) -> None:
    assert application.execute("task.inspect", {"task_id": "missing"}).code == "TASK_NOT_FOUND"
    unknown_graph = application.execute("codegraph.unknown", {"project_id": "app"})
    assert unknown_graph.code == "OPERATION_NOT_FOUND"
    assert application.execute("worktree.unknown", {}).code == "OPERATION_NOT_FOUND"
    assert application.execute("unknown").code == "OPERATION_NOT_FOUND"
    assert application.execute("workspace.init", {}).code == "INVALID_REQUEST"
