from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from praxis.codegraph.service import CodeGraphService, GitSnapshot
from praxis.workspace.service import Project, WorkspaceService


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _workspace(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "tracked.txt").write_text("base")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "init")
    WorkspaceService(tmp_path).init(
        "test", "test-family", "knowledge", [Project("app", "python", "repo", "main")]
    )
    return repo


def test_dirty_fingerprint_covers_staged_unstaged_and_untracked(tmp_path: Path) -> None:
    repo = _workspace(tmp_path)
    clean = GitSnapshot.capture(repo)
    (repo / "tracked.txt").write_text("unstaged")
    unstaged = GitSnapshot.capture(repo)
    _git(repo, "add", "tracked.txt")
    staged = GitSnapshot.capture(repo)
    (repo / "new.txt").write_text("untracked")
    untracked = GitSnapshot.capture(repo)

    assert (
        len(
            {
                clean.dirty_fingerprint,
                unstaged.dirty_fingerprint,
                staged.dirty_fingerprint,
                untracked.dirty_fingerprint,
            }
        )
        == 4
    )
    assert clean.head == unstaged.head == staged.head == untracked.head


def test_ensure_fresh_initializes_then_skips_unchanged_index(tmp_path: Path) -> None:
    repo = _workspace(tmp_path)
    calls: list[list[str]] = []

    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[1] == "init":
            (cwd / ".codegraph").mkdir()
        return subprocess.CompletedProcess(command, 0, "{}", "")

    service = CodeGraphService(tmp_path, "app", run=run, codegraph_version="1.3.0")
    first = service.ensure_fresh(initialize=True)
    second = service.ensure_fresh(initialize=True)

    assert first.ok and second.ok
    assert calls == [["codegraph", "init", str(repo)]]
    status = service.status().data
    assert status["fresh"] is True
    assert status["indexed_head"] == status["current_head"]
    assert status["codegraph_version"] == "1.3.0"


def test_query_never_uses_stale_index_after_sync_failure(tmp_path: Path) -> None:
    repo = _workspace(tmp_path)
    (repo / ".codegraph").mkdir()
    calls: list[list[str]] = []

    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 9, "", "sync failed")

    service = CodeGraphService(tmp_path, "app", run=run)
    result = service.query("OrderService")

    assert not result.ok
    assert result.code == "CODEGRAPH_SYNC_FAILED"
    assert calls == [["codegraph", "sync", str(repo)]]


def test_changed_worktree_syncs_before_affected_query(tmp_path: Path) -> None:
    repo = _workspace(tmp_path)
    (repo / ".codegraph").mkdir()
    calls: list[list[str]] = []

    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        output = '{"nodes": []}' if "affected" in command else "{}"
        return subprocess.CompletedProcess(command, 0, output, "")

    service = CodeGraphService(tmp_path, "app", run=run)
    assert service.ensure_fresh().ok
    (repo / "untracked.py").write_text("value = 1")
    affected = service.affected()

    assert affected.ok
    assert calls == [
        ["codegraph", "sync", str(repo)],
        ["codegraph", "sync", str(repo)],
        ["codegraph", "affected", "untracked.py", "-p", str(repo), "--json"],
    ]


def test_concurrent_ensure_fresh_runs_one_sync(tmp_path: Path) -> None:
    repo = _workspace(tmp_path)
    (repo / ".codegraph").mkdir()
    calls = 0
    calls_lock = threading.Lock()

    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return subprocess.CompletedProcess(command, 0, "{}", "")

    service = CodeGraphService(tmp_path, "app", run=run, lock_timeout=1)
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(service.ensure_fresh())) for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert all(result.ok for result in results)
    assert calls == 1


def test_each_git_state_transition_triggers_sync(tmp_path: Path) -> None:
    repo = _workspace(tmp_path)
    (repo / ".codegraph").mkdir()
    calls = 0

    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(command, 0, "{}", "")

    service = CodeGraphService(tmp_path, "app", run=run)
    assert service.ensure_fresh().ok
    (repo / "tracked.txt").write_text("unstaged")
    assert service.ensure_fresh().ok
    _git(repo, "add", "tracked.txt")
    assert service.ensure_fresh().ok
    (repo / "new.txt").write_text("untracked")
    assert service.ensure_fresh().ok
    _git(repo, "add", "new.txt")
    _git(repo, "commit", "-m", "change")
    assert service.ensure_fresh().ok
    assert calls == 5


def test_lock_timeout_returns_busy(tmp_path: Path) -> None:
    repo = _workspace(tmp_path)
    (repo / ".codegraph").mkdir()
    service = CodeGraphService(tmp_path, "app", lock_timeout=0.01)
    with service._thread_locks_guard:
        lock = service._thread_locks.setdefault(service.key, threading.Lock())
    lock.acquire()
    try:
        assert service.ensure_fresh().code == "CODEGRAPH_SYNC_BUSY"
    finally:
        lock.release()


def test_build_sync_remove_and_query_error_contracts(tmp_path: Path) -> None:
    repo = _workspace(tmp_path)
    commands = []

    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[1] == "init":
            (repo / ".codegraph").mkdir(exist_ok=True)
        if command[1] == "query":
            return subprocess.CompletedProcess(command, 0, "not-json", "")
        if command[1] == "node":
            return subprocess.CompletedProcess(command, 2, "", "bad query")
        return subprocess.CompletedProcess(command, 0, "{}", "")

    service = CodeGraphService(tmp_path, "app", run=run)
    assert service.sync().code == "CODEGRAPH_NOT_INITIALIZED"
    assert service.build().ok
    assert service.sync().ok
    assert service.query("A").data == {"output": "not-json"}
    assert service.explore("A").ok
    assert service.node("A").code == "CODEGRAPH_QUERY_FAILED"
    assert service.remove_metadata().ok
    assert service.status().data["fresh"] is False


def test_missing_codegraph_binary_never_marks_index_fresh(tmp_path: Path) -> None:
    repo = _workspace(tmp_path)
    (repo / ".codegraph").mkdir()

    def missing(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    service = CodeGraphService(tmp_path, "app", run=missing)
    assert service.sync().code == "CODEGRAPH_NOT_AVAILABLE"
    assert service.query("A").code == "CODEGRAPH_NOT_AVAILABLE"
    assert service.status().data["fresh"] is False


def test_build_and_sync_return_busy_when_lock_is_held(tmp_path: Path) -> None:
    repo = _workspace(tmp_path)
    (repo / ".codegraph").mkdir()
    service = CodeGraphService(tmp_path, "app", lock_timeout=0.01)
    with service._thread_locks_guard:
        lock = service._thread_locks.setdefault(service.key, threading.Lock())
    lock.acquire()
    try:
        assert service.build().code == "CODEGRAPH_SYNC_BUSY"
        assert service.sync().code == "CODEGRAPH_SYNC_BUSY"
    finally:
        lock.release()
