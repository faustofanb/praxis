# Git Rules for Human and AI Parallel Work

- One task per branch/session when practical.
- `git status` before modifying and before staging.
- Stage explicit paths only.
- Never modify unrelated uncommitted work.
- Never `git add .`, `git add -A`, `git stash`, `git reset --hard`, `git checkout .`, `git clean -fd`, or `--no-verify` by default.
- If a conflict is in a file outside your task scope, stop and coordinate rather than guessing.
- Keep mechanical moves/format changes separate from behavioral changes.
- Commit messages follow Conventional Commits.
- Do not rewrite shared history unless explicitly coordinated.
