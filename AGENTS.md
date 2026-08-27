# AGENTS.md — Praxis Harness Standing Orders

Read `docs/02-system-design.md` before changing `packages/contracts` or `packages/core`. Use the relevant `.agents/skills/*/SKILL.md` for high-risk recurring tasks.

## Scope

- Work only on the current task. Do not perform opportunistic refactors, dependency upgrades, or broad cleanup.
- Read target files and relevant tests/contracts in full before wide changes.
- If evidence shows the task scope must expand, explain why before expanding it.

## Architecture

- `contracts` owns schemas/ports; `core` depends only on `contracts`; adapters never enter Core.
- Commands are intent; Events are facts. Durable Event vocabulary is intentionally small.
- Runtime rules (capabilities, state transitions, completion requirements) must not depend on model self-discipline.
- `UNKNOWN`/indeterminate external effects are first-class. Never coerce them to failure and blindly retry.
- Context is bounded working state, not the historical database.
- Multi-Agent, Critic, Judge, Emergency orchestration are not v1 Core features.

## TypeScript

- No `any` unless isolated at a third-party boundary with justification.
- Parse untrusted boundaries from `unknown` with the owning schema.
- Prefer discriminated unions; no TypeScript `enum`/namespace.
- No mutable module-global state in Core.
- Never guess third-party APIs: inspect the pinned version's types/docs/source.

## Tests

- Agent-loop behavior changes MUST add/update integration tests using ScriptedModel.
- Event/schema changes require migration/replay tests.
- Tool lifecycle changes require failure/UNKNOWN/idempotency tests.
- Capability changes require bypass/adversarial tests.
- Do not delete or weaken valid tests to make a change pass.

## Change Size

- Prefer non-mechanical diffs under 500 changed LOC; 800 is the default hard review limit.
- Split larger work into coherent, independently verifiable stages.

## Dependencies

- All dependencies are exact-pinned; never add `^`, `~`, or `latest`.
- Do not add a dependency without checking standard-library alternatives, license, maintenance, failure impact, and removal cost.
- Dependency upgrades are explicit tasks, not side effects of feature work.

## Git

- Run `git status` before edits and before commit.
- Stage explicit paths only. Never use `git add .` or `git add -A`.
- Never run `git reset --hard`, `git checkout .`, `git clean -fd`, `git stash`, or `git commit --no-verify` unless the user explicitly directs it.
- Do not touch unrelated uncommitted changes from other sessions.
- Commit format: Conventional Commits, e.g. `fix(core): preserve indeterminate tool state`.

## Documentation

- One fact, one home. Link rather than duplicate durable rules.
- Architecture docs describe current behavior; ADRs describe decisions; Skills describe procedures.
- Update owning docs in the same change when a public contract or documented subsystem changes.
