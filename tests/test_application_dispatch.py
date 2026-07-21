from __future__ import annotations

from pathlib import Path

import pytest

import praxis.application as application_module
from praxis.application import PraxisApplication
from praxis.result import Result


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

    def remove(self, branch: str) -> Result:
        return Result(True, data={"removed": branch})

    def merge(self, target: str, **kwargs) -> Result:
        return Result(True, data={"target": target})

    def install_hooks(self, project_id: str) -> Result:
        return Result(True, data={"project_id": project_id})


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

    result = application.execute("requirement.analyze", {"requirement_id": requirement_id})

    assert result.ok
    assert result.data["status"] == "investigating"


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
    assert Path(FakeGraph.last_repo) == repository_path

    by_path = application.execute(
        "codegraph.status", {"worktree": repository_path}
    )
    assert by_path.ok
    assert by_path.data["binding_id"] == "WT-REQ-TEST--backend"


@pytest.mark.parametrize(
    ("operation", "arguments"),
    [
        (
            "worktree.create",
            {"requirement_id": "REQ-20260720-001", "repository_id": "app", "stage": "backend"},
        ),
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
