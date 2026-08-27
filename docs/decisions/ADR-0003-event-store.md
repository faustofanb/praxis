# ADR-0003: Append-only Event Store as the Durable Truth Source

- Status: Accepted
- Date: 2026-08-27

## Context

Agent execution crosses nondeterministic model calls and external side effects. Crash recovery, replay, audit, branching, and state reconstruction require one durable account of what actually happened.

## Decision

Persist important facts as typed, append-only Session Events. Derived runtime state is reconstructed by a deterministic reducer. Commands/intent are distinct from factual result events. Evidence, objective, and structural “ledgers” are logical projections of the same Event Store, not separate databases.

## Consequences

- Recovery and replay are first-class.
- Event schema compatibility becomes a serious public contract.
- Event Store does not guarantee exactly-once external effects; tool idempotency/reconciliation remains required.

## Verification

Replay of identical events must produce identical DerivedState. Historical fixtures remain loadable across schema evolution.

## Revisit triggers

Measured storage/replay behavior cannot meet requirements even with snapshots/projections.
