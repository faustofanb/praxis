# Skill: Change Agent Loop / Session Runtime

Core-loop changes are high risk.

## Before edit

- Read relevant core file(s) in full.
- Read current integration tests and Event contracts.
- Capture a short trace of current behavior and desired behavior.
- Identify whether the problem could be solved in ContextBuilder, Tool adapter, Policy, or Extension instead.

## Required checks

- event ordering;
- cancellation;
- model failure;
- tool failure/UNKNOWN;
- no-progress/loop guard;
- context bound;
- resume/replay;
- completion policy;
- no provider-specific types in Core.

## Tests

Every behavior change MUST add/update ScriptedModel integration tests. Side-effect-related changes also run fault/recovery tests.

Prefer a small state transition change over a new orchestration abstraction.
