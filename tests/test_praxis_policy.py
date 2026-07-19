from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def load_policy():
    path = PLUGIN_ROOT / "runtime" / "praxis_core" / "policy.py"
    spec = importlib.util.spec_from_file_location("praxis_core_policy_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quick_policy_selects_l0_without_requirement_docs() -> None:
    policy = load_policy()

    decision = policy.resolve_task_policy(
        mode="quick",
        project_kind="pnpm-web",
        changed_files=["src/components/Label.vue"],
    )

    assert decision.path == "quick"
    assert decision.requires_requirement is False
    assert decision.requires_worktree is True
    assert decision.verification_level == "L0"
    assert decision.quality_review == "waived-small-change"
    assert decision.checks == ("changed-files", "syntax", "focused-contract-test")


def test_quick_policy_uses_manifest_gates() -> None:
    policy = load_policy()

    decision = policy.resolve_task_policy(
        mode="quick",
        project_kind="pnpm-web",
        manifest_task={
            "verification_level": "L0",
            "requires_worktree": True,
            "requires_requirement": False,
            "database_investigation": False,
            "quality_review": False,
            "gates": ["changed-file-boundary", "syntax"],
        },
    )

    assert decision.requires_requirement is False
    assert decision.requires_worktree is True
    assert decision.checks == ("changed-file-boundary", "syntax")


@pytest.mark.parametrize(
    "changed_file",
    [
        "src/main/resources/db/migration/V1__menu.sql",
        "src/reports/DeliveryReport.java",
        "contracts/shared/order.schema.json",
    ],
)
def test_quick_policy_rejects_high_risk_boundaries(changed_file: str) -> None:
    policy = load_policy()

    with pytest.raises(ValueError, match="formal"):
        policy.resolve_task_policy(
            mode="quick",
            project_kind="java-maven",
            changed_files=[changed_file],
        )


def test_manifest_policy_drives_formal_verification_level() -> None:
    policy = load_policy()

    decision = policy.resolve_task_policy(
        mode="formal",
        project_kind="java-maven",
        manifest_task={
            "verification_level": "L2",
            "requires_worktree": True,
            "database_investigation": True,
        },
    )

    assert decision.requires_requirement is True
    assert decision.requires_worktree is True
    assert decision.verification_level == "L2"
    assert decision.database_investigation is True
    assert decision.quality_review == "requires-authorization"


def test_quick_task_state_records_policy_and_worktree(tmp_path: Path) -> None:
    path = PLUGIN_ROOT / "runtime" / "praxis_core" / "quick_task.py"
    spec = importlib.util.spec_from_file_location("praxis_core_quick_task_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    written = module.write_quick_task_state(
        tmp_path,
        task_id="20260719-fix-label",
        project="web",
        task_name="修复标签",
        worktree=tmp_path / ".worktrees/web/20260719-fix-label-dev",
        verification_level="L0",
    )

    text = written.read_text(encoding="utf-8")
    assert written == tmp_path / ".praxis/tasks/20260719-fix-label.toml"
    assert 'mode = "quick"' in text
    assert 'project = "web"' in text
    assert 'verification_level = "L0"' in text


def test_quick_task_state_rejects_path_traversal(tmp_path: Path) -> None:
    path = PLUGIN_ROOT / "runtime" / "praxis_core" / "quick_task.py"
    spec = importlib.util.spec_from_file_location("praxis_core_quick_task_path_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with pytest.raises(ValueError, match="task_id"):
        module.write_quick_task_state(
            tmp_path,
            task_id="../outside",
            project="web",
            task_name="bad",
            worktree=tmp_path / ".worktrees/web/bad-dev",
            verification_level="L0",
        )
