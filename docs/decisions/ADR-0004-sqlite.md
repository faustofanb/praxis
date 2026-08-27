# ADR-0004: SQLite Event Store without ORM for v1

- Status: Accepted
- Date: 2026-08-27

## Context

The v1 durable model is intentionally small and append-oriented. Correct transaction and migration behavior is more important than generic ORM convenience.

## Decision

Implement `EventStore` using Bun's built-in `bun:sqlite` with explicit SQL migrations. Do not use an ORM in v1.

## Consequences

- SQL and transaction semantics remain visible.
- Fewer dependencies and migration abstractions.
- More hand-written SQL, kept isolated in `store-sqlite`.

## Verification

Integration tests cover transactional append, monotonic Session sequence, concurrent append behavior, migrations, and replay.

## Revisit triggers

Projection/query requirements become complex enough that an ORM/query layer measurably reduces defects without leaking into Core.
