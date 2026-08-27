# ADR-0009: Session Event Envelope and Vocabulary v1 (TypeScript/Zod Contracts)

- Status: Accepted
- Date: 2026-08-27
- Owners: 樊彪
- Supersedes: none
- Related: ADR-0003 (append-only event store), ADR-0005 (deterministic core), `docs/02-system-design.md` §6–§8

## Context

M1 needs the durable contract layer in `packages/contracts` before the reducer
(M1-T002) and the SQLite store (M1-T003) can be built against it. The abstract
design — envelope fields, invariants, and the v1 event vocabulary — is already
frozen in `docs/02-system-design.md` §6 and accepted with the M0 baseline. This
ADR freezes the concrete TypeScript/Zod shape so later schema changes are
diffable against a named decision.

## Decision

Implement the envelope as a single generic `SessionEvent<TType, TPayload>`
carrying `id / sessionId / seq / type / schemaVersion / occurredAt / actor /
causationId? / correlationId? / payload`, exactly as `docs/02` §6.1. All
fields are validated by Zod schemas; `zod` (exact pin 4.4.3) becomes the only
runtime dependency of `packages/contracts`, as permitted by `docs/02` §4.1.

v1 implements only the Session/Turn slice of the vocabulary
(`SessionCreated`, `SessionResumed`, `SessionPaused`, `SessionCompleted`,
`TurnStarted`, `TurnCompleted`) plus the generic envelope machinery; the
epistemic, model, and tool event payloads arrive with their owning milestones
(M2–M4) as discriminated-union members of the same envelope. The tool
execution **status union** (`PROPOSED → AUTHORIZED | REJECTED → EXECUTING →
SUCCEEDED | FAILED | INDETERMINATE`, reconciliation back to terminal states)
lands now as a contract because tool-state semantics are invariant across
milestones; transition legality stays in Core's reducer.

IDs (`SessionId`, `EventId`, `TurnId`, `StepId`, `ToolExecutionId`) are
branded strings created through validating wrapper functions. Contracts
performs no generation (no crypto/env/file access): deterministic generators
belong to `packages/testkit`, real randomness to adapters/CLI.

The `EventStore` port is `append(events, expectedHeadSeq)` +
`readStream(sessionId, afterSeq)`; append is atomic, enforces
`(sessionId, seq)` uniqueness with no gaps, and `expectedHeadSeq` gives the
single-writer optimistic-concurrency check. Adapters translate violations
into thrown errors; Core never catches-and-retries blind.

## Consequences

### Positive

- One discriminated envelope keeps the union exhaustive and the reducer
  switch checkable by the compiler.
- Branding prevents ID cross-assignment at zero runtime cost.
- Zod schemas double as parse boundary for untrusted store/provider input.

### Negative / trade-offs

- Payload schema changes are durable-contract changes: they require
  `schemaVersion` bumps and migration/replay gates (Class E changes).
- The union grows through M4; each addition must extend tests.

### Operational / migration impact

- `EVENT_SCHEMA_VERSION = 1` from M1; M5 introduces versioned fixtures and
  migrations on top of this baseline.

## Alternatives considered

### Alternative A: one Zod schema per event including envelope fields duplicated

Rejected: duplicates envelope invariants across N schemas and lets them drift;
the generic envelope + payload schema composition keeps one authority.

### Alternative B: store events as untyped JSON and validate only in Core

Rejected: the persistence boundary is exactly where untrusted input must be
parsed by the owning schema (`AGENTS.md`); moving validation into Core makes
the port type a lie.

## Verification

- Unit tests: schema accept/reject boundaries for envelope and every v1
  payload; branded wrappers reject empty strings.
- Property tests (fast-check): JSON round-trip of valid envelopes; positive-`seq`
  law; discriminated-union dispatch for all v1 types.
- M1-T004 adds replay/parity suites on the same schemas.

## Revisit triggers

- Payload polymorphism needs exceed discriminated-union ergonomics.
- Measured parse cost of Zod at the store boundary becomes a bottleneck.
- A vocabulary change cannot be expressed with `schemaVersion` + migration.
