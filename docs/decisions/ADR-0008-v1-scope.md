# ADR-0008: v1 Scope — Single-Agent Core, Advanced Orchestration as Extensions/Later Work

- Status: Accepted
- Date: 2026-08-27

## Context

The theory explored Multi-Agent coordination, Critic/Judge roles, emergency command, drift analytics, coalition analysis, and governance modes. Mature harnesses demonstrate that the central agent loop can stay small and advanced orchestration can remain optional.

## Decision

v1 Core does **not** include built-in Multi-Agent scheduling, Critic/Judge agents, real-time coalition/drift AI, workflow DSL, automatic constitution mutation, or cloud App Server complexity. Praxis-specific v1 experiments are limited to explicit Observation/Hypothesis state, falsifiable Plan state, and first-class Challenge events around a small recoverable runtime.

## Consequences

- Faster path to a real executable system.
- Theory remains documented but does not automatically become software architecture.
- Extension seams must be sufficient to experiment later without Core rewrites.

## Verification

M0–M8 can be completed without adding these excluded features. Any proposal to pull one into Core requires a new ADR with implementation evidence.
