# ADR-0006: Explicit Tool Effect Classes and First-class Indeterminate Outcomes

- Status: Accepted
- Date: 2026-08-27

## Context

A timeout after an external request does not prove the side effect failed. Blind retry can duplicate email, payment, deployment, database mutation, or other irreversible effects.

## Decision

Every Tool declares an effect class: `read_only`, `idempotent_write`, `reconcilable_write`, or `non_idempotent_write`. Tool execution has a first-class `indeterminate` terminal/intermediate outcome. Writes must define idempotency and/or reconciliation behavior before merge.

## Consequences

- Tool contracts are more demanding but much safer.
- Core never coerces `indeterminate` into ordinary failure.
- Some tools will require escalation instead of automatic retry.

## Verification

Tool integration/fault tests cover response loss after side effect, retry behavior, and reconciliation.
