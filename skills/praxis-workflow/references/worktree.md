# Worktree Rules

Use this reference when deciding where code edits may happen.

## Code Work Requires a Worktree

For business code additions, modifications, deletions or generation, a project worktree is mandatory unless the local workspace contract explicitly defines a narrower rule.

Do not edit business code directly in the aggregate or main project checkout when the startup gate requires a worktree.

## Project Registry Owns Branches

Read branch configuration from local `praxis.projects.toml`:

- `defaultBranch` is the development base for task worktrees.
- `upstreamBranch` is the branch synchronized into the default branch before creating a task worktree.
- `worktreeRoot` controls where worktrees are created.

Do not hard-code branch names in the plugin. Do not ask the user for `local` when the project registry already declares it.

## Dirty Base Checkout

If the local project checkout is dirty before worktree creation, stop and report the concrete status. Do not stash, restore, commit, reset or hand-create a worktree unless the user explicitly asks for that action.
