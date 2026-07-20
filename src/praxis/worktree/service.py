from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService

Runner = Callable[[list[str], Path, dict[str, str] | None], subprocess.CompletedProcess[str]]

_STAGES = {
    "analysis": (1, "需求分析"),
    "backend": (2, "后端开发"),
    "frontend": (3, "前端开发"),
    "database": (4, "数据库开发"),
    "integration-test": (5, "联合测试"),
    "review": (6, "代码审查"),
    "release": (7, "发布验证"),
}


class WorktreeService:
    def __init__(self, root: Path | str, *, run: Runner | None = None):
        self.root = Path(root)
        self.run = run or self._run

    @staticmethod
    def _run(
        command: Sequence[str], cwd: Path, environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=cwd,
            env={**os.environ, **(environment or {})},
            check=False,
            capture_output=True,
            text=True,
        )

    def _execute(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
    ) -> Result:
        command = ["wt", *arguments, "--format=json", "--yes"]
        try:
            process = self.run(command, cwd or self.root, environment)
        except FileNotFoundError:
            return Result(False, "WORKTRUNK_NOT_AVAILABLE")
        if process.returncode:
            return Result(False, "WORKTRUNK_FAILED", data={"stderr": process.stderr.strip()})
        try:
            payload: Any = json.loads(process.stdout)
        except json.JSONDecodeError:
            return Result(False, "WORKTRUNK_OUTPUT_INVALID")
        data = payload if isinstance(payload, dict) else {"items": payload}
        return Result(True, data=data)

    def create(self, branch: str, base: str) -> Result:
        return self._execute(["switch", "--create", branch, "--base", base, "--no-cd"])

    def create_for_requirement(
        self,
        requirement_id: str,
        repository_id: str,
        stage: str,
    ) -> Result:
        if stage not in _STAGES:
            raise ValueError(f"未知任务阶段：{stage}")
        workspace = WorkspaceService(self.root)
        project = workspace.project(repository_id)
        requirement = StateStore(self.root).requirement(requirement_id)
        if not requirement:
            raise KeyError(requirement_id)
        if requirement["status"] not in {"ready", "in_progress"}:
            return Result(False, "REQUIREMENT_NOT_READY", data={"status": requirement["status"]})
        if project.system_id not in requirement["systems"]:
            return Result(False, "WORKTREE_SYSTEM_MISMATCH")
        number, stage_name = _STAGES[stage]
        branch = f"req/{requirement_id}/{number:02d}-{stage}"
        destination = (
            self.root
            / ".worktrees"
            / f"{requirement['short_name']}__{requirement_id}"
            / f"{number:02d}-{stage_name}"
            / repository_id
        ).resolve()
        repo = (self.root / project.path).resolve()
        binding = {
            "group_id": f"WTG-{requirement_id}",
            "requirement_id": requirement_id,
            "repository_id": repository_id,
            "stage": stage,
            "branch": branch,
            "path": str(destination),
            "status": "creating",
            # ponytail: whole-repo scope until requirement stages persist explicit path scopes.
            "allowed_paths": ["**"],
            "forbidden_paths": [".git", ".praxis", ".env", "**/.env"],
        }
        store = StateStore(self.root)
        store.set("worktree", branch, binding)
        result = self._execute(
            ["switch", "--create", branch, "--base", project.default_branch, "--no-cd"],
            cwd=repo,
            environment={"WORKTRUNK_WORKTREE_PATH": str(destination)},
        )
        if not result.ok:
            store.delete("worktree", branch)
            store.audit("worktree.create_failed", result.code, binding)
            return result
        binding["status"] = "active"
        store.set("worktree", branch, binding)
        store.audit("worktree.created", "OK", binding)
        return Result(True, data=binding)

    def list(self) -> Result:
        if not (self.root / "praxis.toml").is_file():
            return self._execute(["list"])
        items = []
        for raw in WorkspaceService(self.root).load().get("projects", []):
            result = self._execute(["list"], cwd=(self.root / raw["path"]).resolve())
            if not result.ok:
                return result
            listed = result.data.get("items", result.data.get("worktrees", []))
            items.extend({**item, "repository_id": raw["id"]} for item in listed)
        return Result(True, data={"items": items})

    def remove(self, branch: str) -> Result:
        binding = StateStore(self.root).get("worktree", branch)
        cwd = self.root
        if binding:
            project = WorkspaceService(self.root).project(binding["repository_id"])
            cwd = (self.root / project.path).resolve()
        result = self._execute(["remove", branch], cwd=cwd)
        if result.ok and binding:
            store = StateStore(self.root)
            store.delete("worktree", branch)
            store.audit("worktree.removed", "OK", binding)
        return result

    def merge(self, target: str, *, branch: str | None = None) -> Result:
        binding = StateStore(self.root).get("worktree", branch) if branch else None
        cwd = Path(binding["path"]) if binding else self.root
        result = self._execute(["merge", target], cwd=cwd)
        if result.ok and binding:
            store = StateStore(self.root)
            current = store.get("worktree", str(branch))
            if current:
                current["status"] = "merged"
                store.set("worktree", str(branch), current)
            store.audit("worktree.merged", "OK", {**binding, "target": target})
        return result

    def install_hooks(self, project_id: str) -> Result:
        project = WorkspaceService(self.root).project(project_id)
        repo = (self.root / project.path).resolve()
        config = repo / ".config" / "wt.toml"
        existing = config.read_text(encoding="utf-8") if config.exists() else ""
        keys = "pre-start|post-start|pre-commit|pre-merge|post-merge|post-remove"
        if re.search(rf"(?m)^\s*(?:(?:{keys})\s*=|\[\[?(?:{keys})\]{{1,2}})", existing):
            return Result(False, "WORKTRUNK_HOOK_CONFLICT", data={"path": str(config)})
        root = shlex.quote(str(self.root.resolve()))

        def command(event: str) -> str:
            return f"praxis --root {root} lifecycle {event} --stdin-json"

        hooks = {
            "pre-start": command("worktree-pre-start"),
            "post-start": command("worktree-post-start"),
            "pre-commit": command("pre-commit"),
            "pre-merge": command("pre-merge"),
            "post-merge": command("post-merge"),
            "post-remove": command("post-remove"),
        }
        block = "\n# Praxis V3 managed CodeGraph lifecycle\n" + "\n".join(
            f"{key} = {json.dumps(value)}" for key, value in hooks.items()
        )
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(existing.rstrip() + block + "\n", encoding="utf-8")
        return Result(True, data={"path": str(config), "hooks": list(hooks)})
