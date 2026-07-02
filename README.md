# Praxis Workflow Codex Plugin

This is a user-level Codex plugin for shared Praxis workflow behavior.

The plugin intentionally keeps project-specific facts out of the package:
`praxis.projects.toml`, project branches, paths, verification commands and
requirement records remain in each workspace. Reusable workflow rules and
skills can live in packaged profiles, then be synced into workspaces.

## Contents

- `skills/praxis-workflow/SKILL.md`: shared Codex operating rules for Praxis
  startup gates, worktree requirements, command surfaces, and config boundaries.
- `skills/praxis-workflow/references/`: detailed Praxis rules loaded on demand.
- `scripts/praxis_check_workspace.py`: checks thin Praxis entry files, agent contracts and local project registry shape.
- `scripts/praxis_init_workspace.py`: renders generic Praxis entry templates into a workspace.
- `scripts/praxis_sync_profile.py`: syncs packaged workflow profiles such as `ifc-mom` into a workspace.
- `scripts/praxis_sync_workspaces.py`: syncs one packaged profile to every workspace listed in that profile's registry.
- `scripts/praxis_doctor.py`: human-facing wrapper for workspace checks.
- `templates/`: project-neutral starter files and agent contracts for new Praxis workspaces.
- `profiles/`: packaged workflow rules, skills, command registries and automation scripts for project families.
- `tests/`: lightweight tests for plugin scripts and reference wiring.

## Boundary

Use this plugin to make new Codex conversations remember the common Praxis
discipline. Use each workspace's `AGENTS.md`, `praxis.toml`,
`praxis.projects.toml`, and installed `.praxis/extensions/*` for actual project
paths, branch names, verification commands, and domain rules.

Packaged profiles provide shared extension and automation assets while leaving
project facts in the workspace:

```bash
python scripts/praxis_sync_profile.py /path/to/workspace ifc-mom --force
python scripts/praxis_sync_workspaces.py ifc-mom --force
python scripts/praxis_init_workspace.py /path/to/workspace --name "IFC MOM" --profile ifc-mom
```

## Management Model

Use the plugin source as the only shared workflow source. Use profile workspace
registries such as `profiles/ifc-mom/workspaces.json` only to list local
workspaces that should receive the shared profile. Keep each workspace's
`praxis.projects.toml` as the source for project facts such as paths, branches,
verification commands and local database names.

Recommended loop:

```bash
python scripts/praxis_sync_workspaces.py ifc-mom --force --dry-run
python scripts/praxis_sync_workspaces.py ifc-mom --force
```

## Iteration

Run the plugin tests and Codex plugin validator before reinstalling:

```bash
uv run --with pytest pytest -q tests
uv run --with PyYAML python /Users/fausto/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py /Users/fausto/plugins/praxis-workflow
```
