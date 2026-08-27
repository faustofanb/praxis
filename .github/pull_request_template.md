## Problem

What concrete problem does this change solve? Link issue/evidence.

## Change

What changed, and which owning subsystem/package is responsible?

## Evidence

What observation, reproduction, benchmark, or requirement supports this change?

## Risk

- [ ] Core state/reducer
- [ ] Agent Loop/context
- [ ] Durable Event/schema
- [ ] External side effect/Tool
- [ ] Capability/security boundary
- [ ] Dependency/runtime upgrade
- [ ] Documentation only / low risk

## Tests

List focused and required gates run. For high-risk changes include replay/fault/security evidence as applicable.

## State / compatibility

- Does this change durable state or Event schema?
- Can old Sessions still migrate/replay?
- Can crash/retry duplicate external effects?

## Scope / non-goals

What was intentionally not changed?

## Documentation / ADR

What owning doc or ADR changed, if any?

## AI-assisted change checklist

- [ ] Target files and owning docs were read before modification.
- [ ] No unrelated refactor or dependency upgrade was introduced.
- [ ] Diff is within review-size guidance or intentionally split.
- [ ] No valid test was weakened/deleted to obtain green CI.
- [ ] `git status` was reviewed and only explicit paths are staged.
