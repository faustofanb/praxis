# ADR-0001: Bun + TypeScript as the v1 Runtime

- Status: Accepted
- Date: 2026-08-27
- Owners: Praxis Harness maintainers
- Supersedes: none

## Context

v1 must validate the Harness architecture quickly while keeping the runtime surface small. The project needs strong TypeScript tooling, fast tests, built-in SQLite/process/file primitives, and low friction for AI-assisted development. Bun 1.4.0 is newly released and includes a major runtime implementation rewrite; the project prioritizes state correctness over immediately adopting the newest runtime.

## Decision

Use mise to provision **Bun 1.3.14** and use **TypeScript 7.0.2** in strict ESM mode. Package versions are exact-pinned and `bun.lock` is committed. Runtime upgrades are explicit compatibility tasks, not incidental dependency updates.

## Consequences

- Fast TypeScript development and a single runtime/package manager.
- v1 intentionally targets Bun rather than claiming Node/Bun portability.
- Bun-specific adapters such as `bun:sqlite` must not leak into `packages/core`.
- We carry upgrade work when Bun 1.4.x becomes sufficiently validated by our own crash/replay/soak suite.

## Alternatives considered

- Node.js + pnpm: mature and conservative, but adds more toolchain surface for the first implementation.
- Rust core: strong correctness/performance, but substantially raises iteration cost before the epistemic/runtime ideas are validated.

## Verification

M0 clean-clone bootstrap and M1–M7 test gates must pass on the locked runtime. A Bun upgrade is accepted only after replay, fault, security, and soak suites pass unchanged or with justified compatibility work.

## Revisit triggers

- Bun 1.3.x no longer receives required fixes.
- A runtime defect blocks reliable tool/process/SQLite behavior.
- Bun 1.4.x passes the full compatibility matrix and offers material value.
