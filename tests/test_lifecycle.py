from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from praxis.codegraph.lifecycle import CodeGraphLifecycle
from praxis.result import Result
from praxis.workspace.service import Project, WorkspaceService
from praxis.worktree.service import WorktreeService


class FakeGraph:
    def __init__(self, outcomes: dict[str, Result] | None = None):
        self.calls: list[tuple[str, bool | None]] = []
        self.outcomes = outcomes or {}

    def ensure_fresh(self, *, initialize: bool = False) -> Result:
        self.calls.append(("ensure_fresh", initialize))
        return self.outcomes.get("ensure_fresh", Result(True))

    def sync(self) -> Result:
        self.calls.append(("sync", None))
        return self.outcomes.get("sync", Result(True))

    def affected(self) -> Result:
        self.calls.append(("affected", None))
        return self.outcomes.get("affected", Result(True, data={"nodes": []}))

    def remove_metadata(self) -> Result:
        self.calls.append(("remove_metadata", None))
        return Result(True)


def test_worktree_service_uses_only_worktrunk_json_commands(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        outputs = {
            "switch": '{"path": "/tmp/worktree"}',
            "list": '{"schema_version": 2, "worktrees": []}',
        }
        return subprocess.CompletedProcess(command, 0, outputs.get(command[1], "{}"), "")

    service = WorktreeService(tmp_path, run=run)
    assert service.create("feature/x", "main").data["path"] == "/tmp/worktree"
    assert service.list().ok
    assert service.remove("feature/x").ok
    assert service.merge("main").ok
    assert all(command[0] == "wt" and "--format=json" in command for command in calls)


def test_codegraph_lifecycle_covers_worktrunk_and_verification_events() -> None:
    graph = FakeGraph()
    lifecycle = CodeGraphLifecycle(graph)  # type: ignore[arg-type]

    assert lifecycle.post_start().ok
    assert lifecycle.task_context(graph_required=True).ok
    assert lifecycle.change_preflight().ok
    assert lifecycle.verify().ok
    assert lifecycle.pre_merge().ok
    assert lifecycle.post_merge().ok
    assert lifecycle.post_remove().ok
    assert graph.calls == [
        ("ensure_fresh", True),
        ("ensure_fresh", False),
        ("ensure_fresh", False),
        ("ensure_fresh", False),
        ("sync", None),
        ("affected", None),
        ("sync", None),
        ("remove_metadata", None),
    ]


def test_simple_context_can_fallback_but_graph_required_context_blocks() -> None:
    failed = Result(False, "CODEGRAPH_SYNC_FAILED")
    lifecycle = CodeGraphLifecycle(FakeGraph({"ensure_fresh": failed}))  # type: ignore[arg-type]

    fallback = lifecycle.task_context(graph_required=False)
    blocked = lifecycle.task_context(graph_required=True)

    assert fallback.ok
    assert fallback.code == "CODEGRAPH_RG_FALLBACK"
    assert blocked == failed


def test_pre_merge_does_not_query_affected_after_sync_failure() -> None:
    graph = FakeGraph({"sync": Result(False, "CODEGRAPH_SYNC_FAILED")})
    result = CodeGraphLifecycle(graph).pre_merge()  # type: ignore[arg-type]
    assert not result.ok
    assert graph.calls == [("sync", None)]


def test_worktrunk_hook_installation_wires_codegraph_lifecycle(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    WorkspaceService(tmp_path).init(
        "demo", "family", "knowledge", [Project("app", "python", "repo", "main")]
    )

    result = WorktreeService(tmp_path).install_hooks("app")

    assert result.ok
    config = (repo / ".config" / "wt.toml").read_text()
    assert "post-start" in config and "--initialize" in config
    assert "pre-merge" in config and "post-merge" in config and "post-remove" in config
    assert "{{ worktree_path }}" in config
    assert "{{ cwd }}" in config


@pytest.mark.parametrize("event", ["task_start", "change_preflight", "verify", "delivery"])
def test_gate_event_names_are_code_owned(event: str) -> None:
    from praxis.gates.engine import GateEvent

    assert GateEvent(event).value == event


def test_gate_engine_runs_in_order_and_stops_on_first_failure() -> None:
    from praxis.gates.engine import GateEngine, GateEvent

    engine = GateEngine()
    calls = []
    engine.register(GateEvent.VERIFY, lambda context: calls.append("first") or Result(True))
    engine.register(
        GateEvent.VERIFY,
        lambda context: calls.append("blocked") or Result(False, "BLOCKED"),
    )
    engine.register(GateEvent.VERIFY, lambda context: calls.append("never") or Result(True))

    result = engine.run(GateEvent.VERIFY, {"project": "app"})
    assert not result.ok and result.code == "BLOCKED"
    assert calls == ["first", "blocked"]


def test_gate_engine_returns_success_for_empty_chain() -> None:
    from praxis.gates.engine import GateEngine, GateEvent

    assert GateEngine().run(GateEvent.DELIVERY).ok


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ("post-start", "ensure_fresh"),
        ("task-context", "ensure_fresh"),
        ("change-preflight", "ensure_fresh"),
        ("verify", "ensure_fresh"),
        ("pre-merge", "sync"),
        ("post-merge", "sync"),
        ("post-remove", "remove_metadata"),
    ],
)
def test_codegraph_hook_dispatch(monkeypatch, tmp_path: Path, event: str, expected: str) -> None:
    import praxis.codegraph.hooks as hooks_module

    graph = FakeGraph()
    monkeypatch.setattr(hooks_module, "CodeGraphService", lambda *args, **kwargs: graph)
    result = hooks_module.CodeGraphHooks(tmp_path).run(event, "app", initialize=True)
    assert result.ok
    assert graph.calls[0][0] == expected


def test_unknown_codegraph_hook_is_rejected(monkeypatch, tmp_path: Path) -> None:
    import praxis.codegraph.hooks as hooks_module

    monkeypatch.setattr(hooks_module, "CodeGraphService", lambda *args, **kwargs: FakeGraph())
    assert hooks_module.CodeGraphHooks(tmp_path).run("unknown", "app").code == "HOOK_NOT_FOUND"
