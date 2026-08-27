# ADR-0005: Deterministic Core, Nondeterministic Edge

- Status: Accepted
- Date: 2026-08-27

## Context

LLMs and external environments are probabilistic/unreliable. Permission, state transitions, recovery, and completion correctness cannot depend on model self-discipline.

## Decision

Keep state reducer, capability enforcement, tool lifecycle, context bounds, replay behavior, and required completion/verification rules deterministic. Model reasoning may propose hypotheses/plans/actions but does not directly mutate durable truth or bypass Core rules.

## Consequences

- More explicit types/state machines.
- Runtime safety behavior remains testable without a real model.
- Prompt instructions are explanations, not security controls.

## Verification

Core correctness suites use ScriptedModel/fake tools and must be deterministic. Runtime invariants receive unit/property/integration tests.
