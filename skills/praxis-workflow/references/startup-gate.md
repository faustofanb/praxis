# Startup Gate

Use this reference when deciding what must happen before implementation.

## Classification

Classify each new user message as one of:

- answer-only;
- read-only investigation;
- pure workflow or rules maintenance;
- docs-only business work;
- code-bearing business work.

## Required Actions

For code-bearing business work, create or restore the project worktree before editing business code. Use one of two explicit modes:

```bash
task project -- quick <project> <short-task-name>
task project -- start <project> <requirement-name> <original-user-request>
```

Use `quick` only for L0 changes with no database, migration, permission, report, shared-contract or cross-project impact. It creates an isolated worktree and resumable `.praxis/tasks/<id>.toml` state without requirement docs. Use `start` for retained requirement documents or higher-risk work.

Create or restore a requirement directory only when the task has documentation output that must be retained (original request, investigation conclusion, SQL draft, implementation note or progress). For docs-only business work, use:

```bash
task req -- init <requirement-name> <original-user-request>
```

Missing required code worktree is a blocker. Missing requirement docs are not a blocker for a pure code change with no document output.

## Fast Path

Use this path when the user prioritizes quick delivery:

1. Route to the project and classify risk. Any database, migration, permission, report, shared-contract or cross-project change exits the fast path.
2. Run `task project -- quick <project> <short-task-name>`. Reuse only the unique exact-name worktree; ambiguity is a blocker.
3. Investigate the relevant call path/data source, modify the smallest code surface, then run `task project -- quick-check <project> <short-task-name>`. High-risk paths fail closed; otherwise execute the manifest-selected L0 checks it reports.
4. Keep the generated `.praxis/tasks/<id>.toml` state. Do not create plan/progress/analysis placeholders or requirement docs.

TDD, broad verification, preflight, global checks and independent Quality review are not part of L0. Increase verification or review only when the manifest/risk policy requires it or the user requests it.

## Waivers

Allowed waiver classes are answer-only responses, read-only investigation, pure workflow or rules maintenance, docs-only work, and code work with no documentation output.

Small edits, one-line fixes, generated files and temporary fixes are not waivers. When waiving, final output must state the waiver reason, substitute action and residual risk.
