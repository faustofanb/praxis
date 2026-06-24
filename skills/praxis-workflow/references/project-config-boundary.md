# Project Configuration Boundary

Use this reference when deciding whether data belongs in the plugin or in a workspace.

## Keep In The Workspace

These facts are project-specific and must remain local:

- `praxis.projects.toml`;
- project names and paths;
- `defaultBranch` and `upstreamBranch`;
- verification commands;
- project kind mappings;
- installed domain extensions;
- generated reports under `.praxis/out/`;
- requirement directories and worktrees.

## Keep In The Plugin

These facts are reusable and may live in the plugin:

- startup gate policy;
- worktree requirement policy;
- command contract guidance;
- thin workspace templates;
- generic workspace doctor scripts;
- plugin tests and validation scripts.

## Extension Split

Use a separate extension plugin for domain-specific behavior. For example, a manufacturing/MOM plugin can carry backend, web, PDA, ETL or MagicAPI rules without contaminating the generic Praxis plugin.
