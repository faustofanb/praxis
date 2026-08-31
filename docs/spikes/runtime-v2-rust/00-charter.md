# RUST-SPIKE-001 Charter

## Question

Should the post-v1 authoritative deterministic core migrate from TypeScript/Bun to Rust?

## Why now

Runtime v1 at `14c905c29299c6b2d7d1957208e84536ba707a1d` is accepted. Workbench product structure now creates a new authority/native boundary question. The spike tests whether Rust produces a materially better deterministic authority core without discarding v1 semantics.

## Reference

- Branch: `v1-rc`
- Commit: `14c905c29299c6b2d7d1957208e84536ba707a1d`
- Tag: `runtime-v1-reference-20260830`
- Reference status: accepted v1 RC

## Hypothesis

Rust may improve exhaustive state modeling, SQLite/daemon ownership, crash/recovery clarity and maintainer auditability while mature OSS reduces native implementation cost.

This is a hypothesis, not current architecture.

## Scope

Allowed semantic candidate surface:

- domain state types
- command validation
- transition/reducer
- capability authority
- operation state including UNKNOWN/reconciliation
- SQLite transaction/reopen compatibility
- minimal TS proposal ↔ Rust decision ↔ observation boundary
- conformance/benchmark evidence

## Forbidden

- real model/provider migration
- MCP/DBX/SSH/Git/TUI/Desktop/Workbench implementation
- modification of accepted v1 semantics to fit Rust
- M9 or M8 task reuse
- production architecture declaration before ADR accepted

## Timebox

Maximum 5 working days after bootstrap commit approval.

## Decisions

Only:

- `KEEP_TS_CORE`
- `MIGRATE_DETERMINISTIC_CORE_TO_RUST`

Any hard gate failure forces the first recommendation unless a human explicitly re-charters the experiment.
