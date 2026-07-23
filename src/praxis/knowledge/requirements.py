from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from praxis.documents.requirements import RequirementProjector
from praxis.domain.requirement import RequirementStatus
from praxis.naming.requirement import RequirementPathPolicy
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService


class RequirementService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.store = StateStore(self.root)

    def create(
        self,
        short_name: str,
        request: str,
        systems: list[str],
        domains: list[str],
        *,
        now: datetime | None = None,
    ) -> Result:
        workspace = WorkspaceService(self.root).load()
        knowledge_root = self.root / workspace.get(
            "knowledge_root", workspace.get("vault", "知识库")
        )
        normalized = RequirementPathPolicy(knowledge_root).validate_short_name(short_name)
        if not request.strip():
            raise ValueError("原始需求不能为空")
        registered_systems = {item["id"]: item for item in workspace.get("systems", [])}
        unknown_systems = sorted(set(systems) - registered_systems.keys())
        if unknown_systems:
            raise ValueError(f"未登记的业务系统：{', '.join(unknown_systems)}")
        registered_domains = {
            domain for system in systems for domain in registered_systems[system].get("domains", [])
        }
        unknown_domains = sorted(set(domains) - registered_domains)
        record = self.store.create_requirement(
            normalized,
            request.rstrip(),
            systems,
            domains,
            now=now,
        )
        self.repair_projections()
        path = RequirementPathPolicy(knowledge_root).requirement_path(
            record["requirement_id"], record["short_name"]
        )
        return Result(
            True,
            data={"requirement_id": record["requirement_id"], "path": str(path)},
            diagnostics=tuple(
                {
                    "code": "BUSINESS_DOMAIN_UNKNOWN",
                    "message": f"业务域尚未登记：{domain}",
                }
                for domain in unknown_domains
            ),
        )

    def transition(self, requirement_id: str, target: RequirementStatus) -> Result:
        current = self.store.requirement(requirement_id)
        if not current:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        if target == RequirementStatus.READY:
            ready = self._ready_gate(current)
            if not ready.ok:
                return ready
        if target == RequirementStatus.COMPLETED:
            complete = self._completion_gate(current)
            if not complete.ok:
                return complete
        record = self.store.transition_requirement(requirement_id, target)
        self.repair_projections()
        return Result(True, data={"requirement_id": requirement_id, "status": record["status"]})

    def reopen(self, requirement_id: str, reason: str) -> Result:
        if not reason.strip():
            return Result(False, "REQUIREMENT_REOPEN_REASON_REQUIRED")
        current = self.store.requirement(requirement_id)
        if not current:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        if current["status"] != RequirementStatus.VERIFYING:
            return Result(
                False,
                "REQUIREMENT_REOPEN_STATUS_INVALID",
                data={"status": current["status"]},
            )
        record = self.store.reopen_requirement(requirement_id, reason.strip())
        self.repair_projections()
        return Result(
            True,
            "REQUIREMENT_REOPENED",
            data={
                "requirement_id": requirement_id,
                "status": record["status"],
                "reason": reason.strip(),
            },
        )

    def _ready_gate(self, record: dict[str, Any]) -> Result:
        workspace = WorkspaceService(self.root).load()
        systems = {item["id"]: item for item in workspace.get("systems", [])}
        registered_domains = {
            domain
            for system_id in record["systems"]
            for domain in systems.get(system_id, {}).get("domains", [])
        }
        unknown_domains = sorted(set(record["domains"]) - registered_domains)
        requirement_root = self._path(workspace, record)
        missing_documents = [
            name
            for name in ("调查分析.md", "实施计划.md")
            if not _has_meaningful_content(requirement_root / name)
        ]
        ok = not unknown_domains and not missing_documents
        return Result(
            ok,
            "OK" if ok else "REQUIREMENT_NOT_READY",
            data={
                "unknown_domains": unknown_domains,
                "missing_documents": missing_documents,
            },
        )

    def _completion_gate(self, record: dict[str, Any]) -> Result:
        from praxis.artifacts.service import ArtifactService

        workspace = WorkspaceService(self.root).load()
        acceptance = self._path(workspace, record) / "验收结论.md"
        artifacts = [
            item
            for item in self.store.list_scope("artifact")
            if item["requirement_id"] == record["requirement_id"]
        ]
        missing = []
        if not _has_meaningful_content(acceptance):
            missing.append("验收结论.md")
        if not artifacts:
            missing.append("产出物")
        elif any(
            not ArtifactService(self.root).verify(item["artifact_id"]).ok for item in artifacts
        ):
            missing.append("产出物完整性")
        return Result(
            not missing,
            "OK" if not missing else "REQUIREMENT_ACCEPTANCE_INCOMPLETE",
            data={"missing": missing},
        )

    def _path(self, workspace: dict[str, Any], record: dict[str, Any]) -> Path:
        return RequirementPathPolicy(self.root / str(workspace["knowledge_root"])).requirement_path(
            str(record["requirement_id"]), str(record["short_name"])
        )

    def show(self, requirement_id: str) -> Result:
        record = self.store.requirement(requirement_id)
        return Result(
            bool(record),
            "OK" if record else "REQUIREMENT_NOT_FOUND",
            data=self._enriched_record(record) if record else {},
        )

    def add_constraint(
        self,
        requirement_id: str,
        statement: str,
        *,
        supersedes: list[str] | None = None,
        source: str = "",
    ) -> Result:
        requirement = self.store.requirement(requirement_id)
        if not requirement:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        if not statement.strip():
            return Result(False, "REQUIREMENT_CONSTRAINT_EMPTY")
        requested = list(dict.fromkeys(supersedes or []))
        records = {
            item["constraint_id"]: item
            for item in self.store.list_scope("requirement_constraint")
        }
        invalid = [
            constraint_id
            for constraint_id in requested
            if constraint_id not in records
            or records[constraint_id].get("requirement_id") != requirement_id
            or records[constraint_id].get("status") != "active"
        ]
        if invalid:
            return Result(
                False,
                "REQUIREMENT_CONSTRAINT_SUPERSEDES_INVALID",
                data={"invalid": invalid},
            )
        timestamp = datetime.now(UTC)
        constraint_id = f"CON-{timestamp:%Y%m%dT%H%M%S}-{uuid4().hex[:8].upper()}"
        constraint = {
            "constraint_id": constraint_id,
            "requirement_id": requirement_id,
            "statement": statement.strip(),
            "source": source.strip(),
            "status": "active",
            "supersedes": requested,
            "superseded_by": "",
            "created_at": timestamp.isoformat(),
        }
        updates = [("requirement_constraint", constraint_id, constraint)]
        for replaced_id in requested:
            replaced = {**records[replaced_id]}
            replaced.update(status="superseded", superseded_by=constraint_id)
            updates.append(("requirement_constraint", replaced_id, replaced))
        self.store.set_many(updates)
        self.store.audit("requirement.constraint_added", "OK", constraint)
        self.project_current(requirement_id)
        return Result(True, "REQUIREMENT_CONSTRAINT_ADDED", data=constraint)

    def list_constraints(self, requirement_id: str) -> Result:
        if not self.store.requirement(requirement_id):
            return Result(False, "REQUIREMENT_NOT_FOUND")
        historical = sorted(
            (
                item
                for item in self.store.list_scope("requirement_constraint")
                if item.get("requirement_id") == requirement_id
            ),
            key=lambda item: (item.get("created_at", ""), item["constraint_id"]),
        )
        return Result(
            True,
            data={
                "active": [item for item in historical if item.get("status") == "active"],
                "historical": historical,
            },
        )

    def record_implementation(
        self,
        requirement_id: str,
        project_id: str,
        *,
        artifact_ids: list[str] | None = None,
    ) -> Result:
        if not self.store.requirement(requirement_id):
            return Result(False, "REQUIREMENT_NOT_FOUND")
        if not project_id.strip():
            return Result(False, "REQUIREMENT_PROJECT_REQUIRED")
        delivery = self._delivery(requirement_id)
        delivery["implementation"][project_id] = {
            "status": "implemented",
            "artifact_ids": list(dict.fromkeys(artifact_ids or [])),
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        self.store.set("requirement_delivery", requirement_id, delivery)
        self.store.audit(
            "requirement.implementation_recorded",
            "OK",
            {"requirement_id": requirement_id, "project_id": project_id},
        )
        self.project_current(requirement_id)
        return Result(
            True,
            "REQUIREMENT_IMPLEMENTATION_RECORDED",
            data=self._delivery_summary(delivery),
        )

    def delivery(self, requirement_id: str) -> Result:
        if not self.store.requirement(requirement_id):
            return Result(False, "REQUIREMENT_NOT_FOUND")
        return Result(True, data=self._delivery_summary(self._delivery(requirement_id)))

    def project_current(self, requirement_id: str) -> None:
        record = self.store.requirement(requirement_id)
        if not record:
            raise KeyError(requirement_id)
        workspace = WorkspaceService(self.root).load()
        RequirementProjector(self.root / workspace["knowledge_root"]).project(
            self._enriched_record(record)
        )

    def _delivery(self, requirement_id: str) -> dict[str, Any]:
        return self.store.get("requirement_delivery", requirement_id) or {
            "requirement_id": requirement_id,
            "implementation": {},
            "verification": {},
            "manual_acceptance_status": "awaiting_manual_acceptance",
        }

    @staticmethod
    def _delivery_summary(delivery: dict[str, Any]) -> dict[str, Any]:
        implementations = delivery.get("implementation", {})
        verification = delivery.get("verification", {})
        return {
            **delivery,
            "implementation_status": (
                "implemented"
                if implementations
                and all(item.get("status") == "implemented" for item in implementations.values())
                else "not_recorded"
            ),
            "verification_status": (
                "verification_not_authorized"
                if any(
                    item.get("status") in {"declined", "not_authorized"}
                    for item in verification.values()
                )
                else "not_recorded"
            ),
            "manual_acceptance_status": delivery.get(
                "manual_acceptance_status", "awaiting_manual_acceptance"
            ),
        }

    def _enriched_record(self, record: dict[str, Any]) -> dict[str, Any]:
        constraints = self.list_constraints(record["requirement_id"]).data
        return {
            **record,
            "constraints": constraints,
            "delivery": self._delivery_summary(self._delivery(record["requirement_id"])),
        }

    def progress(self, requirement_id: str, message: str) -> Result:
        record = self.store.requirement(requirement_id)
        if not record:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        if not message.strip():
            return Result(False, "REQUIREMENT_PROGRESS_EMPTY")
        workspace = WorkspaceService(self.root).load()
        path = self._path(workspace, record) / "执行进度.md"
        timestamp = datetime.now().astimezone().isoformat()
        with path.open("a", encoding="utf-8") as progress:
            progress.write(f"\n- {timestamp}：{message.strip()}\n")
        audit_id = self.store.audit(
            "requirement.progress",
            "OK",
            {"requirement_id": requirement_id, "message": message.strip()},
        )
        return Result(True, data={"requirement_id": requirement_id, "audit_id": audit_id})

    def rename(self, requirement_id: str, short_name: str) -> Result:
        record = self.store.requirement(requirement_id)
        if not record:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        workspace = WorkspaceService(self.root).load()
        policy = RequirementPathPolicy(self.root / workspace["knowledge_root"])
        normalized = policy.validate_short_name(short_name)
        old_path = policy.requirement_path(requirement_id, record["short_name"])
        new_path = policy.requirement_path(requirement_id, normalized)
        if new_path.exists():
            return Result(False, "REQUIREMENT_PATH_EXISTS", data={"path": str(new_path)})
        old_path.rename(new_path)
        try:
            self.store.rename_requirement(requirement_id, normalized)
        except BaseException:
            new_path.rename(old_path)
            raise
        self.repair_projections()
        return Result(
            True,
            data={
                "requirement_id": requirement_id,
                "short_name": normalized,
                "path": str(new_path),
            },
        )

    def repair_projections(self) -> Result:
        workspace = WorkspaceService(self.root).load()
        knowledge_root = self.root / workspace.get(
            "knowledge_root", workspace.get("vault", "知识库")
        )
        projector = RequirementProjector(knowledge_root)
        processed = 0
        for item in self.store.pending_outbox():
            if item["topic"] != "requirement.project":
                continue
            projector.project(self._enriched_record(item["payload"]))
            self.store.mark_outbox_processed(item["id"])
            processed += 1
        return Result(True, data={"processed": processed})


def _has_meaningful_content(path: Path) -> bool:
    if not path.is_file():
        return False
    return any(
        line.strip()
        and not line.lstrip().startswith(("#", "---"))
        and line.strip() not in {"暂无。", "待调查。"}
        for line in path.read_text(encoding="utf-8").splitlines()
    )
