---
name: praxis-workflow
description: Use when working in a Praxis workspace, changing Praxis workflow behavior, initializing or checking a Praxis workspace, deciding whether a task needs a requirement directory or worktree, using Praxis helper scripts or templates, or explaining Praxis project configuration boundaries.
---

# Praxis Workflow

## Purpose

Use this skill as the shared Codex entry discipline for Praxis workspaces. It packages reusable workflow rules, thin templates and helper scripts while leaving project-specific paths, branch names, verification commands and domain rules in the current workspace.

## Load Local Sources First

At the start of an acting turn inside a Praxis workspace:

1. Read the workspace `AGENTS.md`.
2. Read `praxis.toml`.
3. Read `praxis.projects.toml`.
4. Read `.praxis/core.toml`.
5. Read `.praxis/project-adapter.toml`.
6. Read `.praxis/contracts/agents/turn.schema.json` when present.
7. Read `.praxis/contracts/agents/delivery.schema.json` when doing delivery or closeout work.
8. Read `.praxis/rules/praxis-workflow.md` when present.
9. Load extension manifests and rules only when the task matches that extension.

Treat this plugin as shared behavior, not as the source of project facts.

## Reference Map

Read only the reference needed for the task:

- Startup gate decisions: `references/startup-gate.md`.
- Requirement worktree rules: `references/worktree.md`.
- Command examples and drift checks: `references/command-contract.md`.
- Project branch/path ownership: `references/project-config-boundary.md`.
- Verification, resume and final response evidence: `references/verification-closeout.md`.
- Delivery candidate auditing and confirmations: `references/delivery-contract.md`.

## Helper Scripts

Use scripts from this plugin only for generic Praxis workspace operations:

```bash
python scripts/praxis_check_workspace.py <workspace>
python scripts/praxis_check_workspace.py <workspace> --json
python scripts/praxis_doctor.py <workspace>
python scripts/praxis_init_workspace.py <workspace> --name "Workspace Name"
python scripts/praxis_sync_profile.py <workspace> ifc-mom --force
python scripts/praxis_sync_workspaces.py ifc-mom --force
```

Prefer the workspace's own `task ...` commands after a workspace already has its Praxis entry files. If a workspace imports RTK instructions, prefix shell commands with `rtk`.

## Packaged Profiles

Profiles under `profiles/` carry reusable project-family assets such as extension rules, skills, command registries and automation scripts. Use them to reduce per-workspace duplication while keeping project facts local:

- `ifc-mom`: IFC MOM workflow rules, MOM/AOTU skills, command registry, delivery automation, ETL/report, backend, web, PDA and big-screen guidance.

Profile workspace registries such as `profiles/ifc-mom/workspaces.json` are local orchestration lists for syncing shared profile assets to multiple workspaces. They do not replace workspace-local `praxis.projects.toml`.

Profile sync must not overwrite project registries, branch names, verification commands or requirement records unless the user explicitly asks for that local project change.

## Boundary

Do not treat this plugin as the source for project-specific facts. Read local configuration for project names, paths, `defaultBranch`, `upstreamBranch`, worktree root, verification commands, installed extensions and domain rules.

Do not ask the user to provide `local` as a branch name when the workspace already has `defaultBranch` in `praxis.projects.toml`. A manual branch argument is only appropriate for an explicit diagnostic or override path.
