from __future__ import annotations

import tomllib
from typing import Any

from .config import project_config
from .core_runtime import load_praxis_core
from .git_worktree import create_worktree, project_worktree_dir
from .names import branch_today, safe_path_leaf
from .paths import ROOT_DIR
from .workflow_checks import changed_files
from .process import fail

load_praxis_core()

from praxis_core.policy import resolve_task_policy  # noqa: E402
from praxis_core.quick_task import write_quick_task_state  # noqa: E402


def manifest_task(name: str) -> dict[str, Any] | None:
    """Load one unique task policy from installed extension manifests."""
    matches: list[dict[str, Any]] = []
    extension_root = ROOT_DIR / ".praxis" / "extensions"
    if not extension_root.is_dir():
        return None
    for manifest_path in sorted(extension_root.glob("*/manifest.toml")):
        try:
            payload = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            fail(f"invalid extension manifest: {manifest_path}: {exc}")
        task = payload.get("task", {}).get(name)
        if task is not None:
            if not isinstance(task, dict):
                fail(f"manifest task must be a table: {manifest_path}: {name}")
            matches.append(task)
    if len(matches) > 1:
        fail(f"multiple extension manifests define task policy: {name}")
    return matches[0] if matches else None


def start_quick_task(config: dict[str, Any], project: str, task_name: str):
    """Create an isolated L0 code worktree without business requirement docs."""
    project_data = project_config(config, project)
    decision = resolve_task_policy(
        mode="quick",
        project_kind=str(project_data.get("kind") or ""),
        manifest_task=manifest_task("quick"),
    )
    if not decision.requires_worktree:
        fail("quick path is only for code projects; use the docs requirement path for documentation work")

    worktree = create_worktree(
        config,
        project,
        task_name,
        None,
        require_requirement=False,
    )
    task_id = f"{branch_today()}-{safe_path_leaf(task_name)}"
    state_path = write_quick_task_state(
        ROOT_DIR,
        task_id=task_id,
        project=project,
        task_name=task_name,
        worktree=worktree,
        verification_level=decision.verification_level,
        checks=decision.checks,
    )
    print(f"Quick task: {task_id}")
    print(f"Worktree: {worktree}")
    print(f"State: {state_path}")
    print("Boundary: L0 only; database, migration, permission, report, or shared-contract changes must upgrade to formal mode.")
    return worktree


def check_quick_task(config: dict[str, Any], project: str, task_name: str) -> int:
    """Fail closed when an active quick task crosses a formal-work boundary."""
    project_data = project_config(config, project)
    worktree = project_worktree_dir(config, project, task_name)
    files = changed_files(worktree)
    try:
        decision = resolve_task_policy(
            mode="quick",
            project_kind=str(project_data.get("kind") or ""),
            changed_files=files,
            manifest_task=manifest_task("quick"),
        )
    except ValueError as exc:
        fail(str(exc))
    print("Quick task boundary passed.")
    print(f"Worktree: {worktree}")
    print(f"Changed files: {len(files)}")
    print(f"Required checks: {', '.join(decision.checks)}")
    return 0
