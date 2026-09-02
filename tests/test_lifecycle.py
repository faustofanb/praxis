from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from praxis.codegraph.lifecycle import CodeGraphLifecycle
from praxis.codegraph.service import CodeGraphService
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


def test_worktree_remove_falls_back_to_git_branch_delete_and_cleans_binding(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示开发工作空间",
        "知识库",
        [Project("app", "python", "repo", "local")],
    )
    branch = "praxis/REQ-TEST"
    workspace_path = tmp_path / ".worktrees" / "REQ-TEST__清理验证"
    repository_path = workspace_path / "app"
    repository_path.mkdir(parents=True)
    store = StateStore(tmp_path)
    store.set(
        "worktree",
        "WT-REQ-TEST--app",
        {
            "binding_id": "WT-REQ-TEST--app",
            "requirement_id": "REQ-TEST",
            "repository_id": "app",
            "branch": branch,
            "path": str(workspace_path),
            "repository_path": str(repository_path),
            "status": "active",
        },
    )

    calls: list[list[str]] = []

    def run(command, cwd, environment):
        calls.append(command)
        if command[0] == "wt":
            repository_path.rmdir()
            return subprocess.CompletedProcess(
                command,
                0,
                '{"items": [{"branch": "praxis/REQ-TEST", "branch_deleted": true}]}',
                "",
            )
        if command[:3] == ["git", "branch", "--list"]:
            return subprocess.CompletedProcess(command, 0, f"  {branch}\n", "")
        if command[:3] == ["git", "branch", "-D"]:
            return subprocess.CompletedProcess(command, 0, f"Deleted branch {branch}\n", "")
        raise AssertionError(command)

    result = WorktreeService(tmp_path, run=run).remove(branch)

    assert result.ok
    assert ["git", "branch", "-D", branch] in calls
    assert store.get("worktree", "WT-REQ-TEST--app") is None
    assert not workspace_path.exists()
    event = store.audit_events()[-1]
    assert event["event"] == "worktree.removed"


