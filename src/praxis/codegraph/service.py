from __future__ import annotations

import fcntl
import hashlib
import json
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService

Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


def _git(repo: Path, *args: str) -> bytes:
    process = subprocess.run(["git", *args], cwd=repo, check=False, capture_output=True, text=False)
    if process.returncode:
        raise RuntimeError(process.stderr.decode(errors="replace").strip())
    return process.stdout


@dataclass(frozen=True)
class GitSnapshot:
    head: str
    dirty_fingerprint: str

    @classmethod
    def capture(cls, repo: Path) -> GitSnapshot:
        head = _git(repo, "rev-parse", "HEAD").decode().strip()
        digest = hashlib.sha256()
        for label, args in (
            (b"staged\0", ("diff", "--cached", "--binary", "--no-ext-diff")),
            (b"unstaged\0", ("diff", "--binary", "--no-ext-diff")),
        ):
            digest.update(label)
            digest.update(_git(repo, *args))
        untracked = _git(repo, "ls-files", "--others", "--exclude-standard", "-z")
        for raw_path in sorted(path for path in untracked.split(b"\0") if path):
            relative = raw_path.decode(errors="surrogateescape")
            if relative.startswith((".codegraph/", ".praxis/")):
                continue
            path = repo / relative
            digest.update(b"untracked\0" + raw_path + b"\0")
            if path.is_symlink():
                digest.update(path.readlink().as_posix().encode())
            elif path.is_file():
                digest.update(hashlib.sha256(path.read_bytes()).digest())
            else:
                digest.update(b"missing")
        return cls(head, digest.hexdigest())

    @staticmethod
    def changed_files(repo: Path, default_branch: str) -> list[str]:
        groups: list[bytes] = []
        with suppress(RuntimeError):
            groups.append(_git(repo, "diff", "--name-only", "-z", f"{default_branch}...HEAD"))
        groups.extend(
            [
                _git(repo, "diff", "--cached", "--name-only", "-z"),
                _git(repo, "diff", "--name-only", "-z"),
                _git(repo, "ls-files", "--others", "--exclude-standard", "-z"),
            ]
        )
        changed = {
            path.decode(errors="surrogateescape")
            for group in groups
            for path in group.split(b"\0")
            if path
        }
        return sorted(path for path in changed if not path.startswith((".codegraph/", ".praxis/")))


class _SyncBusy(Exception):
    pass


