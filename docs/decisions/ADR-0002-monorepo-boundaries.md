# ADR-0002: Small Bun Workspace Monorepo with Strict Dependency Direction

- Status: Accepted
- Date: 2026-08-27

## Context

The runtime must keep deterministic Core logic independent from SQLite, model vendors, and concrete tools while avoiding an over-fragmented package graph.

## Decision

Use one Bun workspace repository with these initial packages: `contracts`, `core`, `store-sqlite`, `provider-openai`, `tools-local`, `testkit`, plus `apps/cli` as composition root.

Dependency direction is enforced conceptually and by tests/tooling:

```text
contracts <- core
contracts <- store/provider/tools
contracts + core <- testkit (test only)
implementations -> apps/cli
```

Core imports no adapter implementation.

## Consequences

- Provider/store/tool replacements do not require Core changes.
- Package count remains small enough for easy navigation.
- Cross-package abstractions require evidence; no generic `shared` package in v1.

## Verification

CI dependency checks and review rules reject reverse imports. Architecture tests may be added once source exists.

## Revisit triggers

A concrete repeated dependency problem cannot be solved without a new package boundary.