def test_worktree_status_filters_binding_and_projects_bound_active_state(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示开发工作空间",
        "知识库",
        [Project("app", "python", "repo", "local")],
    )
    repository_path = tmp_path / ".worktrees" / "REQ-TEST" / "REQ-TEST__app"
    StateStore(tmp_path).set(
        "worktree",
        "WT-REQ-TEST--app",
        {
            "binding_id": "WT-REQ-TEST--app",
            "requirement_id": "REQ-TEST",
            "repository_id": "app",
            "branch": "praxis/REQ-TEST",
            "path": str(repository_path.parent),
            "repository_path": str(repository_path),
            "status": "active",
        },
    )

    def run(command, cwd, environment):
        assert cwd == repo
        return subprocess.CompletedProcess(
            command,
            0,
            '{"items": [{"branch": "praxis/REQ-TEST", "path": "'
            + str(repository_path)
            + '", "worktree": {"state": "branch_worktree_mismatch"}, "symbols": "⚑"}]}',
            "",
        )

    result = WorktreeService(tmp_path, run=run).status(
        binding_id="WT-REQ-TEST--app"
    )

    assert result.ok
    assert result.data["binding_id"] == "WT-REQ-TEST--app"
    assert len(result.data["items"]) == 1
    item = result.data["items"][0]
    assert item["worktree"]["state"] == "bound_active"
    assert item["worktrunk_state"] == "bound_active"
    assert item["worktrunk_raw_state"] == "branch_worktree_mismatch"


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
    graph_calls: list[tuple[str, Path]] = []
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
        if command[1] == "list":
            repository_path = (
                tmp_path
                / ".worktrees"
                / f"{requirement['requirement_id']}__演示需求实现"
                / f"{requirement['requirement_id']}__演示需求实现__app"
            ).resolve()
            return subprocess.CompletedProcess(
                command,
                0,
                '{"worktrees": [{"branch": "praxis/'
                + requirement["requirement_id"]
                + "__演示需求实现"
                + '", "path": "'
                + str(repository_path)
                + '", "worktree": {"state": "branch_worktree_mismatch"}, '
                '"symbols": "⚑", "statusline": "branch ⚑"}]}',
                "",
            )
        path = "created" if "--create" in command else str(template_path)
        return subprocess.CompletedProcess(command, 0, f'{{"path": "{path}"}}', "")

    service = WorktreeService(
        tmp_path,
        run=run,
        initialize_graph=lambda project_id, path: graph_calls.append((project_id, path))
        or Result(True, "CODEGRAPH_INITED", data={"worktree": str(path)}),
    )
    result = service.create_for_requirement(
        requirement["requirement_id"], "app", "backend"
    )

    assert result.ok
    assert result.data["branch"] == (
        f"praxis/{requirement['requirement_id']}__演示需求实现"
    )
    assert result.data["binding_id"] == f"WT-{requirement['requirement_id']}--app"
    assert result.data["base_branch"] == "local"
    assert result.data["upstream_branch"] == "origin/develop"
    assert result.data["base_revision"] == "abc123"
    assert result.data["status"] == "active"
    assert result.data["codegraph_status"] == "CODEGRAPH_INITED"
    assert graph_calls == [("app", Path(result.data["repository_path"]))]
    commands = [call[0] for call in calls]
    assert commands[:6] == [
        [
            "git",
            "check-ref-format",
            "--branch",
            result.data["branch"],
        ],
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
    command, cwd, environment = next(
        call for call in calls if call[0][1:3] == ["switch", "--create"]
    )
    assert cwd == repo
    assert command[:5] == [
        "wt",
        "switch",
        "--create",
        result.data["branch"],
        "--base",
    ]
    assert environment and environment["WORKTRUNK_WORKTREE_PATH"].endswith(
        f"{requirement['requirement_id']}__演示需求实现/"
        f"{requirement['requirement_id']}__演示需求实现__app"
    )
    assert result.data["path"].endswith(
        f"{requirement['requirement_id']}__演示需求实现"
    )
    assert result.data["repository_path"].endswith(
        f"{requirement['requirement_id']}__演示需求实现/"
        f"{requirement['requirement_id']}__演示需求实现__app"
    )
    context = {
        "branch": result.data["branch"],
        "repo_path": str(repo),
        "worktree_path": result.data["repository_path"],
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

    repeated = service.create_for_requirement(
        requirement["requirement_id"], "app", None
    )
    assert repeated.ok
    assert repeated.code == "WORKTREE_ALREADY_ACTIVE"
    assert repeated.data["branch"] == result.data["branch"]
    assert repeated.data["stages"] == ["backend", "development"]
    assert graph_calls == [
        ("app", Path(result.data["repository_path"])),
        ("app", Path(result.data["repository_path"])),
    ]

    listed = service.list().data["items"][0]
    assert listed["worktree"]["state"] == "bound_active"
    assert listed["worktrunk_state"] == "bound_active"
    assert listed["worktrunk_raw_state"] == "branch_worktree_mismatch"
    assert "⚑" not in listed["symbols"]
    assert "⚑" not in listed["statusline"]


def test_worktree_preview_then_ensure_uses_confirmed_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[Project("app", "python", "repo", "local")],
    )
    store = StateStore(tmp_path)
    requirement = store.create_requirement("批量准备", "一次确认后准备仓库", ["demo"], [])
    service = WorktreeService(tmp_path)
    created: list[tuple[str, str, str | None]] = []

    def create(requirement_id: str, repository_id: str, stage: str | None) -> Result:
        created.append((requirement_id, repository_id, stage))
        return Result(True, data={"repository_id": repository_id, "status": "active"})

    monkeypatch.setattr(service, "create_for_requirement", create)
    preview = service.preview_for_requirement(requirement["requirement_id"], ["app", "app"])
    ensured = service.ensure_for_requirement(
        requirement["requirement_id"],
        ["app", "app"],
        preview_id=preview.data["preview_id"],
    )

    assert preview.ok
    assert preview.data["items"][0]["worktree_display_name"].endswith("__app")
    assert ensured.ok and ensured.code == "WORKTREE_ENSURED"
    assert created == [(requirement["requirement_id"], "app", "development")]


def test_worktree_preview_and_ensure_fail_closed_for_invalid_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[Project("app", "python", "repo", "local")],
    )
    store = StateStore(tmp_path)
    requirement = store.create_requirement("确认门禁", "必须确认最终名称", ["demo"], [])
    requirement_id = requirement["requirement_id"]
    service = WorktreeService(tmp_path)

    assert service.preview_for_requirement("REQ-MISSING", ["app"]).code == (
        "REQUIREMENT_NOT_FOUND"
    )
    assert service.preview_for_requirement(requirement_id, []).code == (
        "WORKTREE_REPOSITORY_REQUIRED"
    )
    preview = service.preview_for_requirement(requirement_id, ["app"])
    assert service.ensure_for_requirement(
        requirement_id, ["other"], preview_id=preview.data["preview_id"]
    ).code == "WORKTREE_PREVIEW_MISMATCH"

    expired = store.get("worktree_preview", preview.data["preview_id"])
    assert expired is not None
    expired["expires_at"] = "invalid"
    store.set("worktree_preview", preview.data["preview_id"], expired)
    assert service.ensure_for_requirement(
        requirement_id, ["app"], preview_id=preview.data["preview_id"]
    ).code == "WORKTREE_PREVIEW_EXPIRED"

    fresh = service.preview_for_requirement(requirement_id, ["app"])
    group_id = f"WTG-{requirement_id}"
    group = store.get("worktree_group", group_id)
    assert group is not None
    group["branch_name"] = f"praxis/{requirement_id}__changed"
    store.set("worktree_group", group_id, group)
    assert service.ensure_for_requirement(
        requirement_id, ["app"], preview_id=fresh.data["preview_id"]
    ).code == "WORKTREE_PREVIEW_STALE"

    current = service.preview_for_requirement(requirement_id, ["app"])
    store.set(
        "worktree_ensure_attempt",
        f"{requirement_id}:app",
        {"attempts": 2, "limit": 2},
    )
    monkeypatch.setattr(
        service,
        "create_for_requirement",
        lambda *args: pytest.fail("retry budget should stop creation"),
    )
    exhausted = service.ensure_for_requirement(
        requirement_id, ["app"], preview_id=current.data["preview_id"]
    )
    assert exhausted.code == "WORKTREE_ENSURE_PARTIAL"
    assert exhausted.data["items"][0]["code"] == "WORKTREE_RETRY_BUDGET_EXHAUSTED"


