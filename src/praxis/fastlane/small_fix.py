from __future__ import annotations

import re
import shlex
import shutil
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

from praxis.artifacts.service import ArtifactService
from praxis.domain.requirement import RequirementStatus
from praxis.fastlane.diagnostics import (
    baseline_fingerprint,
    compare_diagnostics,
    normalize_diagnostics,
)
from praxis.fastlane.service import (
    _BASELINE_SCOPE,
    _RISK_CODE,
    _TEST_PATH,
    FastLaneService,
)
from praxis.governance.service import ApprovalService
from praxis.integrations.process import ProcessRunner
from praxis.knowledge.requirements import RequirementService
from praxis.result import Result
from praxis.skills.routing import NodeSkillRouter, NodeSkillRoutingRequest
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService
from praxis.worktree.service import WorktreeService

_STATE_SCOPE = "small_fix"
_PROFILE = "small-fix-v2"
_MAX_BUSINESS_FILES = 3
_MAX_CHANGED_LINES = 80
_GOVERNANCE_BUDGET_SECONDS = 120.0
_RISK_PATH = re.compile(
    r"(^|/)(?:migrations?|flyway|database|permissions?|generated|openapi|swagger)(/|$)|"
    r"(^|/)(?:src/)?(?:shared|common|components)(/|$)|"
    r"\.(?:sql)$",
    re.IGNORECASE,
)


