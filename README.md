# Praxis Workflow Codex Plugin

This is a user-level Codex plugin for shared Praxis workflow behavior.

The plugin intentionally does not vendor a project's `.praxis` directory,
`praxis.projects.toml`, project branches, or business rules. Those remain in
each workspace so project-specific configuration stays local and reviewable.

## Contents

- `skills/praxis-workflow/SKILL.md`: shared Codex operating rules for Praxis
  startup gates, worktree requirements, command surfaces, and config boundaries.

## Boundary

Use this plugin to make new Codex conversations remember the common Praxis
discipline. Use each workspace's `AGENTS.md`, `praxis.toml`,
`praxis.projects.toml`, and installed `.praxis/extensions/*` for actual project
paths, branch names, verification commands, and domain rules.
