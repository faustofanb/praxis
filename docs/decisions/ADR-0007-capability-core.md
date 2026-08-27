# ADR-0007: Capability Enforcement is Core; Approval UX is Extensible

- Status: Accepted
- Date: 2026-08-27

## Context

Pi demonstrates that many governance features can be extensions, while Codex/DeepSeek show that actual execution boundaries must be enforced outside model prompts. Optional safety plugins are insufficient for a runtime intended to support real side effects.

## Decision

Capability checks and execution isolation boundaries belong to Core/Tool Runtime. Human approval UX, policy presentation, and advanced governance flows may be extensions. Governance/approval unavailability fails closed when authorization is required.

## Consequences

- Core is slightly larger than a purely minimal coding harness.
- Missing UI extension cannot silently remove the actual security boundary.
- Policies must be reflected consistently in model-visible context and runtime enforcement.

## Verification

Security tests attempt direct and delegated capability bypass, expired lease use, scope escape, and fail-open behavior.
