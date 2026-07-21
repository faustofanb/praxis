from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from praxis.result import Result
from praxis.storage.sqlite import StateStore

_BUDGET_LIMITS = {"evidence": 6, "recovery": 1, "retry": 1}


class ApprovalService:
    def __init__(self, root: Path | str):
        self.store = StateStore(root)

    def grant(
        self,
        requirement_id: str,
        scope: str,
        entries: list[str],
        *,
        user_evidence: str,
        authorized_by_user: bool,
        expires_at: str = "",
    ) -> Result:
        if not self.store.requirement(requirement_id):
            return Result(False, "REQUIREMENT_NOT_FOUND")
        normalized = list(dict.fromkeys(item.strip() for item in entries if item.strip()))
        if not scope.strip() or not normalized:
            return Result(False, "APPROVAL_SCOPE_INVALID")
        if not authorized_by_user or not user_evidence.strip():
            return Result(False, "USER_APPROVAL_REQUIRED")
        if expires_at:
            try:
                expiry = datetime.fromisoformat(expires_at)
            except ValueError:
                return Result(False, "APPROVAL_EXPIRY_INVALID")
            if expiry.tzinfo is None:
                return Result(False, "APPROVAL_EXPIRY_INVALID")
        timestamp = datetime.now(UTC)
        receipt_id = f"APR-{timestamp:%Y%m%dT%H%M%S}-{uuid4().hex[:8].upper()}"
        receipt = {
            "receipt_id": receipt_id,
            "requirement_id": requirement_id,
            "scope": scope.strip(),
            "entries": normalized,
            "user_evidence": user_evidence.strip(),
            "authorized_by_user": True,
            "created_at": timestamp.isoformat(),
            "expires_at": expires_at,
            "status": "active",
        }
        self.store.set("approval_receipt", receipt_id, receipt)
        audit_id = self.store.audit("approval.granted", "OK", receipt)
        return Result(True, "APPROVAL_GRANTED", data={**receipt, "audit_id": audit_id})

    def check(self, requirement_id: str, scope: str, entry: str) -> Result:
        now = datetime.now(UTC)
        matched = []
        for receipt in self.store.list_scope("approval_receipt"):
            if (
                receipt.get("requirement_id") != requirement_id
                or receipt.get("scope") != scope
                or receipt.get("status") != "active"
                or entry not in receipt.get("entries", [])
            ):
                continue
            expires_at = str(receipt.get("expires_at", ""))
            if expires_at and datetime.fromisoformat(expires_at) < now:
                continue
            matched.append(receipt)
        return Result(
            bool(matched),
            "APPROVAL_MATCHED" if matched else "USER_APPROVAL_REQUIRED",
            data={"receipts": matched, "scope": scope, "entry": entry},
        )

    def list(self, requirement_id: str = "") -> Result:
        receipts = self.store.list_scope("approval_receipt")
        if requirement_id:
            receipts = [
                item for item in receipts if item.get("requirement_id") == requirement_id
            ]
        return Result(True, data={"receipts": receipts})


class ExecutionBudgetService:
    def __init__(self, root: Path | str):
        self.store = StateStore(root)

    def consume(
        self,
        requirement_id: str,
        node: str,
        kind: str,
        operation_key: str,
    ) -> Result:
        if kind not in _BUDGET_LIMITS:
            return Result(False, "EXECUTION_BUDGET_KIND_INVALID")
        if not self.store.requirement(requirement_id):
            return Result(False, "REQUIREMENT_NOT_FOUND")
        key = f"{requirement_id}:{node}:{kind}:{operation_key}"
        record = self.store.get("execution_budget", key) or {
            "requirement_id": requirement_id,
            "node": node,
            "kind": kind,
            "operation_key": operation_key,
            "used": 0,
            "limit": _BUDGET_LIMITS[kind],
        }
        if int(record["used"]) >= int(record["limit"]):
            audit_id = self.store.audit("execution.budget_exhausted", "EXECUTION_BUDGET_EXHAUSTED", record)
            return Result(False, "EXECUTION_BUDGET_EXHAUSTED", data={**record, "audit_id": audit_id})
        record.update(
            used=int(record["used"]) + 1,
            updated_at=datetime.now(UTC).isoformat(),
        )
        self.store.set("execution_budget", key, record)
        audit_id = self.store.audit("execution.budget_consumed", "OK", record)
        return Result(True, "EXECUTION_BUDGET_CONSUMED", data={**record, "audit_id": audit_id})

    def status(self, requirement_id: str, node: str = "") -> Result:
        records = [
            item
            for item in self.store.list_scope("execution_budget")
            if item.get("requirement_id") == requirement_id
            and (not node or item.get("node") == node)
        ]
        return Result(True, data={"budgets": records, "defaults": _BUDGET_LIMITS})