def test_worktree_ensure_preflight_failures_do_not_consume_retry_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[Project("app", "python", "repo", "local")],
    )
    store = StateStore(tmp_path)
    requirement = store.create_requirement("创建预检", "基础设施失败不消耗重试次数", ["demo"], [])
    requirement_id = requirement["requirement_id"]
    service = WorktreeService(tmp_path)
    results = iter(
        [
            Result(False, "WORKTREE_TEMPLATE_FETCH_FAILED"),
            Result(False, "WORKTREE_TEMPLATE_MERGE_FAILED"),
            Result(True, data={"repository_id": "app", "status": "active"}),
        ]
    )
    calls = 0

    def create(*args: object) -> Result:
        nonlocal calls
        calls += 1
        return next(results)

    monkeypatch.setattr(service, "create_for_requirement", create)

    for expected_code in (
        "WORKTREE_TEMPLATE_FETCH_FAILED",
        "WORKTREE_TEMPLATE_MERGE_FAILED",
    ):
        preview = service.preview_for_requirement(requirement_id, ["app"])
        ensured = service.ensure_for_requirement(
            requirement_id, ["app"], preview_id=preview.data["preview_id"]
        )
        assert ensured.data["items"][0]["code"] == expected_code

    preview = service.preview_for_requirement(requirement_id, ["app"])
    ensured = service.ensure_for_requirement(
        requirement_id, ["app"], preview_id=preview.data["preview_id"]
    )

    assert ensured.ok
    assert calls == 3
    assert store.get("worktree_ensure_attempt", f"{requirement_id}:app") is None


def test_worktree_ensure_creation_failures_consume_retry_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[Project("app", "python", "repo", "local")],
    )
    store = StateStore(tmp_path)
    requirement = store.create_requirement("创建重试", "真实创建失败消耗重试次数", ["demo"], [])
    requirement_id = requirement["requirement_id"]
    service = WorktreeService(tmp_path)
    calls = 0

    def fail_creation(*args: object) -> Result:
        nonlocal calls
        calls += 1
        return Result(False, "WORKTRUNK_FAILED")

    monkeypatch.setattr(service, "create_for_requirement", fail_creation)

    for _ in range(2):
        preview = service.preview_for_requirement(requirement_id, ["app"])
        service.ensure_for_requirement(
            requirement_id, ["app"], preview_id=preview.data["preview_id"]
        )

    preview = service.preview_for_requirement(requirement_id, ["app"])
    exhausted = service.ensure_for_requirement(
        requirement_id, ["app"], preview_id=preview.data["preview_id"]
    )

    attempt = store.get("worktree_ensure_attempt", f"{requirement_id}:app")
    assert attempt is not None and attempt["attempts"] == 2
    assert calls == 2
    assert exhausted.data["items"][0]["code"] == "WORKTREE_RETRY_BUDGET_EXHAUSTED"


