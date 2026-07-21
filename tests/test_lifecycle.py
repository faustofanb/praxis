from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from praxis.codegraph.lifecycle import CodeGraphLifecycle
from praxis.domain.requirement import RequirementStatus
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService
from praxis.worktree.lifecycle import WorktreeLifecycle
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

    def run(
        command: list[str], cwd: Path, environment: dict[str, str] | None
    ) -> subprocess.CompletedProcess[str]:
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


def test_worktree_creation_binds_requirement_repository_and_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示开发工作空间",
        "知识库",
        [
            Project(
                "app",
                "python",
                "repo",
                "local",
                template_branches=("develop",),
                lint_commands=("ruff check .",),
                typecheck_commands=("ty check",),
            )
        ],
    )
    store = StateStore(tmp_path)
    requirement = store.create_requirement("演示需求实现", "原始需求", ["demo"], [])
    for status in (
        RequirementStatus.INVESTIGATING,
        RequirementStatus.ANALYZED,
        RequirementStatus.PLANNED,
        RequirementStatus.READY,
    ):
        store.transition_requirement(requirement["requirement_id"], status)
    calls: list[tuple[list[str], Path, dict[str, str] | None]] = []
    template_path = tmp_path / ".worktrees" / ".templates" / "app"

    def run(
        command: list[str], cwd: Path, environment: dict[str, str] | None
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, cwd, environment))
        if command[:3] == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, "abc123\n", "")
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 0, "", "")
        path = "created" if "--create" in command else str(template_path)
        return subprocess.CompletedProcess(command, 0, f'{{"path": "{path}"}}', "")

    result = WorktreeService(tmp_path, run=run).create_for_requirement(
        requirement["requirement_id"], "app", "backend"
    )

    assert result.ok
    assert result.data["branch"] == f"req/{requirement['requirement_id']}/02-backend"
    assert result.data["base_branch"] == "local"
    assert result.data["upstream_branch"] == "origin/develop"
    assert result.data["base_revision"] == "abc123"
    assert [call[0] for call in calls[:5]] == [
        ["git", "fetch", "origin", "develop"],
        [
            "wt",
            "switch",
            "local",
            "--no-cd",
            "--no-hooks",
            "--format=json",
            "--yes",
        ],
        ["git", "status", "--porcelain"],
        ["git", "merge", "--no-edit", "origin/develop"],
        ["git", "rev-parse", "HEAD"],
    ]
    command, cwd, environment = calls[5]
    assert cwd == repo
    assert command[:5] == [
        "wt",
        "switch",
        "--create",
        result.data["branch"],
        "--base",
    ]
    assert environment and environment["WORKTRUNK_WORKTREE_PATH"].endswith(
        f"演示需求实现__{requirement['requirement_id']}/02-后端开发/app"
    )
    context = {
        "branch": result.data["branch"],
        "repo_path": str(repo),
        "worktree_path": result.data["path"],
    }
    lifecycle = WorktreeLifecycle(tmp_path)
    assert lifecycle.run("worktree-pre-start", context).ok

    import praxis.worktree.lifecycle as lifecycle_module

    process_calls: list[list[str]] = []

    class SuccessfulGraphHooks:
        def __init__(self, root: Path):
            pass

        def run(self, *args, **kwargs) -> Result:
            return Result(True)

    class SuccessfulProcessRunner:
        def __init__(self, cwd: Path, **kwargs):
            pass

        def run(self, command: list[str], *, machine_output: bool) -> Result:
            process_calls.append(command)
            return Result(True, data={"command": command, "stdout": ""})

    monkeypatch.setattr(lifecycle_module, "CodeGraphHooks", SuccessfulGraphHooks)
    monkeypatch.setattr(lifecycle_module, "ProcessRunner", SuccessfulProcessRunner)
    assert lifecycle.run("pre-commit", context).ok
    assert lifecycle.run("pre-merge", context).ok
    assert process_calls == [
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    skipped = {
        event["event"]
        for event in StateStore(tmp_path).audit_events()
        if event["code"] == "USER_APPROVAL_REQUIRED"
    }
    assert skipped == {"quality.execution_skipped", "test.execution_skipped"}
    assert any(
        event["event"] == "worktree.template_synced"
        for event in StateStore(tmp_path).audit_events()
    )


def test_worktree_creation_blocks_when_local_template_branch_is_dirty(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    template_path = tmp_path / ".worktrees" / ".templates" / "app"
    repo.mkdir()
    template_path.mkdir(parents=True)
    calls: list[list[str]] = []

    def run(
        command: list[str], cwd: Path, environment: dict[str, str] | None
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[0] == "wt":
            return subprocess.CompletedProcess(
                command,
                0,
                f'{{"path": "{template_path}"}}',
                "",
            )
        stdout = "local.env\n" if command[:3] == ["git", "status", "--porcelain"] else ""
        return subprocess.CompletedProcess(command, 0, stdout, "")

    project = Project(
        "app",
        "python",
        "repo",
        "local",
        template_branches=("develop",),
    )
    result = WorktreeService(tmp_path, run=run)._sync_default_branch(
        project, "app", repo
    )

    assert not result.ok
    assert result.code == "WORKTREE_TEMPLATE_DIRTY"
    assert result.data == {"path": str(template_path), "branch": "local"}
    assert not any(command[:2] == ["git", "merge"] for command in calls)


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
    for event in (
        "worktree-pre-start",
        "worktree-post-start",
        "pre-commit",
        "pre-merge",
        "post-merge",
        "post-remove",
    ):
        assert f"lifecycle {event} --stdin-json" in config


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
