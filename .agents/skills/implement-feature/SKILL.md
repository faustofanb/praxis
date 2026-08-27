# Skill: Implement Feature

## Trigger

Use for a scoped new behavior that does not primarily fix an existing defect.

## Procedure

1. Read task Problem/Evidence/Acceptance/Non-goals.
2. Read `AGENTS.md`, relevant system/subsystem docs and contracts.
3. Inspect existing behavior/tests in full.
4. Decide whether the feature fits an existing Core seam/adapter/extension. Default: do not add a new manager/hook.
5. Write a minimal implementation plan with expected observable behavior.
6. Implement the smallest vertical slice.
7. Add tests required by change type.
8. Run focused tests, then required gates.
9. Review diff for scope creep, dependency drift and unbounded state/context.
10. Update the single owning document/ADR if public behavior changed.

## Stop conditions

Stop and re-plan if:

- the feature requires changing v1 Non-goals;
- a Core invariant must be weakened;
- the diff will exceed review limits without a mechanical reason;
- a third-party API is unknown/unverified;
- existing evidence contradicts the planned architecture.