def test_worktree_prepare_runs_deferred_setup_once(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    repo.mkdir()
    worktree.mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[
            Project(
                "app",
                "python",
                "repo",
                "local",
                worktree_setup_commands=(f"{sys.executable} --version",),
            )
        ],
    )
    requirement = StateStore(tmp_path).create_requirement(
        "延迟依赖", "首次构建时准备", ["demo"], []
    )
    binding_id = f"WT-{requirement['requirement_id']}--app"
    StateStore(tmp_path).set(
        "worktree",
        binding_id,
        {
            "binding_id": binding_id,
            "requirement_id": requirement["requirement_id"],
            "repository_id": "app",
            "repository_path": str(worktree),
            "status": "active",
            "worktree_setup_status": "WORKTREE_SETUP_DEFERRED",
            "codegraph_status": "CODEGRAPH_QUEUED",
        },
    )
    calls: list[list[str]] = []

    def run(command, cwd, environment):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "Python 3", "")

    service = WorktreeService(tmp_path, run=run)
    prepared = service.prepare_for_requirement(requirement["requirement_id"], "app")
    repeated = service.prepare_for_requirement(requirement["requirement_id"], "app")

    assert prepared.ok and prepared.code == "WORKTREE_SETUP_COMPLETED"
    assert repeated.code == "WORKTREE_SETUP_ALREADY_PREPARED"
    assert calls == [[sys.executable, "--version"]]


def test_worktree_runner_drops_environment_values_that_are_not_utf8(
    tmp_path: Path, monkeypatch
) -> None:
    captured: dict[str, str] = {}
    monkeypatch.setenv("_", "invalid\udcff")

    def run(command, **kwargs):
        captured.update(kwargs["env"])
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)

    WorktreeService._run(["wt", "--version"], tmp_path)

    assert "_" not in captured


def test_worktree_setup_reports_missing_and_failed_commands(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    empty = Project("app", "python", "repo", "local")
    missing = Project(
        "app",
        "python",
        "repo",
        "local",
        worktree_setup_commands=("missing-tool setup",),
    )
    failed = Project(
        "app",
        "python",
        "repo",
        "local",
        worktree_setup_commands=("python setup.py",),
    )

    def missing_run(command, cwd, environment):
        raise FileNotFoundError(command[0])

    def failed_run(command, cwd, environment):
        return subprocess.CompletedProcess(command, 2, "", "failed")

    assert WorktreeService(tmp_path)._run_worktree_setup_commands(
        empty, repository
    ).code == "WORKTREE_SETUP_NOT_CONFIGURED"
    assert WorktreeService(
        tmp_path, run=missing_run
    )._run_worktree_setup_commands(missing, repository).code == (
        "WORKTREE_SETUP_COMMAND_NOT_FOUND"
    )
    assert WorktreeService(
        tmp_path, run=failed_run
    )._run_worktree_setup_commands(failed, repository).code == (
        "WORKTREE_SETUP_COMMAND_FAILED"
    )


def test_local_runtime_files_copy_only_declared_paths_and_preserve_existing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "config").mkdir()
    (source / "config" / ".env.development").write_text("PORT=3000\n")
    project = Project(
        "web",
        "node",
        "source",
        "local",
        local_files=("config/.env.development",),
    )

    copied = WorktreeService._prepare_local_files(project, source, destination)
    existing = WorktreeService._prepare_local_files(project, source, destination)

    assert copied.ok and copied.data["copied"] == ["config/.env.development"]
    assert existing.ok and existing.data["existing"] == ["config/.env.development"]
    assert (destination / "config" / ".env.development").read_text() == "PORT=3000\n"


