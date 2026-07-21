from __future__ import annotations

from pathlib import Path

from praxis.governance.service import ApprovalService, ExecutionBudgetService
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService


def _requirement(root: Path) -> str:
    WorkspaceService(root).init("demo", "演示工作空间")
    return StateStore(root).create_requirement("验证治理", "验证批准与预算", [], [
    ])["requirement_id"]


def test_verification_approval_is_exact_and_user_authorized(tmp_path: Path) -> None:
    requirement_id = _requirement(tmp_path)
    approvals = ApprovalService(tmp_path)

    denied = approvals.grant(
        requirement_id,
        "verification",
        ["pytest", "pytest"],
        user_evidence="",
        authorized_by_user=False,
    )
    granted = approvals.grant(
        requirement_id,
        "verification",
        [" pytest ", "ruff"],
        user_evidence="用户明确批准验证矩阵",
        authorized_by_user=True,
    )

    assert denied.code == "USER_APPROVAL_REQUIRED"
    assert approvals.grant(
        "REQ-MISSING",
        "verification",
        ["pytest"],
        user_evidence="用户批准",
        authorized_by_user=True,
    ).code == "REQUIREMENT_NOT_FOUND"
    assert approvals.grant(
        requirement_id,
        "",
        [],
        user_evidence="用户批准",
        authorized_by_user=True,
    ).code == "APPROVAL_SCOPE_INVALID"
    assert approvals.grant(
        requirement_id,
        "verification",
        ["pytest"],
        user_evidence="用户批准",
        authorized_by_user=True,
        expires_at="not-a-date",
    ).code == "APPROVAL_EXPIRY_INVALID"
    assert granted.ok
    assert granted.data["entries"] == ["pytest", "ruff"]
    assert approvals.check(requirement_id, "verification", "pytest").ok
    assert approvals.check(requirement_id, "verification", "mypy").code == (
        "USER_APPROVAL_REQUIRED"
    )
    assert approvals.list(requirement_id).data["receipts"] == [
        {key: value for key, value in granted.data.items() if key != "audit_id"}
    ]

    expired = approvals.grant(
        requirement_id,
        "verification",
        ["mypy"],
        user_evidence="历史批准",
        authorized_by_user=True,
        expires_at="2020-01-01T00:00:00+00:00",
    )
    assert expired.ok
    assert approvals.check(requirement_id, "verification", "mypy").code == (
        "USER_APPROVAL_REQUIRED"
    )


def test_execution_budget_allows_one_retry_then_stops(tmp_path: Path) -> None:
    requirement_id = _requirement(tmp_path)
    budgets = ExecutionBudgetService(tmp_path)

    first = budgets.consume(requirement_id, "in_progress", "retry", "setup:backend")
    exhausted = budgets.consume(requirement_id, "in_progress", "retry", "setup:backend")

    assert first.ok and first.data["used"] == 1
    assert budgets.consume(requirement_id, "in_progress", "unknown", "x").code == (
        "EXECUTION_BUDGET_KIND_INVALID"
    )
    assert budgets.consume("REQ-MISSING", "in_progress", "retry", "x").code == (
        "REQUIREMENT_NOT_FOUND"
    )
    assert exhausted.code == "EXECUTION_BUDGET_EXHAUSTED"
    assert budgets.status(requirement_id, "in_progress").data["budgets"][0]["limit"] == 1
