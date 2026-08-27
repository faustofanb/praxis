# Skill: Release Check

## Required

1. Frozen install from clean clone.
2. `mise run check:all`.
3. Integration/replay/fault/security suites.
4. Historical session fixtures migrate/replay.
5. No unexpected Knip findings.
6. Dependency/license inventory updated.
7. Config/example docs work from scratch.
8. Known limitations documented.
9. No P0/P1 open correctness issue.
10. Changelog/semver decision explicit.

## For runtime/tool/store upgrades

Also run soak/crash matrix and compatibility fixtures.

A release is not approved because a live model demo worked once.
