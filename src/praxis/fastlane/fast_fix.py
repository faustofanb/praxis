from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from praxis.artifacts.service import ArtifactService
from praxis.domain.requirement import RequirementStatus
from praxis.fastlane.service import FastLaneService
from praxis.knowledge.requirements import RequirementService
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.worktree.service import resolve_worktree_binding

_STATE_SCOPE = "fast_fix"
_EVIDENCE_SCOPE = "fast_fix_evidence"
_PROFILE = "fast-fix-v3"
_RISK_PATH = re.compile(
    r"(^|/)(?:permissions?|generated|openapi|swagger)(/|$)",
    re.IGNORECASE,
)
_RISK_ADDITION = re.compile(
    r"\b(?:transaction|transactional|for\s+update|lock|mutex|semaphore|"
    r"synchronized|concurrent|create\s+table|alter\s+table|drop\s+table|"
    r"truncate\s+table|grant|revoke|update|delete)\b",
    re.IGNORECASE,
)
_PUBLIC_INTERFACE_ADDITION = re.compile(
    r"^\s*public\s+(?:class|interface|record|enum)\s+|"
    r"^\s*export\s+(?:default\s+)?(?:class|function|interface|type)\b"
)
_CHANGE_KIND = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_MAX_FILES = 3
_MAX_CHANGED_LINES = 80
_OMITTED = [
    "tests",
    "compile",
    "full_typecheck",
    "quality_review",
    "integration_verification",
]


