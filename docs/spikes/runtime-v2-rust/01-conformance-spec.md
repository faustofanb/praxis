# Conformance Specification

Day 1 must build language-neutral fixtures before Rust semantic implementation.

Mandatory case families:

- legal/illegal transitions
- Command ≠ durable Event
- capability allow/deny/bypass
- completion blocking
- UNKNOWN after dispatch
- crash before effect / after dispatch
- reconciliation to known success/no-effect/failure
- replay determinism
- persistence reopen
- duplicate/retry/idempotency semantics
- invalid boundary input fail closed

Fixture rules:

- fixed IDs/timestamps/random data
- JSON serializable
- no TypeScript-only representation
- no Rust-only representation
- TS reference runner must pass 100% before Day 2
- fixture changes after Rust failure require human review; AI may not weaken them