def test_local_runtime_files_reject_missing_or_unsafe_paths(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    missing = Project("web", "node", "source", "local", local_files=(".env",))
    assert WorktreeService._prepare_local_files(missing, source, destination).code == (
        "WORKTREE_LOCAL_FILE_SOURCE_MISSING"
    )

    outside = tmp_path / "secret.env"
    outside.write_text("TOKEN=secret")
    (source / "linked.env").symlink_to(outside)
    unsafe = Project(
        "web", "node", "source", "local", local_files=("linked.env",)
    )
    assert WorktreeService._prepare_local_files(unsafe, source, destination).code == (
        "WORKTREE_LOCAL_FILE_SOURCE_UNSAFE"
    )


def test_pnpm_setup_uses_exact_project_version_and_valid_lockfile(tmp_path: Path) -> None:
    repository = tmp_path / "web"
    repository.mkdir()
    (repository / "package.json").write_text('{"packageManager":"pnpm@9.15.0"}')
    (repository / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    calls: list[list[str]] = []

    def run(command, cwd, environment):
        calls.append(command)
        stdout = "9.15.0\n" if command[-1] == "--version" else ""
        return subprocess.CompletedProcess(command, 0, stdout, "")

    project = Project(
        "web",
        "node",
        "web",
        "local",
        worktree_setup_commands=("pnpm install --offline",),
    )
    service = WorktreeService(tmp_path, run=run)

    preflight = service._preflight_worktree_setup(project, repository)
    setup = service._run_worktree_setup_commands(project, repository)

    assert preflight.ok and preflight.data["package_managers"][0]["version"] == "9.15.0"
    assert setup.ok and setup.data["completed"] == 1
    assert calls == [
        ["pnpm", "--version"],
        ["pnpm", "--version"],
        ["pnpm", "install", "--offline"],
    ]


@pytest.mark.parametrize(
    ("manifest", "expected_code"),
    [
        (None, "WORKTREE_PACKAGE_MANAGER_MANIFEST_MISSING"),
        ("not-json", "WORKTREE_PACKAGE_MANAGER_MANIFEST_INVALID"),
        ("{}", "WORKTREE_PACKAGE_MANAGER_VERSION_REQUIRED"),
        ('{"packageManager":"npm@11.0.0"}', "WORKTREE_PACKAGE_MANAGER_MISMATCH"),
        ('{"packageManager":"pnpm@latest"}', "WORKTREE_PACKAGE_MANAGER_VERSION_INVALID"),
    ],
)
def test_pnpm_setup_rejects_missing_or_unpinned_project_version(
    tmp_path: Path, manifest: str | None, expected_code: str
) -> None:
    repository = tmp_path / "web"
    repository.mkdir()
    if manifest is not None:
        (repository / "package.json").write_text(manifest)

    result = WorktreeService(tmp_path)._resolve_pnpm(repository)

    assert result.code == expected_code


@pytest.mark.parametrize(
    ("lockfile", "expected_code"),
    [
        (None, "WORKTREE_SETUP_LOCKFILE_MISSING"),
        ("packages: {}\n", "WORKTREE_SETUP_LOCKFILE_INVALID"),
        ("lockfileVersion: '9.0'\n<<<<<<< ours\n", "WORKTREE_SETUP_LOCKFILE_INVALID"),
    ],
)
def test_pnpm_preflight_rejects_missing_or_invalid_lockfile(
    tmp_path: Path, lockfile: str | None, expected_code: str
) -> None:
    repository = tmp_path / "web"
    repository.mkdir()
    (repository / "package.json").write_text('{"packageManager":"pnpm@9.15.0"}')
    if lockfile is not None:
        (repository / "pnpm-lock.yaml").write_text(lockfile)

    def run(command, cwd, environment):
        return subprocess.CompletedProcess(command, 0, "9.15.0\n", "")

    project = Project(
        "web",
        "node",
        "web",
        "local",
        worktree_setup_commands=("pnpm install",),
    )
    result = WorktreeService(tmp_path, run=run)._preflight_worktree_setup(
        project, repository
    )

    assert result.code == expected_code


def test_worktree_name_migration_moves_path_branch_and_reactivates_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    old_workspace = tmp_path / ".worktrees" / "legacy"
    old_repository = old_workspace / "app"
    repo.mkdir()
    old_repository.mkdir(parents=True)
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[Project("app", "python", "repo", "local")],
    )
    store = StateStore(tmp_path)
    requirement = store.create_requirement("可读名称", "迁移旧工作树名称", ["demo"], [])
    binding_id = f"WT-{requirement['requirement_id']}--app"
    old_branch = f"praxis/{requirement['requirement_id']}"
    store.set(
        "worktree",
        binding_id,
        {
            "binding_id": binding_id,
            "requirement_id": requirement["requirement_id"],
            "repository_id": "app",
            "branch": old_branch,
            "path": str(old_workspace),
            "repository_path": str(old_repository),
            "status": "blocked",
        },
    )

    def run(command, cwd, environment):
        if command[:3] == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(command, 0, old_branch + "\n", "")
        if command[:3] == ["git", "branch", "--list"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:3] == ["git", "worktree", "move"]:
            Path(command[3]).rename(Path(command[4]))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(CodeGraphService, "_detect_version", staticmethod(lambda: "test"))
    monkeypatch.setattr(
        CodeGraphService,
        "enqueue",
        lambda self, *, binding_id="": Result(
            True, "CODEGRAPH_QUEUED", data={"job_id": "CGJ-TEST"}
        ),
    )
    migrated = WorktreeService(tmp_path, run=run).migrate_name(
        requirement["requirement_id"], "app"
    )

    assert migrated.ok and migrated.code == "WORKTREE_NAME_MIGRATED"
    assert migrated.data["status"] == "active"
    assert migrated.data["migration_previous_status"] == "blocked"
    assert Path(migrated.data["repository_path"]).name.endswith("__app")
    assert Path(migrated.data["repository_path"]).is_dir()
    assert migrated.data["branch"].endswith("__可读名称")


def test_interrupted_worktree_name_migration_rolls_back_once_and_reactivates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[Project("app", "python", "repo", "local")],
    )
    store = StateStore(tmp_path)
    requirement = store.create_requirement("中断恢复", "恢复迁移中的工作树", ["demo"], [])
    requirement_id = requirement["requirement_id"]
    workspace_name = f"{requirement_id}__中断恢复"
    expected_workspace = tmp_path / ".worktrees" / workspace_name
    expected_repository = expected_workspace / f"{workspace_name}__app"
    expected_repository.mkdir(parents=True)
    old_workspace = tmp_path / ".worktrees" / "legacy"
    old_workspace.mkdir()
    old_repository = old_workspace / "app"
    old_branch = f"praxis/{requirement_id}"
    expected_branch = f"praxis/{workspace_name}"
    binding_id = f"WT-{requirement_id}--app"
    store.set(
        "worktree",
        binding_id,
        {
            "binding_id": binding_id,
            "requirement_id": requirement_id,
            "repository_id": "app",
            "branch": expected_branch,
            "path": str(expected_workspace),
            "repository_path": str(expected_repository),
            "status": "migrating",
            "migration_old_workspace_path": str(old_workspace),
            "migration_old_repository_path": str(old_repository),
            "migration_old_branch": old_branch,
            "migration_previous_status": "blocked",
        },
    )

    def run(command, cwd, environment):
        if command[:3] == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(command, 0, expected_branch + "\n", "")
        if command[:3] == ["git", "worktree", "move"]:
            Path(command[3]).rename(Path(command[4]))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(CodeGraphService, "_detect_version", staticmethod(lambda: "test"))
    monkeypatch.setattr(
        CodeGraphService,
        "enqueue",
        lambda self, *, binding_id="": Result(
            True, "CODEGRAPH_QUEUED", data={"job_id": "CGJ-RECOVERED"}
        ),
    )
    recovered = WorktreeService(tmp_path, run=run).migrate_name(requirement_id, "app")

    assert recovered.ok and recovered.code == "WORKTREE_NAME_MIGRATION_RECOVERED"
    assert recovered.data["status"] == "active"
    assert recovered.data["repository_path"] == str(old_repository)
    assert recovered.data["branch"] == old_branch
    assert old_repository.is_dir() and not expected_repository.exists()


