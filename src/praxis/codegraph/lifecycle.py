from __future__ import annotations

from typing import Protocol

from praxis.result import Result


class GraphOperations(Protocol):
    def ensure_fresh(self, *, initialize: bool = False) -> Result: ...

    def sync(self) -> Result: ...

    def affected(self) -> Result: ...

    def remove_metadata(self) -> Result: ...


class CodeGraphLifecycle:
    def __init__(self, graph: GraphOperations):
        self.graph = graph

    def post_start(self) -> Result:
        return self.graph.ensure_fresh(initialize=True)

    def task_context(self, *, graph_required: bool) -> Result:
        freshness = self.graph.ensure_fresh()
        if freshness.ok or graph_required:
            return freshness
        return Result(
            True,
            "CODEGRAPH_RG_FALLBACK",
            diagnostics=(
                {
                    "code": "CODEGRAPH_RG_FALLBACK",
                    "message": "CodeGraph unavailable; use rg without reading the stale graph.",
                },
            ),
        )

    def change_preflight(self) -> Result:
        return self.graph.ensure_fresh()

    def verify(self) -> Result:
        return self.graph.ensure_fresh()

    def pre_merge(self) -> Result:
        sync = self.graph.sync()
        return self.graph.affected() if sync.ok else sync

    def post_merge(self) -> Result:
        return self.graph.sync()

    def post_remove(self) -> Result:
        return self.graph.remove_metadata()
