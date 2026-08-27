# Architecture Rules

## Dependency direction

```text
contracts <- core
contracts <- store/provider/tools adapters
contracts/core <- testkit (test only)
all implementations <- apps/cli composition root
```

- Core never imports adapter packages.
- Adapters never import each other.
- Shared implementation utility does not automatically justify a new package; prefer duplication until a stable shared concept exists.

## Core admission rule

A feature enters Core only if at least one is true:

1. required to preserve state correctness;
2. required to enforce a hard boundary;
3. required for every Agent Loop implementation;
4. cannot be implemented safely using an existing extension seam.

Otherwise it remains an adapter/extension/product feature.

## Durable state

- New durable facts require an Event or explicit subsystem store with an ADR.
- Do not hide durable state in singleton objects, closure caches, prompt text, or process env.
- Event replay must not cause external side effects.

## Context

- Every context fragment has a bounded size.
- Historical storage and model context are different systems.
- Hard constraints and pending indeterminate effects are structured fragments, not free-form summary content.