class SmallFixService(FastLaneService):
    """A thin, requirement-linked lane for bounded low-risk fixes."""

    def __init__(self, root: Path | str):
        super().__init__(root)
        self.workspace = WorkspaceService(self.root)
        self.store = StateStore(self.root)

    def start(
        self,
        requirement_id: str,
        *,
        repository_id: str,
        small: bool,
        now: datetime | None = None,
    ) -> Result:
        started_at = monotonic()
        if not small:
            return Result(False, "SMALL_FIX_FLAG_REQUIRED")
        existing = self.store.get(_STATE_SCOPE, requirement_id)
        if existing and existing.get("status") in {"started", "implemented"}:
            if existing.get("repository_id") != repository_id:
                return Result(
                    False,
                    "SMALL_FIX_REPOSITORY_MISMATCH",
                    data={
                        "current": existing.get("repository_id", ""),
                        "requested": repository_id,
                    },
                )
            return Result(
                True,
                (
                    "SMALL_FIX_IMPLEMENTED"
                    if existing.get("status") == "implemented"
                    else "SMALL_FIX_STARTED"
                ),
                data=existing,
            )
        if existing and existing.get("status") == "downgraded":
            return Result(False, "SMALL_FIX_DOWNGRADED", data=existing)
        requirement = self.store.requirement(requirement_id)
        if not requirement:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        try:
            project = self.workspace.project(repository_id)
        except KeyError:
            return Result(
                False,
                "SMALL_FIX_PROJECT_NOT_FOUND",
                data={"repository_id": repository_id},
            )
        if (
            len(requirement.get("systems", [])) != 1
            or project.system_id not in requirement["systems"]
        ):
            return Result(False, "SMALL_FIX_SINGLE_REPOSITORY_REQUIRED")
        if shutil.which("rtk") is None:
            return Result(False, "RTK_NOT_AVAILABLE")
        typecheck = self._typecheck_argv(project)
        if isinstance(typecheck, Result):
            return Result(False, typecheck.code, data=typecheck.data)

        requirements = RequirementService(self.root)
        status = RequirementStatus(str(requirement["status"]))
        if status == RequirementStatus.VERIFYING:
            reopened = requirements.reopen(
                requirement_id,
                "小修复快速通道重新进入实现阶段",
            )
            if not reopened.ok:
                return reopened
        elif status == RequirementStatus.READY:
            transitioned = requirements.transition(
                requirement_id, RequirementStatus.IN_PROGRESS
            )
            if not transitioned.ok:
                return transitioned
        elif status != RequirementStatus.IN_PROGRESS:
            return Result(
                False,
                "SMALL_FIX_REQUIREMENT_STATUS_INVALID",
                data={"status": status.value},
            )

        worktrees = WorktreeService(self.root)
        resolved = worktrees.resolve_template_revision(repository_id)
        if not resolved.ok:
            return resolved
        template_sha = str(resolved.data["revision"])
        created = worktrees.create_for_requirement(
            requirement_id,
            repository_id,
            base_revision=template_sha,
        )
        if not created.ok:
            return created
        binding = self._direct_binding(created)
        if not binding:
            return Result(False, "SMALL_FIX_WORKTREE_UNAVAILABLE")
        worktree = Path(str(binding["repository_path"])).resolve()
        changed = self._changed_paths(worktree)
        if changed:
            return self._downgrade_small(
                requirement_id,
                {
                    "requirement_id": requirement_id,
                    "repository_id": repository_id,
                    "worktree": binding,
                    "worktree_path": str(worktree),
                },
                "隔离工作树初始状态不是干净状态",
                extra_files=changed,
            )

        scoped = "{files}" in typecheck
        baseline: dict[str, Any] = {}
        fingerprint = ""
        if not scoped:
            fingerprint = baseline_fingerprint(
                project.id, template_sha, tuple(typecheck), worktree
            )
            baseline = self.store.get(_BASELINE_SCOPE, fingerprint) or {}
            if not baseline:
                runner = ProcessRunner(worktree, audit_root=self.root)
                executed = runner.run(
                    ["rtk", "proxy", *typecheck],
                    machine_output=True,
                )
                output = self._output(executed)
                baseline = {
                    "fingerprint": fingerprint,
                    "project_id": project.id,
                    "template_sha": template_sha,
                    "argv": typecheck,
                    "status": (
                        "captured"
                        if executed.ok or normalize_diagnostics(output, worktree)
                        else "unavailable"
                    ),
                    "command_ok": executed.ok,
                    "output": output,
                    "raw_log": executed.data.get("raw_log", ""),
                    "repository_path": str(worktree),
                    "captured_at": datetime.now(UTC).isoformat(),
                }
                self.store.set(_BASELINE_SCOPE, fingerprint, baseline)

        routed = NodeSkillRouter(self.root).route(
            NodeSkillRoutingRequest(
                node="in_progress",
                profile=_PROFILE,
                intent=f"小修复：{requirement['original_request']}",
                requirement_id=requirement_id,
                project_id=project.id,
                system_id=project.system_id,
                business_domains=tuple(requirement.get("domains", [])),
                repository_kind=project.kind,
            )
        )
        if not routed.ok:
            return routed
        timestamp = now or datetime.now(UTC)
        governance_seconds = monotonic() - started_at
        record = {
            "requirement_id": requirement_id,
            "repository_id": repository_id,
            "project_id": project.id,
            "profile": _PROFILE,
            "status": "started",
            "template_sha": template_sha,
            "worktree": binding,
            "worktree_path": str(worktree),
            "typecheck_mode": "scoped" if scoped else "baseline",
            "typecheck_argv": typecheck,
            "baseline_fingerprint": fingerprint,
            "baseline": {
                key: value for key, value in baseline.items() if key != "output"
            },
            "ready_at": timestamp.isoformat(),
            "governance_seconds": governance_seconds,
            "warnings": self._time_warnings(governance_seconds, 0.0),
            "skill_route": {
                "profile": _PROFILE,
                "route_fingerprint": routed.data.get("route_fingerprint", ""),
                "execution_principles": routed.data.get("execution_principles", []),
                "audited_skills": [
                    item["id"]
                    for item in routed.data.get("decisions", [])
                    if item["mode"]
                    in {"required", "conditional_required", "conditional"}
                ],
            },
            "updated_at": timestamp.isoformat(),
        }
        self.store.set(_STATE_SCOPE, requirement_id, record)
        audit_id = self.store.audit("fix.start", "SMALL_FIX_STARTED", record)
        return Result(
            True,
            "SMALL_FIX_STARTED",
            data={**record, "audit_id": audit_id},
        )

    def finish(
        self,
        requirement_id: str,
        *,
        test_command: str,
        now: datetime | None = None,
    ) -> Result:
        finish_started = monotonic()
        finish_timestamp = now or datetime.now(UTC)
        record = self.store.get(_STATE_SCOPE, requirement_id)
        if not record:
            return Result(False, "SMALL_FIX_NOT_STARTED")
        if record.get("status") == "implemented":
            return Result(
                True,
                str(record.get("result_code", "SMALL_FIX_IMPLEMENTED")),
                data=record,
            )
        if record.get("status") == "downgraded":
            return Result(False, "SMALL_FIX_DOWNGRADED", data=record)
        if shutil.which("rtk") is None:
            return Result(False, "RTK_NOT_AVAILABLE")
        test_argv = self._parse_command(test_command)
        if not test_argv:
            return Result(False, "SMALL_FIX_TEST_COMMAND_INVALID")

        worktree = Path(str(record["worktree_path"])).resolve()
        changed = self._changed_paths(worktree)
        business_files = sorted(path for path in changed if not _TEST_PATH.search(path))
        if not 1 <= len(business_files) <= _MAX_BUSINESS_FILES:
            return self._downgrade_small(
                requirement_id,
                record,
                "业务文件必须为 1–3 个",
                extra_files=business_files,
            )
        risky_paths = [path for path in business_files if _RISK_PATH.search(path)]
        if risky_paths:
            return self._downgrade_small(
                requirement_id,
                record,
                "检测到数据库、契约、权限、生成代码或公共组件路径",
                extra_files=risky_paths,
            )
        content_risk = self._diff_content_risk(worktree, business_files)
        if content_risk:
            return self._downgrade_small(requirement_id, record, content_risk)
        if any(not (worktree / path).is_file() for path in business_files):
            return self._downgrade_small(
                requirement_id, record, "业务文件不存在", extra_files=business_files
            )
        tracked = self._git_output(
            worktree,
            ["ls-files", "--error-unmatch", "--", *business_files],
        )
        if len(tracked.splitlines()) != len(business_files):
            return self._downgrade_small(
                requirement_id,
                record,
                "业务文件必须已受 Git 跟踪",
                extra_files=business_files,
            )
        stats = self._diff_stats(worktree, business_files)
        if isinstance(stats, Result):
            return stats
        if stats["changed_lines"] > _MAX_CHANGED_LINES:
            return self._downgrade_small(
                requirement_id,
                record,
                "业务修改超过 80 行",
                extra_files=business_files,
            )

        typecheck_argv = list(record["typecheck_argv"])
        if record["typecheck_mode"] == "scoped":
            scoped_argv: list[str] = []
            for item in typecheck_argv:
                if item == "{files}":
                    scoped_argv.extend(business_files)
                else:
                    scoped_argv.append(item)
            typecheck_argv = scoped_argv
        entries = [
            shlex.join(["rtk", "test", *test_argv]),
            shlex.join(["rtk", "git", "diff", "--check"]),
            shlex.join(["rtk", "proxy", *typecheck_argv]),
        ]
        approvals = ApprovalService(self.root)
        missing_entries = [
            entry
            for entry in entries
            if not approvals.check(
                requirement_id,
                "small_fix_verification",
                entry,
            ).ok
        ]
        if missing_entries:
            receipt = approvals.grant(
                requirement_id,
                "small_fix_verification",
                missing_entries,
                user_evidence="用户执行 praxis fix finish 并提供精确测试命令",
                authorized_by_user=True,
            )
            if not receipt.ok:
                return receipt

        runner = ProcessRunner(worktree, audit_root=self.root)
        green = runner.run(["rtk", "test", *test_argv], machine_output=True)
        if not green.ok:
            return Result(
                False,
                "SMALL_FIX_GREEN_FAILED",
                data={"raw_log": green.data.get("raw_log", "")},
            )
        diff_check = runner.run(
            ["rtk", "git", "diff", "--check"], machine_output=True
        )
        if not diff_check.ok:
            return Result(
                False,
                "SMALL_FIX_DIFF_CHECK_FAILED",
                data={"raw_log": diff_check.data.get("raw_log", "")},
            )
        checked = runner.run(
            ["rtk", "proxy", *typecheck_argv],
            machine_output=True,
        )
        comparison = self._typecheck_result(record, worktree, checked)
        if record["typecheck_mode"] == "scoped" and not checked.ok:
            return Result(
                False,
                "SMALL_FIX_SCOPED_TYPECHECK_FAILED",
                data={
                    **comparison,
                    "raw_log": checked.data.get("raw_log", ""),
                },
            )
        if comparison["status"] == "failed_new_diagnostics":
            return Result(
                False,
                "SMALL_FIX_NEW_TYPE_DIAGNOSTICS",
                data=comparison,
            )

        artifact = ArtifactService(self.root).add(
            requirement_id,
            "code-change",
            worktree / business_files[0],
            stage="implementation",
            metadata={
                "small_fix_profile": _PROFILE,
                "business_files": business_files,
                "changed_lines": stats["changed_lines"],
                "include_untracked": changed,
            },
        )
        if not artifact.ok:
            return artifact
        implementation = RequirementService(self.root).record_implementation(
            requirement_id,
            str(record["project_id"]),
            artifact_ids=[str(artifact.data["artifact_id"])],
        )
        if not implementation.ok:
            return implementation
        self._advance_to(requirement_id, RequirementStatus.IMPLEMENTED)

        try:
            coding_seconds = max(
                0.0,
                (
                    finish_timestamp
                    - datetime.fromisoformat(str(record["ready_at"]))
                ).total_seconds(),
            )
        except (KeyError, ValueError):
            coding_seconds = 0.0
        governance_seconds = float(record.get("governance_seconds", 0.0)) + (
            monotonic() - finish_started
        )
        inconclusive = comparison["status"] == "baseline_unavailable"
        code = (
            "SMALL_FIX_IMPLEMENTED_VERIFICATION_INCONCLUSIVE"
            if inconclusive
            else "SMALL_FIX_IMPLEMENTED"
        )
        record.update(
            status="implemented",
            result_code=code,
            test_command=test_command,
            business_files=business_files,
            changed_lines=stats["changed_lines"],
            diff=stats,
            artifact_id=artifact.data["artifact_id"],
            verification={
                "green": "passed",
                "diff_check": "passed",
                "typecheck": comparison,
                "green_raw_log": green.data.get("raw_log", ""),
                "diff_raw_log": diff_check.data.get("raw_log", ""),
                "typecheck_raw_log": checked.data.get("raw_log", ""),
            },
            governance_seconds=governance_seconds,
            coding_seconds=coding_seconds,
            warnings=self._time_warnings(governance_seconds, coding_seconds),
            updated_at=finish_timestamp.isoformat(),
        )
        self.store.set(_STATE_SCOPE, requirement_id, record)
        audit_id = self.store.audit("fix.finish", code, record)
        RequirementService(self.root).progress(
            requirement_id,
            (
                "small-fix v2 已登记一个完整 Git diff 产出物并完成聚焦测试、"
                "diff-check 与增量类型检查。"
            ),
        )
        return Result(True, code, data={**record, "audit_id": audit_id})

    @staticmethod
    def _direct_binding(result: Result) -> dict[str, Any] | None:
        path = result.data.get("repository_path") or result.data.get("path")
        if path:
            return {**result.data, "repository_path": path}
        return FastLaneService._binding(result)

    def _typecheck_result(
        self,
        record: dict[str, Any],
        worktree: Path,
        checked: Result,
    ) -> dict[str, Any]:
        if record["typecheck_mode"] == "scoped":
            return {
                "status": "passed" if checked.ok else "failed_new_diagnostics",
                "new_diagnostics": [],
            }
        baseline = self.store.get(
            _BASELINE_SCOPE, str(record.get("baseline_fingerprint", ""))
        )
        current_fingerprint = baseline_fingerprint(
            str(record["project_id"]),
            str(record["template_sha"]),
            tuple(record["typecheck_argv"]),
            worktree,
        )
        output = self._output(checked)
        if (
            current_fingerprint != record.get("baseline_fingerprint")
            or baseline is None
            or baseline.get("status") == "unavailable"
            or (not checked.ok and not normalize_diagnostics(output, worktree))
        ):
            return {"status": "baseline_unavailable", "new_diagnostics": []}
        comparison = compare_diagnostics(
            str(baseline.get("output", "")),
            output,
            worktree,
            baseline_root=Path(str(baseline.get("repository_path", worktree))),
        )
        if checked.ok and comparison["status"] != "failed_new_diagnostics":
            return {**comparison, "status": "passed"}
        return comparison

    def _diff_stats(
        self, worktree: Path, business_files: list[str]
    ) -> dict[str, int] | Result:
        output = self._git_output(
            worktree,
            ["diff", "--numstat", "HEAD", "--", *business_files],
            strip=False,
        )
        insertions = 0
        deletions = 0
        for line in output.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
                return Result(False, "SMALL_FIX_BINARY_DIFF_UNSUPPORTED")
            insertions += int(parts[0])
            deletions += int(parts[1])
        return {
            "files": len(business_files),
            "insertions": insertions,
            "deletions": deletions,
            "changed_lines": insertions + deletions,
        }

    def _diff_content_risk(self, worktree: Path, business_files: list[str]) -> str:
        output = self._git_output(
            worktree,
            ["diff", "--unified=0", "HEAD", "--", *business_files],
            strip=False,
        )
        additions = "\n".join(
            line[1:]
            for line in output.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        return (
            "检测到事务、锁或并发特征"
            if _RISK_CODE.search(additions)
            else ""
        )

    def _downgrade_small(
        self,
        requirement_id: str,
        record: dict[str, Any],
        reason: str,
        *,
        extra_files: list[str] | None = None,
    ) -> Result:
        record.update(
            status="downgraded",
            downgrade_reason=reason,
            extra_files=extra_files or [],
            updated_at=datetime.now(UTC).isoformat(),
        )
        self.store.set(_STATE_SCOPE, requirement_id, record)
        audit_id = self.store.audit(
            "fix.downgraded",
            "SMALL_FIX_DOWNGRADED",
            {"requirement_id": requirement_id, "reason": reason},
        )
        return Result(
            False,
            "SMALL_FIX_DOWNGRADED",
            data={**record, "audit_id": audit_id},
        )

    @staticmethod
    def _time_warnings(
        governance_seconds: float,
        coding_seconds: float,
    ) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        if governance_seconds > _GOVERNANCE_BUDGET_SECONDS:
            warnings.append(
                {
                    "code": "SMALL_FIX_GOVERNANCE_BUDGET_EXCEEDED",
                    "governance_seconds": round(governance_seconds, 3),
                    "budget_seconds": _GOVERNANCE_BUDGET_SECONDS,
                }
            )
        if coding_seconds > 0 and governance_seconds > coding_seconds * 2:
            warnings.append(
                {
                    "code": "SMALL_FIX_GOVERNANCE_RATIO_EXCEEDED",
                    "governance_seconds": round(governance_seconds, 3),
                    "coding_seconds": round(coding_seconds, 3),
                }
            )
        return warnings
