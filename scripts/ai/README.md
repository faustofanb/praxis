# Praxis AI Development Controller

The control plane commands are exposed through mise (spec: `docs/06-ai-development-control-plane.md` §5):

```text
mise run ai:status   show current machine-readable project state
mise run ai:brief    build bounded task context for the coding AI
mise run ai:plan -- .praxis/tasks/<id>.yaml   validate a Task Contract and transition to PLAN_READY
mise run ai:guard    check diff scope, architecture boundaries and dependency rules
mise run ai:verify   derive required gates from the real diff and execute them
mise run ai:accept   evaluate task acceptance evidence (machine or human boundary)
mise run ai:handoff  persist a stable cross-session handoff
```

`praxis-dev.ts` is the repo-local development controller. It validates Task
Contracts against `.praxis/schemas/task.schema.json`, enforces scope via
`git status` against the active contract's `allowed_paths`/`forbidden_paths`,
checks workspace dependency direction against `.praxis/architecture.yaml`,
derives required quality gates from `.praxis/quality-gates.yaml` and the real
diff, runs them, and drives the DevState machine in `.praxis/state.yaml`.
Behavior is covered by `tests/praxis-dev.test.ts`.

`check-architecture.ts` enforces `.praxis/architecture.yaml` (import graph and
package manifests) and runs as the `test:architecture` gate inside
`mise run check`.

Both scripts honor the `PRAXIS_ROOT` environment variable to operate on an
alternate repository root; the controller tests use it to drive isolated
fixture repositories.