class FastFixService(FastLaneService):
    """Record a risk-bounded small fix without expanding verification."""

    def __init__(self, root: Path | str):
        super().__init__(root)
        self.store = StateStore(self.root)

    def record(
        self,
        requirement_id: str,
        *,
        file: str | Sequence[str],
        verification: str,
        reason: str,
        change_kind: str = "",
        risk: str = "",
        evidence: str = "",
        command_count: int = 0,
        elapsed_seconds: float = 0.0,
        new_risk_justification: str = "",
    ) -> Result:
        requirement = self.store.requirement(requirement_id)
        if not requirement:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        normalized_reason = reason.strip()
        if not normalized_reason:
            return Result(False, "FAST_FIX_REASON_REQUIRED")
        normalized_verification = verification.strip().casefold()
        if normalized_verification not in {"declined", "direct"}:
            return Result(False, "FAST_FIX_VERIFICATION_INVALID")
        if command_count < 0 or elapsed_seconds < 0:
            return Result(False, "FAST_FIX_BUDGET_INVALID")

        binding_result = self._active_binding(requirement_id)
        if isinstance(binding_result, Result):
            return binding_result
        binding_id, binding = binding_result
        repository = Path(str(binding["repository_path"])).resolve()
        target_result = self._target_paths(repository, file)
        if isinstance(target_result, Result):
            return target_result
        targets = target_result
        relatives = sorted(relative for _, relative in targets)
        target_by_relative = {relative: target for target, relative in targets}

        changed_files = sorted(self._changed_paths(repository))
        if changed_files != relatives:
            return Result(
                False,
                "FAST_FIX_TARGET_FILE_ONLY_REQUIRED",
                data={"target_files": relatives, "changed_files": changed_files},
            )
        risky_paths = [relative for relative in relatives if _RISK_PATH.search(relative)]
        if risky_paths:
            return Result(
                False,
                "FAST_FIX_HIGH_RISK_PATH",
                data={"target_files": risky_paths},
            )

        normalized_kind = self._change_kind(change_kind, normalized_reason)
        if not normalized_kind:
            return Result(
                False,
                "FAST_FIX_CHANGE_KIND_REQUIRED",
                data={"format": "lowercase letters, digits, underscores, or hyphens"},
            )
        diff = self._git_output(
            repository,
            ["diff", "--unified=0", "--no-color", "HEAD", "--", *relatives],
            strip=False,
        )
        if not diff.strip():
            return Result(False, "FAST_FIX_TARGET_DIFF_REQUIRED")
        additions, deletions = self._changed_lines(diff)
        content_risk = self._content_risk(diff)
        if content_risk:
            return Result(
                False,
                content_risk,
                data={"target_files": relatives},
            )

        head = self._git_output(repository, ["rev-parse", "HEAD"])
        if not head:
            return Result(False, "FAST_FIX_HEAD_UNAVAILABLE")
        file_fingerprints = {
            relative: self._file_fingerprint(target_by_relative[relative])
            for relative in relatives
        }
        evidence_key = self._evidence_key(
            binding_id,
            head,
            file_fingerprints,
        )
        existing = self.store.get(_EVIDENCE_SCOPE, evidence_key)
        if existing:
            return Result(
                True,
                str(existing.get("result_code", "FAST_FIX_RECORDED")),
                data={**existing, "reused_evidence": True},
            )

        changed_lines = additions + deletions
        budget = self._budget(changed_lines, command_count, elapsed_seconds)
        if budget["hard_exceeded"]:
            return Result(
                False,
                "FAST_FIX_HARD_BUDGET_EXCEEDED",
                data={"budget": budget},
            )
        if budget["soft_exceeded"] and not new_risk_justification.strip():
            return Result(
                False,
                "FAST_FIX_COMMAND_BUDGET_EXCEEDED",
                data={
                    "budget": budget,
                    "requires": "new_risk_justification",
                },
            )
        if normalized_verification == "direct" and (
            not risk.strip() or not evidence.strip()
        ):
            return Result(
                False,
                "FAST_FIX_DIRECT_EVIDENCE_REQUIRED",
                data={"required": ["risk", "evidence"]},
            )

        prepared = self._prepare_requirement(requirement_id)
        if not prepared.ok:
            return prepared
        representative = target_by_relative[relatives[0]]
        artifact = ArtifactService(self.root).add(
            requirement_id,
            "code-change",
            representative,
            stage="implementation",
            metadata={
                "fast_fix_profile": _PROFILE,
                "business_files": relatives,
                "changed_lines": changed_lines,
                "change_kind": normalized_kind,
                "include_untracked": changed_files,
            },
        )
        if not artifact.ok:
            return artifact

        verification_record = self._record_verification(
            requirement_id,
            evidence_key,
            normalized_verification,
            reason=normalized_reason,
            risk=risk.strip(),
            evidence=evidence.strip(),
        )
        implementation = RequirementService(self.root).record_implementation(
            requirement_id,
            str(binding["repository_id"]),
            artifact_ids=[str(artifact.data["artifact_id"])],
        )
        if not implementation.ok:
            return implementation
        self._advance_to(requirement_id, RequirementStatus.IMPLEMENTED)

        timestamp = datetime.now(UTC).isoformat()
        record = {
            "requirement_id": requirement_id,
            "repository_id": str(binding["repository_id"]),
            "binding_id": binding_id,
            "worktree_path": str(repository),
            "profile": _PROFILE,
            "mode": "fast_fix",
            "tests": (
                "declined_by_user"
                if normalized_verification == "declined"
                else "not_run"
            ),
            "compile": "not_requested",
            "scope": (
                "target_file_only" if len(relatives) == 1 else "bounded_files_only"
            ),
            "status": "implemented",
            "result_code": "FAST_FIX_RECORDED",
            "target_file": relatives[0],
            "target_files": relatives,
            "change_kind": normalized_kind,
            "changed_lines": changed_lines,
            "head": head,
            "file_fingerprint": (
                file_fingerprints[relatives[0]]
                if len(relatives) == 1
                else self._combined_fingerprint(file_fingerprints)
            ),
            "file_fingerprints": file_fingerprints,
            "evidence_key": evidence_key,
            "reused_evidence": False,
            "reason": normalized_reason,
            "verification": verification_record,
            "omitted_verification": list(_OMITTED),
            "budget": budget,
            "new_risk_justification": new_risk_justification.strip(),
            "artifact_id": str(artifact.data["artifact_id"]),
            "skill_audit": "consolidated",
            "audited_skills": [],
            "execution_principles": [
                "file-search",
                "ponytail",
                "karpathy-guidelines",
            ],
            "recorded_at": timestamp,
        }
        self.store.set_many(
            (
                (_STATE_SCOPE, requirement_id, record),
                (_EVIDENCE_SCOPE, evidence_key, record),
            )
        )
        audit_id = self.store.audit("fix.record", "FAST_FIX_RECORDED", record)
        RequirementService(self.root).progress(
            requirement_id,
            (
                "fast_fix 已一次登记有界目标文件、验证省略和 implementation；"
                "未运行测试、编译、全量类型检查或质量复核。"
            ),
        )
        return Result(
            True,
            "FAST_FIX_RECORDED",
            data={**record, "audit_id": audit_id},
        )

    def _active_binding(
        self,
        requirement_id: str,
    ) -> tuple[str, dict[str, Any]] | Result:
        candidates: list[tuple[str, dict[str, Any]]] = []
        for item in self.store.list_scope("worktree"):
            if (
                item.get("requirement_id") != requirement_id
                or item.get("status") != "active"
            ):
                continue
            identifier = str(item.get("binding_id") or item.get("branch", ""))
            resolved = resolve_worktree_binding(self.store, identifier)
            if resolved:
                candidates.append(resolved)
        if len(candidates) != 1:
            return Result(
                False,
                "FAST_FIX_SINGLE_ACTIVE_WORKTREE_REQUIRED",
                data={"active_worktrees": len(candidates)},
            )
        return candidates[0]

    @staticmethod
    def _target_path(
        repository: Path,
        requested: str,
    ) -> tuple[Path, str] | Result:
        value = requested.strip().replace("\\", "/")
        if not value or Path(value).is_absolute() or ".." in Path(value).parts:
            return Result(False, "FAST_FIX_TARGET_FILE_INVALID")
        if "/" in value:
            candidates = [repository / value]
        else:
            candidates = [
                path
                for path in repository.rglob(value)
                if path.is_file() and ".git" not in path.parts
            ]
        existing = [
            path.resolve()
            for path in candidates
            if path.is_file() and path.resolve().is_relative_to(repository)
        ]
        if len(existing) != 1:
            return Result(
                False,
                "FAST_FIX_TARGET_FILE_AMBIGUOUS",
                data={"requested": value, "matches": len(existing)},
            )
        target = existing[0]
        return target, target.relative_to(repository).as_posix()

    @classmethod
    def _target_paths(
        cls,
        repository: Path,
        requested: str | Sequence[str],
    ) -> list[tuple[Path, str]] | Result:
        values = [requested] if isinstance(requested, str) else list(requested)
        if not 1 <= len(values) <= _MAX_FILES:
            return Result(
                False,
                "FAST_FIX_TARGET_FILES_INVALID",
                data={"count": len(values), "max_files": _MAX_FILES},
            )
        targets: list[tuple[Path, str]] = []
        for value in values:
            result = cls._target_path(repository, str(value))
            if isinstance(result, Result):
                return result
            targets.append(result)
        relatives = [relative for _, relative in targets]
        if len(set(relatives)) != len(relatives):
            return Result(False, "FAST_FIX_TARGET_FILES_INVALID", data={"duplicates": True})
        return targets

    @staticmethod
    def _change_kind(explicit: str, reason: str) -> str:
        normalized = explicit.strip().casefold()
        if normalized:
            return normalized if _CHANGE_KIND.fullmatch(normalized) else ""
        lowered = reason.casefold()
        for kind, signals in (
            ("annotation", ("注解", "annotation", "导入", "import")),
            ("null_guard", ("空值", "判空", "null")),
            ("condition", ("条件", "condition")),
            ("parameter", ("参数", "parameter")),
        ):
            if any(signal in lowered for signal in signals):
                return kind
        return "bounded_change"

    @staticmethod
    def _changed_lines(diff: str) -> tuple[int, int]:
        additions = 0
        deletions = 0
        for line in diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
        return additions, deletions

    @staticmethod
    def _content_risk(diff: str) -> str:
        added_lines = [
            line[1:]
            for line in diff.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        if any(_RISK_ADDITION.search(line) for line in added_lines):
            return "FAST_FIX_HIGH_RISK_CONTENT"
        if any(_PUBLIC_INTERFACE_ADDITION.search(line) for line in added_lines):
            return "FAST_FIX_PUBLIC_INTERFACE_CHANGE"
        return ""

    @staticmethod
    def _file_fingerprint(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _evidence_key(
        binding_id: str,
        head: str,
        file_fingerprints: dict[str, str],
    ) -> str:
        identity = [
            item
            for relative, fingerprint in sorted(file_fingerprints.items())
            for item in (relative, fingerprint)
        ]
        payload = "\0".join((binding_id, head, *identity))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _combined_fingerprint(file_fingerprints: dict[str, str]) -> str:
        payload = "\0".join(
            item
            for relative, fingerprint in sorted(file_fingerprints.items())
            for item in (relative, fingerprint)
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _budget(
        changed_lines: int,
        command_count: int,
        elapsed_seconds: float,
    ) -> dict[str, Any]:
        level = "micro" if changed_lines <= 10 else "small"
        max_commands = 2 if level == "micro" else 5
        target_seconds = 120 if level == "micro" else 300
        return {
            "level": level,
            "changed_lines": changed_lines,
            "command_count": command_count,
            "elapsed_seconds": elapsed_seconds,
            "max_commands": max_commands,
            "target_seconds": target_seconds,
            "hard_max_commands": 5,
            "hard_max_seconds": 180,
            "soft_exceeded": (
                command_count > max_commands or elapsed_seconds > target_seconds
            ),
            "hard_max_changed_lines": _MAX_CHANGED_LINES,
            "hard_exceeded": (
                changed_lines > _MAX_CHANGED_LINES
                or command_count > 5
                or elapsed_seconds > 180
            ),
        }

    def _prepare_requirement(self, requirement_id: str) -> Result:
        requirements = RequirementService(self.root)
        current = requirements.show(requirement_id)
        if not current.ok:
            return current
        status = RequirementStatus(str(current.data["status"]))
        if status == RequirementStatus.VERIFYING:
            return requirements.reopen(
                requirement_id,
                "用户要求单文件 fast_fix 一次登记",
            )
        if status == RequirementStatus.BLOCKED:
            return requirements.transition(
                requirement_id,
                RequirementStatus.IN_PROGRESS,
            )
        if status in {
            RequirementStatus.COMPLETED,
            RequirementStatus.CANCELLED,
            RequirementStatus.ARCHIVED,
        }:
            return Result(
                False,
                "FAST_FIX_REQUIREMENT_STATUS_INVALID",
                data={"status": status.value},
            )
        if status not in {
            RequirementStatus.IN_PROGRESS,
            RequirementStatus.IMPLEMENTED,
        }:
            order = (
                RequirementStatus.CAPTURED,
                RequirementStatus.INVESTIGATING,
                RequirementStatus.ANALYZED,
                RequirementStatus.PLANNED,
                RequirementStatus.READY,
                RequirementStatus.IN_PROGRESS,
            )
            if status not in order:
                return Result(
                    False,
                    "FAST_FIX_REQUIREMENT_STATUS_INVALID",
                    data={"status": status.value},
                )
            while status != RequirementStatus.IN_PROGRESS:
                status = order[order.index(status) + 1]
                self.store.transition_requirement(requirement_id, status)
            requirements.repair_projections()
        current = requirements.show(requirement_id)
        if not current.ok or current.data["status"] not in {
            RequirementStatus.IN_PROGRESS,
            RequirementStatus.IMPLEMENTED,
        }:
            return Result(
                False,
                "FAST_FIX_REQUIREMENT_STATUS_INVALID",
                data={"status": current.data.get("status", "") if current.ok else ""},
            )
        return Result(True, "FAST_FIX_REQUIREMENT_READY")

    def _record_verification(
        self,
        requirement_id: str,
        evidence_key: str,
        verification: str,
        *,
        reason: str,
        risk: str,
        evidence: str,
    ) -> dict[str, Any]:
        timestamp = datetime.now(UTC).isoformat()
        receipt_id = f"VDR-FAST-{evidence_key[:16].upper()}"
        status = "declined" if verification == "declined" else "evidence_recorded"
        record = {
            "receipt_id": receipt_id,
            "requirement_id": requirement_id,
            "entry": "fast_fix_validation",
            "status": status,
            "user_evidence": reason,
            "authorized_by_user": True,
            "risk": risk,
            "evidence": evidence,
            "recorded_at": timestamp,
        }
        requirements = RequirementService(self.root)
        delivery = requirements._delivery(requirement_id)
        delivery["verification"]["fast_fix_validation"] = {
            "status": status,
            "receipt_id": receipt_id,
            "recorded_at": timestamp,
        }
        scope = (
            "verification_decline"
            if verification == "declined"
            else "fast_fix_verification"
        )
        self.store.set_many(
            (
                (scope, receipt_id, record),
                ("requirement_delivery", requirement_id, delivery),
            )
        )
        self.store.audit(
            "verification.declined"
            if verification == "declined"
            else "verification.evidence_recorded",
            "OK",
            record,
        )
        return record
