from __future__ import annotations

import json
import re
import shlex
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from praxis.result import Result
from praxis.workspace.service import WorkspaceService

Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


class WorktreeService:
    def __init__(self, root: Path | str, *, run: Runner | None = None):
        self.root = Path(root)
        self.run = run or self._run

    @staticmethod
    def _run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)

    def _execute(self, arguments: Sequence[str]) -> Result:
        command = ["wt", *arguments, "--format=json"]
        try:
            process = self.run(command, self.root)
        except FileNotFoundError:
            return Result(False, "WORKTRUNK_NOT_AVAILABLE")
        if process.returncode:
            return Result(False, "WORKTRUNK_FAILED", data={"stderr": process.stderr.strip()})
        try:
            data: dict[str, Any] = json.loads(process.stdout)
        except json.JSONDecodeError:
            return Result(False, "WORKTRUNK_OUTPUT_INVALID")
        return Result(True, data=data)

    def create(self, branch: str, base: str) -> Result:
        return self._execute(["switch", "--create", branch, "--base", base, "--no-cd"])

    def list(self) -> Result:
        return self._execute(["list"])

    def remove(self, branch: str) -> Result:
        return self._execute(["remove", branch])

    def merge(self, target: str) -> Result:
        return self._execute(["merge", target])

    def install_hooks(self, project_id: str) -> Result:
        project = WorkspaceService(self.root).project(project_id)
        repo = (self.root / project.path).resolve()
        config = repo / ".config" / "wt.toml"
        existing = config.read_text(encoding="utf-8") if config.exists() else ""
        keys = "post-start|pre-merge|post-merge|post-remove"
        if re.search(rf"(?m)^\s*(?:{keys})\s*=", existing):
            return Result(False, "WORKTRUNK_HOOK_CONFLICT", data={"path": str(config)})
        root = shlex.quote(str(self.root.resolve()))
        project_arg = shlex.quote(project_id)

        def command(event: str, extra: str = "", path_variable: str = "worktree_path") -> str:
            return (
                f"praxis --root {root} hook {event} --project {project_arg} "
                f"--worktree {{{{ {path_variable} }}}}{extra} --json"
            )

        hooks = {
            "post-start": command("post-start", " --initialize"),
            "pre-merge": command("pre-merge"),
            "post-merge": command("post-merge", path_variable="cwd"),
            "post-remove": command("post-remove"),
        }
        block = "\n# Praxis V2 managed CodeGraph lifecycle\n" + "\n".join(
            f"{key} = {json.dumps(value)}" for key, value in hooks.items()
        )
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(existing.rstrip() + block + "\n", encoding="utf-8")
        return Result(True, data={"path": str(config), "hooks": list(hooks)})
