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

For code-bearing business work, create or restore the project worktree before editing business code. First look for a matching active requirement and its worktree; create a new worktree only for an independent task. Prefer the workspace command:

```bash
task project -- start <project> <requirement-name> <original-user-request>
```

Create or restore a requirement directory only when the task has documentation output that must be retained (original request, investigation conclusion, SQL draft, implementation note or progress). For docs-only business work, use:

```bash
task req -- init <requirement-name> <original-user-request>
```

Missing required code worktree is a blocker. Missing requirement docs are not a blocker for a pure code change with no document output.

## Fast Path

Use this path when the user prioritizes quick delivery:

1. Route to the project and search same-name requirements; use same-aggregate results only as candidates.
2. Reuse only an exact-name requirement and worktree. A different name creates an independent requirement and worktree.
3. Investigate the relevant call path/data source, modify the smallest code surface, and run a syntax or parser check.
4. Write only the files that are actual retained outputs. Do not create plan/progress/analysis placeholders.

TDD, broad verification, preflight, global checks and subagents are opt-in rather than default steps.

## Waivers

Allowed waiver classes are answer-only responses, read-only investigation, pure workflow or rules maintenance, docs-only work, and code work with no documentation output.

Small edits, one-line fixes, generated files and temporary fixes are not waivers. When waiving, final output must state the waiver reason, substitute action and residual risk.
