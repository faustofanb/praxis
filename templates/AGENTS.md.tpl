# AGENTS.md

This is the thin Agent entrypoint for {{ workspace_name }}.

## Load Order

1. Read `praxis.toml`.
2. Read `praxis.projects.toml`.
3. Read `.praxis/core.toml`.
4. Read `.praxis/project-adapter.toml`.
5. Read `.praxis/contracts/agents/turn.schema.json`.
6. Read installed extension manifests only when a task matches that extension.

## Operating Rules

- Use `task ...` as the human-facing command surface when this workspace provides it.
- Keep Praxis core project-neutral.
- Keep domain or stack-specific rules in extensions.
- Keep generated reports under `.praxis/out/`.
- Use project configuration for branch names and project paths.

## Every Turn Contract

- Treat each user message as a new turn.
- Reconcile the latest user request, active task state, workspace state and loaded Praxis sources.
- For code-bearing business work, create or restore the requirement directory and project worktree before editing business code.
- For docs-only business work, create or restore the requirement directory before drafting implementation detail.
- Answer-only, read-only investigation and pure workflow maintenance may waive the business worktree, but the final answer must state the waiver reason and residual risk.
