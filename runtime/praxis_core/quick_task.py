from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Sequence


def write_quick_task_state(
    workspace: str | Path,
    *,
    task_id: str,
    project: str,
    task_name: str,
    worktree: str | Path,
    verification_level: str,
    checks: Sequence[str] = (),
) -> Path:
    """Persist the minimum resumable state for a quick code task."""
    if not task_id or Path(task_id).name != task_id or task_id in {".", ".."}:
        raise ValueError("task_id must be one safe path segment")
    root = Path(workspace).expanduser().resolve()
    target = root / ".praxis" / "tasks" / f"{task_id}.toml"
    values = {
        "schema_version": 1,
        "id": task_id,
        "mode": "quick",
        "project": project,
        "task_name": task_name,
        "worktree": str(Path(worktree)),
        "verification_level": verification_level,
        "checks": list(checks),
        "status": "active",
    }
    lines = []
    for key, value in values.items():
        rendered = str(value) if isinstance(value, int) else json.dumps(value, ensure_ascii=False)
        lines.append(f"{key} = {rendered}")
    target.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines) + "\n"
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        os.replace(temp_path, target)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
    return target
