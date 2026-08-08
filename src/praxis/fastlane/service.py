from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from praxis.artifacts.service import ArtifactService
from praxis.documents.atomic_writer import atomic_write_text
from praxis.domain.requirement import RequirementStatus
from praxis.fastlane.diagnostics import (
    baseline_fingerprint,
    compare_diagnostics,
    normalize_diagnostics,
)
from praxis.governance.service import ApprovalService
from praxis.integrations.process import ProcessRunner
from praxis.knowledge.requirements import RequirementService
from praxis.naming.requirement import RequirementPathPolicy, requirement_document
from praxis.result import Result
from praxis.skills.routing import NodeSkillRouter, NodeSkillRoutingRequest
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService
from praxis.worktree.service import WorktreeService

_STATE_SCOPE = "fast_lane"
_BASELINE_SCOPE = "fast_lane_baseline"
_PROFILE = "fast-defect-v1"
_FORBIDDEN_RISKS = {
    "api",
    "api-contract",
    "concurrency",
    "database",
    "migration",
    "permission",
    "transaction",
    "lock",
}
_RISK_PATH = re.compile(
    r"(^|/)(?:migrations?|flyway|database|permissions?)(/|$)|"
    r"(?:openapi|swagger)|\.(?:sql)$",
    re.IGNORECASE,
)
_RISK_CODE = re.compile(
    r"@Transactional|FOR\s+UPDATE|SELECT\s+.+\s+FOR\s+UPDATE|"
    r"\b(lock|mutex|semaphore|concurrent|transaction)\b",
    re.IGNORECASE,
)
_TEST_PATH = re.compile(
    r"(^|/)(?:tests?|__tests__)(/|$)|(?:\.test\.|\.spec\.)",
    re.IGNORECASE,
)
_START = "<!-- PRAXIS:FAST-LANE:START -->"
_END = "<!-- PRAXIS:FAST-LANE:END -->"


