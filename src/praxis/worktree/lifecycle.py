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

_BUSINESS_CODE_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".cpp",
        ".cs",
        ".go",
        ".groovy",
        ".h",
        ".java",
        ".js",
        ".jsx",
        ".json",
        ".kt",
        ".kts",
        ".php",
        ".py",
        ".pyi",
        ".rb",
        ".rs",
        ".scala",
        ".sql",
        ".svelte",
        ".ts",
        ".tsx",
        ".vue",
        ".xml",
        ".yaml",
        ".yml",
    }
)


class WorktreeLifecycle:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.store = StateStore(self.root)

    def run(self, event: str, context: dict[str, Any]) -> Result:
        branch = str(context.get("branch", ""))
        root_guard = self._root_business_change_guard(event, context, branch)
        if root_guard is not None:
            return root_guard
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
        if event == "worktree-post-start":
            from praxis.codegraph.service import CodeGraphService

            return CodeGraphService(
                self.root,
                project_id,
                repo=worktree,
            ).enqueue(binding_id=binding_key)
        graph_event = {
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
            initialize=False,
        )
        graph_fallback = not result.ok and result.data.get("fallback") == "rg"
        if graph_fallback and event in {"pre-commit", "pre-merge"}:
            fallback = self._change_gates(binding, Path(str(worktree)))
            if fallback.ok:
                result = Result(
                    True,
                    "CODEGRAPH_FALLBACK_RG",
                    data={**result.data, "codegraph_code": result.code},
                    diagnostics=result.diagnostics,
                )
            else:
                result = fallback
        if (
            result.ok
            and event in {"pre-commit", "pre-merge"}
            and not graph_fallback
        ):
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

    def _root_business_change_guard(
        self, event: str, context: dict[str, Any], branch: str
    ) -> Result | None:
        if event not in {"pre-commit", "pre-merge"}:
            return None
        candidate_value = context.get("worktree_path") or context.get("repo_path")
        if not candidate_value:
            return None
        candidate = Path(str(candidate_value)).resolve()
        try:
            workspace = WorkspaceService(self.root).load()
        except (KeyError, OSError, ValueError):
            return None
        project_roots = {
            (self.root / str(project.get("path", ""))).resolve()
            for project in workspace.get("projects", [])
            if project.get("path")
        }
        if candidate not in project_roots:
            return None
        if resolve_worktree_binding(self.store, branch, worktree_path=candidate):
            return None
        runner = ProcessRunner(candidate, audit_root=self.root)
        changed: set[str] = set()
        for command in (
            ["git", "diff", "--name-only", "HEAD"],
            ["git", "ls-files", "--others", "--exclude-standard"],
        ):
            result = runner.run(command, machine_output=True)
            if not result.ok:
                return Result(False, "CHANGED_FILES_UNAVAILABLE", data=result.data)
            changed.update(str(result.data.get("stdout", "")).splitlines())
        blocked = sorted(
            path
            for path in changed
            if Path(path).suffix.lower() in _BUSINESS_CODE_SUFFIXES
        )
        if not blocked:
            return None
        return Result(
            False,
            "WORKTREE_BINDING_REQUIRED",
            data={
                "message": "主仓库检测到业务代码改动，请走 praxis 工作树",
                "blocked_paths": blocked,
                "worktree_path": str(candidate),
            },
        )

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
