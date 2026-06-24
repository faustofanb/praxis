# Praxis Workflow Codex Plugin

This is a user-level Codex plugin for shared Praxis workflow behavior.

The plugin intentionally does not vendor a project's `.praxis` directory,
`praxis.projects.toml`, project branches, or business rules. Those remain in
each workspace so project-specific configuration stays local and reviewable.

## Contents

- `skills/praxis-workflow/SKILL.md`: shared Codex operating rules for Praxis
  startup gates, worktree requirements, command surfaces, and config boundaries.
- `skills/praxis-workflow/references/`: detailed Praxis rules loaded on demand.
- `scripts/praxis_check_workspace.py`: checks thin Praxis entry files and local project registry shape.
- `scripts/praxis_init_workspace.py`: renders generic Praxis entry templates into a workspace.
- `scripts/praxis_doctor.py`: human-facing wrapper for workspace checks.
- `templates/`: project-neutral starter files for new Praxis workspaces.
- `tests/`: lightweight tests for plugin scripts and reference wiring.

## Boundary

Use this plugin to make new Codex conversations remember the common Praxis
discipline. Use each workspace's `AGENTS.md`, `praxis.toml`,
`praxis.projects.toml`, and installed `.praxis/extensions/*` for actual project
paths, branch names, verification commands, and domain rules.

## Iteration

Run the plugin tests and Codex plugin validator before reinstalling:

```bash
uv run --with pytest pytest -q tests
uv run --with PyYAML python /Users/fausto/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py /Users/fausto/plugins/praxis-workflow
```
