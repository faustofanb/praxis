# Delivery Contract

Use this reference before preparing delivery, cleanup, push or other destructive or remote commands.

## Candidate Audit

Delivery readiness must make commit selection explicit:

- confirmed commits that are intended for delivery;
- excluded commits, including local tests, experiments and unrelated changes;
- candidate audit evidence, such as base branch, changed files, hidden local dependencies and conflict notes;
- required user confirmations before cherry-pick, cleanup, push or deletion.

Do not silently filter non-test commits. If a commit is excluded for anything other than an obvious local test or test-support reason, report it and ask for confirmation.

## Local Test Support

Test commits, local verification commits, temporary experiments and test-support-only dependency changes are not production delivery by default. Include them only when the user explicitly confirms that they belong in the delivery branch.

## Conflict And Verification Notes

When cherry-picking across a delivery branch, compare the requirement worktree base with `origin/<upstreamBranch>` before the pick. State whether the work depends on local commits that are not upstream, which files are expected to move, and which docs or local config must stay out of the feature branch.

If scoped verification is empty because the feature branch is already committed, use an upstream-range file audit such as `git diff --name-only origin/<upstreamBranch>...HEAD` to choose an equivalent verification command, and report that substitution.