def test_worktree_creation_stays_active_when_codegraph_queueing_fails(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示开发工作空间",
        "知识库",
        [Project("app", "python", "repo", "local", template_branches=("develop",))],
    )
    store = StateStore(tmp_path)
    requirement = store.create_requirement("图谱失败", "原始需求", ["demo"], [])
    for status in (
        RequirementStatus.INVESTIGATING,
        RequirementStatus.ANALYZED,
        RequirementStatus.PLANNED,
        RequirementStatus.READY,
    ):
        store.transition_requirement(requirement["requirement_id"], status)

    def run(command, cwd, environment):
        if command[:3] == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, "abc123\n", "")
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 0, "", "")
        path = "created" if "--create" in command else str(tmp_path / ".templates" / "app")
        return subprocess.CompletedProcess(command, 0, f'{{"path": "{path}"}}', "")

    result = WorktreeService(
        tmp_path,
        run=run,
        initialize_graph=lambda project_id, path: Result(
            False, "CODEGRAPH_NOT_AVAILABLE"
        ),
    ).create_for_requirement(requirement["requirement_id"], "app", None)

    assert result.ok
    assert result.code == "OK"
    binding = store.get("worktree", f"WT-{requirement['requirement_id']}--app")
    assert binding is not None
    assert binding["status"] == "active"
    assert binding["codegraph_status"] == "CODEGRAPH_NOT_AVAILABLE"


