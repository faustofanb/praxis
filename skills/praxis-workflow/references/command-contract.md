# Command Contract

Use this reference when maintaining Praxis command examples or diagnosing command drift.

## Human-Facing Command Surface

Prefer the workspace's documented `task ...` commands for human-facing workflow actions. Underlying scripts are implementation details unless the workspace documents otherwise.

For go-task command dispatch, pass subcommands through `--` when required by the local Taskfile:

```bash
task project -- start <project> <requirement-name> <original-user-request>
task req -- init <requirement-name> <original-user-request>
task context -- --brief <project> <requirement-name>
task system -- check
```

## Drift Checks

When changing commands, keep these synchronized:

- Taskfile entry;
- script parser;
- command registry or manifest;
- AGENTS instructions;
- workflow rules and examples;
- tests.

Run the workspace's own checks when present, for example:

```bash
task system -- check
task system -- template-check
```
