from __future__ import annotations

from pathlib import Path
from typing import Any

from praxis.codegraph.hooks import CodeGraphHooks
from praxis.gates.policies import allowed_paths_gate, secret_gate
from praxis.integrations.process import ProcessRunner
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService
from praxis.worktree.service import resolve_worktree_binding


class WorktreeLifecycle:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.store = StateStore(self.root)

    def run(self, event: str, context: dict[str, Any]) -> Result:
        branch = str(context.get("branch", ""))
        resolved = resolve_worktree_binding(
            self.store,
            branch,
            worktree_path=context.get("worktree_path"),
        )
        if not resolved:
            return Result(False, "WORKTREE_BINDING_NOT_FOUND", data={"branch": branch})
        binding_key, binding = resolved
        if event == "worktree-pre-start":
            return self._pre_start(binding, context)

        project_id = binding["repository_id"]
        worktree = context.get("worktree_path")
        if not worktree:
            return Result(False, "LIFECYCLE_CONTEXT_INVALID", data={"field": "worktree_path"})
        graph_event = {
            "worktree-post-start": "post-start",
            "pre-commit": "change-preflight",
            "pre-merge": "pre-merge",
            "post-merge": "post-merge",
            "post-remove": "post-remove",
        }.get(event)
        if not graph_event:
            return Result(False, "LIFECYCLE_EVENT_NOT_FOUND", data={"event": event})
        result = CodeGraphHooks(self.root).run(
            graph_event,
            project_id,
            worktree=worktree,
            initialize=event == "worktree-post-start",
        )
        if result.ok and event in {"pre-commit", "pre-merge"}:
            result = self._change_gates(binding, Path(str(worktree)))
        if result.ok and event in {"pre-commit", "pre-merge"}:
            check_kind = "quality" if event == "pre-commit" else "test"
            self.store.audit(
                f"{check_kind}.execution_skipped",
                "USER_APPROVAL_REQUIRED",
                {
                    "branch": branch,
                    "repository_id": project_id,
                    "source": "worktree_hook",
                },
            )
        if result.ok and event == "post-remove":
            self.store.delete("worktree", binding_key)
        return result

    def _pre_start(self, binding: dict[str, Any], context: dict[str, Any]) -> Result:
        requirement = self.store.requirement(binding["requirement_id"])
        if not requirement or requirement["status"] not in {"ready", "in_progress"}:
            return Result(False, "REQUIREMENT_NOT_READY")
        project = WorkspaceService(self.root).project(binding["repository_id"])
        expected_repo = (self.root / project.path).resolve()
        expected_worktree = Path(
            binding.get("repository_path", binding["path"])
        ).resolve()
        actual_repo = Path(str(context.get("repo_path", ""))).resolve()
        actual_worktree = Path(str(context.get("worktree_path", ""))).resolve()
        if actual_repo != expected_repo or actual_worktree != expected_worktree:
            return Result(
                False,
                "WORKTREE_BINDING_MISMATCH",
                data={
                    "expected_repo": str(expected_repo),
                    "actual_repo": str(actual_repo),
                    "expected_worktree": str(expected_worktree),
                    "actual_worktree": str(actual_worktree),
                },
            )
        return Result(True, data=binding)

    def _change_gates(self, binding: dict[str, Any], worktree: Path) -> Result:
        runner = ProcessRunner(worktree, audit_root=self.root)
        changed: set[str] = set()
        for command in (
            ["git", "diff", "--name-only", "HEAD"],
            ["git", "ls-files", "--others", "--exclude-standard"],
        ):
            result = runner.run(command, machine_output=True)
            if not result.ok:
                return Result(False, "CHANGED_FILES_UNAVAILABLE", data=result.data)
            changed.update(result.data["stdout"].splitlines())
        paths = sorted(changed)
        result = allowed_paths_gate(
            paths,
            binding.get("allowed_paths", ()),
            binding.get("forbidden_paths", ()),
        )
        if not result.ok:
            return result
        root = worktree.resolve()
        files = {}
        for name in paths:
            path = (root / name).resolve()
            if not path.is_relative_to(root):
                return Result(False, "GATE_PATH_OUT_OF_SCOPE", data={"blocked_paths": [name]})
            if path.is_file():
                files[name] = path.read_text(encoding="utf-8", errors="ignore")
        return secret_gate(files)
