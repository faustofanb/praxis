from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from hashlib import blake2b
from pathlib import Path
from typing import Any
from uuid import uuid4

from praxis.documents.atomic_writer import atomic_write_text
from praxis.naming.requirement import RequirementPathPolicy, requirement_document
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
        binding_id: str = "",
    ) -> Result:
        requirement = self.store.requirement(requirement_id)
        if not requirement:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        if artifact_type not in _ARTIFACT_TYPES:
            return Result(False, "ARTIFACT_TYPE_INVALID")
        source = Path(source_path).resolve()
        source_allowed = source.is_relative_to(self.root.resolve())
        binding: dict[str, Any] | None = None
        if binding_id:
            from praxis.worktree.service import resolve_worktree_binding

            resolved = resolve_worktree_binding(self.store, binding_id)
            if not resolved:
                return Result(
                    False,
                    "ARTIFACT_SOURCE_INVALID",
                    data={"message": "binding 不存在或与 source 不匹配", "binding_id": binding_id},
                )
            _, binding = resolved
            if binding.get("requirement_id") != requirement_id:
                return Result(
                    False,
                    "ARTIFACT_SOURCE_INVALID",
                    data={"message": "binding 不属于当前需求", "binding_id": binding_id},
                )
            if binding.get("status") not in {"active", "bound_active"}:
                return Result(
                    False,
                    "ARTIFACT_SOURCE_INVALID",
                    data={"message": "binding 未处于 active 状态", "binding_id": binding_id},
                )
            repository_path = Path(
                str(binding.get("repository_path") or binding.get("path", ""))
            ).resolve()
            source_allowed = source.is_relative_to(repository_path)
        if not source.is_file() or not source_allowed:
            return Result(False, "ARTIFACT_SOURCE_INVALID")
        facts = dict(metadata or {})
        if binding_id:
            facts["binding_id"] = binding_id
        if artifact_type == "sql":
            missing = sorted(_SQL_METADATA - facts.keys())
            if missing:
                return Result(False, "ARTIFACT_SQL_METADATA_REQUIRED", data={"missing": missing})
        if artifact_type == "code-change":
            included = facts.get("include_untracked", [])
            include_untracked = (
                [str(item) for item in included]
                if isinstance(included, list)
                else []
            )
            code_change = _code_change_facts(
                source,
                include_untracked=include_untracked,
            )
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
        archived = self._archive(
            requirement,
            artifact_id,
            artifact_type,
            source,
            facts,
        )
        data = {
            **(existing or {}),
            "artifact_id": artifact_id,
            "requirement_id": requirement_id,
            "type": artifact_type,
            "category_zh": _ARTIFACT_TYPES[artifact_type],
            "source_path": str(source),
            "archived_path": str(archived),
            "stage": stage,
            "content_hash": _hash(source),
            "archived_hash": _hash(archived),
            "size": source.stat().st_size,
            "metadata": facts,
            **({"binding_id": binding_id} if binding_id else {}),
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
        if not artifact.get("archived_path"):
            source = Path(artifact["source_path"])
            if not source.is_file():
                return Result(
                    False,
                    "ARTIFACT_LEGACY_SOURCE_MISSING",
                    data={"artifact_id": artifact_id, "migration_required": True},
                )
            actual = _hash(source)
            ok = actual == artifact["content_hash"]
            return Result(
                ok,
                (
                    "ARTIFACT_LEGACY_SOURCE_VERIFIED"
                    if ok
                    else "ARTIFACT_LEGACY_HASH_MISMATCH"
                ),
                data={
                    "artifact_id": artifact_id,
                    "expected": artifact["content_hash"],
                    "actual": actual,
                    "source_status": "matched" if ok else "changed",
                    "migration_required": True,
                },
            )
        archived = Path(artifact["archived_path"])
        if not archived.is_file():
            return Result(
                False,
                "ARTIFACT_ARCHIVE_MISSING",
                data={"artifact_id": artifact_id, "archived_path": str(archived)},
            )
        actual = _hash(archived)
        ok = actual == artifact.get("archived_hash", artifact["content_hash"])
        source = Path(artifact["source_path"])
        source_status = "missing"
        if source.is_file():
            source_status = (
                "matched"
                if _hash(source) == artifact["content_hash"]
                else "changed"
            )
        return Result(
            ok,
            "OK" if ok else "ARTIFACT_ARCHIVE_HASH_MISMATCH",
            data={
                "artifact_id": artifact_id,
                "expected": artifact.get("archived_hash", artifact["content_hash"]),
                "actual": actual,
                "archived_path": str(archived),
                "source_status": source_status,
            },
        )

    def repair_archives(self, requirement_id: str = "") -> Result:
        artifacts = [
            artifact
            for artifact in self.store.list_scope("artifact")
            if not requirement_id or artifact.get("requirement_id") == requirement_id
        ]
        migrated: list[str] = []
        blocked: list[dict[str, str]] = []
        affected_requirements: set[str] = set()
        for artifact in artifacts:
            archived_value = artifact.get("archived_path")
            archived = Path(str(archived_value)) if archived_value else None
            if archived and archived.is_file() and artifact.get("archived_hash"):
                continue
            requirement = self.store.requirement(artifact["requirement_id"])
            if not requirement:
                blocked.append(
                    {
                        "artifact_id": artifact["artifact_id"],
                        "reason": "requirement_missing",
                    }
                )
                continue
            source = Path(artifact["source_path"]).resolve()
            code_change = artifact.get("metadata", {}).get("code_change")
            if artifact["type"] != "code-change":
                if (
                    not source.is_file()
                    or not source.is_relative_to(self.root.resolve())
                ):
                    blocked.append(
                        {
                            "artifact_id": artifact["artifact_id"],
                            "reason": "source_missing",
                        }
                    )
                    continue
                if _hash(source) != artifact["content_hash"]:
                    blocked.append(
                        {
                            "artifact_id": artifact["artifact_id"],
                            "reason": "source_changed",
                        }
                    )
                    continue
            elif not isinstance(code_change, dict):
                blocked.append(
                    {
                        "artifact_id": artifact["artifact_id"],
                        "reason": "code_change_metadata_missing",
                    }
                )
                continue
            archived = self._archive(
                requirement,
                artifact["artifact_id"],
                artifact["type"],
                source,
                artifact.get("metadata", {}),
            )
            updated = {
                **artifact,
                "archived_path": str(archived),
                "archived_hash": _hash(archived),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self.store.set("artifact", artifact["artifact_id"], updated)
            migrated.append(artifact["artifact_id"])
            affected_requirements.add(artifact["requirement_id"])
        for affected in sorted(affected_requirements):
            requirement = self.store.requirement(affected)
            if requirement:
                self._write_index(requirement)
        data = {"migrated": migrated, "blocked": blocked}
        data["audit_id"] = self.store.audit(
            "artifact.archives_repaired",
            "OK" if not blocked else "ARTIFACT_ARCHIVE_REPAIR_INCOMPLETE",
            data,
        )
        return Result(
            not blocked,
            "ARTIFACT_ARCHIVES_REPAIRED"
            if not blocked
            else "ARTIFACT_ARCHIVE_REPAIR_INCOMPLETE",
            data=data,
        )

    def refresh_index(self, requirement_id: str) -> Result:
        requirement = self.store.requirement(requirement_id)
        if not requirement:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        self._write_index(requirement)
        return Result(True, data={"requirement_id": requirement_id})

    def _write_index(self, requirement: dict[str, Any]) -> None:
        workspace = WorkspaceService(self.root).load()
        policy = RequirementPathPolicy(
            self.root / workspace["knowledge_root"]
        )
        requirement_root = policy.locate_requirement_path(
            requirement["requirement_id"], requirement["short_name"]
        )
        artifacts = self.list(requirement["requirement_id"]).data["artifacts"]
        lines = [f"需求编号: {requirement['requirement_id']}", "产出物:"]
        for artifact in artifacts:
            lines.extend(
                (
                    f"  - 产出物编号: {artifact['artifact_id']}",
                    f"    类型: {artifact['category_zh']}",
                    f"    任务阶段: {artifact['stage']}",
                    f"    源路径: {artifact['source_path']}",
                    f"    归档路径: {artifact.get('archived_path', '')}",
                    f"    源内容哈希: {artifact['content_hash']}",
                    f"    归档内容哈希: {artifact.get('archived_hash', '')}",
                )
            )
        atomic_write_text(
            requirement_root / requirement_document("artifacts"),
            "\n".join(lines) + "\n",
        )

    def _archive(
        self,
        requirement: dict[str, Any],
        artifact_id: str,
        artifact_type: str,
        source: Path,
        metadata: dict[str, Any],
    ) -> Path:
        workspace = WorkspaceService(self.root).load()
        policy = RequirementPathPolicy(self.root / workspace["knowledge_root"])
        requirement_root = policy.locate_requirement_path(
            requirement["requirement_id"], requirement["short_name"]
        )
        category = requirement_root / "产出物" / _ARTIFACT_TYPES[artifact_type]
        category.mkdir(parents=True, exist_ok=True)
        if artifact_type == "code-change":
            archived = category / f"{artifact_id}.json"
            atomic_write_text(
                archived,
                json.dumps(
                    metadata["code_change"],
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
            return archived
        archived = category / f"{artifact_id}__{source.name}"
        shutil.copy2(source, archived)
        return archived


def _hash(path: Path) -> str:
    return "blake2b:" + blake2b(path.read_bytes(), digest_size=20).hexdigest()


def _code_change_facts(
    source: Path,
    *,
    include_untracked: list[str] | None = None,
) -> dict[str, Any] | None:
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

    tracked_files = [item for item in names_result.stdout.split("\0") if item]
    untracked_files: list[str] = []
    if include_untracked:
        untracked_result = _git(
            repository,
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        )
        if untracked_result.returncode != 0:
            return None
        requested = set(include_untracked)
        untracked_files = [
            item
            for item in untracked_result.stdout.split("\0")
            if item and item in requested
        ]
    files = list(dict.fromkeys([*tracked_files, *untracked_files]))
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
    for relative in untracked_files:
        path = repository / relative
        if path.is_file():
            changed += 1
            insertions += len(
                path.read_text(encoding="utf-8", errors="replace").splitlines()
            )
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
