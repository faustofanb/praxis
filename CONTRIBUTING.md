# Contributing to Praxis Harness

## Setup

1. Install the repository-pinned mise version or a compatible mise capable of reading `mise.lock`.
2. Trust the repository mise config (first clone only): `mise trust`.
3. Run `mise install`.
4. Run `bun install --frozen-lockfile` after lockfiles exist.
5. Install hooks: `bunx lefthook install`.
6. Verify: `mise run check:all`.

## Before coding

- Choose/create a `PRA-###` task.
- Read `AGENTS.md`.
- Read `docs/02-system-design.md` for Core/contracts changes.
- Read the relevant Skill.
- Define Problem, Evidence, Scope, Non-goals, Acceptance, Tests.

## Pull Requests

Keep PRs narrow and evidence-driven. Any change to Agent Loop, Event schema, Tool lifecycle, Capability policy, or recovery behavior must include the required integration/fault/replay tests.

## Commits

Use Conventional Commits. Stage only files changed by the current task.

## Architecture decisions

Use an ADR when changing package boundaries, persistence model, Core invariants, dependency/runtime baseline, public contracts, or v1 non-goals.