class FastLaneService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.store = StateStore(self.root)
        self.workspace = WorkspaceService(self.root)

    def start(
        self,
        *,
        short_name: str,
        request: str,
        systems: list[str],
        domains: list[str],
        project_id: str,
        reproduction: str,
        now: datetime | None = None,
    ) -> Result:
        timestamp = now or datetime.now(UTC)
        if not reproduction.strip():
            return Result(False, "FAST_LANE_REPRODUCTION_REQUIRED")
        try:
            project = self.workspace.project(project_id)
        except KeyError:
            return Result(False, "FAST_LANE_PROJECT_NOT_FOUND", data={"project_id": project_id})
        if not systems or len(set(systems)) != 1 or project.system_id not in systems:
            return Result(False, "FAST_LANE_SINGLE_PROJECT_REQUIRED")
        existing = next(
            (
                item
                for item in self.store.list_scope(_STATE_SCOPE)
                if item.get("status") == "candidate"
                and item.get("project_id") == project_id
                and item.get("short_name") == short_name.strip()
                and item.get("request") == request.rstrip()
                and item.get("reproduction") == reproduction.strip()
            ),
            None,
        )
        if existing:
            return Result(True, "FAST_LANE_CANDIDATE", data=self._status_data(existing))
        requirement = RequirementService(self.root).create(
            short_name, request, systems, domains, now=timestamp
        )
        if not requirement.ok:
            return requirement
        requirement_id = str(requirement.data["requirement_id"])
        preview = WorktreeService(self.root).preview_for_requirement(
            requirement_id, [project_id]
        )
        if not preview.ok:
            return preview
        record = {
            "requirement_id": requirement_id,
            "short_name": short_name.strip(),
            "request": request.rstrip(),
            "systems": systems,
            "domains": domains,
            "project_id": project_id,
            "reproduction": reproduction.strip(),
            "profile": _PROFILE,
            "status": "candidate",
            "preview_id": preview.data["preview_id"],
            "created_at": timestamp.isoformat(),
            "updated_at": timestamp.isoformat(),
            "deadlines": {
                "locate": (timestamp + timedelta(minutes=5)).isoformat(),
            },
            "pending_confirmation": [
                "1–3 个已跟踪业务文件",
                "根因与调查证据",
                "聚焦测试命令与预期 RED",
                "显式风险声明",
                "一次性限定授权",
            ],
        }
        self.store.set(_STATE_SCOPE, requirement_id, record)
        audit_id = self.store.audit("fast.start", "FAST_LANE_CANDIDATE", record)
        return Result(
            True,
            "FAST_LANE_CANDIDATE",
            data={**self._status_data(record), "audit_id": audit_id},
            diagnostics=requirement.diagnostics,
        )

    def confirm(
        self,
        requirement_id: str,
        *,
        preview_id: str,
        business_files: list[str],
        root_cause: str,
        evidence: str,
        test_command: str,
        expected_red: str,
        risks: list[str],
        user_evidence: str,
        authorized_by_user: bool,
        now: datetime | None = None,
    ) -> Result:
        record = self.store.get(_STATE_SCOPE, requirement_id)
        if not record:
            return Result(False, "FAST_LANE_NOT_FOUND")
        self._check_budgets(record)
        if record.get("status") in {"confirmed", "red_recorded", "implemented"}:
            return Result(True, "FAST_LANE_CONFIRMED", data=self._status_data(record))
        if record.get("status") == "downgraded":
            return Result(False, "FAST_LANE_DOWNGRADED", data=self._status_data(record))
        if preview_id != record.get("preview_id"):
            return Result(False, "WORKTREE_PREVIEW_MISMATCH")
        if not authorized_by_user or not user_evidence.strip():
            return Result(False, "USER_APPROVAL_REQUIRED")
        required = {
            "root_cause": root_cause,
            "evidence": evidence,
            "test_command": test_command,
            "expected_red": expected_red,
        }
        missing = [key for key, value in required.items() if not value.strip()]
        if missing:
            return Result(False, "FAST_LANE_EVIDENCE_REQUIRED", data={"missing": missing})
        normalized = self._business_files(business_files)
        if not normalized:
            return Result(False, "FAST_LANE_BUSINESS_FILES_INVALID")
        reason = self._risk_reason(normalized, risks)
        if reason:
            return self._downgrade(record, reason)
        if shutil.which("rtk") is None:
            return Result(False, "RTK_NOT_AVAILABLE")
        project = self.workspace.project(str(record["project_id"]))
        typecheck = self._typecheck_argv(project)
        if isinstance(typecheck, Result):
            return typecheck
        test_argv = self._parse_command(test_command)
        if not test_argv:
            return Result(False, "FAST_LANE_TEST_COMMAND_INVALID")

        with self._stage_requirement_documents(requirement_id, project):
            ensured = WorktreeService(self.root).ensure_for_requirement(
                requirement_id, [project.id], preview_id=preview_id
            )
        if not ensured.ok:
            return ensured
        binding = self._binding(ensured)
        if not binding:
            return Result(False, "FAST_LANE_WORKTREE_UNAVAILABLE")
        worktree = Path(str(binding["repository_path"])).resolve()
        runner = ProcessRunner(worktree, audit_root=self.root)
        tracked = runner.run(
            ["rtk", "git", "ls-files", "--error-unmatch", "--", *normalized],
            machine_output=True,
        )
        if not tracked.ok:
            return self._downgrade(
                record,
                "业务文件不存在或未受 Git 跟踪",
                worktree=worktree,
                binding=binding,
            )
        dirty = self._changed_paths(worktree)
        if dirty:
            return self._downgrade(
                record,
                "工作树在生成类型基线前不是干净状态",
                worktree=worktree,
                binding=binding,
                extra_files=dirty,
            )
        content_risk = self._content_risk(worktree, normalized)
        if content_risk:
            return self._downgrade(
                record, content_risk, worktree=worktree, binding=binding
            )

        development_entry = shlex.join(["rtk", "test", *test_argv])
        verification_entries = [
            shlex.join(["rtk", "git", "diff", "--check"]),
            shlex.join(["rtk", "proxy", *typecheck]),
        ]
        existing_scopes = {
            item.get("scope")
            for item in self.store.list_scope("approval_receipt")
            if item.get("requirement_id") == requirement_id
        }
        if "development_tdd" not in existing_scopes:
            granted = ApprovalService(self.root).grant(
                requirement_id,
                "development_tdd",
                [development_entry],
                user_evidence=user_evidence,
                authorized_by_user=True,
            )
            if not granted.ok:
                return granted
        if "verification" not in existing_scopes:
            granted = ApprovalService(self.root).grant(
                requirement_id,
                "verification",
                verification_entries,
                user_evidence=user_evidence,
                authorized_by_user=True,
            )
            if not granted.ok:
                return granted

        template_sha = self._git_output(worktree, ["rev-parse", "HEAD"]) or "unavailable"
        fingerprint = baseline_fingerprint(
            project.id, template_sha, tuple(typecheck), worktree
        )
        baseline = self.store.get(_BASELINE_SCOPE, fingerprint)
        if not baseline:
            executed = runner.run(["rtk", "proxy", *typecheck], machine_output=True)
            output = self._output(executed)
            baseline_status = (
                "captured"
                if executed.ok or normalize_diagnostics(output, worktree)
                else "unavailable"
            )
            baseline = {
                "fingerprint": fingerprint,
                "project_id": project.id,
                "template_sha": template_sha,
                "argv": typecheck,
                "status": baseline_status,
                "command_ok": executed.ok,
                "output": output,
                "raw_log": executed.data.get("raw_log", ""),
                "repository_path": str(worktree),
                "captured_at": datetime.now(UTC).isoformat(),
            }
            self.store.set(_BASELINE_SCOPE, fingerprint, baseline)

        timestamp = now or datetime.now(UTC)
        record.update(
            status="confirmed",
            business_files=normalized,
            root_cause=root_cause.strip(),
            evidence=evidence.strip(),
            test_command=test_command.strip(),
            test_argv=test_argv,
            expected_red=expected_red.strip(),
            risks=risks,
            user_evidence=user_evidence.strip(),
            authorized_by_user=True,
            worktree=binding,
            worktree_path=str(worktree),
            typecheck_argv=typecheck,
            baseline_fingerprint=fingerprint,
            baseline={
                key: value for key, value in baseline.items() if key != "output"
            },
            deadlines={
                **record.get("deadlines", {}),
                "implementation": (timestamp + timedelta(minutes=10)).isoformat(),
                "governance": (timestamp + timedelta(minutes=2)).isoformat(),
            },
            updated_at=timestamp.isoformat(),
        )
        self._write_documents(record)
        self._advance_to(requirement_id, RequirementStatus.IN_PROGRESS)
        routed = NodeSkillRouter(self.root).route(
            NodeSkillRoutingRequest(
                node="in_progress",
                profile=_PROFILE,
                intent=f"低风险缺陷：{record['request']}",
                requirement_id=requirement_id,
                project_id=project.id,
                system_id=project.system_id,
                business_domains=tuple(record.get("domains", [])),
                repository_kind=project.kind,
                risks=tuple(risks),
            )
        )
        if not routed.ok:
            return routed
        record["skill_route"] = {
            "profile": _PROFILE,
            "route_fingerprint": routed.data.get("route_fingerprint", ""),
            "execution_principles": routed.data.get("execution_principles", []),
            "audited_skills": [
                item["id"]
                for item in routed.data.get("decisions", [])
                if item["mode"] in {"required", "conditional_required", "conditional"}
            ],
        }
        self.store.set(_STATE_SCOPE, requirement_id, record)
        audit_id = self.store.audit("fast.confirm", "FAST_LANE_CONFIRMED", record)
        return Result(
            True,
            "FAST_LANE_CONFIRMED",
            data={**self._status_data(record), "audit_id": audit_id},
        )

    def red(self, requirement_id: str, *, now: datetime | None = None) -> Result:
        record = self.store.get(_STATE_SCOPE, requirement_id)
        if not record:
            return Result(False, "FAST_LANE_NOT_FOUND")
        self._check_budgets(record)
        if record.get("status") == "red_recorded":
            return Result(True, "FAST_LANE_RED_RECORDED", data=self._status_data(record))
        if record.get("status") != "confirmed":
            return Result(False, "FAST_LANE_RED_NOT_READY", data=self._status_data(record))
        worktree = Path(str(record["worktree_path"]))
        changed = set(self._changed_paths(worktree))
        touched = sorted(changed & set(record["business_files"]))
        if touched:
            return Result(
                False,
                "FAST_LANE_RED_AFTER_IMPLEMENTATION",
                data={"modified_business_files": touched},
            )
        if shutil.which("rtk") is None:
            return Result(False, "RTK_NOT_AVAILABLE")
        approval = ApprovalService(self.root).check(
            requirement_id,
            "development_tdd",
            shlex.join(["rtk", "test", *record["test_argv"]]),
        )
        if not approval.ok:
            return approval
        runner = ProcessRunner(worktree, audit_root=self.root)
        executed = runner.run(
            ["rtk", "test", *record["test_argv"]], machine_output=True
        )
        output = self._output(executed)
        if executed.ok or str(record["expected_red"]) not in output:
            return Result(
                False,
                "FAST_LANE_RED_INVALID",
                data={
                    "exit_was_nonzero": not executed.ok,
                    "expected_red": record["expected_red"],
                    "raw_log": executed.data.get("raw_log", ""),
                },
            )
        timestamp = now or datetime.now(UTC)
        record.update(
            status="red_recorded",
            red={
                "status": "recorded",
                "expected_red": record["expected_red"],
                "raw_log": executed.data.get("raw_log", ""),
                "recorded_at": timestamp.isoformat(),
            },
            updated_at=timestamp.isoformat(),
        )
        self.store.set(_STATE_SCOPE, requirement_id, record)
        audit_id = self.store.audit("fast.red", "FAST_LANE_RED_RECORDED", record["red"])
        return Result(
            True,
            "FAST_LANE_RED_RECORDED",
            data={**self._status_data(record), "audit_id": audit_id},
        )

    def status(self, requirement_id: str) -> Result:
        record = self.store.get(_STATE_SCOPE, requirement_id)
        if not record:
            return Result(False, "FAST_LANE_NOT_FOUND")
        return Result(True, "OK", data=self._status_data(record))

    def finish(self, requirement_id: str, *, now: datetime | None = None) -> Result:
        record = self.store.get(_STATE_SCOPE, requirement_id)
        if not record:
            return Result(False, "FAST_LANE_NOT_FOUND")
        self._check_budgets(record)
        if record.get("status") == "implemented":
            code = str(record.get("result_code", "FAST_LANE_IMPLEMENTED"))
            return Result(True, code, data=self._status_data(record))
        if record.get("status") != "red_recorded":
            return Result(False, "FAST_LANE_FINISH_NOT_READY", data=self._status_data(record))
        if shutil.which("rtk") is None:
            return Result(False, "RTK_NOT_AVAILABLE")
        worktree = Path(str(record["worktree_path"]))
        changed = self._changed_paths(worktree)
        business_changed = [
            path for path in changed if not _TEST_PATH.search(path)
        ]
        extras = sorted(set(business_changed) - set(record["business_files"]))
        if extras or not business_changed:
            return self._downgrade(
                record,
                "实际业务文件超出已确认范围" if extras else "没有检测到业务文件修改",
                extra_files=extras,
            )
        content_risk = self._content_risk(worktree, business_changed)
        if content_risk:
            return self._downgrade(record, content_risk)

        approvals = (
            ApprovalService(self.root).check(
                requirement_id,
                "development_tdd",
                shlex.join(["rtk", "test", *record["test_argv"]]),
            ),
            ApprovalService(self.root).check(
                requirement_id,
                "verification",
                shlex.join(["rtk", "git", "diff", "--check"]),
            ),
            ApprovalService(self.root).check(
                requirement_id,
                "verification",
                shlex.join(["rtk", "proxy", *record["typecheck_argv"]]),
            ),
        )
        missing_approval = next((item for item in approvals if not item.ok), None)
        if missing_approval:
            return missing_approval
        runner = ProcessRunner(worktree, audit_root=self.root)
        green = runner.run(
            ["rtk", "test", *record["test_argv"]], machine_output=True
        )
        if not green.ok:
            return Result(
                False,
                "FAST_LANE_GREEN_FAILED",
                data={"raw_log": green.data.get("raw_log", "")},
            )
        diff = runner.run(
            ["rtk", "git", "diff", "--check"], machine_output=True
        )
        if not diff.ok:
            return Result(
                False,
                "FAST_LANE_DIFF_CHECK_FAILED",
                data={"raw_log": diff.data.get("raw_log", "")},
            )
        checked = runner.run(
            ["rtk", "proxy", *record["typecheck_argv"]], machine_output=True
        )
        baseline = self.store.get(
            _BASELINE_SCOPE, str(record.get("baseline_fingerprint", ""))
        )
        current_fingerprint = baseline_fingerprint(
            str(record["project_id"]),
            str(record.get("baseline", {}).get("template_sha", "unavailable")),
            tuple(record["typecheck_argv"]),
            worktree,
        )
        current_output = self._output(checked)
        if (
            current_fingerprint != record.get("baseline_fingerprint")
            or baseline is None
            or baseline.get("status") == "unavailable"
            or (not checked.ok and not normalize_diagnostics(current_output, worktree))
        ):
            comparison: dict[str, Any] = {
                "status": "baseline_unavailable",
                "new_diagnostics": [],
            }
        else:
            comparison = compare_diagnostics(
                str(baseline.get("output", "")),
                current_output,
                worktree,
                baseline_root=Path(str(baseline.get("repository_path", worktree))),
            )
            if checked.ok and comparison["status"] != "failed_new_diagnostics":
                comparison = {**comparison, "status": "passed"}
        if comparison["status"] == "failed_new_diagnostics":
            return Result(False, "FAST_LANE_NEW_TYPE_DIAGNOSTICS", data=comparison)

        artifact = ArtifactService(self.root).add(
            requirement_id,
            "code-change",
            worktree / business_changed[0],
            stage="implementation",
            metadata={
                "fast_lane_profile": _PROFILE,
                "business_files": sorted(business_changed),
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
        timestamp = now or datetime.now(UTC)
        inconclusive = comparison["status"] == "baseline_unavailable"
        code = (
            "FAST_LANE_IMPLEMENTED_VERIFICATION_INCONCLUSIVE"
            if inconclusive
            else "FAST_LANE_IMPLEMENTED"
        )
        record.update(
            status="implemented",
            result_code=code,
            verification={
                "green": "passed",
                "diff_check": "passed",
                "typecheck": comparison,
                "green_raw_log": green.data.get("raw_log", ""),
                "diff_raw_log": diff.data.get("raw_log", ""),
                "typecheck_raw_log": checked.data.get("raw_log", ""),
            },
            artifact_id=artifact.data["artifact_id"],
            updated_at=timestamp.isoformat(),
        )
        self.store.set(_STATE_SCOPE, requirement_id, record)
        audit_id = self.store.audit("fast.finish", code, record["verification"])
        RequirementService(self.root).progress(
            requirement_id,
            "快车道实现与限定验证已登记；未执行提交、推送、全量验证或 reviewer。",
        )
        return Result(
            True,
            code,
            data={**self._status_data(record), "audit_id": audit_id},
        )

    @staticmethod
    def _parse_command(command: str) -> list[str]:
        try:
            return shlex.split(command)
        except ValueError:
            return []

    @staticmethod
    def _business_files(files: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in files:
            value = raw.strip().replace("\\", "/")
            path = PurePosixPath(value)
            if (
                not value
                or path.is_absolute()
                or any(part in {"", ".", ".."} for part in path.parts)
            ):
                return []
            if value not in normalized:
                normalized.append(value)
        return normalized if 1 <= len(normalized) <= 3 else []

    @staticmethod
    def _typecheck_argv(project: Project) -> list[str] | Result:
        if not project.typecheck_commands:
            return Result(False, "FAST_LANE_TYPECHECK_NOT_CONFIGURED")
        if len(project.typecheck_commands) != 1:
            return Result(
                False,
                "FAST_LANE_TYPECHECK_AMBIGUOUS",
                data={"commands": list(project.typecheck_commands)},
            )
        try:
            argv = shlex.split(project.typecheck_commands[0])
        except ValueError:
            argv = []
        return argv or Result(False, "FAST_LANE_TYPECHECK_COMMAND_INVALID")

    @staticmethod
    def _binding(ensured: Result) -> dict[str, Any] | None:
        items = ensured.data.get("items", [])
        if not items:
            return None
        item = items[0]
        payload = item.get("data", item)
        path = payload.get("repository_path") or payload.get("path")
        return {**payload, "repository_path": path} if path else None

    def _risk_reason(self, files: list[str], risks: list[str]) -> str:
        normalized = {risk.strip().casefold() for risk in risks if risk.strip()}
        forbidden = sorted(normalized & _FORBIDDEN_RISKS)
        if forbidden:
            return "显式高风险：" + ", ".join(forbidden)
        risky_paths = [path for path in files if _RISK_PATH.search(path)]
        if risky_paths:
            return "高风险路径：" + ", ".join(risky_paths)
        return ""

    @staticmethod
    def _content_risk(worktree: Path, files: list[str]) -> str:
        risky = []
        for relative in files:
            path = worktree / relative
            if not path.is_file():
                return f"业务文件不存在：{relative}"
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _RISK_CODE.search(content):
                risky.append(relative)
        return "检测到事务、锁或并发特征：" + ", ".join(risky) if risky else ""

    def _downgrade(
        self,
        record: dict[str, Any],
        reason: str,
        *,
        worktree: Path | None = None,
        binding: dict[str, Any] | None = None,
        extra_files: list[str] | None = None,
    ) -> Result:
        record.update(
            status="downgraded",
            downgrade_reason=reason,
            updated_at=datetime.now(UTC).isoformat(),
        )
        if worktree is not None:
            record["worktree_path"] = str(worktree)
        if binding is not None:
            record["worktree"] = binding
        if extra_files:
            record["extra_files"] = extra_files
        self.store.set(_STATE_SCOPE, str(record["requirement_id"]), record)
        audit_id = self.store.audit(
            "fast.downgraded", "FAST_LANE_DOWNGRADED", {"reason": reason}
        )
        return Result(
            False,
            "FAST_LANE_DOWNGRADED",
            data={**self._status_data(record), "audit_id": audit_id},
        )

    @staticmethod
    def _output(result: Result) -> str:
        return "\n".join(
            part for part in (result.data.get("stdout", ""), result.data.get("stderr", "")) if part
        )

    @staticmethod
    def _git_output(
        repository: Path, arguments: list[str], *, strip: bool = True
    ) -> str:
        try:
            completed = subprocess.run(
                ["git", *arguments],
                cwd=repository,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return ""
        if completed.returncode != 0:
            return ""
        return completed.stdout.strip() if strip else completed.stdout.rstrip("\n")

    def _changed_paths(self, repository: Path) -> list[str]:
        output = self._git_output(
            repository,
            ["status", "--porcelain", "--untracked-files=all"],
            strip=False,
        )
        paths = []
        for line in output.splitlines():
            value = line[3:]
            if " -> " in value:
                value = value.split(" -> ", 1)[1]
            if value and value not in paths:
                paths.append(value)
        return paths

    def _status_data(self, record: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        warnings = []
        budgets: dict[str, dict[str, Any]] = {}
        for budget, deadline in record.get("deadlines", {}).items():
            try:
                target = datetime.fromisoformat(str(deadline))
            except ValueError:
                continue
            remaining = round((target - now).total_seconds(), 3)
            exceeded = remaining < 0
            budgets[budget] = {
                "deadline": deadline,
                "remaining_seconds": max(0.0, remaining),
                "exceeded": exceeded,
            }
            if exceeded:
                warnings.append(
                    {
                        "code": "FAST_LANE_BUDGET_EXCEEDED",
                        "budget": budget,
                        "deadline": deadline,
                    }
                )
        receipts = [
            {
                "receipt_id": item.get("receipt_id"),
                "scope": item.get("scope"),
                "entries": item.get("entries", []),
                "status": item.get("status"),
            }
            for item in self.store.list_scope("approval_receipt")
            if item.get("requirement_id") == record.get("requirement_id")
        ]
        return {
            **record,
            "budgets": budgets,
            "receipts": receipts,
            "warnings": warnings,
        }

    def _check_budgets(self, record: dict[str, Any]) -> None:
        warnings = self._status_data(record)["warnings"]
        if warnings:
            self.store.audit(
                "fast.budget_exceeded",
                "FAST_LANE_BUDGET_EXCEEDED",
                {"requirement_id": record["requirement_id"], "warnings": warnings},
            )

    def _write_documents(self, record: dict[str, Any]) -> None:
        requirement = self.store.requirement(str(record["requirement_id"]))
        if not requirement:
            return
        workspace = self.workspace.load()
        directory = RequirementPathPolicy(
            self.root / str(workspace["knowledge_root"])
        ).locate_requirement_path(
            str(requirement["requirement_id"]), str(requirement["short_name"])
        )
        files = {
            requirement_document("analysis"): "\n".join(
                (
                    "## 快车道调查",
                    "",
                    f"- 复现：{record['reproduction']}",
                    f"- 根因：{record['root_cause']}",
                    f"- 证据：{record['evidence']}",
                    f"- 业务文件：{', '.join(record['business_files'])}",
                )
            ),
            requirement_document("plan"): "\n".join(
                (
                    "## 快车道实施计划",
                    "",
                    f"- RED：`{record['test_command']}`，预期包含 `{record['expected_red']}`",
                    "- GREEN：同一聚焦测试",
                    "- 验证：`git diff --check` 与配置的增量类型检查",
                    "- 边界：不提交、不推送、不运行全量构建、全量测试或 reviewer",
                )
            ),
            requirement_document("progress"): "\n".join(
                (
                    "## 快车道进度",
                    "",
                    "- 已确认一次性开发与限定验证授权。",
                    "- 等待可信 RED。",
                )
            ),
        }
        for name, body in files.items():
            self._managed_block(directory / name, body)

    @staticmethod
    def _managed_block(path: Path, body: str) -> None:
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        block = f"{_START}\n{body.rstrip()}\n{_END}"
        if _START in current and _END in current:
            prefix, remainder = current.split(_START, 1)
            _, suffix = remainder.split(_END, 1)
            updated = prefix.rstrip() + "\n\n" + block + suffix
        else:
            updated = current.rstrip() + "\n\n" + block + "\n"
        atomic_write_text(path, updated)

    def _advance_to(self, requirement_id: str, target: RequirementStatus) -> None:
        requirements = RequirementService(self.root)
        order = (
            RequirementStatus.CAPTURED,
            RequirementStatus.INVESTIGATING,
            RequirementStatus.ANALYZED,
            RequirementStatus.PLANNED,
            RequirementStatus.READY,
            RequirementStatus.IN_PROGRESS,
            RequirementStatus.IMPLEMENTED,
        )
        current = requirements.show(requirement_id)
        if not current.ok:
            return
        status = RequirementStatus(str(current.data["status"]))
        if status not in order or target not in order:
            return
        while order.index(status) < order.index(target):
            next_status = order[order.index(status) + 1]
            transitioned = requirements.transition(requirement_id, next_status)
            if not transitioned.ok:
                break
            status = next_status

    @contextmanager
    def _stage_requirement_documents(
        self, requirement_id: str, project: Project
    ) -> Iterator[None]:
        requirement = self.store.requirement(requirement_id)
        repository = (self.root / project.path).resolve()
        if not requirement or not repository.is_dir():
            yield
            return
        knowledge_root = self.root / str(self.workspace.load()["knowledge_root"])
        directory = RequirementPathPolicy(knowledge_root).locate_requirement_path(
            requirement_id, str(requirement["short_name"])
        )
        try:
            relative = directory.resolve().relative_to(repository)
        except ValueError:
            yield
            return
        status = self._git_output(
            repository,
            ["status", "--porcelain", "--untracked-files=all", "--", relative.as_posix()],
        )
        if not status or any(not line.startswith("?? ") for line in status.splitlines()):
            yield
            return
        staged = self.root / ".praxis" / "fast-lane-staging" / requirement_id
        staged.parent.mkdir(parents=True, exist_ok=True)
        if staged.exists():
            raise FileExistsError(staged)
        shutil.move(str(directory), str(staged))
        try:
            yield
        finally:
            directory.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged), str(directory))
