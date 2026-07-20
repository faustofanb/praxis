from __future__ import annotations

from pathlib import Path

import pytest

import praxis.application as application_module
from praxis.application import PraxisApplication
from praxis.result import Result


class FakeGraph:
    def __init__(self, *args, **kwargs):
        pass

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

    def create(self, branch: str, base: str) -> Result:
        return Result(True, data={"branch": branch, "base": base})

    def list(self) -> Result:
        return Result(True, data={"items": []})

    def remove(self, branch: str) -> Result:
        return Result(True, data={"removed": branch})

    def merge(self, target: str) -> Result:
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


@pytest.fixture
def application(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PraxisApplication:
    monkeypatch.setattr(application_module, "CodeGraphService", FakeGraph)
    monkeypatch.setattr(application_module, "WorktreeService", FakeWorktree)
    monkeypatch.setattr(application_module, "TaskService", FakeTask)
    return PraxisApplication(tmp_path)


def test_workspace_requirement_and_skill_dispatch(application: PraxisApplication) -> None:
    root = application.root
    initialized = application.execute(
        "workspace.init",
        {
            "workspace_id": "demo",
            "product_family": "family",
            "projects": [{"id": "app", "kind": "python", "path": "app", "default_branch": "main"}],
        },
    )
    assert initialized.ok
    assert application.execute("workspace.inspect").data["schema_version"] == 2
    assert application.execute("workspace.bootstrap").ok
    assert application.execute(
        "requirement.create",
        {
            "requirement_id": "REQ-1",
            "title": "Example",
            "request": "Original",
            "domain_tags": ["demo"],
        },
    ).ok
    assert (root / "knowledge" / "requirements" / "REQ-1").exists()
    assert application.execute("skill.inspect", {"id": "dbx-database-investigation"}).ok
    uri = "praxis://skills/system/dbx-database-investigation"
    assert application.execute("skill.resource", {"uri": uri}).ok


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


@pytest.mark.parametrize(
    ("operation", "arguments"),
    [
        ("worktree.create", {"branch": "feature", "base": "main"}),
        ("worktree.list", {}),
        ("worktree.remove", {"branch": "feature"}),
        ("worktree.merge", {"target": "main"}),
        ("worktree.install-hooks", {"project_id": "app"}),
        ("task.start", {"task_id": "T", "title": "T", "project_id": "app"}),
        ("task.resume", {"task_id": "T"}),
        ("task.progress", {"task_id": "T", "message": "done"}),
        ("task.inspect", {"task_id": "T"}),
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
