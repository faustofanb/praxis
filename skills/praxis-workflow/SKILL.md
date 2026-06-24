---
name: praxis-workflow
description: Use when working in a Praxis workspace, changing Praxis workflow behavior, deciding whether a task needs a requirement directory or worktree, or explaining Praxis project configuration boundaries.
---

# Praxis Workflow

## Purpose

Use this skill as the shared Codex entry discipline for Praxis workspaces. It
keeps reusable workflow rules in the user-level plugin while leaving
project-specific paths, branch names, verification commands, and domain rules in
the current workspace.

## Load Local Sources First

At the start of an acting turn inside a Praxis workspace:

1. Read the workspace `AGENTS.md`.
2. Read `praxis.toml`.
3. Read `praxis.projects.toml`.
4. Read `.praxis/core.toml`.
5. Read `.praxis/project-adapter.toml`.
6. Read `.praxis/contracts/agents/turn.schema.json` when present.
7. Read `.praxis/rules/praxis-workflow.md` when present.
8. Load extension manifests and rules only when the task matches that extension.

Treat this plugin as shared behavior, not as the source of project facts.

## Command Surface

- Prefer the workspace's documented `task ...` commands for human-facing
  workflow actions.
- If a workspace imports an RTK instruction, prefix shell commands with `rtk`.
- Do not expose underlying implementation commands as the primary user-facing
  workflow unless the local workspace says otherwise.

## Startup Gate

Before editing business code from a fresh or resumed Codex dialog:

1. Classify the task as answer-only, read-only investigation, docs/process
   maintenance, docs-only business work, or code-bearing business work.
2. For code-bearing business work, run:

   ```bash
   task project -- start <project> <需求名> <用户原始需求原文>
   ```

3. For docs-only business work, run:

   ```bash
   task req -- init <需求名> <用户原始需求原文>
   ```

4. Do not edit business code until the requirement directory and required
   project worktree exist.

Missing requirement docs or a missing required worktree is a blocker, not a
warning. Small edits, one-line fixes, generated files, and temporary fixes are
not startup-gate waivers.

## Worktree Rule

For business code additions, modifications, deletions, or generation, a project
worktree is mandatory unless the local workspace contract explicitly defines a
narrower rule.

Allowed waiver classes are limited to:

- answer-only responses;
- read-only investigation;
- pure rules or process maintenance;
- docs-only work that does not edit business code.

When waiving a code worktree, the final answer must state the waiver reason,
substitute action, and residual risk.

## Project Config Boundary

Project-specific facts must come from local project configuration:

- project names and paths;
- `defaultBranch` and `upstreamBranch`;
- worktree root;
- verification commands;
- installed extensions and domain rules.

Do not ask the user to provide `local` as a branch name when the workspace
already has `defaultBranch` in `praxis.projects.toml`. A manual branch argument
is only appropriate for an explicit diagnostic or override path.

## Plugin Boundary

This plugin should contain reusable Codex/Praxis behavior only. Keep these
outside the plugin and inside the project:

- `praxis.projects.toml`;
- `.praxis/project-adapter.toml` project-specific paths;
- domain extensions;
- generated reports under `.praxis/out/`;
- business requirement directories;
- project worktrees.

## Resume Discipline

After interruption, compaction, or handoff:

1. Bind to the newest user request.
2. Run a minimal workspace state check before editing.
3. Re-read the local Praxis entry files needed for the next action.
4. Discard stale plan steps that conflict with the newest request.
5. Verify or explain why verification was not run before final delivery.