class CodeGraphService:
    _thread_locks: dict[str, threading.Lock] = {}
    _thread_locks_guard = threading.Lock()

    def __init__(
        self,
        root: Path | str,
        project_id: str,
        *,
        run: Runner | None = None,
        store: StateStore | None = None,
        codegraph_version: str | None = None,
        lock_timeout: float = 30,
        repo: Path | str | None = None,
    ):
        self.root = Path(root)
        self.project_id = project_id
        project = WorkspaceService(self.root).project(project_id)
        self.default_branch = project.default_branch
        self.repo = (
            Path(repo).resolve() if repo is not None else (self.root / project.path).resolve()
        )
        self.run = run or self._run
        self.store = store or StateStore(self.root)
        self.codegraph_version = codegraph_version or (
            self._detect_version() if run is None else "unknown"
        )
        self.lock_timeout = lock_timeout
        identity = f"{project_id}\0{self.repo}"
        self.key = hashlib.sha256(identity.encode()).hexdigest()

    @staticmethod
    def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)

    @staticmethod
    def _detect_version() -> str:
        try:
            process = subprocess.run(
                ["codegraph", "--version"], check=False, capture_output=True, text=True
            )
        except FileNotFoundError:
            return "unavailable"
        return process.stdout.strip() if process.returncode == 0 else "unknown"

    def _metadata(self) -> dict[str, Any] | None:
        return self.store.get("codegraph", self.key)

    def _fresh(self, snapshot: GitSnapshot, metadata: dict[str, Any] | None) -> bool:
        return bool(
            metadata
            and (self.repo / ".codegraph").exists()
            and metadata.get("indexed_head") == snapshot.head
            and metadata.get("indexed_dirty_fingerprint") == snapshot.dirty_fingerprint
        )

    def status(self) -> Result:
        snapshot = GitSnapshot.capture(self.repo)
        metadata = self._metadata() or {}
        data = {
            "project_id": self.project_id,
            "worktree": str(self.repo),
            "current_head": snapshot.head,
            "current_dirty_fingerprint": snapshot.dirty_fingerprint,
            "fresh": self._fresh(snapshot, metadata),
            **metadata,
        }
        return Result(True, data=data)

    @contextmanager
    def _lock(self) -> Iterator[None]:
        lock_path = self.root / ".praxis" / "locks" / f"codegraph-{self.key}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._thread_locks_guard:
            thread_lock = self._thread_locks.setdefault(self.key, threading.Lock())
        if not thread_lock.acquire(timeout=self.lock_timeout):
            raise _SyncBusy
        handle = lock_path.open("a+")
        deadline = time.monotonic() + self.lock_timeout
        try:
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise _SyncBusy from None
                    time.sleep(0.02)
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()
            thread_lock.release()

    def ensure_fresh(self, *, initialize: bool = False) -> Result:
        snapshot = GitSnapshot.capture(self.repo)
        if self._fresh(snapshot, self._metadata()):
            return Result(True, code="CODEGRAPH_FRESH", data=self.status().data)
        try:
            with self._lock():
                snapshot = GitSnapshot.capture(self.repo)
                if self._fresh(snapshot, self._metadata()):
                    return Result(True, code="CODEGRAPH_FRESH", data=self.status().data)
                initialized = (self.repo / ".codegraph").exists()
                if not initialized and not initialize:
                    return Result(False, "CODEGRAPH_NOT_INITIALIZED")
                action = "sync" if initialized else "init"
                return self._execute_sync(action)
        except _SyncBusy:
            return Result(False, "CODEGRAPH_SYNC_BUSY")

    def build(self) -> Result:
        try:
            with self._lock():
                return self._execute_sync("init")
        except _SyncBusy:
            return Result(False, "CODEGRAPH_SYNC_BUSY")

    def sync(self) -> Result:
        try:
            with self._lock():
                if not (self.repo / ".codegraph").exists():
                    return Result(False, "CODEGRAPH_NOT_INITIALIZED")
                return self._execute_sync("sync")
        except _SyncBusy:
            return Result(False, "CODEGRAPH_SYNC_BUSY")

    def _execute_sync(self, action: str) -> Result:
        command = ["codegraph", action, str(self.repo)]
        try:
            process = self.run(command, self.repo)
        except FileNotFoundError:
            return Result(False, "CODEGRAPH_NOT_AVAILABLE")
        if process.returncode:
            return Result(
                False,
                "CODEGRAPH_SYNC_FAILED",
                data={"action": action, "stderr": process.stderr.strip()},
            )
        snapshot = GitSnapshot.capture(self.repo)
        metadata = {
            "project_id": self.project_id,
            "indexed_head": snapshot.head,
            "indexed_dirty_fingerprint": snapshot.dirty_fingerprint,
            "indexed_at": datetime.now(UTC).isoformat(),
            "codegraph_version": self.codegraph_version,
        }
        self.store.set("codegraph", self.key, metadata)
        self.store.audit(f"codegraph.{action}", "OK", metadata)
        return Result(True, code=f"CODEGRAPH_{action.upper()}ED", data=metadata)

    def _query(self, arguments: list[str]) -> Result:
        freshness = self.ensure_fresh()
        if not freshness.ok:
            return freshness
        command = ["codegraph", *arguments, "-p", str(self.repo), "--json"]
        try:
            process = self.run(command, self.repo)
        except FileNotFoundError:
            return Result(False, "CODEGRAPH_NOT_AVAILABLE")
        if process.returncode:
            return Result(False, "CODEGRAPH_QUERY_FAILED", data={"stderr": process.stderr.strip()})
        try:
            data = json.loads(process.stdout)
        except json.JSONDecodeError:
            data = {"output": process.stdout}
        return Result(True, data=data)

    def query(self, expression: str) -> Result:
        return self._query(["query", expression])

    def explore(self, target: str) -> Result:
        return self._query(["explore", target])

    def node(self, node_id: str) -> Result:
        return self._query(["node", node_id])

    def affected(self) -> Result:
        freshness = self.ensure_fresh()
        if not freshness.ok:
            return freshness
        files = GitSnapshot.changed_files(self.repo, self.default_branch)
        if not files:
            return Result(True, data={"files": [], "tests": []})
        return self._query(["affected", *files])

    def remove_metadata(self) -> Result:
        self.store.delete("codegraph", self.key)
        return Result(True, code="CODEGRAPH_METADATA_REMOVED")
