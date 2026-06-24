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

For code-bearing business work, create or restore both the requirement directory and project worktree before editing business code. Prefer the workspace command:

```bash
task project -- start <project> <requirement-name> <original-user-request>
```

For docs-only business work, create or restore the requirement directory:

```bash
task req -- init <requirement-name> <original-user-request>
```

Missing requirement docs or a missing required code worktree is a blocker.

## Waivers

Allowed waiver classes are answer-only responses, read-only investigation, pure workflow or rules maintenance, and docs-only work that does not edit business code.

Small edits, one-line fixes, generated files and temporary fixes are not waivers. When waiving, final output must state the waiver reason, substitute action and residual risk.