def test_worktree_codegraph_busy_keeps_binding_active(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    repo.mkdir()
    worktree.mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示开发工作空间",
        "知识库",
        [Project("app", "python", "repo", "local")],
    )
    store = StateStore(tmp_path)
    binding = {
        "binding_id": "WT-REQ-TEST--app",
        "requirement_id": "REQ-TEST",
        "repository_id": "app",
        "repository_path": str(worktree),
    }
    service = WorktreeService(
        tmp_path,
        initialize_graph=lambda project_id, path: Result(
            False,
            "CODEGRAPH_SYNC_BUSY",
            data={"operation": {"status": "running"}},
        ),
    )

    result = service._activate_binding(store, binding["binding_id"], binding)

    assert result.ok
    assert result.code == "OK"
    persisted = store.get("worktree", binding["binding_id"])
    assert persisted is not None
    assert persisted["status"] == "active"
    assert persisted["codegraph_status"] == "CODEGRAPH_SYNC_BUSY"
    assert "codegraph_completed_at" not in persisted


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


def test_worktree_creation_from_fixed_revision_skips_dirty_template_sync(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示开发工作空间",
        "知识库",
        [Project("app", "python", "repo", "main", template_branches=("develop",))],
    )
    store = StateStore(tmp_path)
    requirement = store.create_requirement("固定模板", "原始需求", ["demo"], [])
    for status in (
        RequirementStatus.INVESTIGATING,
        RequirementStatus.ANALYZED,
        RequirementStatus.PLANNED,
        RequirementStatus.READY,
    ):
        store.transition_requirement(requirement["requirement_id"], status)
    calls: list[list[str]] = []

    def run(command, cwd, environment):
        calls.append(command)
        if command[:4] == ["git", "rev-parse", "--verify", "abc123^{commit}"]:
            return subprocess.CompletedProcess(command, 0, "deadbeef\n", "")
        if command[0] == "wt":
            repository_path = Path(environment["WORKTRUNK_WORKTREE_PATH"])
            repository_path.mkdir(parents=True)
            return subprocess.CompletedProcess(command, 0, "{}", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    result = WorktreeService(
        tmp_path,
        run=run,
        initialize_graph=lambda project_id, path: Result(True, "CODEGRAPH_QUEUED"),
    ).create_for_requirement(
        requirement["requirement_id"],
        "app",
        base_revision="abc123",
    )

    assert result.ok
    assert result.data["base_revision"] == "deadbeef"
    assert [
        "wt",
        "switch",
        "--create",
        result.data["branch"],
        "--base",
        "deadbeef",
        "--no-cd",
        "--format=json",
        "--yes",
    ] in calls
    assert not any(command[:3] == ["git", "status", "--porcelain"] for command in calls)
    assert not any(command[:2] == ["git", "merge"] for command in calls)
    events = store.audit_events()
    assert any(
        item["event"] == "worktree.template_revision_selected"
        for item in events
    )
    assert not any(item["event"] == "worktree.template_synced" for item in events)


def test_worktree_resolves_remote_template_to_fixed_revision(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示开发工作空间",
        "知识库",
        [Project("app", "python", "repo", "main", template_branches=("develop",))],
    )
    calls: list[list[str]] = []

    def run(command, cwd, environment):
        calls.append(command)
        stdout = (
            "deadbeef\n"
            if command[:3] == ["git", "rev-parse", "--verify"]
            else ""
        )
        return subprocess.CompletedProcess(command, 0, stdout, "")

    result = WorktreeService(tmp_path, run=run).resolve_template_revision("app")

    assert result.ok
    assert result.data["revision"] == "deadbeef"
    assert calls == [
        ["git", "fetch", "origin", "develop"],
        ["git", "rev-parse", "--verify", "origin/develop^{commit}"],
    ]


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
