from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

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
        heartbeat_interval: float = 5,
        operation_stale_after: float = 30,
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
        self._uses_default_runner = run is None
        self.store = store or StateStore(self.root)
        self.codegraph_version = codegraph_version or (
            self._detect_version() if run is None else "unknown"
        )
        self.lock_timeout = lock_timeout
        self.heartbeat_interval = heartbeat_interval
        self.operation_stale_after = operation_stale_after
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

    def _operation(self) -> dict[str, Any] | None:
        return self.store.get("codegraph_operation", self.key)

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
        operation = self._operation()
        if operation:
            data["operation"] = operation
        background = self.store.get("codegraph_background", self.key)
        if background:
            data["background"] = background
        return Result(True, data=data)

    def enqueue(self, *, binding_id: str = "") -> Result:
        """Queue graph initialization without making it a worktree activation gate."""
        current = self.store.get("codegraph_background", self.key)
        if current and current.get("status") in {"queued", "running"}:
            if self._background_active(current):
                return Result(True, "CODEGRAPH_ALREADY_QUEUED", data=current)
            budget = self._consume_background_budget(binding_id, "recovery")
            if budget is not None and not budget.ok:
                return budget
            current.update(
                status="stale",
                code="CODEGRAPH_BACKGROUND_STALE",
                completed_at=datetime.now(UTC).isoformat(),
            )
            self.store.set("codegraph_background", self.key, current)
            self.store.audit("codegraph.background_stale", current["code"], current)
        elif current and current.get("status") == "failed":
            budget = self._consume_background_budget(binding_id, "retry")
            if budget is not None and not budget.ok:
                return budget
        timestamp = datetime.now(UTC)
        log_path = (
            self.root
            / ".praxis"
            / "raw-logs"
            / f"codegraph-background-{timestamp:%Y%m%dT%H%M%S}-{uuid4().hex[:8]}.log"
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        job: dict[str, Any] = {
            "job_id": f"CGJ-{timestamp:%Y%m%dT%H%M%S}-{uuid4().hex[:8].upper()}",
            "project_id": self.project_id,
            "worktree": str(self.repo),
            "binding_id": binding_id,
            "status": "queued",
            "queued_at": timestamp.isoformat(),
            "log_path": str(log_path),
        }
        self.store.set("codegraph_background", self.key, job)
        command = [
            sys.executable,
            "-m",
            "praxis.codegraph.worker",
            "--root",
            str(self.root.resolve()),
            "--project",
            self.project_id,
            "--worktree",
            str(self.repo),
        ]
        if binding_id:
            command.extend(("--binding", binding_id))
        environment = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[2])
        environment["PYTHONPATH"] = os.pathsep.join(
            value for value in (source_root, environment.get("PYTHONPATH", "")) if value
        )
        try:
            with log_path.open("ab") as stream:
                process = subprocess.Popen(
                    command,
                    cwd=self.repo,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        except OSError as error:
            job.update(
                status="failed",
                code="CODEGRAPH_BACKGROUND_START_FAILED",
                completed_at=datetime.now(UTC).isoformat(),
                error_type=type(error).__name__,
            )
            self.store.set("codegraph_background", self.key, job)
            audit_id = self.store.audit(
                "codegraph.background_start_failed", job["code"], job
            )
            return Result(False, job["code"], data={**job, "audit_id": audit_id})
        current: dict[str, Any] = (
            self.store.get("codegraph_background", self.key) or job
        )
        if current.get("job_id") == job["job_id"] and current.get("status") == "queued":
            current.update(
                status="running",
                pid=process.pid,
                started_at=datetime.now(UTC).isoformat(),
            )
            self.store.set("codegraph_background", self.key, current)
        audit_id = self.store.audit("codegraph.background_queued", "OK", current)
        return Result(True, "CODEGRAPH_QUEUED", data={**current, "audit_id": audit_id})

    def run_pending(self, *, binding_id: str = "") -> Result:
        job = self.store.get("codegraph_background", self.key) or {
            "job_id": f"CGJ-{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid4().hex[:8].upper()}",
            "project_id": self.project_id,
            "worktree": str(self.repo),
            "binding_id": binding_id,
            "queued_at": datetime.now(UTC).isoformat(),
        }
        job.update(
            status="running",
            pid=os.getpid(),
            started_at=job.get("started_at") or datetime.now(UTC).isoformat(),
        )
        self.store.set("codegraph_background", self.key, job)
        started = time.monotonic_ns()
        result = self.ensure_fresh(initialize=True)
        completed_at = datetime.now(UTC).isoformat()
        job.update(
            status="completed" if result.ok else "failed",
            code=result.code,
            completed_at=completed_at,
            duration_ms=round((time.monotonic_ns() - started) / 1_000_000, 3),
        )
        self.store.set("codegraph_background", self.key, job)
        target_binding = binding_id or str(job.get("binding_id", ""))
        if target_binding:
            binding = self.store.get("worktree", target_binding)
            if binding:
                binding.update(
                    codegraph_status=result.code,
                    codegraph_completed_at=completed_at,
                    codegraph_job_id=job["job_id"],
                )
                self.store.set("worktree", target_binding, binding)
        self.store.audit(
            "codegraph.background_completed" if result.ok else "codegraph.background_failed",
            result.code,
            job,
        )
        return Result(result.ok, result.code, data={**job, "codegraph": result.data})

    def wait(self, *, timeout: float = 0) -> Result:
        deadline = time.monotonic() + max(timeout, 0)
        while True:
            job = self.store.get("codegraph_background", self.key)
            if not job:
                return Result(False, "CODEGRAPH_BACKGROUND_NOT_QUEUED")
            if job.get("status") not in {"queued", "running"}:
                if job.get("status") == "completed":
                    freshness = self.ensure_fresh()
                    current = self.status().data if freshness.ok else freshness.data
                    return Result(
                        freshness.ok,
                        freshness.code,
                        data={
                            "background": job,
                            "codegraph": current,
                        },
                        diagnostics=freshness.diagnostics,
                    )
                return Result(
                    False,
                    str(job.get("code", "CODEGRAPH_BACKGROUND_FAILED")),
                    data=job,
                )
            if not self._background_active(job):
                job.update(
                    status="stale",
                    code="CODEGRAPH_BACKGROUND_STALE",
                    completed_at=datetime.now(UTC).isoformat(),
                )
                self.store.set("codegraph_background", self.key, job)
                self.store.audit("codegraph.background_stale", job["code"], job)
                return Result(False, job["code"], data={**job, "fallback": "rg"})
            if time.monotonic() >= deadline:
                return Result(
                    False,
                    "CODEGRAPH_BACKGROUND_PENDING",
                    data={**job, "fallback": "rg"},
                )
            time.sleep(min(0.1, max(deadline - time.monotonic(), 0)))

    def cancel(self) -> Result:
        """Stop this worktree's background graph process before removing the worktree."""
        job = self.store.get("codegraph_background", self.key)
        if not job or job.get("status") not in {"queued", "running"}:
            return Result(True, "CODEGRAPH_BACKGROUND_NOT_ACTIVE", data=job or {})
        pid = int(job.get("pid") or 0)
        if pid and pid != os.getpid() and self._background_active(job):
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except OSError as error:
                return Result(
                    False,
                    "CODEGRAPH_BACKGROUND_CANCEL_FAILED",
                    data={**job, "error_type": type(error).__name__},
                )
        completed_at = datetime.now(UTC).isoformat()
        job.update(
            status="cancelled",
            code="CODEGRAPH_BACKGROUND_CANCELLED",
            completed_at=completed_at,
        )
        self.store.set("codegraph_background", self.key, job)
        operation = self._operation()
        if operation and operation.get("status") == "running":
            operation.update(status="cancelled", completed_at=completed_at)
            self.store.set("codegraph_operation", self.key, operation)
        audit_id = self.store.audit("codegraph.background_cancelled", job["code"], job)
        return Result(True, job["code"], data={**job, "audit_id": audit_id})

    @staticmethod
    def _background_active(job: dict[str, Any]) -> bool:
        if job.get("status") == "queued":
            try:
                queued_at = datetime.fromisoformat(str(job["queued_at"]))
            except (KeyError, TypeError, ValueError):
                return False
            return datetime.now(UTC) - queued_at <= timedelta(seconds=30)
        try:
            pid = int(job["pid"])
            os.kill(pid, 0)
        except (KeyError, TypeError, ValueError, ProcessLookupError, PermissionError):
            return False
        return True

    def _consume_background_budget(self, binding_id: str, kind: str) -> Result | None:
        if not binding_id:
            return None
        binding = self.store.get("worktree", binding_id)
        if not binding:
            return None
        from praxis.governance.service import ExecutionBudgetService

        return ExecutionBudgetService(self.root).consume(
            str(binding["requirement_id"]),
            "in_progress",
            kind,
            f"codegraph:{self.project_id}",
        )

    def _start_operation(self, action: str) -> dict[str, Any]:
        started_at = datetime.now(UTC).isoformat()
        operation = {
            "operation_id": f"CGO-{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid4().hex[:8].upper()}",
            "project_id": self.project_id,
            "worktree": str(self.repo),
            "action": action,
            "status": "running",
            "started_at": started_at,
            "heartbeat_at": started_at,
            "heartbeat_count": 0,
        }
        self.store.set("codegraph_operation", self.key, operation)
        self.store.audit("codegraph.operation_started", "OK", operation)
        return operation

    def _heartbeat_operation(self, operation: dict[str, Any]) -> None:
        operation["heartbeat_at"] = datetime.now(UTC).isoformat()
        operation["heartbeat_count"] = int(operation.get("heartbeat_count", 0)) + 1
        self.store.set("codegraph_operation", self.key, operation)

    def _finish_operation(
        self,
        operation: dict[str, Any],
        status: str,
        code: str,
        **details: Any,
    ) -> None:
        completed_at = datetime.now(UTC).isoformat()
        operation.update(
            status=status,
            code=code,
            heartbeat_at=completed_at,
            completed_at=completed_at,
            **details,
        )
        self.store.set("codegraph_operation", self.key, operation)
        self.store.audit(f"codegraph.operation_{status}", code, operation)

    def _operation_is_recent(self, operation: dict[str, Any]) -> bool:
        try:
            heartbeat = datetime.fromisoformat(str(operation["heartbeat_at"]))
        except (KeyError, TypeError, ValueError):
            return False
        return datetime.now(UTC) - heartbeat <= timedelta(seconds=self.operation_stale_after)

    def _run_with_heartbeat(
        self,
        command: list[str],
        cwd: Path,
        operation: dict[str, Any],
    ) -> subprocess.CompletedProcess[str]:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        operation["pid"] = process.pid
        self._heartbeat_operation(operation)
        while True:
            try:
                stdout, stderr = process.communicate(timeout=self.heartbeat_interval)
                return subprocess.CompletedProcess(
                    command,
                    process.returncode,
                    stdout or "",
                    stderr or "",
                )
            except subprocess.TimeoutExpired:
                self._heartbeat_operation(operation)

    def _recover_existing_index(self, snapshot: GitSnapshot) -> Result | None:
        command = ["codegraph", "status", str(self.repo), "--json"]
        try:
            process = self.run(command, self.repo)
        except FileNotFoundError:
            return None
        if process.returncode:
            return None
        try:
            payload = json.loads(process.stdout)
            project_path = Path(str(payload["projectPath"])).resolve()
            pending = payload["pendingChanges"]
            index = payload["index"]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None
        if not isinstance(pending, dict) or not isinstance(index, dict):
            return None
        if not (
            payload.get("initialized") is True
            and project_path == self.repo
            and index.get("state") == "complete"
            and int(index.get("pendingRefs", -1)) == 0
            and payload.get("worktreeMismatch") is None
            and all(
                int(pending.get(name, -1)) == 0
                for name in ("added", "modified", "removed")
            )
        ):
            return None
        operation = self._operation()
        metadata = {
            "project_id": self.project_id,
            "indexed_head": snapshot.head,
            "indexed_dirty_fingerprint": snapshot.dirty_fingerprint,
            "indexed_at": str(payload.get("lastIndexed") or datetime.now(UTC).isoformat()),
            "codegraph_version": str(payload.get("version") or self.codegraph_version),
            "recovered_from_existing_index": True,
        }
        if operation:
            metadata["recovered_operation_id"] = operation.get("operation_id")
        self.store.set("codegraph", self.key, metadata)
        if operation and operation.get("status") in {"running", "interrupted"}:
            self._finish_operation(operation, "recovered", "CODEGRAPH_RECOVERED")
        self.store.audit("codegraph.recovered", "CODEGRAPH_RECOVERED", metadata)
        return Result(True, "CODEGRAPH_RECOVERED", data=metadata)

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
        background = self.store.get("codegraph_background", self.key)
        if (
            background
            and background.get("status") in {"queued", "running"}
            and background.get("pid") != os.getpid()
        ):
            return Result(
                False,
                "CODEGRAPH_BACKGROUND_PENDING",
                data={**background, "fallback": "rg", "hint": "run codegraph wait explicitly"},
            )
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
                operation = self._operation()
                recovering = bool(
                    initialized
                    and (
                        (initialize and self._metadata() is None)
                        or (operation and operation.get("status") in {"running", "interrupted"})
                    )
                )
                if (
                    operation
                    and operation.get("status") == "running"
                    and self._operation_is_recent(operation)
                ):
                    return Result(
                        False,
                        "CODEGRAPH_SYNC_BUSY",
                        data={"operation": operation, "worktree": str(self.repo)},
                    )
                if recovering and (self.repo / ".codegraph" / "lock").exists():
                    return Result(
                        False,
                        "CODEGRAPH_SYNC_BUSY",
                        data={"operation": operation or {}, "worktree": str(self.repo)},
                    )
                if recovering:
                    recovered = self._recover_existing_index(snapshot)
                    if recovered:
                        return recovered
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
        operation = self._start_operation(action)
        try:
            process = (
                self._run_with_heartbeat(command, self.repo, operation)
                if self._uses_default_runner
                else self.run(command, self.repo)
            )
            if process.returncode:
                self._finish_operation(
                    operation,
                    "failed",
                    "CODEGRAPH_SYNC_FAILED",
                    returncode=process.returncode,
                    stderr=process.stderr.strip(),
                )
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
                "operation_id": operation["operation_id"],
            }
            self.store.set("codegraph", self.key, metadata)
            self._finish_operation(operation, "completed", f"CODEGRAPH_{action.upper()}ED")
            self.store.audit(f"codegraph.{action}", "OK", metadata)
            return Result(True, code=f"CODEGRAPH_{action.upper()}ED", data=metadata)
        except FileNotFoundError:
            self._finish_operation(operation, "failed", "CODEGRAPH_NOT_AVAILABLE")
            return Result(False, "CODEGRAPH_NOT_AVAILABLE")
        except BaseException as error:
            self._finish_operation(
                operation,
                "interrupted",
                "CODEGRAPH_INTERRUPTED",
                error_type=type(error).__name__,
            )
            raise

    def _query(self, arguments: list[str]) -> Result:
        background = self.store.get("codegraph_background", self.key)
        if background and background.get("status") in {"queued", "running"}:
            return Result(
                False,
                "CODEGRAPH_BACKGROUND_PENDING",
                data={**background, "fallback": "rg", "hint": "run codegraph wait explicitly"},
            )
        if background and background.get("status") == "failed":
            return Result(
                False,
                str(background.get("code", "CODEGRAPH_BACKGROUND_FAILED")),
                data={**background, "fallback": "rg"},
            )
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
        background = self.store.get("codegraph_background", self.key)
        if background and background.get("status") in {"queued", "running"}:
            return Result(
                False,
                "CODEGRAPH_BACKGROUND_PENDING",
                data={**background, "fallback": "rg", "hint": "run codegraph wait explicitly"},
            )
        if background and background.get("status") == "failed":
            return Result(
                False,
                str(background.get("code", "CODEGRAPH_BACKGROUND_FAILED")),
                data={**background, "fallback": "rg"},
            )
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
