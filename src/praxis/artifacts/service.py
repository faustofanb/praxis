from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from hashlib import blake2b
from pathlib import Path
from typing import Any
from uuid import uuid4

from praxis.documents.atomic_writer import atomic_write_text
from praxis.naming.requirement import RequirementPathPolicy
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService

_ARTIFACT_TYPES = {
    "sql": "SQL",
    "database-migration": "数据库迁移",
    "script": "脚本",
    "patch": "补丁",
    "code-change": "代码变更",
    "test-report": "测试报告",
    "other": "其他",
}
_SQL_METADATA = {
    "connection_ref",
    "purpose",
    "stage",
    "parameters",
    "precheck",
    "postimpact",
    "approval",
}


class ArtifactService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.store = StateStore(self.root)

    def add(
        self,
        requirement_id: str,
        artifact_type: str,
        source_path: Path | str,
        *,
        stage: str,
        metadata: dict[str, Any] | None = None,
    ) -> Result:
        requirement = self.store.requirement(requirement_id)
        if not requirement:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        if artifact_type not in _ARTIFACT_TYPES:
            return Result(False, "ARTIFACT_TYPE_INVALID")
        source = Path(source_path).resolve()
        if not source.is_file() or not source.is_relative_to(self.root.resolve()):
            return Result(False, "ARTIFACT_SOURCE_INVALID")
        facts = dict(metadata or {})
        if artifact_type == "sql":
            missing = sorted(_SQL_METADATA - facts.keys())
            if missing:
                return Result(False, "ARTIFACT_SQL_METADATA_REQUIRED", data={"missing": missing})
        if artifact_type == "code-change":
            code_change = _code_change_facts(source)
            if code_change is None:
                return Result(False, "ARTIFACT_CODE_CHANGE_GIT_REQUIRED")
            facts["code_change"] = code_change
        timestamp = datetime.now(UTC)
        existing = next(
            (
                item
                for item in self.store.list_scope("artifact")
                if item.get("requirement_id") == requirement_id
                and Path(str(item.get("source_path", ""))).resolve() == source
            ),
            None,
        )
        artifact_id = (
            str(existing["artifact_id"])
            if existing
            else f"ART-{timestamp:%Y%m%dT%H%M%S}-{uuid4().hex[:8].upper()}"
        )
        data = {
            **(existing or {}),
            "artifact_id": artifact_id,
            "requirement_id": requirement_id,
            "type": artifact_type,
            "category_zh": _ARTIFACT_TYPES[artifact_type],
            "source_path": str(source),
            "stage": stage,
            "content_hash": _hash(source),
            "size": source.stat().st_size,
            "metadata": facts,
            "created_at": (
                existing.get("created_at", timestamp.isoformat())
                if existing
                else timestamp.isoformat()
            ),
            "updated_at": timestamp.isoformat(),
        }
        self.store.set("artifact", artifact_id, data)
        self._write_index(requirement)
        event = "artifact.refreshed" if existing else "artifact.registered"
        code = "ARTIFACT_REFRESHED" if existing else "ARTIFACT_REGISTERED"
        audit_id = self.store.audit(event, "OK", data)
        return Result(True, code, data={**data, "audit_id": audit_id})

    def list(self, requirement_id: str | None = None) -> Result:
        artifacts = self.store.list_scope("artifact")
        if requirement_id:
            artifacts = [
                artifact
                for artifact in artifacts
                if artifact["requirement_id"] == requirement_id
            ]
        return Result(True, data={"artifacts": artifacts})

    def verify(self, artifact_id: str) -> Result:
        artifact = self.store.get("artifact", artifact_id)
        if not artifact:
            return Result(False, "ARTIFACT_NOT_FOUND")
        source = Path(artifact["source_path"])
        if not source.is_file():
            return Result(False, "ARTIFACT_SOURCE_MISSING", data={"artifact_id": artifact_id})
        actual = _hash(source)
        ok = actual == artifact["content_hash"]
        return Result(
            ok,
            "OK" if ok else "ARTIFACT_HASH_MISMATCH",
            data={
                "artifact_id": artifact_id,
                "expected": artifact["content_hash"],
                "actual": actual,
            },
        )

    def refresh_index(self, requirement_id: str) -> Result:
        requirement = self.store.requirement(requirement_id)
        if not requirement:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        self._write_index(requirement)
        return Result(True, data={"requirement_id": requirement_id})

    def _write_index(self, requirement: dict[str, Any]) -> None:
        workspace = WorkspaceService(self.root).load()
        requirement_root = RequirementPathPolicy(
            self.root / workspace["knowledge_root"]
        ).requirement_path(requirement["requirement_id"], requirement["short_name"])
        artifacts = self.list(requirement["requirement_id"]).data["artifacts"]
        lines = [f"需求编号: {requirement['requirement_id']}", "产出物:"]
        for artifact in artifacts:
            lines.extend(
                (
                    f"  - 产出物编号: {artifact['artifact_id']}",
                    f"    类型: {artifact['category_zh']}",
                    f"    任务阶段: {artifact['stage']}",
                    f"    路径: {artifact['source_path']}",
                    f"    内容哈希: {artifact['content_hash']}",
                )
            )
        atomic_write_text(requirement_root / "产出物清单.yaml", "\n".join(lines) + "\n")


def _hash(path: Path) -> str:
    return "blake2b:" + blake2b(path.read_bytes(), digest_size=20).hexdigest()


def _code_change_facts(source: Path) -> dict[str, Any] | None:
    root_result = _git(source.parent, "rev-parse", "--show-toplevel")
    if root_result.returncode != 0:
        return None
    repository = Path(root_result.stdout.strip()).resolve()
    branch_result = _git(repository, "branch", "--show-current")
    stats_result = _git(repository, "diff", "--numstat", "HEAD")
    names_result = _git(repository, "diff", "--name-only", "-z", "HEAD")
    if any(
        result.returncode != 0
        for result in (branch_result, stats_result, names_result)
    ):
        return None

    files = [item for item in names_result.stdout.split("\0") if item]
    source_relative = source.relative_to(repository).as_posix()
    if source_relative not in files:
        files.append(source_relative)
    file_hashes = []
    for relative in sorted(set(files)):
        path = repository / relative
        if path.is_file():
            file_hashes.append({"path": relative, "content_hash": _hash(path)})

    insertions = 0
    deletions = 0
    changed = 0
    for line in stats_result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        changed += 1
        if parts[0].isdigit():
            insertions += int(parts[0])
        if parts[1].isdigit():
            deletions += int(parts[1])
    if changed == 0 and source_relative in files:
        changed = 1
        insertions = len(source.read_text(encoding="utf-8", errors="replace").splitlines())
    return {
        "repository": str(repository),
        "branch": branch_result.stdout.strip(),
        "diff": {
            "files": changed,
            "insertions": insertions,
            "deletions": deletions,
        },
        "files": file_hashes,
    }


def _git(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", *arguments],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
