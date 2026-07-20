from __future__ import annotations

from pathlib import Path

from praxis.codegraph.lifecycle import CodeGraphLifecycle
from praxis.codegraph.service import CodeGraphService
from praxis.result import Result


class CodeGraphHooks:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def run(
        self,
        event: str,
        project_id: str,
        *,
        worktree: Path | str | None = None,
        initialize: bool = False,
        graph_required: bool = True,
    ) -> Result:
        graph = CodeGraphService(self.root, project_id, repo=worktree)
        lifecycle = CodeGraphLifecycle(graph)
        if event == "post-start":
            return graph.ensure_fresh(initialize=initialize)
        if event == "task-context":
            return lifecycle.task_context(graph_required=graph_required)
        if event == "change-preflight":
            return lifecycle.change_preflight()
        if event == "verify":
            return lifecycle.verify()
        if event == "pre-merge":
            return lifecycle.pre_merge()
        if event == "post-merge":
            return lifecycle.post_merge()
        if event == "post-remove":
            return lifecycle.post_remove()
        return Result(False, "HOOK_NOT_FOUND", data={"event": event})
